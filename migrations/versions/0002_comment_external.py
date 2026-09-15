"""comments.external_id für Jira-Kommentar-Sync

Revision ID: 0002_comment_external
Revises: 0001_initial
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_comment_external"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("comments", sa.Column("external_id", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("comments", "external_id")
