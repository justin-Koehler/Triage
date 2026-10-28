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
from app.services.prose import complete_prose
from app.services.settings_service import get_runtime_config
from app.triage.providers import LlmUnavailable, build_provider, build_provider_from_runtime

MAX_BRIEF = 800
MAX_LINE = 120
MAX_COMMENTS = 5
PROMPT_VERSION = "v4-summary"

# Felder (UI: Body = comment_ablauf, Hub = stand_summary)
BRIEF_KEY = "comment_ablauf"
LINE_KEY = "stand_summary"
DIGEST_KEY = "stand_digest"
SOURCE_KEY = "stand_source"

SYSTEM = """Du fasst die letzten Kommentare zu einem verständlichen Stand zusammen.

Quellen: comments (chronologisch, die letzten fünf), status_updates und ticket. Nur daraus, nichts erfinden.
Der letzte Kommentar ist der aktuelle Stand. Liegt er mit einem älteren im Widerspruch, gilt der letzte:
wurde abgebrochen und später doch nicht, ist es nicht abgebrochen.
Ein Plan, den ein späterer Kommentar aufhebt, bleibt weg, auch wenn der Abbruch danach zurückgenommen wird.
Schreib in eigenen Worten, nicht als Zitat und nicht als Liste der Kommentare.
Denselben Satz nicht zweimal. Kein „Nächster Schritt:“.

brief: 2–3 kurze Sätze. Zuerst, wo es jetzt steht. Dann, was noch offen oder blockiert ist.
line: EIN Satz, der nur den aktuellen Stand sagt.

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
    """Hub-Zeile: immer aus dem Ticket-Stand (Ablauf), damit Liste und Ticket denselben Stand zeigen."""
    brief = _one_line(
        values.get(BRIEF_KEY) or values.get("status_ablauf") or values.get("current_status") or ""
    )
    if brief:
        return brief
    return _one_line(
        values.get(LINE_KEY) or values.get("comment_summary") or values.get("status_summary") or ""
    )


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
    early = status.casefold() in {"", "steckbrief", "entwurf"}
    frame = ""
    if ticket.get("start") and ticket.get("end"):
        frame = f" Zeitraum {ticket['start']} bis {ticket['end']}."
    elif ticket.get("start"):
        frame = f" Start {ticket['start']}."
    first = next(
        (p.strip() for p in _SENTENCE.split(ticket.get("description") or "") if p.strip()),
        "",
    )
    if first:
        # Beschreibung trägt den Stand — Workflow-Stufe nur nennen, wenn sie über Steckbrief hinaus ist.
        head = f"Steht auf {status}. " if status and not early else ""
        brief = f"{head}{first.rstrip('.')}." + frame
        line = (
            _one_line(f"Steht auf {status}: {first}")
            if status and not early
            else _one_line(first)
        )
        return _brief(brief), line
    if status and not early:
        return (
            _brief(f"Steht auf {status}.{frame}"),
            _one_line(f"Steht auf {status}."),
        )
    return (
        _brief(f"Steckbrief liegt vor.{frame} Noch keine Rückmeldung im Ticket."),
        _one_line("Noch keine Rückmeldung."),
    )


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9äöüß]+", "", str(text or "").lower())


def _echoes(a: str, b: str) -> bool:
    """Gleicher oder enthaltener Satz — kurze Wörter zählen nicht als Wiederholung."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    short, long = (na, nb) if len(na) <= len(nb) else (nb, na)
    return len(short) >= 12 and short in long


_STOP = re.compile(
    r"(?<!nicht )(?<!kein )(?<!keine )"
    r"(abgebrochen|abgesagt|gestoppt|eingestellt|pausiert|verschoben|gecancelt)",
    re.I,
)
_FUTURE = re.compile(r"\bstartet\b|\bgeht live\b|go-live", re.I)


def _overruled(core: str, newest: str, older: list[str]) -> bool:
    """Älterer Plan, den der neueste Kommentar aufhebt."""
    if not newest or _echoes(core, newest):
        return False
    if not _STOP.search(newest):
        return False
    if _FUTURE.search(core) and not _STOP.search(core):
        return True
    return any(_echoes(core, old) for old in older)
_STEP_PREFIX = re.compile(
    r"^(nächste[rs]\s+schritt|nächste\s+schritte)\s*:\s*",
    re.I,
)


def _core(sentence: str) -> str:
    return _STEP_PREFIX.sub("", str(sentence or "").strip()).strip()


def _align_to_latest(brief: str, comments: list[dict]) -> str:
    """Ältere Pläne und doppelte Sätze raus, wenn ein neuerer Kommentar sie überholt."""
    newest = str(comments[-1].get("body") or "").strip() if comments else ""
    older = [str(row.get("body") or "").strip() for row in comments[:-1]] if comments else []
    kept: list[str] = []
    for part in _SENTENCE.split(str(brief or "")):
        core = _core(part).rstrip(".")
        if not core:
            continue
        if any(_echoes(core, prev) for prev in kept):
            continue
        if _overruled(core, newest, older):
            continue
        kept.append(core)
    if not kept:
        return ""
    return _brief(". ".join(item.rstrip(".") for item in kept) + ".")


def _drop_stale_next(request: Request, comments: list[dict]) -> None:
    """Gespeicherter nächster Schritt, der nur einen älteren Kommentar wiederholt."""
    if len(comments) < 2 or not request.status_updates:
        return
    newest = str(comments[-1].get("body") or "")
    if not _STOP.search(newest):
        return
    older = [str(row.get("body") or "") for row in comments[:-1]]
    last = max(
        request.status_updates,
        key=lambda item: (
            str(item.reported_on or ""),
            item.created_at.isoformat() if item.created_at else "",
        ),
    )
    step = str(last.next_steps or "").strip()
    if step and _overruled(step, newest, older):
        last.next_steps = ""


_REVERSAL = re.compile(r"doch nicht abgebrochen|nicht abgebrochen|nicht gestoppt|nicht abgesagt", re.I)


def _fallback(comments: list[dict], updates: list[dict]) -> tuple[str, str]:
    """Letzte Kommentare zum aktuellen Stand, nicht als Zitatliste."""
    bodies = [
        " ".join(str(row.get("body") or "").split()).strip()
        for row in comments[-MAX_COMMENTS:]
    ]
    bodies = [body for body in bodies if len(body) > 2]
    newest = bodies[-1] if bodies else ""
    older = bodies[:-1]
    if _REVERSAL.search(newest):
        match = re.search(r"\b((?:es |man )?muss\b.+)$", newest, re.I)
        need = (match.group(1).strip().rstrip(".") if match else "")
        if need[:1].islower():
            need = need[:1].upper() + need[1:]
        brief = "Der Change ist nicht abgebrochen."
        if need:
            brief = f"{brief} {need}."
        return _brief(brief), _one_line(brief)
    bits: list[str] = []
    if newest and not _STOP.search(newest):
        bits.append(newest.rstrip("."))
    elif newest:
        bits.append(newest.rstrip("."))
    for raw in reversed(older):
        if len(bits) >= 2 or _echoes(raw, newest) or _overruled(raw, newest, older):
            continue
        if _STOP.search(newest) and not _STOP.search(raw):
            continue
        bits.append(raw.rstrip("."))
    if not bodies and updates:
        for row in updates:
            core = _core(str(row.get("summary") or "")).rstrip(".")
            if core and not any(_echoes(core, bit) for bit in bits):
                bits.append(core)
    elif updates:
        last = updates[-1]
        for raw in (
            str(last.get("summary") or "").strip(),
            str(last.get("next_steps") or "").strip(),
        ):
            core = _core(raw).rstrip(".")
            if not core or any(_echoes(core, bit) for bit in bits):
                continue
            if _overruled(core, newest, older):
                continue
            bits.append(core)
    if not bits:
        return "", ""
    brief = _brief(". ".join(bits) + ".")
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


def _digest(comments: list[dict], updates: list[dict], ticket: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            {"c": comments, "u": updates, "t": ticket, "v": PROMPT_VERSION},
            ensure_ascii=False,
            sort_keys=True,
        ).encode()
    ).hexdigest()[:16]


def stand_needs_refresh(db: Session, request: Request) -> bool:
    comments, updates = _sources(db, request)
    digest = _digest(comments, updates, _ticket_payload(request))
    stored = (request.field_values().get(DIGEST_KEY) or "").strip()
    return stored not in {digest, f"draft:{digest}"}


def refresh_stand(db: Session, request: Request, *, llm: bool = True) -> dict:
    db.flush()
    comments, _updates = _sources(db, request)
    _drop_stale_next(request, comments)
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

    digest = _digest(comments, updates, ticket)

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
    brief = _align_to_latest(brief, comments) or brief
    # Hub und Ticket teilen denselben Stand: Kurzzeile = erster Satz des Ablaufs.
    if brief:
        line = _one_line(brief)
    elif not line:
        line = ""
    if comments and line:
        newest = str(comments[-1].get("body") or "")
        older = [str(row.get("body") or "") for row in comments[:-1]]
        if _overruled(line, newest, older):
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


NEXT_SYSTEM = """Du nennst, was als Nächstes zu tun ist.

Der neueste Kommentar ist der aktuelle Stand. Hebt er einen älteren Plan auf
(abgebrochen, gestoppt, verschoben), gilt nur noch dieser Stand.
Den überholten Plan nicht wiederholen und nicht als nächsten Schritt nennen.
Nur aus den Angaben. Nichts erfinden, keine Namen oder Termine dazuerfinden.
Ein bis drei kurze Sätze. Keine Überschrift, keine Aufzählungszeichen.
Wenn nichts Offenes erkennbar ist, ein Satz, worauf es jetzt ankommt.
"""


RISK_SYSTEM = """Du schätzt die Risiken zum aktuellen Stand ein.

Das ist nicht die Liste der bekannten Risiken aus dem Steckbrief.
Der neueste Kommentar ist der Stand. Nur was daraus jetzt schiefgehen kann.
Bekannte Risiken nur nennen, wenn sie zu diesem Stand noch gelten.
Wenn nichts darauf hindeutet, genau dieser Satz: Keine aktuellen Risiken.
Ein bis drei kurze Sätze. Keine Überschrift, keine Aufzählung.
"""

NO_CURRENT_RISK = "Keine aktuellen Risiken."


def _stand_lines(request: Request) -> tuple[list, list[str]]:
    values = request.field_values()
    comments = sorted(request.comments or [], key=lambda row: row.created_at or "")
    updates = list(request.status_updates or [])
    lines = [
        f"Titel: {request.steckbrief_name or request.title or ''}".strip(),
        f"Beschreibung: {_brief(request.description or values.get('description') or '', 700)}",
    ]
    for key, label in (
        ("benefit", "Nutzen"),
        ("reason", "Begründung"),
        ("solution", "Lösung"),
    ):
        text = str(values.get(key) or "").strip()
        if text:
            lines.append(f"{label}: {_brief(text, 400)}")
    known = " ".join(
        str(values.get(key) or "").strip()
        for key in ("risks", "risks_obstacles")
        if str(values.get(key) or "").strip()
    ).strip()
    if known:
        lines.append(f"Bekannte Risiken im Steckbrief, nicht der aktuelle Stand: {_brief(known, 400)}")
    recent = comments[-6:]
    for index, row in enumerate(recent):
        body = " ".join(str(row.body or "").split())
        if not body:
            continue
        tag = "Neuester Kommentar, das gilt" if index == len(recent) - 1 else "Älterer Kommentar"
        lines.append(f"{tag}, {row.author_name}: {_brief(body, 300)}")
    return comments, lines


def suggest_status_risks(db: Session, request: Request) -> str:
    """Risiken zum jetzigen Stand, nicht die bekannten Risiken aus dem Steckbrief."""
    _comments, lines = _stand_lines(request)
    provider = build_provider_from_runtime(get_runtime_config(db))
    try:
        text = complete_prose(provider, RISK_SYSTEM, "\n".join(lines))
    except LlmUnavailable:
        text = ""
    text = _brief(" ".join(str(text or "").split()), 500)
    return text or NO_CURRENT_RISK


def suggest_next_steps(db: Session, request: Request) -> str:
    """Nächste Schritte nur aus dem, was auf dem Ticket steht."""
    comments, lines = _stand_lines(request)
    updates = list(request.status_updates or [])
    for item in list(reversed(updates))[-3:]:
        chunk = " ".join(
            part
            for part in (
                str(item.summary or "").strip(),
                str(item.decisions or "").strip(),
                str(item.risks or "").strip(),
            )
            if part
        )
        if chunk:
            lines.append(f"Status: {_brief(chunk, 300)}")
    provider = build_provider_from_runtime(get_runtime_config(db))
    try:
        text = complete_prose(provider, NEXT_SYSTEM, "\n".join(lines))
    except LlmUnavailable:
        text = ""
    newest = " ".join(str(comments[-1].body or "").split()) if comments else ""
    older = [" ".join(str(row.body or "").split()) for row in comments[:-1]]
    kept: list[str] = []
    for part in _SENTENCE.split(text):
        core = _core(part).rstrip(".")
        if not core or _overruled(core, newest, older):
            continue
        if any(_echoes(core, prev) for prev in kept):
            continue
        kept.append(core)
    if not kept:
        return _next_from_comments(comments)
    return _brief(". ".join(kept) + ".", 500)


def _next_from_comments(comments: list) -> str:
    """Wenn das Modell nichts liefert: der offene Punkt aus dem neuesten Kommentar."""
    if not comments:
        return ""
    newest = " ".join(str(comments[-1].body or "").split())
    older = [" ".join(str(row.body or "").split()) for row in comments[:-1]]
    match = re.search(r"\b((?:es |man )?muss\b.+)$", newest, re.I)
    text = (match.group(1) if match else newest).strip()
    if text[:1].islower():
        text = text[:1].upper() + text[1:]
    if text and not text.endswith((".", "!", "?")):
        text += "."
    if not text or _overruled(text, newest, older):
        return ""
    return _brief(text, 500)
