"""Was gerade los ist: KI-Fassung aus dem ganzen Status-Tab. Nichts erfinden."""

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

MAX_STATUS = 2500
MAX_BLURB = 90
MAX_ENTRIES = 40
DIGEST_KEY = "status_digest"
PROMPT_VERSION = "v6-split"

RAG_LABELS = {
    "green": "grün",
    "yellow": "gelb",
    "amber": "gelb",
    "red": "rot",
    "blue": "blau",
}

SYSTEM = """Du schreibst zwei Texte zum Status eines Changes.

Quelle: alle Status-Einträge (Datum, Ampel, Satz, nächster Schritt, Risiko). Nichts erfinden.
summary: eine Zeile, maximal 12 Wörter, nur der letzte Stand. Für Titel und Liste.
ablauf: detaillierter Fließtext, chronologisch ältester zuerst, neuester zuletzt.
Jeder inhaltliche Eintrag kommt im Ablauf vor. Ampel, nächster Schritt und Risiko mitnehmen, wenn sie stehen.
Verstehe die Logik: Frage und spätere Antwort sind ein Vorgang, in Zeitreihenfolge.
Kurze Hauptsätze. Ein Gedanke pro Satz. Kein Schachtelsatz.
Deutsche Orthografie mit Umlauten und ß.

Gut: „Heilbronn wurde nach den Kosten gefragt. Rückmeldung: 5 Euro.“
Schlecht: „wurde gefragt und gewartet, woraufhin mitgeteilt wurde, dass Heilbronn 5 Euro sagte.“

Datum nennen, wenn es den Schritt datiert (z. B. am 17.08.2026).
Kein Satz über fehlende Historie. Kein „Anfangs wurde das Projekt gestartet“, wenn das nicht im Eintrag steht.
Keine Floskeln. Keine Stichpunkte.

JSON: {"ablauf": "...", "summary": "..."}"""

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_EMPTY_PAST = re.compile(
    r"(?i)"
    r"(keine|kein|nichts|nicht).{0,48}"
    r"(aktivit|eintr[aä]g|dokument|historie|verlauf|status)"
)
_STARTED_PAD = re.compile(
    r"(?i)\b(anfangs|zu beginn|zunächst|zunaechst)\b.{0,40}\b(gestartet|begonnen|gestartet wurde)\b"
)


class StatusEmpty(ValueError):
    """Keine Status-Eintraege zum Zusammenfassen."""


def _clip(text: str, limit: int) -> str:
    raw = " ".join(str(text or "").split()).strip()
    if not raw:
        return ""
    if len(raw) <= limit:
        return raw
    cut = raw[: limit - 1].rsplit(" ", 1)[0]
    return f"{cut}…"


def _fallback_summary(text: str) -> str:
    parts = [p.strip() for p in _SENTENCE.split(text.strip()) if p.strip()]
    first = parts[0] if parts else text.strip()
    return _clip(first, MAX_BLURB)


def _fallback_prose(texts: list[str]) -> str:
    """Neueste zuerst, dann Vergangenheit. Ein Fliesstext ohne KI."""
    seen: list[str] = []
    lowered: set[str] = set()
    for raw in texts:
        line = " ".join(str(raw or "").split())
        key = line.lower()
        if not line or key in lowered:
            continue
        seen.append(line.rstrip("."))
        lowered.add(key)
    return _clip(". ".join(seen) + ("." if seen else ""), MAX_STATUS)


def _strip_filler(text: str) -> str:
    """Keine Saetze ueber leere Vergangenheit oder 'Projekt gestartet'."""
    parts = [p.strip() for p in _SENTENCE.split(str(text or "").strip()) if p.strip()]
    kept: list[str] = []
    for part in parts:
        low = part.lower()
        if _EMPTY_PAST.search(low) or _STARTED_PAD.search(low):
            continue
        kept.append(part if part[-1] in ".!?" else f"{part}.")
    return _clip(" ".join(kept), MAX_STATUS)


def _sorted_updates(request: Request, *, newest_first: bool = True) -> list:
    return sorted(
        request.status_updates,
        key=lambda u: (u.reported_on or "", u.created_at.isoformat() if u.created_at else ""),
        reverse=newest_first,
    )


def _entry_body(item) -> str:
    chunks = []
    summary = str(item.summary or "").strip()
    if summary:
        chunks.append(summary)
    next_steps = str(item.next_steps or "").strip()
    if next_steps:
        chunks.append(f"Nächster Schritt: {next_steps}")
    risks = str(item.risks or "").strip()
    if risks:
        chunks.append(f"Risiko: {risks}")
    decisions = str(item.decisions or "").strip()
    if decisions:
        chunks.append(decisions)
    return "\n".join(chunks)


def _updates_payload(request: Request) -> list[dict]:
    rows = []
    for item in _sorted_updates(request, newest_first=False)[:MAX_ENTRIES]:
        if not _entry_body(item):
            continue
        rows.append(
            {
                "date": _format_day(item.reported_on),
                "rag": _rag_label(item.overall_rag),
                "summary": item.summary or "",
                "next_steps": item.next_steps or "",
                "risks": item.risks or "",
            }
        )
    return rows


def _rag_label(value: str) -> str:
    key = str(value or "").strip().lower()
    return RAG_LABELS.get(key, key or "—")


def _format_day(raw: str) -> str:
    text = str(raw or "").strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return f"{text[8:10]}.{text[5:7]}.{text[:4]}"
    return text


def status_tab_text(request: Request, *, newest_first: bool = True) -> str:
    """Status-Tab: Datum, Ampel, Text."""
    blocks = []
    for item in _sorted_updates(request, newest_first=newest_first)[:MAX_ENTRIES]:
        body = _entry_body(item)
        if not body:
            continue
        head = f"{item.reported_on or '—'} · {_rag_label(item.overall_rag)}"
        blocks.append(f"{head}\n{body}")
    return "\n\n".join(blocks)


def _update_texts(request: Request, *, newest_first: bool = True) -> list[str]:
    return [
        body
        for item in _sorted_updates(request, newest_first=newest_first)
        if (body := _entry_body(item))
    ]


def _fallback_ablauf(request: Request) -> str:
    """Chronologisch, aeltester zuerst. Ohne KI."""
    parts: list[str] = []
    seen: set[str] = set()
    for item in _sorted_updates(request, newest_first=False):
        body = " ".join(_entry_body(item).split())
        if not body:
            continue
        key = body.lower()
        if key in seen:
            continue
        seen.add(key)
        day = _format_day(item.reported_on)
        chunk = f"{day}: {body.rstrip('.')}" if day else body.rstrip(".")
        parts.append(chunk)
    return _clip(". ".join(parts) + ("." if parts else ""), MAX_STATUS)


def _digest(tab: str) -> str:
    return hashlib.sha256(f"{PROMPT_VERSION}\n{tab}".encode()).hexdigest()[:16]


def list_blurb(values: dict[str, str]) -> str:
    return _clip((values.get("status_summary") or "").strip(), MAX_BLURB)


def summarize(db: Session, request: Request) -> dict:
    tab = status_tab_text(request, newest_first=False)
    if not tab:
        raise StatusEmpty("Keine Status-Einträge.")

    digest = _digest(tab)
    values = request.field_values()
    ablauf = (values.get("status_ablauf") or values.get("current_status") or "").strip()
    blurb = (values.get("status_summary") or "").strip()
    if values.get(DIGEST_KEY) == digest and ablauf:
        return {"ablauf": ablauf, "current_status": ablauf, "summary": blurb, "source": tab, "unchanged": True}

    ablauf = ""
    blurb = ""
    try:
        raw = build_provider().complete_json(
            SYSTEM,
            json.dumps(
                {
                    "title": request.steckbrief_name or request.title,
                    "updates": _updates_payload(request),
                    "status_tab": tab,
                },
                ensure_ascii=False,
            ),
        )
        ablauf = _strip_filler(
            _clip(str(raw.get("ablauf") or raw.get("current_status") or "").strip(), MAX_STATUS)
        )
        blurb = _clip(str(raw.get("summary") or "").strip(), MAX_BLURB)
    except LlmUnavailable:
        ablauf = ""
        blurb = ""
    texts = _update_texts(request, newest_first=False)
    if not ablauf:
        ablauf = _fallback_ablauf(request)
    if not blurb:
        newest = next(
            (
                str(item.summary or "").strip()
                for item in _sorted_updates(request, newest_first=True)
                if str(item.summary or "").strip()
            ),
            texts[0] if texts else "",
        )
        blurb = _fallback_summary(newest)

    spec = get_rules().spec(parse_kind(request.kind) or RequestKind.CHANGE_REQUEST).field_map()
    ablauf_label = spec["status_ablauf"].label if "status_ablauf" in spec else "Ablauf"
    status_label = spec["current_status"].label if "current_status" in spec else "Was gerade los ist"
    blurb_label = spec["status_summary"].label if "status_summary" in spec else "KI-Zusammenfassung"
    svc._upsert_field(db, request, "status_ablauf", ablauf_label, ablauf)
    svc._upsert_field(db, request, "current_status", status_label, ablauf)
    svc._upsert_field(db, request, "status_summary", blurb_label, blurb)
    svc._upsert_field(db, request, DIGEST_KEY, "Status-Digest", digest)
    db.flush()
    return {"ablauf": ablauf, "current_status": ablauf, "summary": blurb, "source": texts[0]}
