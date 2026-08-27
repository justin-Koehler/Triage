"""Eigenes Schema. Primaerschluessel sind unsere UUIDs, Jira-Keys nur Referenz."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.domain.types import (
    OutboxOperation,
    Priority,
    RequestKind,
    RequestStatus,
    SyncState,
    TriageSource,
)


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(32), default="requester")
    external_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)


class IntakeSession(Base, TimestampMixin):
    """Dialogzustand. Frueher ein Prozess-Dict, jetzt ueberlebt es den Restart."""

    __tablename__ = "intake_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    phase: Mapped[str] = mapped_column(String(24), default="collect")
    questions_asked: Mapped[int] = mapped_column(Integer, default=0)
    draft: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Gespraechskontext des Assistenten: client, last_request_id, pending.
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    request_id: Mapped[str | None] = mapped_column(ForeignKey("requests.id"), nullable=True)

    messages: Mapped[list[Message]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="Message.created_at"
    )
    triage_runs: Mapped[list[TriageRun]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="TriageRun.turn"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("intake_sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    # Antwort auf eine Feldfrage. Nur Nachrichten ohne Key sind echte Meldung
    # und landen in der Beschreibung.
    field_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[IntakeSession] = relationship(back_populates="messages")


class TriageRun(Base):
    """Ein Turn der Triage. Basis fuer Qualitaetsmessung und Prompt-Verbesserung."""

    __tablename__ = "triage_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("intake_sessions.id", ondelete="CASCADE"), index=True
    )
    turn: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[TriageSource] = mapped_column(String(20))
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[RequestKind | None] = mapped_column(String(32), nullable=True)
    previous_kind: Mapped[RequestKind | None] = mapped_column(String(32), nullable=True)
    priority: Mapped[Priority | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[IntakeSession] = relationship(back_populates="triage_runs")


class Request(Base, TimestampMixin):
    __tablename__ = "requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    reference: Mapped[str] = mapped_column(String(24), unique=True)
    kind: Mapped[RequestKind] = mapped_column(String(32), index=True)
    status: Mapped[RequestStatus] = mapped_column(
        String(32), default=RequestStatus.STECKBRIEF, index=True
    )
    priority: Mapped[Priority] = mapped_column(String(16), default=Priority.MEDIUM, index=True)
    title: Mapped[str] = mapped_column(String(200))
    steckbrief_name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    company: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    change_lead: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    incomplete: Mapped[bool] = mapped_column(Boolean, default=False)
    triage_failed: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reworked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    fields: Mapped[list[RequestField]] = relationship(
        back_populates="request", cascade="all, delete-orphan", order_by="RequestField.position"
    )
    comments: Mapped[list[Comment]] = relationship(
        back_populates="request", cascade="all, delete-orphan", order_by="Comment.created_at"
    )
    external_refs: Mapped[list[ExternalRef]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )
    status_updates: Mapped[list[StatusUpdate]] = relationship(
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="StatusUpdate.reported_on.desc()",
    )
    author: Mapped[User | None] = relationship()

    def field_values(self) -> dict[str, str]:
        return {f.key: f.value for f in self.fields}


class RequestField(Base):
    __tablename__ = "request_fields"
    __table_args__ = (UniqueConstraint("request_id", "key", name="uq_request_field"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(
        ForeignKey("requests.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(120))
    value: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)

    request: Mapped[Request] = relationship(back_populates="fields")


class StatusUpdate(Base, TimestampMixin):
    """Ein Statusbericht zum Change. Historie, kein Ueberschreiben."""

    __tablename__ = "status_updates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(
        ForeignKey("requests.id", ondelete="CASCADE"), index=True
    )
    reported_on: Mapped[str] = mapped_column(String(10), default="")
    overall_rag: Mapped[str] = mapped_column(String(16), default="green")
    summary: Mapped[str] = mapped_column(Text, default="")
    decisions: Mapped[str] = mapped_column(Text, default="")
    risks: Mapped[str] = mapped_column(Text, default="")
    next_steps: Mapped[str] = mapped_column(Text, default="")
    schedule_rag: Mapped[str] = mapped_column(String(16), default="blue")
    schedule_reason: Mapped[str] = mapped_column(Text, default="")
    plan_start: Mapped[str] = mapped_column(String(40), default="")
    plan_end: Mapped[str] = mapped_column(String(40), default="")
    actual_start: Mapped[str] = mapped_column(String(40), default="")
    actual_end: Mapped[str] = mapped_column(String(40), default="")
    milestones: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    cost_rag: Mapped[str] = mapped_column(String(16), default="blue")
    cost_plan_fb: Mapped[str] = mapped_column(String(40), default="")
    cost_plan_it: Mapped[str] = mapped_column(String(40), default="")
    cost_plan_license: Mapped[str] = mapped_column(String(40), default="")
    cost_actual_fb: Mapped[str] = mapped_column(String(40), default="")
    cost_actual_it: Mapped[str] = mapped_column(String(40), default="")
    cost_actual_license: Mapped[str] = mapped_column(String(40), default="")

    request: Mapped[Request] = relationship(back_populates="status_updates")


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(
        ForeignKey("requests.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    author_name: Mapped[str] = mapped_column(String(120), default="unbekannt")
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    request: Mapped[Request] = relationship(back_populates="comments")


class ExternalRef(Base):
    """Ein Anliegen kann in Fremdsystemen gespiegelt sein. Nie umgekehrt."""

    __tablename__ = "external_refs"
    __table_args__ = (UniqueConstraint("request_id", "system", name="uq_external_ref"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(
        ForeignKey("requests.id", ondelete="CASCADE"), index=True
    )
    system: Mapped[str] = mapped_column(String(32))
    external_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sync_state: Mapped[SyncState] = mapped_column(String(16), default=SyncState.PENDING)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    request: Mapped[Request] = relationship(back_populates="external_refs")


class OutboxJob(Base):
    __tablename__ = "sync_outbox"
    __table_args__ = (Index("ix_outbox_state_next", "state", "next_attempt_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(
        ForeignKey("requests.id", ondelete="CASCADE"), index=True
    )
    operation: Mapped[OutboxOperation] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    state: Mapped[SyncState] = mapped_column(String(16), default=SyncState.PENDING)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IdempotencyKey(Base):
    """Doppelklick auf 'Anlegen' darf kein zweites Anliegen erzeugen."""

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    scope: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    response: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FakeExternalIssue(Base):
    """Datenbestand des Fake-Fremdsystems. Verhaelt sich wie Jira, ist es aber nicht."""

    __tablename__ = "fake_external_issues"

    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    issue_type: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(32), default="Medium")
    labels: Mapped[list[str]] = mapped_column(JSON, default=list)
    fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    comments: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AppSetting(Base):
    """Key/Value-Einstellungen. Secrets liegen verschluesselt in value."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    secret: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
