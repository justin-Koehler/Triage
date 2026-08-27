"""Initial schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-24

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("external_subject", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "requests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("reference", sa.String(length=24), nullable=False, unique=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("steckbrief_name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("company", sa.String(length=80), nullable=True),
        sa.Column("change_lead", sa.String(length=80), nullable=True),
        sa.Column("incomplete", sa.Boolean(), nullable=False),
        sa.Column("triage_failed", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("reworked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_requests_kind", "requests", ["kind"])
    op.create_index("ix_requests_status", "requests", ["status"])
    op.create_index("ix_requests_priority", "requests", ["priority"])
    op.create_index("ix_requests_company", "requests", ["company"])
    op.create_index("ix_requests_change_lead", "requests", ["change_lead"])

    op.create_table(
        "intake_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("phase", sa.String(length=24), nullable=False),
        sa.Column("questions_asked", sa.Integer(), nullable=False),
        sa.Column("draft", sa.JSON(), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("request_id", sa.String(length=36), sa.ForeignKey("requests.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("intake_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("field_key", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_messages_session_id", "messages", ["session_id"])

    op.create_table(
        "triage_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("intake_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("turn", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=True),
        sa.Column("previous_kind", sa.String(length=32), nullable=True),
        sa.Column("priority", sa.String(length=16), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_triage_runs_session_id", "triage_runs", ["session_id"])

    op.create_table(
        "request_fields",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "request_id",
            sa.String(length=36),
            sa.ForeignKey("requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("request_id", "key", name="uq_request_field"),
    )
    op.create_index("ix_request_fields_request_id", "request_fields", ["request_id"])

    op.create_table(
        "status_updates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "request_id",
            sa.String(length=36),
            sa.ForeignKey("requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reported_on", sa.String(length=10), nullable=False),
        sa.Column("overall_rag", sa.String(length=16), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("decisions", sa.Text(), nullable=False),
        sa.Column("risks", sa.Text(), nullable=False),
        sa.Column("next_steps", sa.Text(), nullable=False),
        sa.Column("schedule_rag", sa.String(length=16), nullable=False),
        sa.Column("schedule_reason", sa.Text(), nullable=False),
        sa.Column("plan_start", sa.String(length=40), nullable=False),
        sa.Column("plan_end", sa.String(length=40), nullable=False),
        sa.Column("actual_start", sa.String(length=40), nullable=False),
        sa.Column("actual_end", sa.String(length=40), nullable=False),
        sa.Column("milestones", sa.JSON(), nullable=False),
        sa.Column("cost_rag", sa.String(length=16), nullable=False),
        sa.Column("cost_plan_fb", sa.String(length=40), nullable=False),
        sa.Column("cost_plan_it", sa.String(length=40), nullable=False),
        sa.Column("cost_plan_license", sa.String(length=40), nullable=False),
        sa.Column("cost_actual_fb", sa.String(length=40), nullable=False),
        sa.Column("cost_actual_it", sa.String(length=40), nullable=False),
        sa.Column("cost_actual_license", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_status_updates_request_id", "status_updates", ["request_id"])

    op.create_table(
        "comments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "request_id",
            sa.String(length=36),
            sa.ForeignKey("requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("author_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("author_name", sa.String(length=120), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_comments_request_id", "comments", ["request_id"])

    op.create_table(
        "external_refs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "request_id",
            sa.String(length=36),
            sa.ForeignKey("requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("system", sa.String(length=32), nullable=False),
        sa.Column("external_key", sa.String(length=64), nullable=True),
        sa.Column("external_url", sa.String(length=500), nullable=True),
        sa.Column("sync_state", sa.String(length=16), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.UniqueConstraint("request_id", "system", name="uq_external_ref"),
    )
    op.create_index("ix_external_refs_request_id", "external_refs", ["request_id"])

    op.create_table(
        "sync_outbox",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "request_id",
            sa.String(length=36),
            sa.ForeignKey("requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_sync_outbox_request_id", "sync_outbox", ["request_id"])
    op.create_index("ix_outbox_state_next", "sync_outbox", ["state", "next_attempt_at"])

    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.String(length=120), primary_key=True),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=True),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "fake_external_issues",
        sa.Column("key", sa.String(length=32), primary_key=True),
        sa.Column("issue_type", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("labels", sa.JSON(), nullable=False),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("comments", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=120), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("secret", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_table("fake_external_issues")
    op.drop_table("idempotency_keys")
    op.drop_index("ix_outbox_state_next", table_name="sync_outbox")
    op.drop_index("ix_sync_outbox_request_id", table_name="sync_outbox")
    op.drop_table("sync_outbox")
    op.drop_index("ix_external_refs_request_id", table_name="external_refs")
    op.drop_table("external_refs")
    op.drop_index("ix_comments_request_id", table_name="comments")
    op.drop_table("comments")
    op.drop_index("ix_status_updates_request_id", table_name="status_updates")
    op.drop_table("status_updates")
    op.drop_index("ix_request_fields_request_id", table_name="request_fields")
    op.drop_table("request_fields")
    op.drop_index("ix_triage_runs_session_id", table_name="triage_runs")
    op.drop_table("triage_runs")
    op.drop_index("ix_messages_session_id", table_name="messages")
    op.drop_table("messages")
    op.drop_table("intake_sessions")
    op.drop_index("ix_requests_change_lead", table_name="requests")
    op.drop_index("ix_requests_company", table_name="requests")
    op.drop_index("ix_requests_priority", table_name="requests")
    op.drop_index("ix_requests_status", table_name="requests")
    op.drop_index("ix_requests_kind", table_name="requests")
    op.drop_table("requests")
    op.drop_table("users")
