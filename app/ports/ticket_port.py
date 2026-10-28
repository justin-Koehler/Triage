"""Vertrag zu Fremdsystemen. Domain rein, Fremd-Key raus — nie umgekehrt."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.domain.types import Priority, RequestKind


# Stand, Ablauf und Kommentarzusammenfassung bleiben in CRITR.
# Sie haben kein Jira-Feld und dürfen die Beschreibung nicht auffüllen.
DESCRIPTION_OMIT_KEYS = frozenset(
    {
        "current_status",
        "status_summary",
        "status_digest",
        "status_ablauf",
        "comment_digest",
        "comment_ablauf",
        "comment_summary",
        "stand_digest",
        "stand_summary",
        "stand_health",
        # Teilkosten bleiben lokal; Gesamtsumme geht nach Jira Costs.
        "costs",
        "material_costs",
        # Betrieb-PT und Aufschlüsselungen nicht in die Jira-Beschreibung.
        "operate_scs_pt",
        "operate_cit_pt",
        "operate_scs_pt_detail",
        "operate_cit_pt_detail",
        "operate_scs_material",
        "operate_cit_material",
        "operate_cit_released_pt",
    }
)

# Meta-Zeilen, die früher in die Beschreibung geschrieben wurden.
_DESCRIPTION_META_LINE = re.compile(
    r"^(Steckbrief-Name|Interne Referenz|Betrieb PT Plan(?: SCS| CIT)?|"
    r"Erstellt von)\s*:",
    re.IGNORECASE,
)


def clean_description_lead(raw: str) -> str:
    """Meta-Zeilen entfernen, Freitext und CRITR-Links behalten."""
    text = str(raw or "").strip()
    if not text:
        return ""
    kept: list[str] = []
    for line in text.splitlines():
        if _DESCRIPTION_META_LINE.match(line.strip()):
            continue
        kept.append(line)
    # Überzählige Leerzeilen nach dem Strip zusammenziehen.
    out = "\n".join(kept).strip()
    return re.sub(r"\n{3,}", "\n\n", out)


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

    def add_comment(self, key: str, body: str, author: str) -> str | None: ...

    def list_comments(
        self,
        key: str,
        *,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> list[dict[str, Any]]: ...

    def delete_comment(
        self,
        key: str,
        comment_id: str,
        *,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> None: ...

    def list_attachments(
        self,
        key: str,
        *,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> list[dict[str, Any]]: ...

    def download_attachment(
        self,
        attachment_id: str,
        *,
        user_token: str | None = None,
        user_email: str | None = None,
        thumbnail: bool = False,
    ) -> tuple[bytes, str, str]: ...

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
    ) -> list[dict[str, Any]]: ...

    def update_fields(
        self,
        key: str,
        fields: dict[str, str],
        priority: Priority | None = None,
        *,
        user_token: str | None = None,
        user_email: str | None = None,
        request_id: str | None = None,
    ) -> None: ...

    def search_similar(self, text: str, limit: int = 5) -> list[dict[str, str]]: ...

    def get_issue(self, key: str) -> dict[str, Any] | None: ...

    def list_issues(
        self,
        *,
        query: str = "",
        limit: int = 50,
        include_closed: bool = False,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> list[dict[str, Any]]: ...

    def inbox_issue(
        self,
        key: str,
        *,
        user_token: str | None = None,
        user_email: str | None = None,
    ) -> dict[str, Any] | None: ...
