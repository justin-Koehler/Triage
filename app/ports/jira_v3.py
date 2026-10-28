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
from app.ports.ticket_port import (
    DESCRIPTION_OMIT_KEYS,
    ExternalIssueRef,
    IssuePayload,
    TicketPortError,
    clean_description_lead,
)
from app.services.settings_service import RuntimeConfig

_OAUTH_CACHE: dict[str, tuple[str, float]] = {}
_ISSUE_KEY = re.compile(r"[A-Z][A-Z0-9]+-\d+", re.IGNORECASE)
_STAFF = re.compile(r"\bscs\b|\bcit\b|\(scs\)|\(cit\)", re.IGNORECASE)


def user_picker_label(row: dict[str, str]) -> str:
    """Anzeigename plus E-Mail. Der Jira-Username bleibt unsichtbar."""
    display = str(row.get("displayName") or row.get("name") or "").strip()
    email = str(row.get("emailAddress") or "").strip()
    if display and email:
        return f"{display} · {email}"
    return email or display


def user_staff_rank(row: dict[str, str]) -> int:
    blob = " ".join(
        str(row.get(key) or "")
        for key in ("displayName", "emailAddress", "name")
    )
    if not _STAFF.search(blob):
        return 2
    if re.search(r"\bscs\b|\(scs\)", blob, re.IGNORECASE):
        return 0
    return 1


def user_picker_sort_key(row: dict[str, str], needle: str, match_rank=None) -> tuple:
    """SCS und CIT zuerst. Bei einer Suche zählt der Treffer vor der Gruppe."""
    staff = user_staff_rank(row)
    name = str(row.get("displayName") or row.get("name") or "").casefold()
    if not (needle or "").strip():
        return (staff, name)
    rank = match_rank(row, needle) if match_rank else 50
    return (rank, staff, name)


def public_browse_url(url: str | None, key: str | None = None) -> str:
    """Link, den ein Browser öffnen kann. Das API-Gateway ist keine Jira-Seite."""
    raw = (url or "").strip()
    issue = (key or "").strip()
    if not issue:
        found = _ISSUE_KEY.search(raw)
        issue = found.group(0) if found else ""
    gateway = "live.api.schwarz" in raw.lower()
    if issue and (gateway or not raw):
        return f"https://jira.schwarz/browse/{issue}"
    return raw


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


def adf_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    parts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "text":
                parts.append(str(node.get("text") or ""))
            for child in node.get("content") or []:
                walk(child)
            if node.get("type") in {"paragraph", "heading", "listItem"}:
                parts.append("\n")
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    text = "".join(parts)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


_URL = re.compile(r"https?://[^\s\]|]+")


def _wiki_description(text: str) -> str:
    """API2/Wiki: URLs als [Text|url], damit Links nicht an ? abbrechen."""
    out: list[str] = []
    for line in str(text or "").splitlines():
        raw = line.strip()
        match = re.match(
            r"^(CRITR\s+(?:Ticket|Status update|Aufwand Sheet)|"
            r"Ticket|Status update|Aufwand Sheet)\s*:\s*(https?://\S+)\s*$",
            raw,
            re.IGNORECASE,
        )
        if match:
            label = match.group(1).strip()
            url = match.group(2).rstrip(").,;")
            out.append(f"[{label}|{url}]")
            continue
        # Sonstige nackte URLs in der Zeile ebenfalls verlinken.
        def _wrap(m: re.Match[str]) -> str:
            url = m.group(0).rstrip(").,;")
            return f"[{url}|{url}]"

        out.append(_URL.sub(_wrap, line))
    return "\n".join(out)


def _adf_inline(line: str) -> list[dict]:
    content: list[dict] = []
    pos = 0
    for match in _URL.finditer(line):
        if match.start() > pos:
            content.append({"type": "text", "text": line[pos : match.start()]})
        url = match.group(0)
        content.append(
            {
                "type": "text",
                "text": url,
                "marks": [{"type": "link", "attrs": {"href": url}}],
            }
        )
        pos = match.end()
    if pos < len(line):
        content.append({"type": "text", "text": line[pos:]})
    return content


def _adf_paragraph(text: str) -> dict:
    lines = (text or "").split("\n")
    content = [
        {"type": "paragraph", "content": _adf_inline(line) if line else []}
        for line in lines
    ] or [{"type": "paragraph", "content": []}]
    return {"type": "doc", "version": 1, "content": content}


def _critr_public_base() -> str:
    """Öffentliche CRITR-URL für Links in Jira (nicht localhost)."""
    from urllib.parse import urlparse

    from app.config import get_settings

    settings = get_settings()
    base = (settings.public_base_url or "").strip().rstrip("/")
    if base and "127.0.0.1" not in base and "localhost" not in base:
        return base
    redirect = (settings.cidaas_redirect_url or "").strip()
    if redirect.startswith("http"):
        parsed = urlparse(redirect)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    return base or "http://127.0.0.1:8787"


def _critr_link_block(request_id: str) -> str:
    rid = str(request_id or "").strip()
    if not rid:
        return ""
    base = _critr_public_base()
    # Status-update ohne Query — Jira-Wiki bricht URLs sonst an „?“ ab.
    return (
        f"CRITR Ticket: {base}/workspace/{rid}\n"
        f"CRITR Status update: {base}/status-update/{rid}"
    )


_EFFORT_URL_RE = re.compile(
    r"(https?://[^\s\]|]+/aufwand/[0-9a-fA-F-]{36}|https?://docs\.google\.com/spreadsheets/d/[^\s\]|]+)",
    re.IGNORECASE,
)
_EFFORT_LINE_RE = re.compile(
    r"^(?:CRITR\s+)?Aufwand\s*Sheet\s*:\s*\S+",
    re.IGNORECASE,
)
_CRITR_LINK_LINE_RE = re.compile(
    r"^(?:CRITR\s+)?(?:Ticket|Status update)\s*:\s*\S+",
    re.IGNORECASE,
)


def _resolve_effort_url(text: str, effort_url: str = "") -> str:
    """Effort-Sheet-URL aus Parameter oder bestehendem Beschreibungstext."""
    direct = str(effort_url or "").strip()
    if direct:
        return direct
    body = str(text or "")
    match = _EFFORT_URL_RE.search(body)
    if match:
        return match.group(1).rstrip(").,;")
    sid = re.search(r"/aufwand/([0-9a-fA-F-]{36})", body)
    if sid:
        return f"{_critr_public_base()}/aufwand/{sid.group(1)}"
    return ""


def _with_critr_links(text: str, request_id: str, *, effort_url: str = "") -> str:
    rid = str(request_id or "").strip()
    body = (text or "").strip()
    base = _critr_public_base()
    effort = _resolve_effort_url(body, effort_url)

    # Alte Link-/Aufwand-Zeilen entfernen — unten einheitlich neu anhängen.
    cleaned: list[str] = []
    for line in body.splitlines():
        raw = line.strip()
        if _CRITR_LINK_LINE_RE.match(raw) or _EFFORT_LINE_RE.match(raw):
            continue
        if effort and effort in raw and ("aufwand" in raw.casefold() or "effort" in raw.casefold()):
            continue
        if rid and (
            f"/workspace/{rid}" in raw
            or f"/status-update/{rid}" in raw
            or f"/status-update?id={rid}" in raw
            or f"status-update?id={rid}" in raw
        ):
            continue
        cleaned.append(line)
    body = "\n".join(cleaned).strip()

    lines: list[str] = []
    if rid:
        lines.append(f"CRITR Ticket: {base}/workspace/{rid}")
        lines.append(f"CRITR Status update: {base}/status-update/{rid}")
    if effort:
        lines.append(f"CRITR Aufwand Sheet: {effort}")
    if not lines:
        return body
    block = "\n".join(lines)
    return f"{body}\n\n{block}".strip() if body else block


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


def mapped_custom_fields_for_update(
    field_map: dict[str, Any],
    fields: dict[str, str],
    *,
    format_value,
) -> dict[str, Any]:
    """Domain-Felder → Jira customfield-Payload.

    Leerer String im Payload setzt das Jira-Feld auf null (löschen).
    Fehlt der Key im Payload, wird das Jira-Feld nicht angefasst.
    """
    out: dict[str, Any] = {}
    meta_fields = (field_map.get("fields") or {}) if isinstance(field_map, dict) else {}
    for name, value in (fields or {}).items():
        meta = meta_fields.get(name) or {}
        if not isinstance(meta, dict):
            continue
        jira_id = meta.get("jira")
        if not jira_id or jira_id in ("summary", "description"):
            continue
        if meta.get("create") is False:
            continue
        raw = str(value or "").strip()
        formatted = format_value(meta, value)
        if formatted is not None:
            out[str(jira_id)] = formatted
        elif raw == "":
            out[str(jira_id)] = None
    return out


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
        from app.domain.dates import parse_german_date

        # Nur echte ISO-Daten — „bald“/„test“ dürfen Create nicht sprengen.
        iso = parse_german_date(raw)
        return iso if iso and re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso) else None
    if jira_type == "number":
        from app.domain.calc import parse_money_amount

        amount = parse_money_amount(raw)
        if amount is None:
            return None
        return int(amount) if amount == int(amount) else amount
    if jira_type == "user":
        from app.triage.engine import is_unknown_answer

        if is_unknown_answer(raw):
            return None
        if user_resolver:
            return user_resolver(raw)
        name = _jira_username(raw)
        return {"name": name} if name else None
    if jira_type == "users":
        from app.triage.engine import is_unknown_answer

        if is_unknown_answer(raw):
            return None
        parts = [part.strip() for part in raw.replace(";", ",").split(",") if part.strip()]
        out: list[dict[str, str]] = []
        seen: set[str] = set()
        for part in parts:
            if is_unknown_answer(part):
                continue
            resolved = user_resolver(part) if user_resolver else None
            if not resolved:
                name = _jira_username(part)
                resolved = {"name": name} if name else None
            if not resolved:
                continue
            key = str(resolved.get("name") or resolved.get("accountId") or "").lower()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(resolved)
        return out or None
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


def _is_kalk_filename(name: str) -> bool:
    low = (name or "").strip().lower()
    return low.endswith("-kalkulation.xlsx") or low.endswith("-kalkulation.csv") or low in {
        "kalkulation.xlsx",
        "kalkulation.csv",
    }


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
    if "cannot be set" in low and "customfield_19753" in low:
        return (
            "Jira: Steckbrief-Name (customfield_19753) steht nicht auf dem Create-Screen "
            "dieses Vorgangstyps und wird weggelassen."
        )
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
        self._component_cache: list[dict[str, str]] | None = None
        self._validate()

    def _project_key(self) -> str:
        return self._runtime.jira_project_key or self._field_map.get("project_key") or "CHANGE"

    def _user_row_from_jira(self, row: dict[str, Any]) -> dict[str, str] | None:
        name = str(
            row.get("name") or row.get("key") or row.get("accountId") or ""
        ).strip()
        if not name:
            return None
        avatars = row.get("avatarUrls") if isinstance(row.get("avatarUrls"), dict) else {}
        avatar = str(
            row.get("avatarUrl")
            or avatars.get("48x48")
            or avatars.get("32x32")
            or avatars.get("24x24")
            or ""
        ).strip()
        return {
            "name": name,
            "displayName": str(row.get("displayName") or name).strip(),
            "emailAddress": str(row.get("emailAddress") or "").strip(),
            "avatarUrl": avatar,
        }

    @staticmethod
    def _user_match_rank(row: dict[str, str], needle: str) -> int:
        """Niedriger = besser. Volle Namen und Display-Treffer vor Username-Prefix."""
        n = (needle or "").strip().casefold()
        if not n:
            return 50
        display = (row.get("displayName") or "").casefold()
        name = (row.get("name") or "").casefold()
        email = (row.get("emailAddress") or "").casefold()
        if display == n or name == n:
            return 0
        tokens = [t for t in n.split() if t]
        if tokens and all(t in display for t in tokens):
            if display.startswith(tokens[0]) and tokens[-1] in display:
                return 1
            return 2
        if display.startswith(n) or name.startswith(n):
            return 3
        if n in display or n in name or (email and n in email):
            return 4
        return 40

    def _search_users_picker(
        self,
        query: str,
        *,
        limit: int,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> list[dict[str, str]]:
        """User-Picker: findet Personen per Anzeigename (nicht nur Assignable/Username)."""
        needle = (query or "").strip()
        if not needle:
            return []
        want = max(1, min(int(limit or 10), 100))
        # Mehrere Varianten: voller Text, Nachname, Vorname — dann ranken.
        variants = [needle]
        parts = needle.split()
        if len(parts) >= 2:
            variants.append(parts[-1])
            variants.append(parts[0])
        seen: set[str] = set()
        out: list[dict[str, str]] = []
        for variant in variants:
            params = {
                "query": variant,
                "maxResults": min(50, max(want, 20)),
                "showAvatar": "true",
            }
            try:
                response = self._request(
                    "GET",
                    "/user/picker",
                    params=params,
                    user_token=user_token,
                    user_email=user_email,
                )
            except TicketPortError:
                continue
            data = response.json()
            rows = (
                data.get("users")
                if isinstance(data, dict)
                else (data if isinstance(data, list) else [])
            ) or []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                parsed = self._user_row_from_jira(row)
                if not parsed:
                    continue
                key = parsed["name"].casefold()
                if key in seen:
                    continue
                seen.add(key)
                out.append(parsed)
        out.sort(key=lambda row: user_picker_sort_key(row, needle, self._user_match_rank))
        return out[:want]

    def _search_users_assignable(
        self,
        query: str = "",
        *,
        limit: int = 10,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> list[dict[str, str]]:
        # Nur Assignable im Projekt — ergänzt Picker, reicht allein nicht für alle Personen.
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
                parsed = self._user_row_from_jira(row)
                if not parsed:
                    continue
                key = parsed["name"].casefold()
                if key in seen:
                    continue
                seen.add(key)
                out.append(parsed)
                added += 1
                if len(out) >= want:
                    break
            if added == 0 or len(rows) < batch:
                break
            start += len(rows)
            if start >= 10000:
                break
        return out

    def search_assignable_users(
        self,
        query: str = "",
        *,
        limit: int = 10,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> list[dict[str, str]]:
        """Personensuche für UI: Picker (Anzeigename) + Assignable zusammenführen."""
        want = max(1, min(int(limit or 10), 5000))
        needle = (query or "").strip()
        if not needle:
            rows = self._search_users_assignable(
                "", limit=max(want, 80), user_token=user_token, user_email=user_email
            )
            rows.sort(key=lambda row: user_picker_sort_key(row, ""))
            return rows[:want]
        picked = self._search_users_picker(
            needle, limit=want, user_token=user_token, user_email=user_email
        )
        # Assignable nur nachziehen, wenn Picker wenig liefert (kurze Queries).
        if len(picked) >= min(want, 5):
            return picked[:want]
        try:
            assignable = self._search_users_assignable(
                needle, limit=want, user_token=user_token, user_email=user_email
            )
        except TicketPortError:
            assignable = []
        seen = {row["name"].casefold() for row in picked}
        for row in assignable:
            key = row["name"].casefold()
            if key in seen:
                continue
            seen.add(key)
            picked.append(row)
        picked.sort(key=lambda row: user_picker_sort_key(row, needle, self._user_match_rank))
        return picked[:want]

    def list_component_records(
        self,
        *,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> list[dict[str, str]]:
        if self._component_cache is not None:
            return [dict(row) for row in self._component_cache]
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
        records = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            records.append(
                {
                    "id": str(row.get("id") or ""),
                    "name": name,
                    "description": str(row.get("description") or "").strip(),
                }
            )
        self._component_cache = records
        return [dict(row) for row in records]

    def list_components(
        self,
        *,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> list[str]:
        records = self.list_component_records(
            user_token=user_token, user_email=user_email
        )
        return [row["name"] for row in records]

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
        hits = self.search_assignable_users(
            text, limit=20, user_token=user_token, user_email=user_email
        )
        if not hits:
            return None
        needle = text.casefold()
        tokens = [t for t in needle.split() if t]
        best = hits[0]
        rank = self._user_match_rank(best, text)
        # Exakt / Vor+Nachname sicher; einzelnes Token nur bei eindeutigem Treffer.
        if rank <= 1:
            return {"name": best["name"]}
        if rank == 2 and len(tokens) >= 2:
            return {"name": best["name"]}
        for row in hits:
            if (
                row["name"].casefold() == needle
                or (row.get("displayName") or "").casefold() == needle
            ):
                return {"name": row["name"]}
        direct = _jira_username(text)
        if direct:
            for row in hits:
                if row["name"].casefold() == direct.casefold():
                    return {"name": row["name"]}
        if tokens:
            token_hits = [
                row
                for row in hits
                if all(t in (row.get("displayName") or "").casefold() for t in tokens)
            ]
            if len(token_hits) == 1:
                return {"name": token_hits[0]["name"]}
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
            # Wiki-Markup: klickbare Links inkl. Query/?-freie Pfade.
            return _wiki_description(text)
        return _adf_paragraph(text)

    def _comment_body(self, text: str) -> dict | str:
        if self._uses_api2():
            return text
        return _adf_paragraph(text)

    def _issue_path(self, suffix: str = "") -> str:
        if self._rest_root():
            return f"/issue{suffix}"
        return f"/rest/api/3/issue{suffix}"

    def _attachment_path(self, attachment_id: str) -> str:
        aid = str(attachment_id or "").strip()
        if self._rest_root():
            return f"/attachment/{aid}"
        return f"/rest/api/3/attachment/{aid}"

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
        url = path if str(path).startswith("http://") or str(path).startswith("https://") else self._url(path)
        try:
            response = httpx.request(
                method,
                url,
                auth=auth,
                timeout=60,
                headers=headers,
                follow_redirects=bool(kwargs.pop("follow_redirects", False)),
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
        steckbrief_value = (
            (payload.steckbrief_name or "").strip()
            or (payload.title or "").strip()
            or (payload.reference or "").strip()
            or "Ohne Titel"
        )[:255]
        title_value = (payload.title or "").strip()[:255] or steckbrief_value
        jira_fields: dict[str, Any] = {
            "project": {"key": project},
            "summary": title_value,
            "issuetype": {"name": self._issue_type(payload.kind)},
            "priority": {"name": self._priority_name(payload.priority)},
        }
        mapped_keys: set[str] = set()

        def meta_for(key: str) -> dict[str, Any]:
            meta = dict(field_defs.get(key) or {})
            if key == "effort_sheet_url" and self._runtime.jira_effort_sheet_field:
                meta["jira"] = self._runtime.jira_effort_sheet_field
            return meta

        def field_applies(key: str) -> bool:
            allowed_kinds = meta_for(key).get("kinds")
            if not allowed_kinds:
                return True
            return payload.kind.value in set(allowed_kinds)

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

        if field_applies("steckbrief_name"):
            assign_domain_field("steckbrief_name", steckbrief_value)
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

        # Gesamtprojektleiter nur, wenn es nicht die anlegende Person ist.
        lead_meta = meta_for("change_lead")
        lead_id = str(lead_meta.get("jira") or "").strip()
        lead_raw = str(payload.fields.get("change_lead") or "").strip()
        creator = {
            str(payload.fields.get("author") or "").strip().casefold(),
            str(payload.reporter_hint or "").strip().casefold(),
            str(payload.created_by or "").strip().casefold(),
        }
        creator.discard("")
        if lead_raw and lead_raw.casefold() in creator:
            from app.services.requests_service import SELF_AS_LEAD

            if lead_id:
                jira_fields.pop(lead_id, None)
            raise TicketPortError(SELF_AS_LEAD)
        if lead_id and lead_id not in jira_fields and field_applies("change_lead") and lead_raw:
            resolved = self.resolve_user(
                lead_raw,
                user_token=payload.user_jira_token,
                user_email=payload.user_jira_email,
            )
            if resolved:
                jira_fields[lead_id] = resolved
                mapped_keys.add("change_lead")

        # Jira-Beschreibung = nur Freitext + CRITR-Links (keine Feld-Fallbacks).
        effort_url = str(payload.fields.get("effort_sheet_url") or "").strip()
        desc_source = str(payload.fields.get("description") or payload.description or "").strip()
        jira_fields["description"] = self._description_body(
            _with_critr_links(
                clean_description_lead(desc_source),
                payload.request_id,
                effort_url=effort_url,
            )
        )

        attempt = dict(jira_fields)
        protected = {
            "project",
            "summary",
            "issuetype",
            "description",
            "priority",
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
            origin = self_url.split("/rest/api/", 1)[0]
            candidate = f"{origin}/browse/{key}"
        else:
            base = (self._runtime.jira_base_url or "https://jira.schwarz").rstrip("/")
            candidate = f"{base}/browse/{key}" if base else ""
        return public_browse_url(candidate, key)

    def add_comment(self, key: str, body: str, author: str) -> str | None:
        text = f"{author}: {body}" if author else body
        response = self._request(
            "POST",
            self._issue_path(f"/{key}/comment"),
            json={"body": self._comment_body(text)},
        )
        if not response.content:
            return None
        try:
            data = response.json()
        except Exception:
            return None
        if isinstance(data, dict) and data.get("id") is not None:
            return str(data["id"])
        return None

    def list_comments(
        self,
        key: str,
        *,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> list[dict[str, Any]]:
        issue_key = (key or "").strip()
        if not issue_key:
            return []
        out: list[dict[str, Any]] = []
        start = 0
        page = 50
        while True:
            response = self._request(
                "GET",
                self._issue_path(f"/{issue_key}/comment"),
                params={"startAt": start, "maxResults": page},
                user_token=user_token,
                user_email=user_email,
            )
            data = _parse_json(response)
            rows = data.get("comments") if isinstance(data, dict) else None
            if not isinstance(rows, list):
                rows = data if isinstance(data, list) else []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                cid = str(row.get("id") or "").strip()
                if not cid:
                    continue
                author_raw = row.get("author") or {}
                author = ""
                if isinstance(author_raw, dict):
                    author = str(
                        author_raw.get("displayName")
                        or author_raw.get("name")
                        or author_raw.get("emailAddress")
                        or ""
                    ).strip()
                elif author_raw:
                    author = str(author_raw).strip()
                out.append(
                    {
                        "id": cid,
                        "author": author,
                        "body": adf_to_text(row.get("body")),
                        "created": str(row.get("created") or "").strip(),
                    }
                )
            total = int(data.get("total") or 0) if isinstance(data, dict) else len(rows)
            start += len(rows)
            if not rows or start >= total or len(rows) < page:
                break
            if start > 500:
                break
        return out

    def delete_comment(
        self,
        key: str,
        comment_id: str,
        *,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> None:
        cid = str(comment_id or "").strip()
        if not cid:
            raise TicketPortError("Jira-Kommentar-ID fehlt")
        try:
            self._request(
                "DELETE",
                self._issue_path(f"/{key}/comment/{cid}"),
                user_token=user_token,
                user_email=user_email,
            )
        except TicketPortError as err:
            # Bereits weg = Erfolg (Doppel-Delete / Race mit Sync)
            if "404" in str(err):
                return
            raise

    def list_attachments(
        self,
        key: str,
        *,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> list[dict[str, Any]]:
        issue_key = (key or "").strip()
        if not issue_key:
            return []
        try:
            response = self._request(
                "GET",
                self._issue_path(f"/{issue_key}"),
                params={"fields": "attachment"},
                user_token=user_token,
                user_email=user_email,
            )
        except TicketPortError:
            return []
        data = _parse_json(response)
        files = ((data.get("fields") or {}).get("attachment")) or []
        out: list[dict[str, Any]] = []
        for row in files:
            if not isinstance(row, dict):
                continue
            aid = str(row.get("id") or "").strip()
            if not aid:
                continue
            author_raw = row.get("author") or {}
            author = ""
            if isinstance(author_raw, dict):
                author = str(
                    author_raw.get("displayName")
                    or author_raw.get("name")
                    or author_raw.get("emailAddress")
                    or ""
                ).strip()
            out.append(
                {
                    "id": aid,
                    "filename": str(row.get("filename") or "anhang").strip() or "anhang",
                    "mimeType": str(row.get("mimeType") or "").strip(),
                    "size": int(row.get("size") or 0),
                    "author": author,
                    "created": str(row.get("created") or "").strip(),
                }
            )
        return out

    def download_attachment(
        self,
        attachment_id: str,
        *,
        user_token: str | None = None,
        user_email: str | None = None,
        thumbnail: bool = False,
    ) -> tuple[bytes, str, str]:
        aid = str(attachment_id or "").strip()
        if not aid:
            raise TicketPortError("Anhang-ID fehlt")
        meta_name = "anhang"
        meta_type = "application/octet-stream"
        meta: dict[str, Any] = {}
        try:
            meta = _parse_json(
                self._request(
                    "GET",
                    self._attachment_path(aid),
                    user_token=user_token,
                    user_email=user_email,
                )
            )
            if not isinstance(meta, dict):
                meta = {}
            meta_name = str(meta.get("filename") or meta_name).strip() or meta_name
            meta_type = str(meta.get("mimeType") or meta_type).strip() or meta_type
        except TicketPortError:
            meta = {}

        content_url = ""
        if thumbnail:
            content_url = str(meta.get("thumbnail") or "").strip()
            if content_url:
                meta_name = f"thumb-{meta_name}"
                meta_type = "image/png"
        if not content_url:
            content_url = str(meta.get("content") or "").strip()

        if content_url.startswith("http://") or content_url.startswith("https://"):
            response = self._request(
                "GET",
                content_url,
                user_token=user_token,
                user_email=user_email,
                follow_redirects=True,
            )
        else:
            # Fallback: REST-Content-Pfad (Cloud / ältere Gateways)
            content_path = (
                f"/attachment/{aid}/content"
                if self._rest_root()
                else f"/rest/api/3/attachment/content/{aid}"
            )
            try:
                response = self._request(
                    "GET",
                    content_path,
                    user_token=user_token,
                    user_email=user_email,
                    follow_redirects=True,
                )
            except TicketPortError:
                # Letzter Versuch: /secure/attachment/{id} relativ zur Base
                base = (self._runtime.jira_base_url or "").rstrip("/")
                if not base:
                    raise
                response = self._request(
                    "GET",
                    f"{base}/secure/attachment/{aid}",
                    user_token=user_token,
                    user_email=user_email,
                    follow_redirects=True,
                )

        ctype = (
            str(response.headers.get("content-type") or "").split(";")[0].strip()
            or meta_type
        )
        return response.content or b"", meta_name, ctype

    def add_attachment(
        self,
        key: str,
        filename: str,
        content: bytes,
        content_type: str = "text/csv",
        *,
        user_token: str | None = None,
        user_email: str | None = None,
        replace_same_name: bool = True,
        strip_kalk: bool = True,
    ) -> list[dict[str, Any]]:
        name = (filename or "kalkulation.csv").strip() or "kalkulation.csv"
        if replace_same_name or strip_kalk:
            self._remove_kalk_attachments(
                key,
                name,
                user_token=user_token,
                user_email=user_email,
                replace_same_name=replace_same_name,
                strip_kalk=strip_kalk,
            )
        response = self._request(
            "POST",
            self._issue_path(f"/{key}/attachments"),
            headers={"X-Atlassian-Token": "no-check"},
            files={"file": (name, content or b"", content_type or "text/csv")},
            user_token=user_token,
            user_email=user_email,
        )
        try:
            data = response.json() if response.content else []
        except ValueError as err:
            raise TicketPortError("Jira: keine JSON-Antwort beim Anhang-Upload") from err
        rows = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            aid = str(row.get("id") or "").strip()
            if not aid:
                continue
            author_raw = row.get("author") or {}
            author = ""
            if isinstance(author_raw, dict):
                author = str(
                    author_raw.get("displayName")
                    or author_raw.get("name")
                    or author_raw.get("emailAddress")
                    or ""
                ).strip()
            out.append(
                {
                    "id": aid,
                    "filename": str(row.get("filename") or name).strip() or name,
                    "mimeType": str(row.get("mimeType") or content_type or "").strip(),
                    "size": int(row.get("size") or len(content or b"") or 0),
                    "author": author,
                    "created": str(row.get("created") or "").strip(),
                }
            )
        return out

    def _remove_kalk_attachments(
        self,
        key: str,
        incoming: str,
        *,
        user_token: str | None = None,
        user_email: str | None = None,
        replace_same_name: bool = True,
        strip_kalk: bool = True,
    ) -> None:
        try:
            response = self._request(
                "GET",
                self._issue_path(f"/{key}"),
                params={"fields": "attachment"},
                user_token=user_token,
                user_email=user_email,
            )
        except TicketPortError:
            return
        files = ((_parse_json(response).get("fields") or {}).get("attachment")) or []
        incoming_l = incoming.strip().lower()
        for item in files:
            if not isinstance(item, dict):
                continue
            fname = str(item.get("filename") or "").strip()
            low = fname.lower()
            same = replace_same_name and low == incoming_l
            kalk = strip_kalk and _is_kalk_filename(low)
            if not same and not kalk:
                continue
            aid = str(item.get("id") or "").strip()
            if not aid:
                continue
            try:
                self._request(
                    "DELETE",
                    self._attachment_path(aid),
                    user_token=user_token,
                    user_email=user_email,
                )
            except TicketPortError:
                continue

    def update_fields(
        self,
        key: str,
        fields: dict[str, str],
        priority: Priority | None = None,
        *,
        user_token: str | None = None,
        user_email: str | None = None,
        request_id: str | None = None,
    ) -> None:
        jira_fields: dict[str, Any] = {}
        if "summary" in fields or "title" in fields:
            jira_fields["summary"] = fields.get("summary") or fields.get("title")
        if "description" in fields or request_id or fields.get("effort_sheet_url"):
            jira_fields["description"] = self._description_body(
                _with_critr_links(
                    str(fields.get("description") or ""),
                    request_id or "",
                    effort_url=str(fields.get("effort_sheet_url") or "").strip(),
                )
            )
        if priority:
            jira_fields["priority"] = {"name": self._priority_name(priority)}
        jira_fields.update(
            mapped_custom_fields_for_update(
                self._field_map,
                fields,
                format_value=lambda meta, value: self._format_domain_value(
                    meta,
                    value,
                    user_token=user_token,
                    user_email=user_email,
                ),
            )
        )
        if not jira_fields:
            return
        # Wie Create: ungültige Optionen entfernen, Rest trotzdem schreiben.
        attempt = dict(jira_fields)
        protected = {"summary", "description", "priority"}
        last_error: TicketPortError | None = None
        for _ in range(6):
            try:
                self._request(
                    "PUT",
                    self._issue_path(f"/{key}"),
                    json={"fields": dict(attempt)},
                    user_token=user_token,
                    user_email=user_email,
                )
                return
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
                if not attempt:
                    raise
        if last_error:
            raise last_error

    def _search_raw(
        self,
        jql: str,
        fields: str,
        limit: int,
        *,
        start_at: int = 0,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> dict[str, Any]:
        params = {"jql": jql, "maxResults": limit, "startAt": start_at, "fields": fields}
        if self._rest_root():
            response = self._request(
                "GET",
                "/search",
                params=params,
                user_token=user_token,
                user_email=user_email,
            )
        elif self._runtime.jira_search_url:
            extra, auth = jira_auth(
                self._runtime, user_token=user_token, user_email=user_email
            )
            headers = {"accept": "*/*", **extra}
            kwargs: dict[str, Any] = {
                "params": params,
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
                params=params,
                user_token=user_token,
                user_email=user_email,
            )
        return _parse_json(response)

    def _mapped_jira_ids(self) -> list[str]:
        ids = [
            "summary",
            "description",
            "status",
            "priority",
            "issuetype",
            "created",
            "updated",
            "assignee",
            "reporter",
        ]
        for meta in (self._field_map.get("fields") or {}).values():
            jira_id = str((meta or {}).get("jira") or "").strip()
            if jira_id and jira_id not in ids:
                ids.append(jira_id)
        return ids

    def _jira_field_text(self, raw: Any) -> str:
        if raw is None:
            return ""
        if isinstance(raw, (str, int, float)):
            return str(raw).strip()
        if isinstance(raw, list):
            parts = [self._jira_field_text(item) for item in raw]
            return ", ".join(part for part in parts if part)
        if isinstance(raw, dict):
            if raw.get("type") == "doc" or "content" in raw:
                text = adf_to_text(raw)
                if text:
                    return text
            for key in ("displayName", "value", "name", "emailAddress"):
                val = raw.get(key)
                if val:
                    return str(val).strip()
        return ""

    def _inbox_from_issue(self, issue: dict[str, Any]) -> dict[str, Any]:
        key = str(issue.get("key") or "").strip()
        fields = issue.get("fields") or {}
        aliases = {
            "summary": "title",
            "start_date": "start",
            "end_date": "end",
            "change_lead": "lead",
            "nonprofit_dss": "nonprofit",
            "problem": "reason",
            "solution_goals": "solution",
            "risks_obstacles": "risks",
            "benefit_savings": "benefit",
            "responsible_sit": "it_owner",
            "concept_scs_pt": "effort_fb",
            "concept_cit_pt": "effort_it",
        }
        values: dict[str, str] = {}
        values["title"] = self._jira_field_text(fields.get("summary"))
        values["description"] = adf_to_text(fields.get("description"))
        from app.services.effort_sheet import JIRA_SHEET_KEYS

        for domain_key, meta in (self._field_map.get("fields") or {}).items():
            jira_id = str((meta or {}).get("jira") or "").strip()
            if not jira_id:
                continue
            present = jira_id in fields
            text = self._jira_field_text(fields.get(jira_id)) if present else ""
            if not text:
                # Leeres Aufwand-/Kostenfeld mitgeben, damit das Sheet es wieder füllt.
                if present and domain_key in JIRA_SHEET_KEYS:
                    values[domain_key] = ""
                    alias = aliases.get(domain_key)
                    if alias:
                        values[alias] = ""
                continue
            values[domain_key] = text
            alias = aliases.get(domain_key)
            if alias:
                values[alias] = text
        type_name = ""
        issuetype = fields.get("issuetype")
        if isinstance(issuetype, dict):
            type_name = str(issuetype.get("name") or "")
        elif issuetype:
            type_name = str(issuetype)
        prio_name = ""
        priority = fields.get("priority")
        if isinstance(priority, dict):
            prio_name = str(priority.get("name") or "")
        elif priority:
            prio_name = str(priority)
        status_name = ""
        status = fields.get("status")
        if isinstance(status, dict):
            status_name = str(status.get("name") or "")
        elif status:
            status_name = str(status)
        low = prio_name.lower()
        if low in {"highest", "critical", "blocker"}:
            prio = "critical"
        elif low in {"high"}:
            prio = "high"
        elif low in {"low", "lowest", "trivial"}:
            prio = "low"
        else:
            prio = "medium"
        kind = (
            "it_request"
            if "it request" in type_name.lower() or type_name.lower().startswith("it ")
            else "change_request"
        )
        assignee = self._jira_field_text(fields.get("assignee"))
        reporter = self._jira_field_text(fields.get("reporter"))
        if reporter:
            values["author"] = reporter
        return {
            "key": key,
            "title": values.get("title") or key,
            "status": status_name or "Offen",
            "priority": prio,
            "kind": kind,
            "createdAt": str(fields.get("created") or ""),
            "updatedAt": str(fields.get("updated") or ""),
            "url": self._browse_url(key, str(issue.get("self") or "")) if key else "",
            "assignee": assignee,
            "reporter": reporter,
            "values": values,
        }

    def list_issues(
        self,
        *,
        query: str = "",
        limit: int = 50,
        include_closed: bool = False,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> list[dict[str, Any]]:
        project = self._project_key()
        # Hub: keine abgeschlossenen/abgebrochenen Tickets (u. a. CRITR-Tests).
        # Auswertung: abgeschlossene und abgelehnte bleiben, nur Abbruch fällt weg.
        if include_closed:
            scope = "status not in (Canceled, Cancelled, Abgebrochen)"
        else:
            scope = (
                "statusCategory != Done AND status not in "
                "(Canceled, Cancelled, Abgebrochen, Closed, Done, Rejected, Abgelehnt)"
            )
        jql = f"project = {project} AND {scope} ORDER BY created DESC"
        needle = (query or "").replace('"', " ").strip()[:80]
        if needle:
            jql = (
                f"project = {project} AND {scope} AND ("
                f'text ~ "{needle}" OR assignee ~ "{needle}" OR reporter ~ "{needle}"'
                f") ORDER BY created DESC"
            )
        want = max(1, min(int(limit), 500))
        fields = ",".join(self._mapped_jira_ids())
        collected: list[dict[str, Any]] = []
        start = 0
        while len(collected) < want:
            page = min(100, want - len(collected))
            data = self._search_raw(
                jql,
                fields,
                page,
                start_at=start,
                user_token=user_token,
                user_email=user_email,
            )
            batch = data.get("issues") or []
            if not batch:
                break
            collected.extend(batch)
            if len(batch) < page:
                break
            start += len(batch)
        return [self._inbox_from_issue(row) for row in collected]

    def inbox_issue(
        self,
        key: str,
        *,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> dict[str, Any] | None:
        raw = self.get_issue(key, user_token=user_token, user_email=user_email)
        if not raw:
            return None
        if "fields" not in raw and raw.get("summary"):
            return raw
        return self._inbox_from_issue(raw)

    def search_similar(self, text: str, limit: int = 5) -> list[dict[str, str]]:
        needle = text.replace('"', " ").strip()[:80]
        if not needle:
            return []
        project = self._project_key()
        jql = f'project = {project} AND text ~ "{needle}" ORDER BY created DESC'
        data = self._search_raw(
            jql,
            "key,summary",
            limit,
        )
        issues = data.get("issues") or []
        return [
            {"key": i["key"], "summary": (i.get("fields") or {}).get("summary", "")}
            for i in issues
        ]

    def get_issue(
        self,
        key: str,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> dict[str, Any] | None:
        try:
            response = self._request(
                "GET",
                self._issue_path(f"/{key}"),
                params={"fields": ",".join(self._mapped_jira_ids())},
                user_token=user_token,
                user_email=user_email,
            )
        except TicketPortError:
            return None
        return _parse_json(response)
