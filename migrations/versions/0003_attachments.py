"""request_attachments für Jira-Anhänge

Revision ID: 0003_attachments
Revises: 0002_comment_external
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_attachments"
down_revision = "0002_comment_external"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "request_attachments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("request_id", sa.String(length=36), sa.ForeignKey("requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("author_name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("request_id", "external_id", name="uq_request_attachment_ext"),
    )
    op.create_index("ix_request_attachments_request_id", "request_attachments", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_request_attachments_request_id", table_name="request_attachments")
    op.drop_table("request_attachments")
