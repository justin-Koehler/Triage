"""Jira → eigene Request-Spiegelung für den Workspace-Hub."""

from __future__ import annotations

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
from app.models import ExternalRef, Request, RequestField, User, utcnow
from app.ports.ticket_port import TicketPort
from app.services.requests_service import to_detail

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
) -> dict:
    issues = port.list_issues(
        query=query, limit=limit, user_token=user_token, user_email=user_email
    )
    keys = [str(item.get("key") or "") for item in issues if item.get("key")]
    refs = []
    if keys:
        refs = db.scalars(
            select(ExternalRef)
            .options(selectinload(ExternalRef.request))
            .where(ExternalRef.external_key.in_(keys))
        ).all()
    by_key = {ref.external_key: ref for ref in refs if ref.external_key}
    items = []
    for item in issues:
        key = str(item.get("key") or "")
        ref = by_key.get(key)
        request = ref.request if ref else None
        prio = parse_priority(item.get("priority")) or Priority.MEDIUM
        items.append(
            {
                "key": key,
                "title": item.get("title") or key,
                "status": item.get("status") or "Offen",
                "priority": prio.value,
                "priorityLabel": PRIORITY_LABELS[prio],
                "kind": item.get("kind") or "change_request",
                "updatedAt": item.get("updatedAt") or "",
                "url": item.get("url") or "",
                "requestId": request.id if request else None,
                "reference": request.reference if request else key,
            }
        )
    return {"items": items, "total": len(items)}


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
            selectinload(Request.external_refs),
            selectinload(Request.status_updates),
            selectinload(Request.author),
        )
        .where(Request.id == request.id)
    )
    return to_detail(loaded or request, actor=user)
