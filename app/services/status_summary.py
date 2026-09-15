"""Status-Rohdaten + Trigger für den einheitlichen Stand."""

from __future__ import annotations

import hashlib
import re

from sqlalchemy.orm import Session

from app.models import Request

MAX_STATUS = 2500
MAX_BLURB = 90
MAX_ENTRIES = 40
DIGEST_KEY = "status_digest"
PROMPT_VERSION = "v9-briefing-prose"

RAG_LABELS = {
    "green": "grün",
    "yellow": "gelb",
    "amber": "gelb",
    "red": "rot",
    "blue": "blau",
}

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_BULLET = re.compile(r"^[\s]*[•\-–*]+\s*")
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


def _as_bullets(text: str, limit: int = MAX_STATUS) -> str:
    """Legacy-Name: knapper Fließtext aus Stichpunkten/Zeilen."""
    raw = str(text or "").strip()
    if not raw:
        return ""
    chunks = re.split(r"[\n\r]+", raw)
    parts: list[str] = []
    for chunk in chunks:
        line = " ".join(chunk.split()).strip()
        line = _BULLET.sub("", line).strip()
        if not line:
            continue
        if not line.endswith((".", "!", "?")):
            line = f"{line.rstrip('.,;:· ')}."
        parts.append(line)
    return _clip(" ".join(parts), limit)


def _fallback_summary(text: str) -> str:
    parts = [p.strip() for p in _SENTENCE.split(text.strip()) if p.strip()]
    first = parts[0] if parts else text.strip()
    return _clip(first, MAX_BLURB)


def _fallback_prose(texts: list[str]) -> str:
    """Neueste zuerst als knapper Fließtext, ohne KI."""
    seen: list[str] = []
    lowered: set[str] = set()
    for raw in texts:
        line = " ".join(str(raw or "").split())
        key = line.lower()
        if not line or key in lowered:
            continue
        seen.append(line.rstrip("."))
        lowered.add(key)
    return _as_bullets("\n".join(seen[:4]), MAX_STATUS)


def _strip_filler(text: str) -> str:
    """Keine Saetze ueber leere Vergangenheit oder 'Projekt gestartet'."""
    parts = [p.strip() for p in re.split(r"[\n\r]+|(?<=[.!?])\s+", str(text or "").strip()) if p.strip()]
    kept: list[str] = []
    for part in parts:
        clean = _BULLET.sub("", part).strip()
        if _EMPTY_PAST.search(clean) or _STARTED_PAD.search(clean):
            continue
        kept.append(clean)
    return _as_bullets("\n".join(kept), MAX_STATUS)


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
    """Neueste Status-Signale als kurzer Text (ohne KI)."""
    parts: list[str] = []
    seen: set[str] = set()
    for item in _sorted_updates(request, newest_first=True):
        body = " ".join(_entry_body(item).split())
        if not body:
            continue
        key = body.lower()
        if key in seen:
            continue
        seen.add(key)
        parts.append(body.rstrip("."))
        if len(parts) >= 3:
            break
    if not parts:
        return ""
    text = ". ".join(reversed(parts)) + "."
    return _clip(text, MAX_STATUS)


def _digest(tab: str) -> str:
    return hashlib.sha256(f"{PROMPT_VERSION}\n{tab}".encode()).hexdigest()[:16]


def list_blurb(values: dict[str, str]) -> str:
    return _clip((values.get("status_summary") or "").strip(), MAX_BLURB)


def summarize(db: Session, request: Request) -> dict:
    from app.services.stand_summary import refresh_stand

    tab = status_tab_text(request, newest_first=False)
    if not tab:
        raise StatusEmpty("Keine Status-Einträge.")

    result = refresh_stand(db, request, llm=True)
    ablauf = str(result.get("ablauf") or "").strip()
    blurb = str(result.get("summary") or "").strip()
    texts = _update_texts(request, newest_first=False)
    return {
        "ablauf": ablauf,
        "current_status": ablauf,
        "summary": blurb,
        "source": texts[0] if texts else tab,
        "unchanged": bool(result.get("unchanged")),
    }
