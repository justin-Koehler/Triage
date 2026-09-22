"""Aktueller Stand: ein Briefing aus Kommentaren + Status (eine LLM-Stufe)."""

from __future__ import annotations

import hashlib
import json
import re

from sqlalchemy.orm import Session

from app.domain.fieldspec import get_rules
from app.domain.types import RequestKind, parse_kind
from app.models import Request
from app.services import requests_service as svc
from app.triage.providers import LlmUnavailable, build_provider

MAX_BRIEF = 800
MAX_LINE = 120
MAX_COMMENTS = 5
PROMPT_VERSION = "v2-last5"

# Felder (UI: Body = comment_ablauf, Hub = stand_summary)
BRIEF_KEY = "comment_ablauf"
LINE_KEY = "stand_summary"
DIGEST_KEY = "stand_digest"
SOURCE_KEY = "stand_source"

SYSTEM = """Du schreibst ein kurzes Briefing zum aktuellen Stand eines Changes.

Quellen: comments (nur die letzten fünf), status_updates und ticket. Nur daraus schöpfen, nichts erfinden.
Der neueste Kommentar wiegt am schwersten. Offene Aufgaben nicht auflisten.
Gibt es weder Kommentare noch Status-Einträge, beschreibe knapp den Stand aus dem ticket
(Vorhaben, Workflow-Status, Zeitraum) und sag klar, dass noch keine Rückmeldung vorliegt.
Erfinde keinen Fortschritt.

brief: 2–4 kurze Hauptsätze als Fließtext.
  Als würde ein Kollege dich gerade updaten: Wo stehen wir jetzt? Was ist geklärt? Was läuft oder blockiert?
  Keine Chronik, keine „Danach/Anschließend“, keine Stichpunkte, keine Autor:Text-Zitate.

line: EIN kurzer Satz für die Übersichtsliste (aktueller Stand).

JSON: {"brief": "...", "line": "..."}"""

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _one_line(text: str, limit: int = MAX_LINE) -> str:
    raw = " ".join(str(text or "").split()).strip()
    if not raw:
        return ""
    first = next((p.strip() for p in _SENTENCE.split(raw) if p.strip()), raw)
    if not first.endswith((".", "!", "?")):
        first = f"{first.rstrip('.,;:· ')}."
    if len(first) <= limit:
        return first
    cut = first[:limit].rsplit(" ", 1)[0].rstrip(".,;:· ")
    return f"{(cut or first[:limit].rstrip())}."


def _brief(text: str, limit: int = MAX_BRIEF) -> str:
    raw = " ".join(str(text or "").split()).strip()
    if not raw:
        return ""
    if len(raw) <= limit:
        return raw
    cut = raw[:limit].rsplit(" ", 1)[0].rstrip(".,;:· ")
    return cut or raw[:limit]


def list_stand(values: dict[str, str]) -> str:
    line = _one_line(values.get(LINE_KEY) or values.get("comment_summary") or values.get("status_summary") or "")
    if line:
        return line
    return _one_line(values.get(BRIEF_KEY) or values.get("status_ablauf") or values.get("current_status") or "")


STAND_HEALTH = {
    "green": "Im Plan",
    "blue": "Im Blick behalten",
    "yellow": "Kritisch",
    "red": "Überzogen",
    "white": "On hold",
    "done": "Done",
}

_HEALTH_ALIASES = {
    "green": "green",
    "grün": "green",
    "gruen": "green",
    "blue": "blue",
    "blau": "blue",
    "yellow": "yellow",
    "gelb": "yellow",
    "amber": "yellow",
    "red": "red",
    "rot": "red",
    "white": "white",
    "hold": "white",
    "onhold": "white",
    "on_hold": "white",
    "done": "done",
    "fertig": "done",
    "erledigt": "done",
}


def normalize_stand_health(raw: str | None) -> str:
    key = re.sub(r"[\s\-]+", "", str(raw or "").strip().lower())
    return _HEALTH_ALIASES.get(key) or _HEALTH_ALIASES.get(str(raw or "").strip().lower()) or "green"


def stand_health(request: Request) -> dict[str, str]:
    """Ampel fürs Ticket: gespeicherter Wert → Workflow Done → letzter Status-RAG."""
    from app.domain.types import RequestStatus

    values = request.field_values()
    stored = normalize_stand_health(values.get("stand_health"))
    if (values.get("stand_health") or "").strip():
        key = stored
    elif str(request.status or "") == RequestStatus.DONE.value:
        key = "done"
    else:
        updates = list(request.status_updates or [])
        rag = updates[0].overall_rag if updates else "green"
        key = normalize_stand_health(rag)
    return {"key": key, "label": STAND_HEALTH.get(key, STAND_HEALTH["green"])}


SOURCE_LABELS = {
    "combined": "Status und Kommentare",
    "comments": "Kommentare",
    "status": "Status",
    "ticket": "Ticketdaten",
}


def stand_trust(values: dict[str, str]) -> dict[str, str]:
    brief = _brief(values.get(BRIEF_KEY) or values.get("status_ablauf") or "")
    line = list_stand(values)
    stored = str(values.get(SOURCE_KEY) or "").strip().lower()
    if stored in SOURCE_LABELS:
        source, label = stored, SOURCE_LABELS[stored]
    else:
        has_comments = bool((values.get(BRIEF_KEY) or "").strip())
        has_status = bool((values.get("status_ablauf") or values.get("current_status") or "").strip())
        if has_comments and has_status:
            source, label = "combined", SOURCE_LABELS["combined"]
        elif has_comments:
            source, label = "comments", SOURCE_LABELS["comments"]
        elif has_status:
            source, label = "status", SOURCE_LABELS["status"]
        else:
            source, label = "", ""
    return {
        "summary": line,
        "source": source,
        "sourceLabel": label,
        "statusBlurb": _one_line(values.get("status_summary") or ""),
        "commentBlurb": _one_line(values.get("comment_summary") or ""),
        "brief": brief,
    }


def _sources(db: Session, request: Request) -> tuple[list[dict], list[dict]]:
    """Nur die letzten fünf Kommentare zählen für den Stand."""
    from app.services.comment_summary import comments_payload_for
    from app.services.status_summary import _updates_payload

    comments = comments_payload_for(db, request)[-MAX_COMMENTS:]
    updates = _updates_payload(request)
    return comments, updates


def _ticket_payload(request: Request) -> dict[str, str]:
    """Der Change selbst — trägt den Stand, solange nichts gemeldet wurde."""
    from app.domain.types import STATUS_LABELS, RequestStatus

    values = request.field_values()
    try:
        status_label = STATUS_LABELS[RequestStatus(request.status)]
    except (ValueError, KeyError):
        status_label = str(request.status or "")
    raw_body = str(values.get("description") or request.description or "")
    body = " ".join(raw_body.split())
    return {
        "title": str(request.steckbrief_name or request.title or "").strip(),
        "workflow_status": status_label,
        "description": _brief(body, 600),
        "start": str(values.get("start_date") or "").strip(),
        "end": str(values.get("end_date") or "").strip(),
    }


def _ticket_fallback(ticket: dict[str, str]) -> tuple[str, str]:
    """Ohne Kommentare und Status: knapper, ehrlicher Satz aus den Ticketdaten."""
    status = (ticket.get("workflow_status") or "").strip()
    frame = ""
    if ticket.get("start") and ticket.get("end"):
        frame = f" Zeitraum {ticket['start']} bis {ticket['end']}."
    elif ticket.get("start"):
        frame = f" Start {ticket['start']}."
    head = f"Steht auf {status}" if status else "Steckbrief liegt vor"
    first = next(
        (p.strip() for p in _SENTENCE.split(ticket.get("description") or "") if p.strip()),
        "",
    )
    body = f" {first.rstrip('.')}." if first else ""
    brief = f"{head}.{body}{frame} Noch keine Rückmeldung im Ticket."
    return _brief(brief), _one_line(f"{head}, noch keine Rückmeldung.")


def _fallback(comments: list[dict], updates: list[dict]) -> tuple[str, str]:
    """Nur die neuesten Signale — neuester Kommentar zuerst."""
    bits: list[str] = []
    if comments:
        for row in reversed(comments[-2:]):
            body = str(row.get("body") or "").strip().rstrip(".")
            if body:
                bits.append(body)
    if updates:
        last = updates[-1]
        chunk = " ".join(
            part
            for part in (
                str(last.get("summary") or "").strip(),
                f"Nächster Schritt: {last['next_steps']}" if last.get("next_steps") else "",
            )
            if part
        )
        if chunk:
            bits.append(chunk.rstrip("."))
    if not bits:
        return "", ""
    brief = _brief(". ".join(bits) + ".")
    # line = neuester Kommentar (erstes Bit), sonst letztes Signal
    return brief, _one_line(bits[0])


def _clear(db: Session, request: Request) -> None:
    spec = get_rules().spec(parse_kind(request.kind) or RequestKind.CHANGE_REQUEST).field_map()
    labels = {
        BRIEF_KEY: "Kommentar-Ablauf",
        "comment_summary": "Kommentar-Kurzfassung",
        "comment_digest": "Kommentar-Digest",
        "status_ablauf": spec["status_ablauf"].label if "status_ablauf" in spec else "Ablauf",
        "current_status": spec["current_status"].label if "current_status" in spec else "Was gerade los ist",
        "status_summary": spec["status_summary"].label if "status_summary" in spec else "KI-Zusammenfassung",
        "status_digest": "Status-Digest",
        LINE_KEY: "Aktueller Stand",
        DIGEST_KEY: "Stand-Digest",
        SOURCE_KEY: "Stand-Quelle",
    }
    for key, label in labels.items():
        svc._upsert_field(db, request, key, label, "")


def _persist(
    db: Session,
    request: Request,
    *,
    brief: str,
    line: str,
    digest: str,
    source: str = "",
) -> None:
    spec = get_rules().spec(parse_kind(request.kind) or RequestKind.CHANGE_REQUEST).field_map()
    svc._upsert_field(db, request, BRIEF_KEY, "Kommentar-Ablauf", brief)
    svc._upsert_field(db, request, "comment_summary", "Kommentar-Kurzfassung", line)
    svc._upsert_field(db, request, "comment_digest", "Kommentar-Digest", digest)
    svc._upsert_field(
        db,
        request,
        "status_ablauf",
        spec["status_ablauf"].label if "status_ablauf" in spec else "Ablauf",
        brief,
    )
    svc._upsert_field(
        db,
        request,
        "current_status",
        spec["current_status"].label if "current_status" in spec else "Was gerade los ist",
        brief,
    )
    svc._upsert_field(
        db,
        request,
        "status_summary",
        spec["status_summary"].label if "status_summary" in spec else "KI-Zusammenfassung",
        line,
    )
    svc._upsert_field(db, request, "status_digest", "Status-Digest", digest)
    svc._upsert_field(db, request, LINE_KEY, "Aktueller Stand", line)
    svc._upsert_field(db, request, DIGEST_KEY, "Stand-Digest", digest)
    svc._upsert_field(db, request, SOURCE_KEY, "Stand-Quelle", source)
    db.flush()


def backfill_missing(db: Session, *, limit: int = 5, llm: bool = True) -> int:
    """Tickets ohne Stand nachziehen — etwa wenn sie nur über Jira hereinkamen."""
    from sqlalchemy import select

    done = 0
    for request in db.scalars(select(Request).order_by(Request.updated_at.desc())).all():
        if done >= limit:
            break
        if (request.field_values().get(LINE_KEY) or "").strip():
            continue
        try:
            if (refresh_stand(db, request, llm=llm).get("line") or "").strip():
                done += 1
        except Exception:
            continue
    return done


def refresh_stand(db: Session, request: Request, *, llm: bool = True) -> dict:
    db.flush()
    comments, updates = _sources(db, request)
    ticket = _ticket_payload(request)
    ticket_only = not comments and not updates
    # Ohne jede Substanz gibt es keinen Stand — sonst trägt das Ticket ihn selbst.
    if ticket_only and not (ticket["description"] or ticket["workflow_status"]):
        _clear(db, request)
        db.flush()
        return {"ablauf": "", "summary": "", "brief": "", "line": "", "unchanged": True}

    if comments and updates:
        source = "combined"
    elif comments:
        source = "comments"
    elif updates:
        source = "status"
    else:
        source = "ticket"

    digest = hashlib.sha256(
        json.dumps(
            {"c": comments, "u": updates, "t": ticket, "v": PROMPT_VERSION},
            ensure_ascii=False,
            sort_keys=True,
        ).encode()
    ).hexdigest()[:16]

    values = request.field_values()
    cached_brief = (values.get(BRIEF_KEY) or "").strip()
    cached_line = (values.get(LINE_KEY) or values.get("comment_summary") or "").strip()
    # Nur vollständige LLM-Läufe cachen — llm=False darf den Digest nicht „besetzen“
    if llm and values.get(DIGEST_KEY) == digest and cached_brief and cached_line:
        return {
            "ablauf": cached_brief,
            "summary": cached_line,
            "brief": cached_brief,
            "line": cached_line,
            "unchanged": True,
        }

    brief = ""
    line = ""
    if llm:
        try:
            raw = build_provider().complete_json(
                SYSTEM,
                json.dumps(
                    {
                        "title": request.steckbrief_name or request.title,
                        "comments": comments,
                        "status_updates": updates,
                        "ticket": ticket,
                    },
                    ensure_ascii=False,
                ),
            )
            brief = _brief(str(raw.get("brief") or raw.get("ablauf") or ""))
            line = _one_line(str(raw.get("line") or raw.get("summary") or ""))
        except (LlmUnavailable, Exception):
            brief, line = "", ""

    if not brief or not line:
        fb_brief, fb_line = (
            _ticket_fallback(ticket) if ticket_only else _fallback(comments, updates)
        )
        brief = brief or fb_brief
        line = line or fb_line
    if not line and brief:
        line = _one_line(brief)

    # Digest nur speichern, wenn LLM lief (oder kein LLM verfügbar → Fallback final)
    store_digest = digest if llm else f"draft:{digest}"
    _persist(db, request, brief=brief, line=line, digest=store_digest, source=source)
    return {
        "ablauf": brief,
        "summary": line,
        "brief": brief,
        "line": line,
        "unchanged": False,
    }
