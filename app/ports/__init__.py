from __future__ import annotations

from functools import lru_cache

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.ports.fake import FakeTicketSystem
from app.ports.ticket_port import (
    ExternalIssueRef,
    IssuePayload,
    TicketPort,
    TicketPortError,
)

__all__ = [
    "ExternalIssueRef",
    "IssuePayload",
    "TicketPort",
    "TicketPortError",
    "build_ticket_port",
    "get_ticket_port",
]


def build_ticket_port(settings: Settings | None = None) -> TicketPort:
    settings = settings or get_settings()
    try:
        from app.services.settings_service import get_runtime_config

        runtime = get_runtime_config()
        if runtime.ticket_port == "jira":
            from app.ports.jira_v3 import JiraRestV3

            return JiraRestV3(runtime=runtime, settings=settings)
        return FakeTicketSystem(SessionLocal, project=runtime.jira_project_key or "TRI")
    except Exception:
        if settings.ticket_port == "jira":
            from app.ports.jira_v3 import JiraRestV3

            return JiraRestV3(settings=settings)
        return FakeTicketSystem(SessionLocal, project=settings.jira_project_key or "TRI")


@lru_cache
def get_ticket_port() -> TicketPort:
    return build_ticket_port()
