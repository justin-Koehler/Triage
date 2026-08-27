"""Lese- und Schreibpfad des Workspace. Quelle ist immer die eigene DB."""

from __future__ import annotations

import re
import yaml
from functools import lru_cache
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.domain.calc import compute
from app.domain.fieldspec import GROUP_LABELS, TriageRules, get_rules
from app.domain.routing import responsible_names
from app.domain.text import todo_from_status
from app.domain.types import (
    KIND_LABELS,
    PRIORITY_LABELS,
    STATUS_LABELS,
    SYNC_LABELS,
    OutboxOperation,
    Priority,
    RequestKind,
    RequestStatus,
    SyncState,
    parse_kind,
)
from app.models import Comment, IntakeSession, Request, RequestField, StatusUpdate, User
from app.sync.outbox import enqueue
from app.config import get_settings
from app.triage.engine import BUNDLE_MEMBERS, Diagnosis, Draft, TriageEngine
from app.triage.providers import NoLlmProvider

EDITABLE_SCALARS = {
    "title",
    "description",
    "status",
    "priority",
    "company",
    "change_lead",
}


@lru_cache
def _jira_field_map_meta() -> dict:
    """Lokal die Jira Feld-Map laden (Adapter kennt `jira: null`)."""
    try:
        return yaml.safe_load(
            get_settings().field_map_path.read_text(encoding="utf-8")
        ) or {}
    except Exception:
        return {}

EXPORT_LIMIT = 5000

PRIORITY_RANK = {
    Priority.CRITICAL: 0,
    Priority.HIGH: 1,
    Priority.MEDIUM: 2,
    Priority.LOW: 3,
}
STATUS_RANK = {
    RequestStatus.DRAFT: 0,
    RequestStatus.STECKBRIEF: 1,
    RequestStatus.IT_REVIEW: 2,
    RequestStatus.QG1: 3,
    RequestStatus.QG2: 4,
    RequestStatus.APPROVED: 5,
    RequestStatus.IN_PROGRESS: 6,
    RequestStatus.DONE: 7,
    RequestStatus.REJECTED: 8,
}
SORT_FIELDS = ("created", "updated", "priority", "status", "reference", "title")


OPEN_STATUSES = tuple(
    status
    for status in RequestStatus
    if status not in (RequestStatus.DONE, RequestStatus.REJECTED)
)


@dataclass
class RequestFilter:
    kind: RequestKind | None = None
    status: RequestStatus | None = None
    # Mehrere Status auf einmal, damit "offen" ausdrueckbar ist.
    statuses: tuple[RequestStatus, ...] = ()
    priority: Priority | None = None
    company: str | None = None
    change_lead: str | None = None
    created_by: str | None = None
    query: str | None = None
    sort: str = "created"
    direction: str = "desc"
    limit: int = 50
    offset: int = 0


def _sync_view(request: Request) -> dict:
    ref = request.external_refs[0] if request.external_refs else None
    state = ref.sync_state if ref else SyncState.DISABLED
    return {
        "state": state.value if hasattr(state, "value") else str(state),
        "label": SYNC_LABELS.get(SyncState(state), str(state)),
        "system": ref.system if ref else None,
        "externalKey": ref.external_key if ref else None,
        "externalUrl": ref.external_url if ref else None,
        "lastError": ref.last_error if ref else None,
        "syncedAt": ref.synced_at.isoformat() if ref and ref.synced_at else None,
    }


def actor_name_needles(actor: User | None) -> list[str]:
    """Display-Name, Jira-Username und E-Mail-Lokalteil für Status-Matching."""
    if not actor:
        return []
    out: list[str] = []
    seen: set[str] = set()
    email = str(getattr(actor, "email", None) or "").strip()
    candidates = [
        getattr(actor, "display_name", None),
        getattr(actor, "external_subject", None),
        email,
    ]
    if email and "@" in email:
        candidates.append(email.split("@", 1)[0])
    for raw in candidates:
        text = (raw or "").strip()
        if len(text) < 3:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def actor_named_in_status(
    request: Request,
    name: str | None = None,
    *,
    actor: User | None = None,
) -> bool:
    """Aktueller Status (Kurzfassung + letzter Eintrag) nennt den Actor."""
    needles = actor_name_needles(actor) if actor else []
    if name and (name or "").strip() and (name or "").strip().lower() not in {
        n.lower() for n in needles
    }:
        if len((name or "").strip()) >= 3:
            needles.append((name or "").strip())
    for needle in needles:
        if len(needle) < 3:
            continue
        if re.search(rf"\b{re.escape(needle)}\b", _waiting_source(request, needle), flags=re.I):
            return True
    return False


def _waiting_source(request: Request, name: str) -> str:
    values = request.field_values()
    summary = values.get("status_summary") or ""
    if name and re.search(rf"\b{re.escape(name)}\b", summary, flags=re.I):
        return summary
    updates = list(request.status_updates or [])
    if updates:
        latest = updates[0]
        for chunk in (latest.next_steps or "", latest.summary or ""):
            if name and re.search(rf"\b{re.escape(name)}\b", chunk, flags=re.I):
                return chunk
    return summary


def waiting_todo(request: Request, actor: User | None) -> str:
    if not actor or not actor_named_in_status(request, actor=actor):
        return ""
    for needle in actor_name_needles(actor):
        source = _waiting_source(request, needle)
        if source and re.search(rf"\b{re.escape(needle)}\b", source, flags=re.I):
            return todo_from_status(source, needle)
    return ""


def to_list_item(request: Request, actor: User | None = None) -> dict:
    # Die Spalten sind String, aus der DB kommen deshalb rohe Werte zurueck.
    kind = parse_kind(request.kind) or RequestKind.CHANGE_REQUEST
    status = RequestStatus(request.status)
    priority = Priority(request.priority)
    waiting = bool(actor and actor_named_in_status(request, actor=actor))
    return {
        "id": request.id,
        "reference": request.reference,
        "kind": kind.value,
        "kindLabel": KIND_LABELS[kind],
        "status": status.value,
        "statusLabel": STATUS_LABELS[status],
        "priority": priority.value,
        "priorityLabel": PRIORITY_LABELS[priority],
        "title": request.title,
        "statusSummary": _status_blurb(request),
        "waitingOnMe": waiting,
        "waitingTodo": waiting_todo(request, actor) if waiting else "",
        "company": request.company,
        "changeLead": request.change_lead,
        "notes": request.field_values().get("other"),
        "conceptScsPt": request.field_values().get("concept_scs_pt"),
        "conceptCitPt": request.field_values().get("concept_cit_pt"),
        "operateScsPt": request.field_values().get("operate_scs_pt"),
        "operateCitPt": request.field_values().get("operate_cit_pt"),
        "incomplete": request.incomplete,
        "missingFields": _missing_labels(request),
        "triageFailed": request.triage_failed,
        "createdBy": request.author.display_name if request.author else None,
        "createdAt": request.created_at.isoformat(),
        "updatedAt": request.updated_at.isoformat(),
        "commentCount": len(request.comments),
        "sync": _sync_view(request),
    }


def _status_blurb(request: Request) -> str:
    from app.services.status_summary import list_blurb

    return list_blurb(request.field_values())


def _field_values(spec) -> list[str]:
    if not spec:
        return []
    if spec.values_from == "responsibles":
        return list(responsible_names())
    return list(spec.values or ())


HIDDEN_DETAIL_KEYS = {"status_summary", "status_digest", "current_status"}


def _grouped_fields(request: Request) -> list[dict]:
    """Ganze YAML-Vorlage, gespeicherte Werte drauf. Leere Felder bleiben sichtbar."""
    spec = get_rules().spec(parse_kind(request.kind) or RequestKind.CHANGE_REQUEST)
    stored = {field.key: field for field in request.fields}
    values = request.field_values()
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    seen: set[str] = set()

    def append(key: str, label: str, value: str, spec_field) -> None:
        group = spec_field.group if spec_field else ""
        if group not in groups:
            groups[group] = []
            order.append(group)
        groups[group].append(
            {
                "key": key,
                "label": label,
                "value": value,
                "type": spec_field.type if spec_field else "text",
                "fill": spec_field.fill if spec_field else "workspace",
                "values": _field_values(spec_field),
                "aiMode": (spec_field.ai_mode if spec_field else "manual_only"),
                "requiredOnConfirm": bool(spec_field.required_on_confirm) if spec_field else False,
                "syncMode": (spec_field.sync_mode if spec_field else "local_only"),
            }
        )
        seen.add(key)

    for spec_field in spec.fields:
        if spec_field.key in HIDDEN_DETAIL_KEYS:
            continue
        if not spec_field.applies(values):
            continue
        row = stored.get(spec_field.key)
        value = row.value if row is not None else str(values.get(spec_field.key) or "")
        append(spec_field.key, spec_field.label, value, spec_field)

    for field in sorted(request.fields, key=lambda item: item.position):
        if field.key in seen or field.key in HIDDEN_DETAIL_KEYS:
            continue
        append(field.key, field.label, field.value, spec.field_map().get(field.key))

    return [
        {
            "group": group,
            "groupLabel": GROUP_LABELS.get(group, group or "Sonstiges"),
            "fields": groups[group],
        }
        for group in order
    ]


def _status_update_view(item: StatusUpdate) -> dict:
    return {
        "id": item.id,
        "reportedOn": item.reported_on,
        "overallRag": item.overall_rag,
        "summary": item.summary,
        "decisions": item.decisions,
        "risks": item.risks,
        "nextSteps": item.next_steps,
        "scheduleRag": item.schedule_rag,
        "scheduleReason": item.schedule_reason,
        "planStart": item.plan_start,
        "planEnd": item.plan_end,
        "actualStart": item.actual_start,
        "actualEnd": item.actual_end,
        "milestones": item.milestones or [],
        "costRag": item.cost_rag,
        "costPlanFb": item.cost_plan_fb,
        "costPlanIt": item.cost_plan_it,
        "costPlanLicense": item.cost_plan_license,
        "costActualFb": item.cost_actual_fb,
        "costActualIt": item.cost_actual_it,
        "costActualLicense": item.cost_actual_license,
        "createdAt": item.created_at.isoformat(),
    }


def _missing_labels(request: Request) -> list[str]:
    spec = get_rules().spec(parse_kind(request.kind) or RequestKind.CHANGE_REQUEST)
    return [f.label for f in spec.missing_hard_fields(request.field_values())]


def to_detail(request: Request, actor: User | None = None) -> dict:
    return to_list_item(request, actor) | {
        "steckbriefName": request.steckbrief_name,
        "description": request.description,
        "confidence": request.confidence,
        "missingFields": _missing_labels(request),
        "fields": [
            {"key": f.key, "label": f.label, "value": f.value}
            for f in sorted(request.fields, key=lambda f: f.position)
            if f.key != "status_digest"
        ],
        "groups": _grouped_fields(request),
        "statusUpdates": [_status_update_view(item) for item in request.status_updates],
        "comments": [
            {
                "id": c.id,
                "author": c.author_name,
                "body": c.body,
                "createdAt": c.created_at.isoformat(),
            }
            for c in request.comments
        ],
    }


def _base_query():
    return select(Request).options(
        selectinload(Request.fields),
        selectinload(Request.comments),
        selectinload(Request.external_refs),
        selectinload(Request.status_updates),
        selectinload(Request.author),
    )


def _conditions(filters: RequestFilter) -> list:
    conditions = []
    if filters.kind:
        conditions.append(Request.kind == filters.kind)
    if filters.status:
        conditions.append(Request.status == filters.status)
    if filters.statuses:
        conditions.append(Request.status.in_([s.value for s in filters.statuses]))
    if filters.priority:
        conditions.append(Request.priority == filters.priority)
    if filters.company:
        conditions.append(func.lower(Request.company) == filters.company.lower())
    if filters.change_lead:
        conditions.append(func.lower(Request.change_lead) == filters.change_lead.lower())
    if filters.created_by:
        conditions.append(Request.created_by == filters.created_by)
    if filters.query:
        needle = f"%{filters.query.lower()}%"
        conditions.append(
            or_(
                func.lower(Request.title).like(needle),
                func.lower(Request.description).like(needle),
                func.lower(Request.reference).like(needle),
            )
        )
    return conditions


def _waiting_on_expr(names: list[str] | str):
    if isinstance(names, str):
        needles = [names]
    else:
        needles = list(names)
    patterns = [f"%{(name or '').strip().lower()}%" for name in needles if len((name or "").strip()) >= 3]
    if not patterns:
        return case((False, 1), else_=0)
    summary_hit = (
        select(RequestField.id)
        .where(
            RequestField.request_id == Request.id,
            RequestField.key == "status_summary",
            or_(*[func.lower(RequestField.value).like(pat) for pat in patterns]),
        )
        .exists()
    )
    latest = (
        select(func.max(StatusUpdate.created_at))
        .where(StatusUpdate.request_id == Request.id)
        .correlate(Request)
        .scalar_subquery()
    )
    update_hit = (
        select(StatusUpdate.id)
        .where(
            StatusUpdate.request_id == Request.id,
            StatusUpdate.created_at == latest,
            or_(
                or_(*[func.lower(StatusUpdate.summary).like(pat) for pat in patterns]),
                or_(*[func.lower(StatusUpdate.next_steps).like(pat) for pat in patterns]),
            ),
        )
        .exists()
    )
    return case((or_(summary_hit, update_hit), 1), else_=0)


def _order_by(filters: RequestFilter, actor: User | None = None):
    pin = ()
    needles = actor_name_needles(actor)
    if needles:
        pin = (_waiting_on_expr(needles).desc(),)
    if filters.sort == "attention":
        # Genannter Status zuerst, dann unvollstaendig, dann neueste.
        return pin + (Request.incomplete.desc(), Request.created_at.desc())
    ranked = {
        "priority": case(
            {p.value: rank for p, rank in PRIORITY_RANK.items()},
            value=Request.priority,
            else_=99,
        ),
        "status": case(
            {s.value: rank for s, rank in STATUS_RANK.items()},
            value=Request.status,
            else_=99,
        ),
        "created": Request.created_at,
        "updated": Request.updated_at,
        "reference": Request.reference,
        "title": func.lower(Request.title),
    }
    column = ranked.get(filters.sort, Request.created_at)
    primary = column.asc() if filters.direction == "asc" else column.desc()
    return pin + (primary, Request.created_at.desc())


def list_requests(db: Session, filters: RequestFilter, actor: User | None = None) -> dict:
    stmt = _base_query()
    count_stmt = select(func.count()).select_from(Request)

    for condition in _conditions(filters):
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(*_order_by(filters, actor)).limit(filters.limit).offset(filters.offset)
    ).all()
    return {
        "total": int(total),
        "limit": filters.limit,
        "offset": filters.offset,
        "sort": filters.sort,
        "direction": filters.direction,
        "items": [to_list_item(row, actor) for row in rows],
    }


def status_counts(db: Session) -> dict:
    """Zaehler je Status fuer die Chips ueber der Tabelle."""
    rows = db.execute(
        select(Request.status, func.count()).group_by(Request.status)
    ).all()
    counted = {str(status): int(count) for status, count in rows}
    return {
        "total": sum(counted.values()),
        "byStatus": [
            {
                "value": status.value,
                "label": STATUS_LABELS[status],
                "count": counted.get(status.value, 0),
            }
            for status in RequestStatus
        ],
    }


EXPORT_HEADER = (
    "Change-Titel",
    "Change-Leitung SCS",
    "Status",
    "Konzeption PT Plan SCS",
    "Konzeption PT Plan CIT",
    "Betrieb PT Plan SCS",
    "Betrieb PT Plan CIT",
    "Sonstiges",
)


def _export_date(value: datetime | None) -> str:
    return value.strftime("%d.%m.%Y %H:%M") if value else ""


def export_rows(db: Session, filters: RequestFilter) -> list[tuple[str, ...]]:
    stmt = _base_query()
    for condition in _conditions(filters):
        stmt = stmt.where(condition)
    rows = db.scalars(
        stmt.order_by(*_order_by(filters)).limit(EXPORT_LIMIT)
    ).all()

    out: list[tuple[str, ...]] = [EXPORT_HEADER]
    for request in rows:
        values = request.field_values()
        out.append(
            (
                request.title,
                request.change_lead or "",
                STATUS_LABELS[RequestStatus(request.status)],
                values.get("concept_scs_pt") or "",
                values.get("concept_cit_pt") or "",
                values.get("operate_scs_pt") or "",
                values.get("operate_cit_pt") or "",
                values.get("other") or "",
            )
        )
    return out


def get_request(db: Session, request_id: str) -> Request | None:
    return db.scalar(_base_query().where(Request.id == request_id))


def delete_request(db: Session, request: Request) -> None:
    """Lokal löschen. Jira bleibt unangetastet."""
    sessions = db.scalars(
        select(IntakeSession).where(IntakeSession.request_id == request.id)
    ).all()
    for session in sessions:
        session.request_id = None
    db.flush()
    db.delete(request)
    db.flush()


def _upsert_field(db: Session, request: Request, key: str, label: str, value: object) -> None:
    text = str(value or "")
    existing = next((f for f in request.fields if f.key == key), None)
    if existing:
        existing.value = text
        return
    item = RequestField(
        request_id=request.id,
        key=key,
        label=label,
        value=text,
        position=len(request.fields),
    )
    db.add(item)
    request.fields.append(item)


def _render_description_for_jira(request: Request, field_meta: dict) -> str:
    """Deterministischer Jira-Fallback für `jira: null` Felder."""
    values = request.field_values()
    lead_raw = str(values.get("description") or request.description or "").strip()
    lead = lead_raw.split("\nSteckbrief-Name:", 1)[0].strip()
    parts = [lead] if lead else []
    parts.extend(
        [
            f"Steckbrief-Name: {request.steckbrief_name}",
            f"Interne Referenz: {request.reference}",
        ]
    )
    for key, meta in field_meta.items():
        if key in {"summary", "title", "description", "steckbrief_name"}:
            continue
        if meta.get("jira") is not None:
            continue
        value = str(values.get(key) or "").strip()
        if not value:
            continue
        label = meta.get("label") or key
        parts.append(f"{label}: {value}")
    return "\n".join(parts).strip()


def update_request(
    db: Session,
    request: Request,
    changes: dict,
    *,
    rules: TriageRules | None = None,
) -> Request:
    """Inline-Edit. Schreibt eigene DB und stellt einen Sync-Job in die Outbox."""
    rules = rules or get_rules()
    spec = rules.spec(parse_kind(request.kind) or RequestKind.CHANGE_REQUEST)
    field_labels = spec.field_map()
    synced_fields: dict[str, str] = {}

    for key, value in changes.items():
        if key in EDITABLE_SCALARS:
            if key == "status":
                request.status = RequestStatus(value)
                # Jira kennt keine Feldzuordnung dafuer, der Fake protokolliert es.
                synced_fields["status"] = request.status.value
            elif key == "priority":
                request.priority = Priority(value)
            else:
                setattr(request, key, value)
                if key in ("title", "description"):
                    synced_fields[key] = str(value)
            # Spalten wie change_lead stehen auch im Steckbrief. Beides ziehen,
            # sonst zeigt die Detailseite nach dem Edit zwei Wahrheiten.
            if key in field_labels:
                _upsert_field(db, request, field_labels[key].key, field_labels[key].label, value)
                synced_fields[key] = str(value or "")
            continue

        if key in {"current_status", "status_summary", "status_digest", "status_ablauf"}:
            continue
        if key not in field_labels:
            continue
        text = str(value or "")
        _upsert_field(db, request, key, field_labels[key].label, text)
        synced_fields[key] = text

    # Jira kennt keine Custom-Fields mit `jira: null`. Dafür schreiben wir die
    # Jira-Description deterministisch aus dem lokalen Zustand neu.
    jira_meta = _jira_field_map_meta()
    field_meta = jira_meta.get("fields") or {}
    null_changed = [
        k
        for k in changes.keys()
        if field_meta.get(k, {}).get("jira") is None
    ]
    null_changed = [k for k in null_changed if k not in {"description"}]
    if null_changed or "description" in synced_fields:
        request.description = _render_description_for_jira(request, field_meta)
        synced_fields["description"] = request.description

    totals = compute(request.field_values() | synced_fields)
    for key, value in totals.items():
        spec_field = field_labels.get(key)
        if spec_field and spec_field.fill == "computed":
            _upsert_field(db, request, key, spec_field.label, value)
            synced_fields[key] = value

    request.incomplete = bool(spec.missing_hard_fields(request.field_values() | synced_fields))
    db.flush()

    if synced_fields or "priority" in changes:
        enqueue(
            db,
            request.id,
            OutboxOperation.UPDATE_FIELDS,
            {"fields": synced_fields, "priority": Priority(request.priority).value},
        )
    return request


def ai_fill_request(
    db: Session,
    request: Request,
    *,
    field_key: str,
    overwrite: bool = False,
) -> Request:
    """Füllt ein Feld (heuristisch über Bundle-Parser) und persistiert über `update_request`.

    KI-Button füllt pro Feld ein sinnvolles Bundle-Set, überschreibt aber bei `overwrite=false`
    keine bereits vorhandenen Werte außerhalb des Ziel-Felds.
    """
    engine = TriageEngine(provider=NoLlmProvider())
    draft = Draft(
        kind=parse_kind(request.kind),
        title=str(request.title or ""),
        service=None,
        priority=Priority(request.priority) if request.priority else None,
        confidence=None,
        values={k: str(v or "") for k, v in request.field_values().items()},
    )

    if draft.kind is None:
        raise ValueError("Art fehlt")

    before = dict(draft.values)
    bundle_key = next(
        (bk for bk, members in BUNDLE_MEMBERS.items() if field_key in members),
        None,
    )
    if bundle_key:
        members = BUNDLE_MEMBERS.get(bundle_key) or ()
        preserved = {
            k: before.get(k, "")
            for k in members
            if str(before.get(k, "") or "").strip()
        }
        engine._apply_answer(draft, (bundle_key, request.description or ""), Diagnosis())
        if not overwrite:
            for k, v in preserved.items():
                if k != field_key:
                    draft.values[k] = v

    # Nur echte Feld-Keys aus dem Ruleset updaten.
    rules = get_rules()
    spec = rules.spec(draft.kind)
    field_labels = spec.field_map()
    changes: dict[str, str] = {}
    for key, value in draft.values.items():
        if key not in field_labels:
            continue
        new = str(value or "")
        if overwrite or str(before.get(key) or "").strip() != new.strip():
            changes[key] = new

    if not changes:
        return request

    updated = update_request(db, request, changes)
    return updated


def add_comment(db: Session, request: Request, body: str, user: User | None) -> Comment:
    comment = Comment(
        request_id=request.id,
        author_id=user.id if user else None,
        author_name=user.display_name if user else "Fachbereich",
        body=body,
    )
    db.add(comment)
    db.flush()
    enqueue(
        db,
        request.id,
        OutboxOperation.ADD_COMMENT,
        {"body": body, "author": comment.author_name, "comment_id": comment.id},
    )
    return comment


def filter_options(db: Session) -> dict:
    companies = [
        row
        for row in db.scalars(select(Request.company).distinct().order_by(Request.company)).all()
        if row
    ]
    return {
        "kinds": [{"value": k.value, "label": v} for k, v in KIND_LABELS.items()],
        "statuses": [{"value": k.value, "label": v} for k, v in STATUS_LABELS.items()],
        "priorities": [{"value": k.value, "label": v} for k, v in PRIORITY_LABELS.items()],
        "companies": companies,
        "responsibles": responsible_names(),
    }


def create_status_update(db: Session, request: Request, payload: dict) -> StatusUpdate:
    item = StatusUpdate(request_id=request.id)
    _apply_status_update(item, payload)
    db.add(item)
    db.flush()
    if item not in request.status_updates:
        request.status_updates.append(item)
    _refresh_live_status(db, request)
    return item


def update_status_update(
    db: Session, item: StatusUpdate, payload: dict
) -> StatusUpdate:
    _apply_status_update(item, payload)
    db.flush()
    request = item.request
    _refresh_live_status(db, request)
    return item


def _refresh_live_status(db: Session, request: Request) -> None:
    from app.services.status_summary import StatusEmpty, summarize

    try:
        summarize(db, request)
    except StatusEmpty:
        return


def _apply_status_update(item: StatusUpdate, payload: dict) -> None:
    mapping = {
        "reportedOn": "reported_on",
        "overallRag": "overall_rag",
        "summary": "summary",
        "decisions": "decisions",
        "risks": "risks",
        "nextSteps": "next_steps",
        "scheduleRag": "schedule_rag",
        "scheduleReason": "schedule_reason",
        "planStart": "plan_start",
        "planEnd": "plan_end",
        "actualStart": "actual_start",
        "actualEnd": "actual_end",
        "milestones": "milestones",
        "costRag": "cost_rag",
        "costPlanFb": "cost_plan_fb",
        "costPlanIt": "cost_plan_it",
        "costPlanLicense": "cost_plan_license",
        "costActualFb": "cost_actual_fb",
        "costActualIt": "cost_actual_it",
        "costActualLicense": "cost_actual_license",
    }
    for incoming, attr in mapping.items():
        if incoming in payload and payload[incoming] is not None:
            setattr(item, attr, payload[incoming])
