"""Eigenes Vokabular. Jira-Begriffe haben hier nichts zu suchen."""

from __future__ import annotations

from enum import StrEnum


class RequestKind(StrEnum):
    CHANGE_REQUEST = "change_request"
    IT_REQUEST = "it_request"


class RequestStatus(StrEnum):
    DRAFT = "entwurf"
    STECKBRIEF = "steckbrief"
    IT_REVIEW = "it_abstimmung"
    QG1 = "qg1"
    QG2 = "qg2"
    APPROVED = "freigegeben"
    IN_PROGRESS = "umsetzung"
    DONE = "abgeschlossen"
    REJECTED = "abgelehnt"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SyncState(StrEnum):
    DISABLED = "disabled"
    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"
    DEAD = "dead"


class OutboxOperation(StrEnum):
    CREATE_ISSUE = "create_issue"
    ADD_COMMENT = "add_comment"
    UPDATE_FIELDS = "update_fields"


class TriageSource(StrEnum):
    LLM = "llm"
    HEURISTIC = "heuristic"
    USER_OVERRIDE = "user_override"


KIND_LABELS: dict[RequestKind, str] = {
    RequestKind.CHANGE_REQUEST: "Change Request",
    RequestKind.IT_REQUEST: "IT Request",
}

STATUS_LABELS: dict[RequestStatus, str] = {
    RequestStatus.DRAFT: "Entwurf",
    RequestStatus.STECKBRIEF: "Steckbrief",
    RequestStatus.IT_REVIEW: "IT-Abstimmung",
    RequestStatus.QG1: "QG1",
    RequestStatus.QG2: "QG2",
    RequestStatus.APPROVED: "Freigegeben",
    RequestStatus.IN_PROGRESS: "Umsetzung",
    RequestStatus.DONE: "Abgeschlossen",
    RequestStatus.REJECTED: "Abgelehnt",
}

PRIORITY_LABELS: dict[Priority, str] = {
    Priority.LOW: "Niedrig",
    Priority.MEDIUM: "Mittel",
    Priority.HIGH: "Hoch",
    Priority.CRITICAL: "Kritisch",
}

SYNC_LABELS: dict[SyncState, str] = {
    SyncState.DISABLED: "Kein Sync",
    SyncState.PENDING: "Sync offen",
    SyncState.SYNCED: "Synchronisiert",
    SyncState.FAILED: "Sync fehlgeschlagen",
    SyncState.DEAD: "Sync aufgegeben",
}

LABEL_INTAKE = "triage-intake"
LABEL_INCOMPLETE = "triage-unvollständig"
LABEL_TRIAGE_FAILED = "triage-fehlgeschlagen"

BADGE_INCOMPLETE = "CRITR unvollständig"
BADGE_TRIAGE_FAILED = "CRITR fehlgeschlagen"

# Alte Keys aus YAML, Prompt und Wissensbasis weiter lesen.
LEGACY_INTENT_TO_KIND: dict[str, RequestKind] = {
    "request_change": RequestKind.CHANGE_REQUEST,
    "change": RequestKind.CHANGE_REQUEST,
    "change_request": RequestKind.CHANGE_REQUEST,
    "changerequest": RequestKind.CHANGE_REQUEST,
    "request_it": RequestKind.IT_REQUEST,
    "it_request": RequestKind.IT_REQUEST,
    "it-request": RequestKind.IT_REQUEST,
    "itrequest": RequestKind.IT_REQUEST,
    "it": RequestKind.IT_REQUEST,
    "request_access": RequestKind.IT_REQUEST,
    "support": RequestKind.IT_REQUEST,
}


def parse_kind(value: object) -> RequestKind | None:
    if value is None:
        return None
    return LEGACY_INTENT_TO_KIND.get(str(value).strip().lower().replace(" ", "_"))


def parse_priority(value: object) -> Priority | None:
    if value is None:
        return None
    raw = str(value).strip().lower()
    aliases = {
        "niedrig": Priority.LOW,
        "mittel": Priority.MEDIUM,
        "hoch": Priority.HIGH,
        "kritisch": Priority.CRITICAL,
        "blocker": Priority.CRITICAL,
    }
    if raw in aliases:
        return aliases[raw]
    try:
        return Priority(raw)
    except ValueError:
        return None


def kind_label(kind: RequestKind | str | None) -> str:
    parsed = parse_kind(kind) if not isinstance(kind, RequestKind) else kind
    return KIND_LABELS[parsed] if parsed else "Change Request"
