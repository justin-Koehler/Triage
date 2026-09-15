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

    def add_attachment(
        self,
        key: str,
        filename: str,
        content: bytes,
        content_type: str = "text/csv",
        *,
        user_token: str | None = None,
        user_email: str | None = None,
        replace_same_name: bool = True,
        strip_kalk: bool = True,
    ) -> list[dict[str, Any]]:
        with self._session_factory() as db:
            issue = db.get(FakeExternalIssue, key)
            if not issue:
                raise TicketPortError(f"unbekannter Key {key}")
            skip = {(filename or "").strip().lower()} if replace_same_name else set()
            if strip_kalk:
                skip.update({"kalkulation.xlsx", "kalkulation.csv"})
            files = []
            for item in list(issue.fields.get("attachments") or []):
                low = str(item.get("filename") or "").strip().lower()
                if low in skip:
                    continue
                if strip_kalk and (
                    low.endswith("-kalkulation.xlsx") or low.endswith("-kalkulation.csv")
                ):
                    continue
                files.append(item)
            aid = f"a-{len(files) + 1}-{len(content or b'')}"
            row = {
                "id": aid,
                "filename": filename,
                "contentType": content_type,
                "mimeType": content_type,
                "size": len(content or b""),
                "author": "fake",
                "created": datetime.now(UTC).isoformat(),
                "content": bytes(content or b""),
            }
            files.append(row)
            issue.fields = dict(issue.fields) | {"attachments": files}
            db.commit()
            return [
                {
                    "id": aid,
                    "filename": filename,
                    "mimeType": content_type,
                    "size": len(content or b""),
                    "author": "fake",
                    "created": row["created"],
                }
            ]

    def add_comment(self, key: str, body: str, author: str) -> str | None:
        with self._session_factory() as db:
            issue = db.get(FakeExternalIssue, key)
            if not issue:
                raise TicketPortError(f"unbekannter Key {key}")
            comment_id = f"c-{len(issue.comments) + 1}"
            issue.comments = [
                *issue.comments,
                {
                    "id": comment_id,
                    "author": author,
                    "body": body,
                    "created": datetime.now(UTC).isoformat(),
                },
            ]
            db.commit()
            return comment_id

    def list_comments(
        self,
        key: str,
        *,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._session_factory() as db:
            issue = db.get(FakeExternalIssue, (key or "").strip().upper())
            if not issue:
                return []
            return [
                {
                    "id": str(c.get("id") or ""),
                    "author": str(c.get("author") or ""),
                    "body": str(c.get("body") or ""),
                    "created": str(c.get("created") or ""),
                }
                for c in (issue.comments or [])
                if str(c.get("id") or "").strip()
            ]

    def list_attachments(
        self,
        key: str,
        *,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._session_factory() as db:
            issue = db.get(FakeExternalIssue, (key or "").strip().upper())
            if not issue:
                return []
            files = list((issue.fields or {}).get("attachments") or [])
            return [
                {
                    "id": str(f.get("id") or ""),
                    "filename": str(f.get("filename") or f.get("name") or "anhang"),
                    "mimeType": str(f.get("mimeType") or f.get("contentType") or ""),
                    "size": int(f.get("size") or 0),
                    "author": str(f.get("author") or ""),
                    "created": str(f.get("created") or ""),
                    "content": f.get("content") or b"",
                }
                for f in files
                if str(f.get("id") or "").strip()
            ]

    def download_attachment(
        self,
        attachment_id: str,
        *,
        user_token: str | None = None,
        user_email: str | None = None,
        thumbnail: bool = False,
    ) -> tuple[bytes, str, str]:
        aid = str(attachment_id or "").strip()
        with self._session_factory() as db:
            rows = db.scalars(select(FakeExternalIssue)).all()
            for issue in rows:
                for f in list((issue.fields or {}).get("attachments") or []):
                    if str(f.get("id") or "") != aid:
                        continue
                    raw = f.get("content")
                    data = raw if isinstance(raw, (bytes, bytearray)) else b""
                    name = str(f.get("filename") or f.get("name") or "anhang")
                    ctype = str(f.get("mimeType") or f.get("contentType") or "application/octet-stream")
                    if thumbnail:
                        return bytes(data[:200] or b"thumb"), f"thumb-{name}", "image/png"
                    return bytes(data), name, ctype
        raise TicketPortError(f"Anhang {aid} unbekannt")

    def delete_comment(
        self,
        key: str,
        comment_id: str,
        *,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> None:
        with self._session_factory() as db:
            issue = db.get(FakeExternalIssue, key)
            if not issue:
                raise TicketPortError(f"unbekannter Key {key}")
            cid = str(comment_id or "").strip()
            issue.comments = [c for c in issue.comments if str(c.get("id") or "") != cid]
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

    def _inbox_item(self, issue: FakeExternalIssue) -> dict[str, Any]:
        fields = dict(issue.fields or {})
        values = {
            "title": issue.summary,
            "description": issue.description or "",
        }
        for key, raw in fields.items():
            if isinstance(raw, (str, int, float)):
                values[key] = str(raw)
        return {
            "key": issue.key,
            "title": issue.summary,
            "status": str(fields.get("status") or "Offen"),
            "priority": (issue.priority or "medium").lower(),
            "kind": "it_request" if "it" in (issue.issue_type or "").lower() else "change_request",
            "updatedAt": issue.updated_at.isoformat() if issue.updated_at else "",
            "url": f"/external/{issue.key}",
            "values": values,
        }

    def list_issues(
        self,
        *,
        query: str = "",
        limit: int = 50,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> list[dict[str, Any]]:
        needle = (query or "").strip().lower()
        with self._session_factory() as db:
            stmt = select(FakeExternalIssue).order_by(FakeExternalIssue.updated_at.desc())
            if needle:
                stmt = stmt.where(func.lower(FakeExternalIssue.summary).contains(needle))
            rows = db.scalars(stmt.limit(limit)).all()
        return [self._inbox_item(row) for row in rows]

    def inbox_issue(
        self,
        key: str,
        *,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> dict[str, Any] | None:
        with self._session_factory() as db:
            issue = db.get(FakeExternalIssue, (key or "").strip().upper())
            if not issue:
                return None
            return self._inbox_item(issue)

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
