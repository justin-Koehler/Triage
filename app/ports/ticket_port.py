"""Vertrag zu Fremdsystemen. Domain rein, Fremd-Key raus — nie umgekehrt."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.domain.types import Priority, RequestKind


class TicketPortError(RuntimeError):
    """Fremdsystem hat nicht mitgespielt. Job bleibt in der Outbox."""

    def __init__(self, message: str, *, rejected_fields: list[str] | None = None) -> None:
        super().__init__(message)
        self.rejected_fields = list(rejected_fields or [])


@dataclass
class IssuePayload:
    request_id: str
    reference: str
    kind: RequestKind
    priority: Priority
    title: str
    steckbrief_name: str
    description: str
    fields: dict[str, str] = field(default_factory=dict)
    labels: list[str] = field(default_factory=list)
    created_by: str | None = None
    reporter_hint: str | None = None
    user_jira_token: str | None = None
    user_jira_email: str | None = None


@dataclass
class ExternalIssueRef:
    key: str
    url: str


class TicketPort(Protocol):
    system: str

    def create_issue(self, payload: IssuePayload) -> ExternalIssueRef: ...

    def add_comment(self, key: str, body: str, author: str) -> None: ...

    def update_fields(
        self,
        key: str,
        fields: dict[str, str],
        priority: Priority | None = None,
        *,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> None: ...

    def search_similar(self, text: str, limit: int = 5) -> list[dict[str, str]]: ...

    def get_issue(self, key: str) -> dict[str, Any] | None: ...
