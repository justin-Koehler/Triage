"""Sync-Out ueber eine Outbox. Das Anliegen existiert auch ohne Fremdsystem."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.types import (
    LABEL_INCOMPLETE,
    LABEL_INTAKE,
    LABEL_TRIAGE_FAILED,
    OutboxOperation,
    SyncState,
    parse_priority,
)
from app.models import ExternalRef, OutboxJob, Request
from app.ports import TicketPort, TicketPortError
from app.ports.ticket_port import IssuePayload
from app.triage.engine import is_unknown_answer

log = logging.getLogger("triage.sync")


def enqueue_effort_attachment(
    db: Session, request: Request, filename_key: str | None = None
) -> None:
    return


def _enqueue_kalkulation_csv(db: Session, request: Request, jira_key: str) -> None:
    enqueue_effort_attachment(db, request, jira_key)


_UPDATE_FIELDS_WINDOW_MINUTES = 10
_UPDATE_FIELDS_MAX_PER_WINDOW = 12


def _jira_push_paused() -> bool:
    import os

    return os.environ.get("CRITR_PAUSE_JIRA_PUSH", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _update_fields_budget_ok(db: Session) -> bool:
    """Harte Bremse gegen Massen-UPDATE_FIELDS (Mail-Flut), alle Aufrufer."""
    from sqlalchemy import text

    since = datetime.now(UTC) - timedelta(minutes=_UPDATE_FIELDS_WINDOW_MINUTES)
    n = db.execute(
        text(
            """
            SELECT count(*) FROM sync_outbox
            WHERE operation = 'update_fields'
              AND created_at >= :since
              AND state IN ('pending', 'synced', 'failed')
            """
        ),
        {"since": since},
    ).scalar()
    return int(n or 0) < _UPDATE_FIELDS_MAX_PER_WINDOW


def enqueue(
    db: Session, request_id: str, operation: OutboxOperation, payload: dict | None = None
) -> OutboxJob | None:
    if operation == OutboxOperation.UPDATE_FIELDS:
        if _jira_push_paused():
            log.warning(
                "CRITR_PAUSE_JIRA_PUSH — skip update_fields for %s", request_id
            )
            return None
        if not _update_fields_budget_ok(db):
            log.warning(
                "update_fields budget exhausted (max %s / %s min) — skip for %s",
                _UPDATE_FIELDS_MAX_PER_WINDOW,
                _UPDATE_FIELDS_WINDOW_MINUTES,
                request_id,
            )
            return None
    job = OutboxJob(request_id=request_id, operation=operation, payload=payload or {})
    db.add(job)
    return job


def _claim_lease() -> timedelta:
    settings = get_settings()
    return timedelta(seconds=max(30, int(settings.outbox_claim_seconds)))


def _claim_job(job: OutboxJob) -> bool:
    """Nur ein Worker führt den Job aus (HTTP-Background und Outbox-Loop)."""
    from app.db import SessionLocal

    # timezone=True-Spalten → aware UTC; naive vergleicht SQLAlchemy sonst kaputt.
    now = datetime.now(UTC)
    lease = _claim_lease()
    with SessionLocal() as other:
        visible = other.get(OutboxJob, job.id)
        if visible is None:
            return True
        result = other.execute(
            update(OutboxJob)
            .where(
                OutboxJob.id == job.id,
                OutboxJob.state == SyncState.PENDING,
                OutboxJob.next_attempt_at <= now,
            )
            .values(next_attempt_at=now + lease)
            .execution_options(synchronize_session=False)
        )
        other.commit()
        return (result.rowcount or 0) == 1


def external_ref(db: Session, request_id: str, system: str) -> ExternalRef | None:
    return db.scalar(
        select(ExternalRef).where(
            ExternalRef.request_id == request_id, ExternalRef.system == system
        )
    )


def _backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(600, 5 * 2**attempts))


_PERMANENT_ERROR_MARKERS = (
    "issue does not exist",
    "could not find usernames",
    "anliegen existiert nicht mehr",
    "issue does not exist or you do not have permission",
    "is required",
    "error parsing date",
    "gesamtprojektleiter is required",
    "option id 'null'",
)


def _is_permanent_error(message: str | None) -> bool:
    text = (message or "").lower()
    return any(marker in text for marker in _PERMANENT_ERROR_MARKERS)


def _user_jira_credentials(
    db: Session, user_id: str | None
) -> tuple[str | None, str | None]:
    """Persönlicher Jira-Token und E-Mail des Erstellers aus der DB."""
    if not user_id:
        return None, None
    from app.models import AppSetting
    from app.services.settings_service import decrypt_secret

    token_row = db.get(AppSetting, f"user.{user_id}.jira_token")
    token = decrypt_secret(token_row.value) if (token_row and token_row.value) else None

    email_row = db.get(AppSetting, f"user.{user_id}.jira_email")
    email = (email_row.value or "").strip() if email_row else None

    return token or None, email or None


def _payload_for(request: Request, db: Session | None = None) -> IssuePayload:
    from app.domain.types import Priority, RequestKind, parse_kind, parse_priority

    kind = request.kind if isinstance(request.kind, RequestKind) else parse_kind(request.kind)
    priority = (
        request.priority
        if isinstance(request.priority, Priority)
        else parse_priority(request.priority)
    )
    if kind is None or priority is None:
        raise TicketPortError("Anliegen hat ungültigen Typ oder Priorität")

    labels = [LABEL_INTAKE]
    if request.incomplete:
        labels.append(LABEL_INCOMPLETE)
    if request.triage_failed:
        labels.append(LABEL_TRIAGE_FAILED)
    values = dict(request.field_values())
    author = request.author
    reporter_hint = (
        str((author.external_subject if author else "") or "").strip()
        or str(values.get("author") or "").strip()
        or (author.display_name if author else "")
        or (author.email if author else "")
        or ""
    )
    # Bearbeiter = Autor (kein eigenes Feld mehr)
    if reporter_hint:
        values["assignee"] = reporter_hint
    # Unbekannte Personenangaben nicht nach Jira schreiben
    for key in list(values):
        if is_unknown_answer(values.get(key)):
            values.pop(key, None)
    lead = str(values.get("change_lead") or "").strip()
    if lead:
        from app.services.requests_service import SELF_AS_LEAD, lead_is_creator

        creator = [
            reporter_hint,
            author.display_name if author else "",
            author.external_subject if author else "",
            author.email if author else "",
            values.get("author"),
        ]
        if lead_is_creator(lead, *creator):
            raise TicketPortError(SELF_AS_LEAD)
    return IssuePayload(
        request_id=request.id,
        reference=request.reference,
        kind=kind,
        priority=priority,
        title=request.title,
        steckbrief_name=request.steckbrief_name,
        description=request.description,
        fields=values,
        labels=labels,
        created_by=author.email if author else None,
        reporter_hint=reporter_hint or None,
        **dict(zip(
            ("user_jira_token", "user_jira_email"),
            _user_jira_credentials(db, request.created_by) if db else (None, None),
            strict=True,
        )),
    )


def _run_job(db: Session, port: TicketPort, job: OutboxJob) -> None:
    request = db.get(Request, job.request_id)
    if not request:
        raise TicketPortError("Anliegen existiert nicht mehr")

    ref = external_ref(db, request.id, port.system)
    operation = OutboxOperation(job.operation)

    if operation == OutboxOperation.CREATE_ISSUE:
        if ref and ref.external_key:
            return  # schon gespiegelt, Job war ein Duplikat
        created = port.create_issue(_payload_for(request, db))
        if not ref:
            ref = ExternalRef(request_id=request.id, system=port.system)
            db.add(ref)
        ref.external_key = created.key
        ref.external_url = created.url
        ref.sync_state = SyncState.SYNCED
        ref.synced_at = datetime.now(UTC)
        ref.last_error = None
        # Ticket-Nummer = Jira-Key, damit UI und Chat dieselbe ID nutzen.
        if created.key and request.reference != created.key:
            clash = db.scalar(
                select(Request.id).where(
                    Request.reference == created.key,
                    Request.id != request.id,
                )
            )
            if not clash:
                request.reference = created.key
        _enqueue_kalkulation_csv(db, request, created.key)
        return

    if not ref or not ref.external_key:
        raise TicketPortError("Anlage im Fremdsystem steht noch aus")

    if operation == OutboxOperation.ADD_ATTACHMENT:
        return

    if operation == OutboxOperation.ADD_COMMENT:
        external_comment_id = port.add_comment(
            ref.external_key,
            job.payload.get("body", ""),
            job.payload.get("author", "triage"),
        )
        local_id = str(job.payload.get("comment_id") or "").strip()
        if external_comment_id and local_id:
            from app.models import Comment

            comment = db.get(Comment, local_id)
            if comment:
                comment.external_id = str(external_comment_id)
        return

    if operation == OutboxOperation.DELETE_COMMENT:
        external_comment_id = str(job.payload.get("external_id") or "").strip()
        if not external_comment_id:
            return
        actor_id = str(job.payload.get("user_id") or "").strip() or request.created_by
        token, email = _user_jira_credentials(db, actor_id)
        port.delete_comment(
            ref.external_key,
            external_comment_id,
            user_token=token,
            user_email=email,
        )
        return

    if operation == OutboxOperation.UPDATE_FIELDS:
        token, email = _user_jira_credentials(db, request.created_by)
        fields = dict(job.payload.get("fields") or {})
        fields["description"] = request.description or ""
        # Effort-Sheet-Link immer mitgeben — landet in der Jira-Beschreibung.
        values = request.field_values() if hasattr(request, "field_values") else {}
        sheet = str(values.get("effort_sheet_url") or fields.get("effort_sheet_url") or "").strip()
        if sheet:
            fields["effort_sheet_url"] = sheet
        port.update_fields(
            ref.external_key,
            fields,
            parse_priority(job.payload.get("priority")),
            user_token=token,
            user_email=email,
            request_id=request.id,
        )
        ref.synced_at = datetime.now(UTC)
        return

    raise TicketPortError(f"unbekannte Operation {job.operation}")


def _apply_job(db: Session, port: TicketPort, job: OutboxJob, settings) -> str:
    job.attempts += 1
    try:
        _run_job(db, port, job)
        job.state = SyncState.SYNCED
        job.completed_at = datetime.now(UTC)
        job.last_error = None
        ref = external_ref(db, job.request_id, port.system)
        if ref and ref.sync_state != SyncState.SYNCED:
            ref.sync_state = SyncState.SYNCED
            ref.last_error = None
            ref.synced_at = datetime.now(UTC)
        return "done"
    except Exception as err:
        job.last_error = str(err)[:500]
        now = datetime.now(UTC)
        permanent = _is_permanent_error(job.last_error)
        if permanent or job.attempts >= settings.outbox_max_attempts:
            job.state = SyncState.DEAD
            if permanent:
                # Daten-/Rechtefehler: nicht endlos erneut anstoßen.
                job.next_attempt_at = now + timedelta(days=3650)
            else:
                # Vorübergehend: nach Cooldown automatisch wiederbeleben.
                job.next_attempt_at = now + timedelta(
                    minutes=max(5, int(settings.outbox_dead_revive_minutes))
                )
            outcome = "dead"
        else:
            job.next_attempt_at = now + _backoff(job.attempts)
            job.state = SyncState.PENDING
            outcome = "failed"
        ref = external_ref(db, job.request_id, port.system)
        if ref:
            ref.sync_state = SyncState.DEAD if outcome == "dead" else SyncState.FAILED
            ref.last_error = job.last_error
        log.warning("outbox job %s fehlgeschlagen: %s", job.id, job.last_error)
        return outcome


def revive_dead_jobs(db: Session, *, limit: int = 20) -> int:
    """DEAD-Jobs nach Cooldown erneut versuchen (vorübergehende Jira-Ausfälle)."""
    now = datetime.now(UTC)
    jobs = list(
        db.scalars(
            select(OutboxJob)
            .where(
                OutboxJob.state == SyncState.DEAD,
                OutboxJob.next_attempt_at <= now,
            )
            .order_by(OutboxJob.next_attempt_at)
            .limit(max(1, min(limit, 50)))
        ).all()
    )
    revived = 0
    for job in jobs:
        if _is_permanent_error(job.last_error):
            job.next_attempt_at = now + timedelta(days=3650)
            continue
        job.state = SyncState.PENDING
        job.attempts = 0
        job.completed_at = None
        job.next_attempt_at = now
        note = (job.last_error or "").strip()
        job.last_error = (f"{note} | revived" if note else "revived")[:500]
        ref = db.scalar(
            select(ExternalRef).where(ExternalRef.request_id == job.request_id)
        )
        if ref and ref.sync_state in {SyncState.DEAD, SyncState.FAILED}:
            ref.sync_state = SyncState.PENDING
            ref.last_error = job.last_error
        revived += 1
    if revived:
        db.commit()
        log.info("outbox revived %s dead job(s)", revived)
    return revived


def process_request(db: Session, port: TicketPort, request_id: str) -> dict[str, int]:
    """CREATE sofort nach Anlage, damit die Jira-ID in der Antwort steht."""
    settings = get_settings()
    now = datetime.now(UTC)
    jobs = db.scalars(
        select(OutboxJob)
        .where(
            OutboxJob.request_id == request_id,
            OutboxJob.state == SyncState.PENDING,
            OutboxJob.next_attempt_at <= now,
        )
        .order_by(OutboxJob.created_at)
    ).all()
    stats = {"done": 0, "failed": 0, "dead": 0, "revived": 0}
    for job in jobs:
        if not _claim_job(job):
            continue
        db.refresh(job)
        stats[_apply_job(db, port, job, settings)] += 1
    return stats


def process_pending(db: Session, port: TicketPort, limit: int = 20) -> dict[str, int]:
    settings = get_settings()
    revived = revive_dead_jobs(db, limit=limit)
    now = datetime.now(UTC)
    jobs = db.scalars(
        select(OutboxJob)
        .where(OutboxJob.state == SyncState.PENDING, OutboxJob.next_attempt_at <= now)
        .order_by(OutboxJob.created_at)
        .limit(limit)
    ).all()

    stats = {"done": 0, "failed": 0, "dead": 0, "revived": revived}
    for job in jobs:
        if not _claim_job(job):
            continue
        db.refresh(job)
        stats[_apply_job(db, port, job, settings)] += 1
        db.commit()
    return stats
