"""Fake-Fremdsystem mit eigenem Key-Raum und eigener Tabelle.

Absicht: sich wie Jira verhalten, damit der Austausch gegen JiraRestV3 nichts
am Rest des Systems aendert. Enthaelt bewusst keine Domain-Logik.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.types import KIND_LABELS, Priority
from app.models import FakeExternalIssue
from app.ports.ticket_port import ExternalIssueRef, IssuePayload, TicketPortError


class FakeTicketSystem:
    system = "fake"

    def __init__(self, session_factory: Callable[[], Session], project: str = "TRI") -> None:
        self._session_factory = session_factory
        self._project = project

    def _next_key(self, db: Session) -> str:
        count = db.scalar(select(func.count()).select_from(FakeExternalIssue)) or 0
        return f"{self._project}-{1001 + int(count)}"

    def create_issue(self, payload: IssuePayload) -> ExternalIssueRef:
        with self._session_factory() as db:
            key = self._next_key(db)
            db.add(
                FakeExternalIssue(
                    key=key,
                    issue_type=KIND_LABELS[payload.kind],
                    summary=payload.title,
                    description=payload.description,
                    priority=payload.priority.value.capitalize(),
                    labels=list(payload.labels),
                    fields=dict(payload.fields) | {"reference": payload.reference},
                    comments=[],
                )
            )
            db.commit()
        return ExternalIssueRef(key=key, url=f"/external/{key}")

    def add_comment(self, key: str, body: str, author: str) -> None:
        with self._session_factory() as db:
            issue = db.get(FakeExternalIssue, key)
            if not issue:
                raise TicketPortError(f"unbekannter Key {key}")
            issue.comments = [
                *issue.comments,
                {"author": author, "body": body, "created": datetime.now(UTC).isoformat()},
            ]
            db.commit()

    def update_fields(
        self,
        key: str,
        fields: dict[str, str],
        priority: Priority | None = None,
        *,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> None:
        with self._session_factory() as db:
            issue = db.get(FakeExternalIssue, key)
            if not issue:
                raise TicketPortError(f"unbekannter Key {key}")
            issue.fields = dict(issue.fields) | dict(fields)
            if "summary" in fields:
                issue.summary = fields["summary"]
            if priority:
                issue.priority = priority.value.capitalize()
            db.commit()

    def search_similar(self, text: str, limit: int = 5) -> list[dict[str, str]]:
        needle = text.strip().lower()[:24]
        if not needle:
            return []
        with self._session_factory() as db:
            rows = db.scalars(
                select(FakeExternalIssue)
                .where(func.lower(FakeExternalIssue.summary).contains(needle))
                .limit(limit)
            ).all()
        return [{"key": row.key, "summary": row.summary} for row in rows]

    def get_issue(self, key: str) -> dict[str, Any] | None:
        with self._session_factory() as db:
            issue = db.get(FakeExternalIssue, key.upper())
            if not issue:
                return None
            return {
                "key": issue.key,
                "issueType": issue.issue_type,
                "summary": issue.summary,
                "description": issue.description,
                "priority": issue.priority,
                "labels": list(issue.labels),
                "fields": dict(issue.fields),
                "comments": list(issue.comments),
                "created": issue.created_at.isoformat(),
                "updated": issue.updated_at.isoformat(),
            }
