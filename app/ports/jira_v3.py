"""Jira REST. Cloud v3 oder Server/Gateway v2. Nur Sync-Out."""

from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx
import yaml

from app.config import Settings, get_settings
from app.domain.types import KIND_LABELS, Priority, RequestKind
from app.ports.ticket_port import ExternalIssueRef, IssuePayload, TicketPortError
from app.services.settings_service import RuntimeConfig

_OAUTH_CACHE: dict[str, tuple[str, float]] = {}


def _oauth_cache_key(runtime: RuntimeConfig) -> str:
    return "|".join(
        [
            runtime.jira_oauth_token_url.strip(),
            runtime.jira_client_id.strip(),
            runtime.jira_client_secret.strip(),
            runtime.jira_api_key.strip(),
        ]
    )


def _oauth_client_credentials_token(runtime: RuntimeConfig) -> str | None:
    token_url = (runtime.jira_oauth_token_url or "").strip()
    client_id = (runtime.jira_client_id or "").strip()
    client_secret = (runtime.jira_client_secret or "").strip()
    if not token_url or not client_id or not client_secret:
        return None
    key = _oauth_cache_key(runtime)
    cached = _OAUTH_CACHE.get(key)
    now = time.time()
    if cached and cached[1] > now + 30:
        return cached[0]
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if runtime.jira_api_key:
        headers["x-apikey"] = runtime.jira_api_key
    try:
        response = httpx.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers=headers,
            timeout=20,
            follow_redirects=False,
            trust_env=False,
        )
    except httpx.ProxyError as err:
        raise TicketPortError(
            "Jira-Proxy blockiert (403). HTTP_PROXY/HTTPS_PROXY prüfen oder deaktivieren."
        ) from err
    except httpx.HTTPError as err:
        raise TicketPortError(str(err)[:300]) from err
    if response.status_code >= 400:
        raise TicketPortError(_format_jira_error(response.status_code, response.text[:800]))
    data = _parse_json(response)
    access_token = str(data.get("access_token") or "").strip()
    if not access_token:
        raise TicketPortError("OAuth: Antwort ohne access_token")
    expires_in = int(data.get("expires_in") or 3600)
    _OAUTH_CACHE[key] = (access_token, now + max(60, expires_in))
    return access_token


def jira_auth(
    runtime: RuntimeConfig,
    user_token: str | None = None,
    user_email: str | None = None,
) -> tuple[dict[str, str], tuple[str, str] | None]:
    """Gateway-Key und Jira-User parallel: x-apikey allein ist anonym.

    user_token/user_email: persönliche Credentials des eingeloggten Nutzers.
    Haben Vorrang vor den globalen Einstellungen wenn angegeben.
    """
    headers: dict[str, str] = {}
    auth: tuple[str, str] | None = None
    if runtime.jira_api_key:
        headers["x-apikey"] = runtime.jira_api_key
    oauth = _oauth_client_credentials_token(runtime)
    if oauth:
        headers["Authorization"] = f"Bearer {oauth}"
        return headers, None
    token = (user_token or runtime.jira_api_token or "").strip()
    user = (user_email or runtime.jira_email or "").strip()
    # Optional: API-Key zusätzlich zum Token (manche Gateways).
    if runtime.jira_api_key and token:
        headers["Authorization"] = f"Bearer {token}"
        return headers, None
    if token and user:
        auth = (user, token)
    elif token:
        headers["Authorization"] = f"Bearer {token}"
    return headers, auth


def _adf_paragraph(text: str) -> dict:
    lines = (text or "").split("\n")
    content = [
        {
            "type": "paragraph",
            "content": [{"type": "text", "text": line}] if line else [],
        }
        for line in lines
    ] or [{"type": "paragraph", "content": []}]
    return {"type": "doc", "version": 1, "content": content}


def _load_field_map(settings: Settings) -> dict:
    return yaml.safe_load(settings.field_map_path.read_text(encoding="utf-8")) or {}


def _jira_username(raw: str) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    if "(" in text:
        text = text.split("(", 1)[0].strip()
    if "@" in text:
        text = text.split("@", 1)[0].strip()
    if re.fullmatch(r"[\w.-]+", text):
        return text
    return None


def _format_jira_field_value(
    meta: dict[str, Any],
    value: object,
    *,
    as_description,
    option_resolver=None,
    user_resolver=None,
    component_resolver=None,
) -> object | None:
    """Domain-Wert in Jira-API-Form. None = Feld nicht setzen (Fallback Description)."""
    raw = str(value or "").strip()
    if not raw:
        return None
    jira_type = str(meta.get("jira_type") or "string").lower()
    jira_id = str(meta.get("jira") or "")
    if jira_type == "date":
        from app.domain.dates import normalize_date_value

        iso = normalize_date_value(raw)
        return iso if re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso) else raw
    if jira_type == "number":
        cleaned = raw.replace(",", ".").replace(" PT", "").replace("PT", "").strip()
        try:
            return float(cleaned) if "." in cleaned else int(cleaned)
        except ValueError:
            return None
    if jira_type == "user":
        from app.triage.engine import is_unknown_answer

        if is_unknown_answer(raw):
            return None
        if user_resolver:
            return user_resolver(raw)
        name = _jira_username(raw)
        return {"name": name} if name else None
    if jira_type == "option":
        if option_resolver:
            resolved = option_resolver(jira_id, raw)
            return resolved
        return {"value": raw}
    if jira_type == "components":
        if component_resolver:
            return component_resolver(raw)
        parts = [part.strip() for part in raw.replace(";", ",").split(",") if part.strip()]
        return [{"name": part} for part in parts] or None
    if jira_type == "text":
        if jira_id == "description":
            return as_description(raw)
        return raw
    return raw


def _rejected_field_ids(body: str) -> list[str]:
    """Field-IDs aus Jira-400 (Screen/unknown/Option ungültig)."""
    raw = (body or "").strip()
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    if not isinstance(data, dict):
        return []
    errors = data.get("errors")
    if not isinstance(errors, dict):
        return []
    out: list[str] = []
    for field_id, message in errors.items():
        text = str(message or "").lower()
        if (
            "cannot be set" in text
            or "unknown" in text
            or "not on the appropriate screen" in text
            or "option id" in text
            or "invalid option" in text
            or "is not valid" in text
        ):
            out.append(str(field_id))
    return out


def _format_jira_error(status: int, body: str) -> str:
    raw = (body or "").strip()
    low = raw.lower()
    if "no project could be found" in low:
        return "Jira-Projekt nicht gefunden. Project Key in den Einstellungen prüfen."
    if "cannot be set" in low and "summary" in low:
        return (
            "Jira lehnt die Anlage ab: der API-Key darf Summary nicht setzen. "
            "Meist fehlt die Create-Berechtigung, oder das Projekt ist für den Key unsichtbar."
        )
    if "issue type is required" in low or "issuetype" in low and "invalid" in low:
        return "Jira kennt den Vorgangstyp nicht. In field_map.yaml den Issue-Type prüfen."
    if "customfield_19753" in low or "summary is required" in low:
        return (
            "Jira verlangt das Pflichtfeld Zusammenfassung (customfield_19753). "
            "Steckbrief-Name muss gesetzt sein."
        )
    if "login required" in low or "must be authenticated" in low:
        return "Jira: nicht angemeldet. API-Key oder Token prüfen."
    snippet = raw.replace("\n", " ")[:240]
    return f"Jira {status}: {snippet}" if snippet else f"Jira {status}"


def _parse_json(response: httpx.Response) -> dict:
    if response.status_code in {301, 302, 303, 307, 308}:
        loc = response.headers.get("location") or ""
        raise TicketPortError(
            f"Jira {response.status_code} Redirect{': ' + loc if loc else ''}. API-URL prüfen."
        )
    if not response.content:
        raise TicketPortError(f"Jira {response.status_code}: leere Antwort")
    try:
        data = response.json()
    except ValueError as err:
        raise TicketPortError(f"Jira {response.status_code}: keine JSON-Antwort") from err
    if not isinstance(data, dict):
        raise TicketPortError(f"Jira {response.status_code}: unerwartete Antwort")
    return data


class JiraRestV3:
    system = "jira"

    def __init__(
        self,
        runtime: RuntimeConfig | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        if runtime is None:
            from app.services.settings_service import get_runtime_config

            runtime = get_runtime_config()
        self._runtime = runtime
        self._field_map = _load_field_map(self._settings)
        self._option_cache: dict[str, dict[str, dict[str, str]]] = {}
        self._component_cache: list[str] | None = None
        self._validate()

    def _project_key(self) -> str:
        return self._runtime.jira_project_key or self._field_map.get("project_key") or "CHANGE"

    def search_assignable_users(
        self,
        query: str = "",
        *,
        limit: int = 10,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> list[dict[str, str]]:
        # Jira liefert oft max. 50 pro Seite — paginieren bis limit oder leer.
        want = max(1, min(int(limit or 10), 5000))
        page_size = 50
        needle = (query or "").strip()
        out: list[dict[str, str]] = []
        seen: set[str] = set()
        start = 0
        while len(out) < want:
            batch = min(page_size, want - len(out))
            params: dict[str, Any] = {
                "project": self._project_key(),
                "maxResults": batch,
                "startAt": start,
            }
            if needle:
                params["username"] = needle
            try:
                response = self._request(
                    "GET",
                    "/user/assignable/search",
                    params=params,
                    user_token=user_token,
                    user_email=user_email,
                )
            except TicketPortError:
                if not out:
                    raise
                break
            data = response.json()
            rows = (
                data
                if isinstance(data, list)
                else (data.get("users") if isinstance(data, dict) else [])
            ) or []
            if not rows:
                break
            added = 0
            for row in rows:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("name") or row.get("key") or row.get("accountId") or "").strip()
                if not name or name.lower() in seen:
                    continue
                seen.add(name.lower())
                out.append(
                    {
                        "name": name,
                        "displayName": str(row.get("displayName") or name).strip(),
                        "emailAddress": str(row.get("emailAddress") or "").strip(),
                    }
                )
                added += 1
                if len(out) >= want:
                    break
            # Gateway ignoriert startAt oft → dieselbe Seite endlos. Dann stoppen.
            if added == 0 or len(rows) < batch:
                break
            start += len(rows)
            if start >= 10000:
                break
        return out

    def list_components(
        self,
        *,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> list[str]:
        if self._component_cache is not None:
            return list(self._component_cache)
        try:
            response = self._request(
                "GET",
                f"/project/{self._project_key()}/components",
                user_token=user_token,
                user_email=user_email,
            )
        except TicketPortError:
            return []
        data = response.json()
        rows = data if isinstance(data, list) else (data.get("components") if isinstance(data, dict) else []) or []
        names = [
            str(row.get("name") or "").strip()
            for row in rows
            if isinstance(row, dict) and str(row.get("name") or "").strip()
        ]
        self._component_cache = names
        return list(names)

    def search_components(
        self,
        query: str = "",
        *,
        limit: int = 20,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> list[str]:
        needle = (query or "").strip().lower()
        hits = self.list_components(user_token=user_token, user_email=user_email)
        if not needle:
            return hits[: max(1, min(limit, 200))]
        matched = [name for name in hits if needle in name.lower()]
        return matched[: max(1, min(limit, 200))]

    def resolve_user(
        self,
        raw: str,
        *,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> dict[str, str] | None:
        text = (raw or "").strip()
        if not text:
            return None
        needle = text.lower()
        hits = self.search_assignable_users(
            text, limit=10, user_token=user_token, user_email=user_email
        )
        for row in hits:
            name = row["name"]
            display = row.get("displayName", "").lower()
            if needle == name.lower() or needle == display:
                return {"name": name}
        direct = _jira_username(text)
        if direct:
            for row in self.search_assignable_users(
                direct, limit=5, user_token=user_token, user_email=user_email
            ):
                if row["name"].lower() == direct.lower():
                    return {"name": row["name"]}
        return None

    def resolve_components(
        self,
        raw: str,
        *,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> list[dict[str, str]] | None:
        parts = [part.strip() for part in str(raw or "").replace(";", ",").split(",") if part.strip()]
        if not parts:
            return None
        catalog = {
            name.lower(): name
            for name in self.list_components(user_token=user_token, user_email=user_email)
        }
        resolved: list[dict[str, str]] = []
        for part in parts:
            key = part.lower()
            exact = catalog.get(key)
            if exact:
                resolved.append({"name": exact})
                continue
            fuzzy = next(
                (catalog[item] for item in catalog if key in item or item in key),
                None,
            )
            if fuzzy:
                resolved.append({"name": fuzzy})
        return resolved or None

    def _field_jira_id(self, field_key: str) -> str | None:
        meta = (self._field_map.get("fields") or {}).get(field_key) or {}
        jira_id = str(meta.get("jira") or "").strip()
        return jira_id or None

    def _option_values_from_allowed(self, allowed: object) -> list[str]:
        rows = allowed if isinstance(allowed, list) else []
        out: list[str] = []
        seen: set[str] = set()
        for row in rows:
            if isinstance(row, str):
                value = row.strip()
            elif isinstance(row, dict):
                value = str(
                    row.get("value")
                    or row.get("name")
                    or row.get("label")
                    or ""
                ).strip()
            else:
                continue
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(value)
        return out

    def _createmeta_fields(
        self,
        *,
        issue_type: str,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> dict[str, Any]:
        project = self._project_key()
        if self._uses_api2():
            response = self._request(
                "GET",
                "/issue/createmeta",
                params={
                    "projectKeys": project,
                    "issuetypeNames": issue_type,
                    "expand": "projects.issuetypes.fields",
                },
                user_token=user_token,
                user_email=user_email,
            )
            data = response.json()
            projects = data.get("projects") if isinstance(data, dict) else None
            if not isinstance(projects, list):
                return {}
            for proj in projects:
                if not isinstance(proj, dict):
                    continue
                for itype in proj.get("issuetypes") or []:
                    if not isinstance(itype, dict):
                        continue
                    fields = itype.get("fields")
                    if isinstance(fields, dict):
                        return fields
            return {}

        # Cloud / v3: erst Issuetypes, dann Felder je Typ.
        types_resp = self._request(
            "GET",
            f"/issue/createmeta/{project}/issuetypes",
            user_token=user_token,
            user_email=user_email,
        )
        types_data = types_resp.json()
        type_rows = (
            types_data.get("issueTypes")
            or types_data.get("values")
            or (types_data if isinstance(types_data, list) else [])
        )
        issue_type_id = ""
        needle = issue_type.lower()
        for row in type_rows if isinstance(type_rows, list) else []:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            if name.lower() == needle:
                issue_type_id = str(row.get("id") or "").strip()
                break
        if not issue_type_id:
            return {}
        fields_resp = self._request(
            "GET",
            f"/issue/createmeta/{project}/issuetypes/{issue_type_id}",
            user_token=user_token,
            user_email=user_email,
        )
        fields_data = fields_resp.json()
        fields = fields_data.get("fields") if isinstance(fields_data, dict) else None
        if isinstance(fields, list):
            mapped: dict[str, Any] = {}
            for row in fields:
                if not isinstance(row, dict):
                    continue
                field_id = str(row.get("fieldId") or row.get("key") or "").strip()
                if field_id:
                    mapped[field_id] = row
            return mapped
        return fields if isinstance(fields, dict) else {}

    def list_field_options(
        self,
        field_key: str,
        *,
        kind: RequestKind | None = None,
        query: str = "",
        limit: int = 200,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> list[str]:
        """AllowedValues eines Option-Feldes aus dem Create-Screen."""
        field_id = self._field_jira_id(field_key)
        if not field_id:
            return []
        issue_kind = kind or RequestKind.IT_REQUEST
        issue_type = self._issue_type(issue_kind)
        cache_key = f"{self._project_key()}:{issue_type}:{field_id}"
        cached = self._option_cache.get(cache_key)
        if cached is None:
            values: list[str] = []
            try:
                fields = self._createmeta_fields(
                    issue_type=issue_type,
                    user_token=user_token,
                    user_email=user_email,
                )
                meta = fields.get(field_id) if isinstance(fields, dict) else None
                if isinstance(meta, dict):
                    values = self._option_values_from_allowed(meta.get("allowedValues"))
            except TicketPortError:
                values = []
            cached = {value.lower(): {"value": value} for value in values}
            self._option_cache[cache_key] = cached

        names = [row["value"] for row in cached.values()]
        needle = (query or "").strip().lower()
        if needle:
            names = [name for name in names if needle in name.lower()]
        return names[: max(1, min(limit, 200))]

    def _resolve_option(self, field_id: str, raw: str) -> dict[str, str] | None:
        text = (raw or "").strip()
        if not text:
            return None
        needle = text.lower()
        for cached in self._option_cache.values():
            hit = cached.get(needle)
            if hit:
                return {"value": hit["value"]}
            for row in cached.values():
                value = row.get("value") or ""
                if needle in value.lower() or value.lower() in needle:
                    return {"value": value}
        return {"value": text}

    def _format_domain_value(
        self,
        meta: dict[str, Any],
        value: object,
        *,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> object | None:
        return _format_jira_field_value(
            meta,
            value,
            as_description=self._description_body,
            option_resolver=self._resolve_option,
            user_resolver=lambda raw: self.resolve_user(
                raw, user_token=user_token, user_email=user_email
            ),
            component_resolver=lambda raw: self.resolve_components(
                raw, user_token=user_token, user_email=user_email
            ),
        )

    def _validate(self) -> None:
        if not self._runtime.jira_base_url:
            raise TicketPortError("Jira Base-URL fehlt")
        has_oauth = bool(
            self._runtime.jira_oauth_token_url
            and self._runtime.jira_client_id
            and self._runtime.jira_client_secret
        )
        if not self._runtime.jira_api_token and not self._runtime.jira_api_key and not has_oauth:
            raise TicketPortError("Jira API-Token, OAuth oder x-apikey fehlt")

    def _uses_api2(self) -> bool:
        blob = f"{self._runtime.jira_search_url} {self._runtime.jira_base_url}"
        return "/api/2/" in blob or "/jira/v1/" in blob

    def _rest_root(self) -> str:
        search = (self._runtime.jira_search_url or "").rstrip("/")
        if search.endswith("/search"):
            return search[: -len("/search")]
        return ""

    def _url(self, path: str) -> str:
        root = self._rest_root()
        if root and path.startswith("/"):
            if path.startswith("/rest/api/3/"):
                path = path.replace("/rest/api/3/", "/", 1)
            return f"{root}{path}"
        return f"{self._runtime.jira_base_url.rstrip('/')}{path}"

    def _description_body(self, text: str) -> dict | str:
        if self._uses_api2():
            return text
        return _adf_paragraph(text)

    def _comment_body(self, text: str) -> dict | str:
        if self._uses_api2():
            return text
        return _adf_paragraph(text)

    def _issue_path(self, suffix: str = "") -> str:
        if self._rest_root():
            return f"/issue{suffix}"
        return f"/rest/api/3/issue{suffix}"

    def _request(
        self,
        method: str,
        path: str,
        user_token: str | None = None,
        user_email: str | None = None,
        **kwargs,
    ) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("accept", "*/*")
        extra, auth = jira_auth(self._runtime, user_token=user_token, user_email=user_email)
        headers.update(extra)
        try:
            response = httpx.request(
                method,
                self._url(path),
                auth=auth,
                timeout=30,
                headers=headers,
                follow_redirects=False,
                trust_env=False,
                **kwargs,
            )
        except httpx.ProxyError as err:
            raise TicketPortError(
                "Jira-Proxy blockiert (403). HTTP_PROXY/HTTPS_PROXY prüfen oder deaktivieren."
            ) from err
        except httpx.HTTPError as err:
            raise TicketPortError(str(err)[:300]) from err
        if response.status_code in {301, 302, 303, 307, 308}:
            loc = response.headers.get("location") or ""
            raise TicketPortError(
                f"Jira {response.status_code} Redirect{': ' + loc if loc else ''}. API-URL prüfen."
            )
        if response.status_code >= 400:
            rejected = _rejected_field_ids(response.text)
            raise TicketPortError(
                _format_jira_error(response.status_code, response.text[:800]),
                rejected_fields=rejected,
            )
        return response

    def _issue_type(self, kind: RequestKind) -> str:
        kinds = self._field_map.get("kinds") or {}
        block = kinds.get(kind.value) or {}
        return block.get("issue_type") or KIND_LABELS.get(kind, kind.value)

    def _priority_name(self, priority: Priority) -> str:
        mapped = (self._field_map.get("priorities") or {}).get(priority.value)
        return mapped or priority.value.capitalize()

    def create_issue(self, payload: IssuePayload) -> ExternalIssueRef:
        project = self._runtime.jira_project_key or self._field_map.get("project_key") or "TRI"
        field_defs = self._field_map.get("fields") or {}
        jira_fields: dict[str, Any] = {
            "project": {"key": project},
            "summary": payload.title[:255],
            "issuetype": {"name": self._issue_type(payload.kind)},
            "priority": {"name": self._priority_name(payload.priority)},
        }
        mapped_keys: set[str] = set()

        def meta_for(key: str) -> dict[str, Any]:
            meta = dict(field_defs.get(key) or {})
            if key == "effort_sheet_url" and self._runtime.jira_effort_sheet_field:
                meta["jira"] = self._runtime.jira_effort_sheet_field
            return meta

        def assign_domain_field(key: str, value: object) -> None:
            meta = meta_for(key)
            jira_id = meta.get("jira")
            if not jira_id or jira_id == "summary":
                return
            allowed_kinds = meta.get("kinds")
            if allowed_kinds and payload.kind.value not in set(allowed_kinds):
                return
            if meta.get("create") is False:
                return
            formatted = self._format_domain_value(
                meta,
                value,
                user_token=payload.user_jira_token,
                user_email=payload.user_jira_email,
            )
            if formatted is None:
                return
            jira_fields[jira_id] = formatted
            mapped_keys.add(key)

        assign_domain_field("description", payload.description)
        for key, value in payload.fields.items():
            assign_domain_field(key, value)

        steckbrief_value = (payload.steckbrief_name or payload.title or "").strip()[:255]
        if steckbrief_value:
            assign_domain_field("steckbrief_name", steckbrief_value)
            if "steckbrief_name" not in mapped_keys and "customfield_19753" not in jira_fields:
                jira_fields["customfield_19753"] = steckbrief_value
                mapped_keys.add("steckbrief_name")

        if "description" not in jira_fields:
            jira_fields["description"] = self._description_body(payload.description or "")

        reporter_candidates = [
            str(payload.fields.get("author") or "").strip(),
            str(payload.reporter_hint or "").strip(),
            str(payload.created_by or "").strip(),
        ]
        for candidate in reporter_candidates:
            if not candidate:
                continue
            resolved = self.resolve_user(
                candidate,
                user_token=payload.user_jira_token,
                user_email=payload.user_jira_email,
            )
            if resolved:
                jira_fields["reporter"] = resolved
                break

        description_parts: list[str] = []
        primary = (payload.description or "").strip()
        if primary and "description" not in mapped_keys:
            description_parts.append(primary)
        description_parts.append(f"Interne Referenz: {payload.reference}")
        if payload.created_by:
            description_parts.append(f"Erstellt von: {payload.created_by}")
        for key, value in payload.fields.items():
            if key in mapped_keys or not str(value or "").strip():
                continue
            label = meta_for(key).get("label") or key
            description_parts.append(f"{label}: {value}")
        if "description" in mapped_keys:
            extra = "\n".join(description_parts[1:] if primary else description_parts)
            if extra.strip():
                base = payload.description or ""
                jira_fields["description"] = self._description_body(
                    f"{base}\n\n{extra}".strip() if base else extra
                )
        else:
            jira_fields["description"] = self._description_body("\n".join(description_parts))

        attempt = dict(jira_fields)
        protected = {
            "project",
            "summary",
            "issuetype",
            "description",
            "priority",
            "customfield_19753",
        }
        response: httpx.Response | None = None
        last_error: TicketPortError | None = None
        for _ in range(6):
            try:
                response = self._request(
                    "POST",
                    self._issue_path(),
                    json={"fields": dict(attempt)},
                    user_token=payload.user_jira_token,
                    user_email=payload.user_jira_email,
                )
                last_error = None
                break
            except TicketPortError as err:
                last_error = err
                rejected = [
                    field_id
                    for field_id in err.rejected_fields
                    if field_id in attempt and field_id not in protected
                ]
                if not rejected:
                    raise
                for field_id in rejected:
                    attempt.pop(field_id, None)
        if last_error or response is None:
            raise last_error or TicketPortError("Jira Create fehlgeschlagen")
        data = _parse_json(response)
        key = data.get("key")
        if not key:
            raise TicketPortError("Jira-Antwort ohne Issue-Key")
        browse = self._browse_url(key, data.get("self"))
        return ExternalIssueRef(key=key, url=browse)

    def _browse_url(self, key: str, issue_self: str | None = None) -> str:
        self_url = str(issue_self or "").strip()
        if self_url.startswith("http") and "/rest/api/" in self_url:
            return self_url.split("/rest/api/", 1)[0] + f"/browse/{key}"
        base = (self._runtime.jira_base_url or "https://jira.schwarz").rstrip("/")
        if "live.api.schwarz" in base:
            return f"https://jira.schwarz/browse/{key}"
        return f"{base}/browse/{key}"

    def add_comment(self, key: str, body: str, author: str) -> None:
        text = f"{author}: {body}" if author else body
        self._request(
            "POST",
            self._issue_path(f"/{key}/comment"),
            json={"body": self._comment_body(text)},
        )

    def update_fields(
        self,
        key: str,
        fields: dict[str, str],
        priority: Priority | None = None,
        *,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> None:
        jira_fields: dict[str, Any] = {}
        if "summary" in fields or "title" in fields:
            jira_fields["summary"] = fields.get("summary") or fields.get("title")
        if "description" in fields:
            jira_fields["description"] = self._description_body(fields["description"])
        if priority:
            jira_fields["priority"] = {"name": self._priority_name(priority)}
        for name, value in fields.items():
            meta = (self._field_map.get("fields") or {}).get(name) or {}
            jira_id = meta.get("jira")
            if not jira_id or jira_id in ("summary", "description"):
                continue
            formatted = self._format_domain_value(
                meta,
                value,
                user_token=user_token,
                user_email=user_email,
            )
            if formatted is not None:
                jira_fields[jira_id] = formatted
        if not jira_fields:
            return
        self._request("PUT", self._issue_path(f"/{key}"), json={"fields": jira_fields})

    def search_similar(self, text: str, limit: int = 5) -> list[dict[str, str]]:
        needle = text.replace('"', " ").strip()[:80]
        if not needle:
            return []
        project = self._runtime.jira_project_key or "TRI"
        jql = f'project = {project} AND text ~ "{needle}" ORDER BY updated DESC'
        if self._rest_root():
            response = self._request(
                "GET",
                "/search",
                params={"jql": jql, "maxResults": limit, "fields": "key,summary"},
            )
        elif self._runtime.jira_search_url:
            extra, auth = jira_auth(self._runtime)
            headers = {"accept": "*/*", **extra}
            kwargs: dict[str, Any] = {
                "params": {
                    "jql": jql,
                    "maxResults": limit,
                    "fields": "key,summary",
                },
                "headers": headers,
                "timeout": 30,
                "follow_redirects": False,
                "trust_env": False,
            }
            if auth:
                kwargs["auth"] = auth
            try:
                response = httpx.get(self._runtime.jira_search_url, **kwargs)
            except httpx.ProxyError as err:
                raise TicketPortError(
                    "Jira-Proxy blockiert (403). HTTP_PROXY/HTTPS_PROXY prüfen oder deaktivieren."
                ) from err
            except httpx.HTTPError as err:
                raise TicketPortError(str(err)[:300]) from err
            if response.status_code >= 400:
                raise TicketPortError(f"Jira {response.status_code}: {response.text[:300]}")
        else:
            response = self._request(
                "GET",
                "/rest/api/3/search",
                params={"jql": jql, "maxResults": limit, "fields": "summary"},
            )
        issues = _parse_json(response).get("issues") or []
        return [
            {"key": i["key"], "summary": (i.get("fields") or {}).get("summary", "")}
            for i in issues
        ]

    def get_issue(self, key: str) -> dict[str, Any] | None:
        try:
            response = self._request(
                "GET",
                self._issue_path(f"/{key}"),
                params={"fields": "summary,description,status,priority,issuetype,labels"},
            )
        except TicketPortError:
            return None
        return _parse_json(response)
