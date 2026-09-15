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
from app.models import Comment, ExternalRef, Request, RequestAttachment, RequestField, User, utcnow
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
    low = (name or "").strip().lower()
    if any(token in low for token in ("done", "fertig", "geschlossen", "abgeschlossen")):
        return RequestStatus.DONE
    if any(token in low for token in ("reject", "ablehn")):
        return RequestStatus.REJECTED
    if any(token in low for token in ("progress", "umsetzung", "in arbeit")):
        return RequestStatus.IN_PROGRESS
    if "qg2" in low:
        return RequestStatus.QG2
    if "qg1" in low:
        return RequestStatus.QG1
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
                latest = max(comments, key=lambda c: c.created_at or datetime.min.replace(tzinfo=UTC))
                if latest.created_at:
                    latest_comment = latest.created_at.isoformat()
            atts = list(request.attachments or [])
            if atts:
                latest_a = max(atts, key=lambda a: a.created_at or datetime.min.replace(tzinfo=UTC))
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
                "updatedAt": item.get("updatedAt") or "",
                "activityAt": activity,
                "url": item.get("url") or "",
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
        existing = by_ext.get(eid)
        if existing:
            if existing.body != body or existing.author_name != author:
                existing.body = body
                existing.author_name = author
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
            if created and (not orphan.created_at or orphan.created_at > created):
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
        return sorted(matches, key=lambda a: a.created_at or utcnow(), reverse=True)[0]
    raise TicketPortError("Anhang wurde hochgeladen, konnte lokal aber nicht gespiegelt werden")


def sync_comments_batch(
    db: Session,
    port: TicketPort,
    *,
    keys: list[str] | None = None,
    limit: int = 25,
    user_token: str | None = None,
    user_email: str | None = None,
) -> dict[str, int]:
    """Kommentare für bekannte Jira-Keys nachziehen (Hub / Hintergrund)."""
    synced = 0
    updated = 0
    failed = 0
    targets: list[ExternalRef] = []
    if keys:
        clean = [k.strip() for k in keys if str(k or "").strip()][: max(1, min(limit, 50))]
        if clean:
            targets = list(
                db.scalars(
                    select(ExternalRef)
                    .options(
                        selectinload(ExternalRef.request).selectinload(Request.comments),
                        selectinload(ExternalRef.request).selectinload(Request.fields),
                        selectinload(ExternalRef.request).selectinload(Request.external_refs),
                        selectinload(ExternalRef.request).selectinload(Request.attachments),
                    )
                    .where(ExternalRef.external_key.in_(clean))
                ).all()
            )
    else:
        targets = list(
            db.scalars(
                select(ExternalRef)
                .options(
                    selectinload(ExternalRef.request).selectinload(Request.comments),
                    selectinload(ExternalRef.request).selectinload(Request.fields),
                    selectinload(ExternalRef.request).selectinload(Request.external_refs),
                    selectinload(ExternalRef.request).selectinload(Request.attachments),
                )
                .where(ExternalRef.external_key.is_not(None))
                .order_by(ExternalRef.synced_at.desc().nulls_last())
                .limit(max(1, min(limit, 50)))
            ).all()
        )
    for ref in targets:
        request = ref.request
        if not request or not ref.external_key:
            continue
        try:
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
            synced += 1
            if n or a:
                updated += 1
        except Exception:
            failed += 1
    return {"synced": synced, "updated": updated, "failed": failed}


def import_issue(
    db: Session,
    port: TicketPort,
    key: str,
    *,
    user: User | None = None,
    user_token: str | None = None,
    user_email: str | None = None,
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
    description = str(values.get("description") or "")
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
    ref.external_url = str(issue.get("url") or "") or ref.external_url
    ref.sync_state = SyncState.SYNCED
    ref.synced_at = utcnow()
    ref.last_error = None

    for field_key, raw in values.items():
        if field_key in SKIP_VALUES:
            continue
        text = str(raw or "").strip()
        if not text:
            continue
        _upsert_field(request, field_key, text)
    db.flush()
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
    return request


def import_issue_view(
    db: Session,
    port: TicketPort,
    key: str,
    *,
    user: User | None = None,
    user_token: str | None = None,
    user_email: str | None = None,
) -> dict:
    request = import_issue(
        db,
        port,
        key,
        user=user,
        user_token=user_token,
        user_email=user_email,
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
