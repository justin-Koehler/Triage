"""Sync-Out ueber eine Outbox. Das Anliegen existiert auch ohne Fremdsystem."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
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


def enqueue(
    db: Session, request_id: str, operation: OutboxOperation, payload: dict | None = None
) -> OutboxJob:
    job = OutboxJob(request_id=request_id, operation=operation, payload=payload or {})
    db.add(job)
    return job


def external_ref(db: Session, request_id: str, system: str) -> ExternalRef | None:
    return db.scalar(
        select(ExternalRef).where(
            ExternalRef.request_id == request_id, ExternalRef.system == system
        )
    )


def _backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(600, 5 * 2**attempts))


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
        return

    if not ref or not ref.external_key:
        raise TicketPortError("Anlage im Fremdsystem steht noch aus")

    if operation == OutboxOperation.ADD_COMMENT:
        port.add_comment(
            ref.external_key,
            job.payload.get("body", ""),
            job.payload.get("author", "triage"),
        )
        return

    if operation == OutboxOperation.UPDATE_FIELDS:
        token, email = _user_jira_credentials(db, request.created_by)
        port.update_fields(
            ref.external_key,
            job.payload.get("fields", {}),
            parse_priority(job.payload.get("priority")),
            user_token=token,
            user_email=email,
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
        return "done"
    except Exception as err:
        job.last_error = str(err)[:500]
        if job.attempts >= settings.outbox_max_attempts:
            job.state = SyncState.DEAD
            outcome = "dead"
        else:
            job.next_attempt_at = datetime.now(UTC) + _backoff(job.attempts)
            job.state = SyncState.PENDING
            outcome = "failed"
        ref = external_ref(db, job.request_id, port.system)
        if ref:
            ref.sync_state = SyncState.DEAD if outcome == "dead" else SyncState.FAILED
            ref.last_error = job.last_error
        log.warning("outbox job %s fehlgeschlagen: %s", job.id, job.last_error)
        return outcome


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
    stats = {"done": 0, "failed": 0, "dead": 0}
    for job in jobs:
        stats[_apply_job(db, port, job, settings)] += 1
    return stats


def process_pending(db: Session, port: TicketPort, limit: int = 20) -> dict[str, int]:
    settings = get_settings()
    now = datetime.now(UTC)
    jobs = db.scalars(
        select(OutboxJob)
        .where(OutboxJob.state == SyncState.PENDING, OutboxJob.next_attempt_at <= now)
        .order_by(OutboxJob.created_at)
        .limit(limit)
    ).all()

    stats = {"done": 0, "failed": 0, "dead": 0}
    for job in jobs:
        stats[_apply_job(db, port, job, settings)] += 1
        db.commit()
    return stats
