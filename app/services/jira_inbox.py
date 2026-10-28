"""Jira → eigene Request-Spiegelung für den Workspace-Hub."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domain.types import (
    PRIORITY_LABELS,
    Priority,
    RequestKind,
    RequestStatus,
    SyncState,
    parse_kind,
    parse_priority,
)
from app.models import (
    Comment,
    ExternalRef,
    Request,
    RequestAttachment,
    RequestField,
    User,
    created_at_utc,
    utcnow,
)
from app.ports.jira_v3 import public_browse_url
from app.ports.ticket_port import TicketPort, TicketPortError
from app.services.requests_service import hub_next_step, to_detail

FIELD_LABELS = {
    "title": "Titel",
    "start": "Start",
    "end": "Ende",
    "sponsor": "Auftraggeber",
    "components": "Stichwörter / Tags",
    "nonprofit": "Ist das Projekt gemeinnützig",
    "description": "Beschreibung",
    "approver": "Genehmigende Person",
    "lead": "Gesamtprojektleitung",
    "change_team": "Change-Team",
    "stakeholder": "Stakeholder",
    "process_owner": "Process Owner",
    "solution_owner": "Solution Owner",
    "it_owner": "Ist die verantwortliche Person aus der IT",
    "author": "Autor",
    "benefit": "Nutzen",
    "reason": "Begründung",
    "solution": "Lösungen/Maßnahme",
    "risks": "Bekannte Risiken",
    "effort_fb": "Aufwand FB",
    "effort_it": "Aufwand IT",
    "costs": "Kosten",
    "it_costs": "IT Cost (one time - in €)",
    "cost_savings": "Kostenersparnis",
    "priority": "Priorität",
}

SKIP_VALUES = {"title", "description", "priority", "kind"}


def _status_from_jira(name: str) -> RequestStatus:
    """Jira-Status → CRITR-Workflow. Unbekannte Werte fallen auf Steckbrief."""
    low = (name or "").strip().lower()
    if any(token in low for token in ("done", "fertig", "geschlossen", "abgeschlossen")):
        return RequestStatus.DONE
    if any(token in low for token in ("reject", "ablehn")):
        return RequestStatus.REJECTED
    # „In Progess“ (Tippfehler in Jira) mit abfangen
    if any(
        token in low
        for token in ("progress", "progess", "umsetzung", "in arbeit", "in progress")
    ):
        return RequestStatus.IN_PROGRESS
    if "qg2" in low or "quality gate 2" in low:
        return RequestStatus.QG2
    if "qg1" in low or "quality gate" in low:
        return RequestStatus.QG1
    if any(
        token in low
        for token in (
            "final version",
            "freigegeben",
            "approved",
            "conception finalized",
            "konzeption final",
        )
    ):
        return RequestStatus.APPROVED
    if any(
        token in low
        for token in ("approval", "freigabe", "review", "abstimmung", "approval required")
    ):
        return RequestStatus.IT_REVIEW
    return RequestStatus.STECKBRIEF


def _find_ref(db: Session, system: str, key: str) -> ExternalRef | None:
    return db.scalar(
        select(ExternalRef)
        .options(selectinload(ExternalRef.request).selectinload(Request.fields))
        .where(ExternalRef.system == system, ExternalRef.external_key == key)
    )


def _upsert_field(request: Request, key: str, value: str) -> None:
    label = FIELD_LABELS.get(key, key)
    existing = next((f for f in request.fields if f.key == key), None)
    if existing:
        existing.value = value
        return
    request.fields.append(
        RequestField(
            request_id=request.id,
            key=key,
            label=label,
            value=value,
            position=len(request.fields),
        )
    )


def list_inbox(
    db: Session,
    port: TicketPort,
    *,
    query: str = "",
    limit: int = 50,
    user_token: str | None = None,
    user_email: str | None = None,
    actor: User | None = None,
) -> dict:
    issues = port.list_issues(
        query=query, limit=limit, user_token=user_token, user_email=user_email
    )
    keys = [str(item.get("key") or "") for item in issues if item.get("key")]
    refs = []
    if keys:
        refs = db.scalars(
            select(ExternalRef)
            .options(
                selectinload(ExternalRef.request).selectinload(Request.fields),
                selectinload(ExternalRef.request).selectinload(Request.comments),
                selectinload(ExternalRef.request).selectinload(Request.status_updates),
                selectinload(ExternalRef.request).selectinload(Request.author),
                selectinload(ExternalRef.request).selectinload(Request.attachments),
            )
            .where(ExternalRef.external_key.in_(keys))
        ).all()
    by_key = {ref.external_key: ref for ref in refs if ref.external_key}
    items = []
    for item in issues:
        key = str(item.get("key") or "")
        ref = by_key.get(key)
        request = ref.request if ref else None
        prio = parse_priority(item.get("priority")) or Priority.MEDIUM
        values = request.field_values() if request else {}
        from app.services.stand_summary import stand_trust

        trust = {}
        if request:
            trust = stand_trust(values)
            stand = trust.get("summary") or ""
        else:
            stand = ""
        activity = str(item.get("updatedAt") or "")
        latest_comment = ""
        latest_attach = ""
        if request:
            comments = list(request.comments or [])
            if comments:
                latest = max(comments, key=created_at_utc)
                if latest.created_at:
                    latest_comment = latest.created_at.isoformat()
            atts = list(request.attachments or [])
            if atts:
                latest_a = max(atts, key=created_at_utc)
                if latest_a.created_at:
                    latest_attach = latest_a.created_at.isoformat()
        for cand in (activity, latest_comment, latest_attach):
            if cand and cand > activity:
                activity = cand
        authors: list[str] = []
        for name in (
            item.get("assignee"),
            item.get("reporter"),
            (request.change_lead if request else None),
            (request.author.display_name if request and request.author else None),
            values.get("lead"),
            values.get("change_lead"),
            values.get("sponsor"),
            values.get("it_owner"),
            values.get("responsible_sit"),
        ):
            text = str(name or "").strip()
            if text and text.lower() not in {a.lower() for a in authors}:
                authors.append(text)
        if request:
            for c in request.comments or []:
                text = str(c.author_name or "").strip()
                if (
                    text
                    and text.lower() != "system"
                    and text.lower() not in {a.lower() for a in authors}
                ):
                    authors.append(text)
        next_info = hub_next_step(request, actor)
        health = {"key": "green", "label": "Im Plan"}
        if request:
            from app.services.stand_summary import stand_health as stand_health_view

            health = stand_health_view(request)
        local_status = str(request.status) if request else ""
        items.append(
            {
                "key": key,
                "title": item.get("title") or key,
                "status": item.get("status") or "Offen",
                "priority": prio.value,
                "priorityLabel": PRIORITY_LABELS[prio],
                "kind": item.get("kind") or "change_request",
                "createdAt": item.get("createdAt") or "",
                "updatedAt": item.get("updatedAt") or "",
                "activityAt": activity,
                "url": public_browse_url(item.get("url"), key) or "",
                "requestId": request.id if request else None,
                "reference": request.reference if request else key,
                "statusSummary": stand,
                "standSource": trust.get("source") or "",
                "standSourceLabel": trust.get("sourceLabel") or "",
                "standHealth": health,
                "localStatus": local_status,
                "completed": local_status == "abgeschlossen"
                or str(health.get("key") or "") == "done",
                "commentCount": len(request.comments or []) if request else 0,
                "attachmentCount": len(request.attachments or []) if request else 0,
                "assignee": str(item.get("assignee") or "").strip(),
                "changeLead": str(request.change_lead or "").strip() if request else "",
                "createdBy": (
                    request.author.display_name if request and request.author else ""
                ),
                "reporter": str(item.get("reporter") or "").strip(),
                "authors": authors,
                "authorsText": " · ".join(authors),
                "waitingOnMe": bool(next_info.get("waitingOnMe")),
                "waitingTodo": str(next_info.get("waitingTodo") or ""),
                "nextStep": str(next_info.get("nextStep") or ""),
            }
        )
    return {"items": items, "total": len(items)}


_PREFIX_BODY = re.compile(r"^([^:\n]{1,80}):\s+([\s\S]+)$")


def _as_utc(dt: datetime | None) -> datetime | None:
    """Immer UTC. Naive Werte sind bereits UTC (so schreibt die App)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _parse_jira_created(raw: str) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    # Jira: 2024-01-15T10:30:00.000+0000
    if re.search(r"[+-]\d{4}$", text):
        text = text[:-5] + text[-5:-2] + ":" + text[-2:]
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _normalize_remote_comment(item: dict) -> tuple[str, str, datetime | None]:
    plain = str(item.get("body") or "").strip()
    jira_author = str(item.get("author") or "").strip() or "Jira"
    created = _parse_jira_created(str(item.get("created") or ""))
    match = _PREFIX_BODY.match(plain)
    if match:
        # CRITR schreibt nach Jira als „Autor: Text“
        return match.group(2).strip(), match.group(1).strip() or jira_author, created
    return plain, jira_author, created


def sync_comments_from_jira(
    db: Session,
    port: TicketPort,
    request: Request,
    *,
    user_token: str | None = None,
    user_email: str | None = None,
    summarize: bool = False,
) -> int:
    """Jira-Kommentare → lokale comments (per external_id)."""
    ref = next((r for r in (request.external_refs or []) if r.external_key), None)
    key = str(ref.external_key if ref else "").strip()
    if not key:
        return 0
    try:
        remote = port.list_comments(key, user_token=user_token, user_email=user_email)
    except TicketPortError:
        return 0
    except Exception:
        return 0

    by_ext = {
        str(c.external_id): c
        for c in (request.comments or [])
        if str(c.external_id or "").strip()
    }
    remote_ids: set[str] = set()
    changed = 0

    for item in remote:
        eid = str(item.get("id") or "").strip()
        if not eid:
            continue
        body, author, created = _normalize_remote_comment(item)
        if not body:
            continue
        remote_ids.add(eid)
        created = _as_utc(created)
        existing = by_ext.get(eid)
        if existing:
            if existing.body != body or existing.author_name != author:
                existing.body = body
                existing.author_name = author
                changed += 1
            if created and _as_utc(existing.created_at) != created:
                existing.created_at = created
                changed += 1
            continue
        plain = str(item.get("body") or "").strip()
        body_norm = " ".join(body.split())
        orphan = next(
            (
                c
                for c in (request.comments or [])
                if not str(c.external_id or "").strip()
                and (
                    " ".join(str(c.body or "").split()) == body_norm
                    or " ".join(f"{c.author_name}: {c.body}".split())
                    == " ".join(plain.split())
                )
            ),
            None,
        )
        if orphan:
            orphan.external_id = eid
            if created and (
                not orphan.created_at or _as_utc(orphan.created_at) > created
            ):
                orphan.created_at = created
            changed += 1
            by_ext[eid] = orphan
            continue
        comment = Comment(
            request_id=request.id,
            author_id=None,
            author_name=author[:120],
            body=body,
            external_id=eid,
            created_at=created or utcnow(),
        )
        db.add(comment)
        if request.comments is not None:
            request.comments.append(comment)
        by_ext[eid] = comment
        changed += 1

    for comment in list(request.comments or []):
        eid = str(comment.external_id or "").strip()
        if eid and eid not in remote_ids:
            db.delete(comment)
            changed += 1

    db.flush()
    if summarize:
        try:
            from app.services.comment_summary import summarize_comments

            # Digest-Cache: LLM nur bei geänderten Kommentaren
            summarize_comments(db, request)
        except Exception:
            pass
    return changed


def sync_attachments_from_jira(
    db: Session,
    port: TicketPort,
    request: Request,
    *,
    user_token: str | None = None,
    user_email: str | None = None,
) -> int:
    """Jira-Anhänge → lokale Metadaten (per external_id)."""
    ref = next((r for r in (request.external_refs or []) if r.external_key), None)
    key = str(ref.external_key if ref else "").strip()
    if not key:
        return 0
    try:
        remote = port.list_attachments(key, user_token=user_token, user_email=user_email)
    except TicketPortError:
        return 0
    except Exception:
        return 0

    by_ext = {
        str(a.external_id): a
        for a in (request.attachments or [])
        if str(a.external_id or "").strip()
    }
    remote_ids: set[str] = set()
    changed = 0

    for item in remote:
        eid = str(item.get("id") or "").strip()
        if not eid:
            continue
        remote_ids.add(eid)
        filename = str(item.get("filename") or "anhang").strip()[:255] or "anhang"
        mime = str(item.get("mimeType") or "").strip()[:120]
        size = int(item.get("size") or 0)
        author = str(item.get("author") or "").strip()[:120]
        created = _parse_jira_created(str(item.get("created") or "")) or utcnow()
        existing = by_ext.get(eid)
        if existing:
            dirty = False
            if existing.filename != filename:
                existing.filename = filename
                dirty = True
            if existing.content_type != mime:
                existing.content_type = mime
                dirty = True
            if existing.size_bytes != size:
                existing.size_bytes = size
                dirty = True
            if author and existing.author_name != author:
                existing.author_name = author
                dirty = True
            if dirty:
                changed += 1
            continue
        row = RequestAttachment(
            request_id=request.id,
            external_id=eid,
            filename=filename,
            content_type=mime,
            size_bytes=size,
            author_name=author or "Jira",
            created_at=created,
        )
        db.add(row)
        if request.attachments is not None:
            request.attachments.append(row)
        by_ext[eid] = row
        changed += 1

    for att in list(request.attachments or []):
        eid = str(att.external_id or "").strip()
        if eid and eid not in remote_ids:
            db.delete(att)
            changed += 1

    if changed:
        db.flush()
    return changed


def upload_attachment(
    db: Session,
    port: TicketPort,
    request: Request,
    *,
    filename: str,
    content: bytes,
    content_type: str = "application/octet-stream",
    user: User | None = None,
) -> RequestAttachment:
    """Datei nach Jira hochladen und lokal als Metadaten spiegeln."""
    ref = next((r for r in (request.external_refs or []) if r.external_key), None)
    key = str(ref.external_key if ref else "").strip()
    if not key:
        raise TicketPortError("Ticket hat noch keinen Jira-Key")
    name = " ".join(str(filename or "anhang").split()).strip()[:255] or "anhang"
    data = content or b""
    if not data:
        raise TicketPortError("Leere Datei")
    if len(data) > 20 * 1024 * 1024:
        raise TicketPortError("Datei zu groß (max. 20 MB)")

    from app.api.jira_lookup import _user_jira_credentials

    token, email = _user_jira_credentials(db, user) if user else (None, None)
    created = port.add_attachment(
        key,
        name,
        data,
        content_type or "application/octet-stream",
        user_token=token,
        user_email=email,
        replace_same_name=True,
        strip_kalk=False,
    )
    sync_attachments_from_jira(
        db, port, request, user_token=token, user_email=email
    )
    db.refresh(request, attribute_names=["attachments"])

    by_ext = {
        str(a.external_id): a
        for a in (request.attachments or [])
        if str(a.external_id or "").strip()
    }
    for item in created or []:
        eid = str(item.get("id") or "").strip()
        row = by_ext.get(eid)
        if row:
            return row

    # Fallback: neueste Datei mit gleichem Namen
    matches = [
        a
        for a in (request.attachments or [])
        if str(a.filename or "").strip().lower() == name.lower()
    ]
    if matches:
        return sorted(matches, key=created_at_utc, reverse=True)[0]
    raise TicketPortError("Anhang wurde hochgeladen, konnte lokal aber nicht gespiegelt werden")


def refresh_stand_after_sync(db: Session, request: Request, *, changed: bool, llm: bool) -> bool:
    """Stand-Feld nach Jira-Sync anlegen bzw. aktualisieren — auch ohne Kommentare."""
    from app.services.stand_summary import BRIEF_KEY, LINE_KEY, refresh_stand

    values = request.field_values()
    missing = not (values.get(LINE_KEY) or "").strip() or not (values.get(BRIEF_KEY) or "").strip()
    if not changed and not missing:
        return False
    try:
        refresh_stand(db, request, llm=llm)
        return True
    except Exception:
        return False



def _push_sheet_over_jira(db: Session, request: Request, drift: dict[str, str]) -> None:
    """Abweichende Aufwand-/Kostenfelder in Jira durch das Sheet ersetzen."""
    if not drift:
        return
    if not any(str(ref.external_key or "").strip() for ref in request.external_refs):
        return
    from sqlalchemy.orm.attributes import flag_modified

    from app.domain.types import OutboxOperation, SyncState
    from app.models import OutboxJob
    from app.services.effort_sheet import amounts_match
    from app.sync.outbox import enqueue

    pending = [
        obj
        for obj in db.new
        if isinstance(obj, OutboxJob)
        and obj.request_id == request.id
        and obj.operation == OutboxOperation.UPDATE_FIELDS
        and obj.state == SyncState.PENDING
    ]
    pending.extend(
        db.scalars(
            select(OutboxJob).where(
                OutboxJob.request_id == request.id,
                OutboxJob.operation == OutboxOperation.UPDATE_FIELDS,
                OutboxJob.state == SyncState.PENDING,
            )
        ).all()
    )
    for job in pending:
        fields = dict((job.payload or {}).get("fields") or {})
        if all(amounts_match(fields.get(key), value) for key, value in drift.items()):
            return
    for job in pending:
        payload = dict(job.payload or {})
        fields = dict(payload.get("fields") or {})
        fields.update(drift)
        payload["fields"] = fields
        job.payload = payload
        flag_modified(job, "payload")
        return
    enqueue(
        db,
        request.id,
        OutboxOperation.UPDATE_FIELDS,
        {"fields": dict(drift), "priority": str(request.priority)},
    )


def apply_effort_share_to_request(
    db: Session,
    request: Request,
    jira_values: dict | None = None,
    *,
    push_jira: bool = True,
) -> bool:
    """Lokales Aufwand-Sheet übernehmen. Weicht Jira ab, wird das Sheet zurückgeschrieben."""
    from app.services.effort_sheet import (
        EFFORT_SYNC_KEYS,
        effort_sync_fields,
        load_share_csv,
        parse_effort_csv,
        share_id_from_url,
        sheet_drift,
    )

    values = request.field_values()
    url = str(values.get("effort_sheet_url") or "").strip()
    if not url:
        return False
    sid = share_id_from_url(url)
    if not sid:
        return False
    csv_text = load_share_csv(db, sid)
    if not csv_text:
        return False
    parsed = effort_sync_fields(parse_effort_csv(csv_text))
    # URL behalten (öffentliche Adresse aus dem Ticket)
    parsed["effort_sheet_url"] = url
    changed = False
    current = request.field_values()
    # effort_it/effort_fb mitziehen, sonst bleibt „Aufwand IT“ lokal stehen.
    aliases = {"concept_scs_pt": "effort_fb", "concept_cit_pt": "effort_it"}
    for key in EFFORT_SYNC_KEYS:
        text = str(parsed.get(key) or "").strip()
        if str(current.get(key) or "").strip() == text:
            continue
        # Leer = Feld leeren (nicht überspringen — sonst bleiben alte PT/Kosten).
        _upsert_field(request, key, text)
        alias = aliases.get(key)
        if alias:
            _upsert_field(request, alias, text)
        changed = True
    drift = sheet_drift(jira_values, parsed)
    if drift and push_jira:
        _push_sheet_over_jira(db, request, drift)
    return changed


def find_request_by_effort_share(db: Session, share_id: str) -> Request | None:
    from app.models import RequestField

    sid = str(share_id or "").strip()
    if not sid:
        return None
    needle = f"/aufwand/{sid}"
    field = db.scalar(
        select(RequestField)
        .where(
            RequestField.key == "effort_sheet_url",
            RequestField.value.ilike(f"%{needle}%"),
        )
        .limit(1)
    )
    if not field:
        return None
    return db.scalar(
        select(Request)
        .options(
            selectinload(Request.fields),
            selectinload(Request.external_refs),
            selectinload(Request.comments),
            selectinload(Request.attachments),
            selectinload(Request.status_updates),
        )
        .where(Request.id == field.request_id)
    )


def _canonical_jira_description(text: str) -> str:
    """Vergleichbar machen: Wiki-[Label|url] und „Label: url“ sowie Whitespace vereinheitlichen."""
    out: list[str] = []
    for line in str(text or "").splitlines():
        raw = line.strip().replace("\xa0", " ")
        if not raw:
            continue
        wiki = re.match(r"^\[([^\]|]+)\|(https?://[^\]\s]+)\]\s*$", raw)
        if wiki:
            label = re.sub(r"^CRITR\s+", "", wiki.group(1).strip(), flags=re.I)
            out.append(f"CRITR {label}: {wiki.group(2).rstrip(').,;')}")
            continue
        plain = re.match(
            r"^((?:CRITR\s+)?(?:Ticket|Status update|Aufwand\s*Sheet))\s*:\s*(https?://\S+)\s*$",
            raw,
            re.I,
        )
        if plain:
            label = re.sub(r"^CRITR\s+", "", plain.group(1).strip(), flags=re.I)
            out.append(f"CRITR {label}: {plain.group(2).rstrip(').,;')}")
            continue
        out.append(re.sub(r"\s+", " ", raw))
    return "\n".join(out).strip()


def _descriptions_equivalent(a: str, b: str) -> bool:
    """True, wenn Inhalt inkl. CRITR-Links gleich ist (Wiki- und Plain-Form zählen gleich)."""
    from app.ports.jira_v3 import _wiki_description

    ca = _canonical_jira_description(a)
    cb = _canonical_jira_description(b)
    if ca == cb:
        return True
    # Einmal Wiki-gerendert vergleichen (so landet es in Jira API2).
    return (
        _canonical_jira_description(_wiki_description(a)) == cb
        or ca == _canonical_jira_description(_wiki_description(b))
        or _canonical_jira_description(_wiki_description(a))
        == _canonical_jira_description(_wiki_description(b))
    )


_JIRA_DESC_FP = "jira_description_fp"
# Harte Bremse: max. so viele Beschreibungs-Updates in dieses Fenster — sonst keine Mails mehr.
_DESC_PUSH_WINDOW_MINUTES = 10
_DESC_PUSH_MAX_PER_WINDOW = 5


def _description_fingerprint(text: str) -> str:
    import hashlib

    return hashlib.sha256(_canonical_jira_description(text).encode("utf-8")).hexdigest()[:32]


def _critr_links_incomplete(request: Request) -> bool:
    """True, wenn Ticket-/Status-/Aufwand-Link mit der aktuellen Request-ID fehlen."""
    rid = str(request.id or "").strip()
    blob = str(request.description or "")
    if not rid:
        return True
    has_ticket = f"/workspace/{rid}" in blob
    has_status = f"/status-update/{rid}" in blob
    has_effort = "/aufwand/" in blob or "docs.google.com/spreadsheets" in blob.lower()
    return not (has_ticket and has_status and has_effort)


def _description_push_budget_ok(db: Session) -> bool:
    """Verhindert Massen-Updates (Mail-Flut): max. N Beschreibungs-Jobs im Zeitfenster."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import text

    since = datetime.now(UTC) - timedelta(minutes=_DESC_PUSH_WINDOW_MINUTES)
    # payload::text enthält bei UPDATE_FIELDS typischerweise "description"
    n = db.execute(
        text(
            """
            SELECT count(*) FROM sync_outbox
            WHERE operation = 'update_fields'
              AND created_at >= :since
              AND (
                state IN ('pending', 'synced', 'failed')
              )
              AND coalesce(payload::text, '') ILIKE '%description%'
            """
        ),
        {"since": since},
    ).scalar()
    return int(n or 0) < _DESC_PUSH_MAX_PER_WINDOW


def _apply_critr_description(
    db: Session,
    request: Request,
    *,
    force: bool = False,
) -> None:
    """Lokale Beschreibung = Freitext + drei CRITR-Links; Sync nach Jira nur bei echter Änderung."""
    import logging
    import os

    log = logging.getLogger("triage.sync")

    # Not-Stop: keine Jira-Feld-Updates (Mails), bis CRITR_PAUSE_JIRA_PUSH wieder aus ist.
    if os.environ.get("CRITR_PAUSE_JIRA_PUSH", "").strip().lower() in {"1", "true", "yes", "on"}:
        return
    from app.domain.types import OutboxOperation, Priority
    from app.services.requests_service import _jira_field_map_meta, _render_description_for_jira
    from app.sync.outbox import enqueue

    meta = (_jira_field_map_meta().get("fields") or {})
    previous = str(request.description or "").strip()
    prose = previous
    cleaned = "\n".join(
        line
        for line in prose.splitlines()
        if not re.match(
            r"^(?:CRITR\s+)?(?:Ticket|Status update|Aufwand\s*Sheet)\s*:",
            line.strip(),
            re.I,
        )
        and not re.match(r"^\[CRITR\s+", line.strip(), re.I)
        and "/workspace/" not in line
        and "/status-update/" not in line
        and "/aufwand/" not in line
    ).strip()
    if cleaned:
        _upsert_field(request, "description", cleaned)
        request.description = cleaned
    desc = _render_description_for_jira(request, meta, db=db)
    effort = str(request.field_values().get("effort_sheet_url") or "").strip()
    fp = _description_fingerprint(desc)
    stored_fp = str(request.field_values().get(_JIRA_DESC_FP) or "").strip()
    # Gleicher Inhalt wie zuletzt geschrieben / wie in Jira → kein Update, keine Mail.
    if not force and (stored_fp == fp or _descriptions_equivalent(desc, previous)):
        request.description = desc
        if stored_fp != fp:
            _upsert_field(request, _JIRA_DESC_FP, fp)
        return
    if not _description_push_budget_ok(db):
        # Nicht lokal „fertig“ machen — sonst greift der Incomplete-Check nicht mehr.
        # Nächster Sync versucht erneut, sobald Budget frei ist.
        log.warning(
            "description-push budget exhausted (max %s / %s min) — skip Jira update for %s",
            _DESC_PUSH_MAX_PER_WINDOW,
            _DESC_PUSH_WINDOW_MINUTES,
            request.id,
        )
        request.description = previous
        return
    fields = {"description": desc}
    if effort:
        fields["effort_sheet_url"] = effort
    request.description = desc
    _upsert_field(request, _JIRA_DESC_FP, fp)
    enqueue(
        db,
        request.id,
        OutboxOperation.UPDATE_FIELDS,
        {"fields": fields, "priority": Priority(request.priority).value},
    )


def mirror_jira_issue(
    db: Session,
    port: TicketPort,
    key: str,
    *,
    user: User | None = None,
    user_token: str | None = None,
    user_email: str | None = None,
    summarize: bool = False,
) -> dict[str, object]:
    """Ein Jira-Ticket nach CRITR spiegeln (neu anlegen oder aktualisieren)."""
    existed = _find_ref(db, port.system, key.strip()) is not None
    request = import_issue(
        db,
        port,
        key.strip(),
        user=user,
        user_token=user_token,
        user_email=user_email,
        defer_enrich=True,
    )
    db.refresh(request, attribute_names=["fields", "external_refs", "comments", "attachments"])
    effort_hit = apply_effort_share_to_request(db, request)
    n = sync_comments_from_jira(
        db,
        port,
        request,
        user_token=user_token,
        user_email=user_email,
        summarize=False,
    )
    a = sync_attachments_from_jira(
        db, port, request, user_token=user_token, user_email=user_email
    )
    # Beschreibung nach Jira nur bei Neuanlage oder fehlenden CRITR-Links —
    # nicht bei jedem Kommentar-Sync (sonst Mail-Flut).
    if (not existed) or _critr_links_incomplete(request):
        _apply_critr_description(db, request)
    stand = 1 if refresh_stand_after_sync(
        db, request, changed=bool(n or a or effort_hit or not existed), llm=summarize
    ) else 0
    return {
        "key": key.strip(),
        "requestId": request.id,
        "created": not existed,
        "updated": bool(n or a or effort_hit or existed),
        "stand": stand,
    }


def pull_new_jira_issues(
    db: Session,
    port: TicketPort,
    *,
    limit: int = 30,
    user_token: str | None = None,
    user_email: str | None = None,
) -> dict[str, int]:
    """Neue Jira-Tickets ohne CRITR-Spiegelung importieren."""
    created = 0
    updated = 0
    failed = 0
    try:
        issues = port.list_issues(
            query="", limit=max(1, min(limit, 50)), user_token=user_token, user_email=user_email
        )
    except TicketPortError:
        return {"created": 0, "updated": 0, "failed": 1}
    keys = [str(item.get("key") or "").strip() for item in issues if item.get("key")]
    if not keys:
        return {"created": 0, "updated": 0, "failed": 0}
    known = {
        ref.external_key
        for ref in db.scalars(
            select(ExternalRef).where(ExternalRef.external_key.in_(keys))
        ).all()
        if ref.external_key
    }
    for key in keys:
        if key in known:
            continue
        try:
            stats = mirror_jira_issue(
                db,
                port,
                key,
                user_token=user_token,
                user_email=user_email,
                summarize=False,
            )
            if stats.get("created"):
                created += 1
            else:
                updated += 1
            known.add(key)
        except Exception:
            failed += 1
    return {"created": created, "updated": updated, "failed": failed}


def sync_comments_batch(
    db: Session,
    port: TicketPort,
    *,
    keys: list[str] | None = None,
    limit: int = 25,
    user_token: str | None = None,
    user_email: str | None = None,
    summarize: bool = False,
) -> dict[str, int]:
    """Jira → CRITR: bekannte Keys spiegeln; unbekannte Keys neu anlegen."""
    synced = 0
    updated = 0
    failed = 0
    stand = 0
    created = 0
    clean = [k.strip() for k in (keys or []) if str(k or "").strip()][: max(1, min(limit, 50))]

    if clean:
        # Explizite Keys: auch ohne ExternalRef importieren (Webhook Create).
        for key in clean:
            try:
                stats = mirror_jira_issue(
                    db,
                    port,
                    key,
                    user_token=user_token,
                    user_email=user_email,
                    summarize=summarize,
                )
                synced += 1
                if stats.get("created"):
                    created += 1
                if stats.get("updated"):
                    updated += 1
                stand += int(stats.get("stand") or 0)
            except Exception:
                failed += 1
        return {
            "synced": synced,
            "updated": updated,
            "failed": failed,
            "stand": stand,
            "created": created,
        }

    targets = list(
        db.scalars(
            select(ExternalRef)
            .options(
                selectinload(ExternalRef.request).selectinload(Request.comments),
                selectinload(ExternalRef.request).selectinload(Request.fields),
                selectinload(ExternalRef.request).selectinload(Request.external_refs),
                selectinload(ExternalRef.request).selectinload(Request.attachments),
                selectinload(ExternalRef.request).selectinload(Request.status_updates),
            )
            .where(ExternalRef.external_key.is_not(None))
            .order_by(ExternalRef.synced_at.desc().nulls_last())
            .limit(max(1, min(limit, 50)))
        ).all()
    )
    for ref in targets:
        if not ref.request or not ref.external_key:
            continue
        try:
            stats = mirror_jira_issue(
                db,
                port,
                ref.external_key,
                user_token=user_token,
                user_email=user_email,
                summarize=summarize,
            )
            synced += 1
            if stats.get("updated"):
                updated += 1
            stand += int(stats.get("stand") or 0)
        except Exception:
            failed += 1
    return {
        "synced": synced,
        "updated": updated,
        "failed": failed,
        "stand": stand,
        "created": created,
    }


def import_issue(
    db: Session,
    port: TicketPort,
    key: str,
    *,
    user: User | None = None,
    user_token: str | None = None,
    user_email: str | None = None,
    defer_enrich: bool = False,
) -> Request:
    issue = port.inbox_issue(
        key.strip(), user_token=user_token, user_email=user_email
    )
    if not issue or not issue.get("key"):
        raise LookupError("Jira-Ticket nicht gefunden")
    jira_key = str(issue["key"])
    values = dict(issue.get("values") or {})
    reporter = str(issue.get("reporter") or "").strip()
    # Autor = Jira-Reporter (überschreibt lokale Fehlzuordnungen)
    if reporter:
        values["author"] = reporter
    title = (values.get("title") or issue.get("title") or jira_key).strip()[:200]
    from app.ports.ticket_port import clean_description_lead

    description = clean_description_lead(str(values.get("description") or ""))
    kind = parse_kind(issue.get("kind")) or RequestKind.CHANGE_REQUEST
    priority = parse_priority(issue.get("priority") or values.get("priority")) or Priority.MEDIUM
    status = _status_from_jira(str(issue.get("status") or ""))

    ref = _find_ref(db, port.system, jira_key)
    now = datetime.now(UTC)
    if ref and ref.request:
        request = ref.request
        request.title = title
        request.steckbrief_name = title
        request.description = description
        request.kind = kind
        request.priority = priority
        request.status = status
        request.company = values.get("company") or request.company
        request.change_lead = values.get("lead") or request.change_lead
        request.updated_at = now
    else:
        request = Request(
            reference=jira_key[:24],
            kind=kind,
            status=status,
            priority=priority,
            title=title,
            steckbrief_name=title,
            description=description,
            company=values.get("company") or None,
            change_lead=values.get("lead") or None,
            created_by=user.id if user else None,
        )
        db.add(request)
        db.flush()
        ref = ExternalRef(request_id=request.id, system=port.system)
        db.add(ref)
        request.external_refs.append(ref)

    ref.external_key = jira_key
    ref.external_url = (
        public_browse_url(issue.get("url"), jira_key) or ref.external_url
    )
    ref.sync_state = SyncState.SYNCED
    ref.synced_at = utcnow()
    ref.last_error = None

    from app.services.effort_sheet import JIRA_SHEET_KEYS, share_id_from_url

    known_sheet = str(values.get("effort_sheet_url") or "").strip()
    if not known_sheet:
        known_sheet = str(request.field_values().get("effort_sheet_url") or "").strip()
    sheet_blob = f"{known_sheet}\n{description}\n{values.get('description') or ''}"
    sheet_owns = share_id_from_url(sheet_blob) is not None
    locked_from_jira = set(JIRA_SHEET_KEYS) | {"effort_fb", "effort_it"}
    for field_key, raw in values.items():
        if field_key in SKIP_VALUES:
            continue
        if sheet_owns and field_key in locked_from_jira:
            continue
        text = str(raw or "").strip()
        if not text:
            continue
        _upsert_field(request, field_key, text)
    # Aufwand-Link aus Beschreibung, falls Feld leer
    from app.services.effort_sheet import ensure_effort_share, share_id_from_url

    sheet_url = str(values.get("effort_sheet_url") or "").strip()
    if not sheet_url:
        blob = f"{description}\n{str(values.get('description') or '')}"
        match = re.search(r"/aufwand/([0-9a-fA-F-]{36})", blob)
        if match:
            from app.config import get_settings

            base = (get_settings().public_base_url or "https://scscm.stackit.gg").rstrip("/")
            if "127.0.0.1" in base or "localhost" in base:
                base = "https://scscm.stackit.gg"
            sheet_url = f"{base}/aufwand/{match.group(1)}"
            _upsert_field(request, "effort_sheet_url", sheet_url)
    sid = share_id_from_url(sheet_url) if sheet_url else None
    if sid:
        ensure_effort_share(db, sid)
    db.flush()
    apply_effort_share_to_request(
        db, request, jira_values=values if sheet_owns else None, push_jira=False
    )
    if defer_enrich:
        # Schnelles Öffnen: Felder sofort, Kommentare/Anhänge im Hintergrund.
        return request
    # Kommentare nachladen, damit relationship aktuell ist
    db.refresh(request, attribute_names=["comments", "external_refs"])
    sync_comments_from_jira(
        db, port, request, user_token=user_token, user_email=user_email
    )
    try:
        db.refresh(request, attribute_names=["attachments"])
    except Exception:
        pass
    sync_attachments_from_jira(
        db, port, request, user_token=user_token, user_email=user_email
    )
    # Stand sofort ohne LLM setzen, damit das Feld direkt nach dem Import steht.
    refresh_stand_after_sync(db, request, changed=True, llm=False)
    return request


def import_issue_view(
    db: Session,
    port: TicketPort,
    key: str,
    *,
    user: User | None = None,
    user_token: str | None = None,
    user_email: str | None = None,
    defer_enrich: bool = False,
) -> dict:
    request = import_issue(
        db,
        port,
        key,
        user=user,
        user_token=user_token,
        user_email=user_email,
        defer_enrich=defer_enrich,
    )
    db.refresh(request)
    loaded = db.scalar(
        select(Request)
        .options(
            selectinload(Request.fields),
            selectinload(Request.comments),
            selectinload(Request.attachments),
            selectinload(Request.external_refs),
            selectinload(Request.status_updates),
            selectinload(Request.author),
        )
        .where(Request.id == request.id)
    )
    return to_detail(loaded or request, actor=user)
