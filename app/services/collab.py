"""Risiken und aehnliche Loesungen im Chat klaeren, nicht still eintragen.

Zwei Turns nach den Fakten: Meinung zeigen, fragen ob uebernehmen, weitere nennen.
Aehnliche Loesungen: lokale Tickets, Wissensbasis, Websuche.
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.domain.overview import formulate_risk
from app.domain.risks import field_text, match_patterns, warning_text
from app.domain.text import mentions
from app.knowledge import cases
from app.services.similarity import find_similar
from app.services.websearch import search as web_search
from app.triage.engine import Draft, MAX_LONGTEXT, is_unknown_answer
from app.triage.providers import LlmUnavailable

COLLAB_RISKS = "collab_risks"
COLLAB_SIMILAR = "collab_similar"
STEPS = (COLLAB_RISKS, COLLAB_SIMILAR)
TARGET = {
    COLLAB_RISKS: "risks_obstacles",
    COLLAB_SIMILAR: "similar_solution",
}
LABEL = {
    COLLAB_RISKS: "Risiken & Hindernisse",
    COLLAB_SIMILAR: "Ähnliche Lösung",
}

YES = {
    "ja", "jap", "jo", "yes", "ok", "okay", "passt", "genau", "stimmt",
    "übernehmen", "uebernehmen", "mach", "machen",
}
NO = {
    "nein", "nö", "noe", "nicht", "lass", "skip",
    "nicht jetzt", "nicht übernehmen", "nicht uebernehmen",
}
_LEAD = re.compile(
    r"^(ja|jap|jo|yes|ok|okay|passt|genau|stimmt|übernehmen|uebernehmen|"
    r"nein|nö|noe|nicht jetzt|nicht übernehmen|nicht uebernehmen)\s*[,.:;–-]*\s*",
    re.I,
)


def next_step(context: dict | None) -> str | None:
    done = set((context or {}).get("collab_done") or [])
    for step in STEPS:
        if step not in done:
            return step
    return None


def mark_done(context: dict, step: str) -> dict:
    done = list(context.get("collab_done") or [])
    if step not in done:
        done.append(step)
    return {**context, "collab_done": done}


def classify(text: str) -> tuple[str, str]:
    raw = str(text or "").strip()
    if not raw or is_unknown_answer(raw):
        return "skip", ""
    low = raw.lower().rstrip("!.")
    if low in NO or low.startswith("nicht übernehmen") or low.startswith("nicht uebernehmen"):
        extra = _LEAD.sub("", raw).strip()
        return "no", extra if extra.lower().rstrip("!.") not in NO else ""
    if low in YES or any(low.startswith(word) for word in YES):
        extra = _LEAD.sub("", raw).strip()
        return "yes", extra
    return "add", raw


def _clip(text: str) -> str:
    return " ".join(str(text or "").split()).strip()[:MAX_LONGTEXT]


def _short(text: str, limit: int = 120) -> str:
    raw = " ".join(str(text or "").split()).strip()
    if not raw:
        return ""
    cut = re.split(r"(?<=[.!?])\s+", raw, maxsplit=1)[0].rstrip(".")
    if len(cut) > limit:
        cut = cut[: limit - 1].rsplit(" ", 1)[0] + "…"
    return cut


RISK_SYSTEM = (
    "Du bist Change-Berater. Eine Meinung: was bremst diesen Change? "
    "Ein Satz, konkret (wer oder welcher Ablauf). Nur aus dem Vorgang. "
    "Kein unklar, kein nicht genannt, keine erfundenen Personennamen. "
    'JSON: {"risk": "..."}'
)
_SKIP_LLM = {"heuristik", "scripted", "none"}


def _story(draft: Draft) -> str:
    return " ".join(
        part
        for part in (
            draft.title,
            draft.values.get("description"),
            draft.values.get("problem"),
        )
        if part
    )


def _context(draft: Draft) -> str:
    extra = str(draft.values.get("solution_goals") or "").strip()
    return " ".join(part for part in (_story(draft), extra) if part)


def _clean_risk(text: str) -> str:
    raw = _clip(text)
    if raw.lower() in {"keine", "kein", "-", "nein"}:
        return ""
    return raw


def heuristic_risk(draft: Draft) -> str:
    """Meinung aus dem Vorgang, ohne Musterdatei und ohne Modell."""
    blob = _context(draft)

    def has(*needles: str) -> bool:
        return any(mentions(blob, word, substring=True) for word in needles)

    if has("papier", "excel", "formular"):
        return "Papier und Excel laufen parallel weiter, der neue Weg wird umgangen."
    if has("schnittstelle", "sap"):
        return "Anbindung und Tests mit den Umsystemen ziehen sich."
    if has("app", "digital"):
        return "Nutzung bleibt freiwillig, der alte Weg bleibt offen."
    title = (draft.title or "der Change").strip()
    return f"Bei „{title}“ bleibt der Ist-Prozess, wenn der neue Weg nicht verbindlich wird."


def _llm_risk(draft: Draft, provider) -> str:
    name = str(getattr(provider, "name", "") or "").lower()
    if not provider or name in _SKIP_LLM or name.startswith("scripted"):
        return ""
    try:
        raw = provider.complete_json(
            RISK_SYSTEM,
            (
                f"Titel: {draft.title}\n"
                f"Beschreibung: {draft.values.get('description') or ''}\n"
                f"Problem: {draft.values.get('problem') or ''}\n"
                f"Lösung: {draft.values.get('solution_goals') or ''}"
            ),
        )
    except (LlmUnavailable, TypeError, ValueError):
        return ""
    if not isinstance(raw, dict):
        return ""
    return _clean_risk(str(raw.get("risk") or raw.get("risks_obstacles") or ""))


def think_risk(draft: Draft, provider=None) -> str:
    return _llm_risk(draft, provider) or heuristic_risk(draft)


def propose_risks(draft: Draft, hits: list | None = None) -> tuple[str, list[dict]]:
    text = _story(draft)
    hits = hits if hits is not None else cases.search(text, limit=1)
    pattern = _clean_risk(field_text(match_patterns(text), hits))
    existing = _clean_risk(str(draft.values.get("risks_obstacles") or ""))
    sources: list[dict] = []
    if hits:
        case = hits[0].case
        sources.append(
            {"kind": "knowledge", "label": f"{case.id} — {case.title}", "id": case.id}
        )
    proposal = pattern or existing
    if not proposal:
        proposal = formulate_risk(draft.title or "", _context(draft))
    return _clip(proposal), sources


def propose_similar(db: Session, draft: Draft) -> tuple[str, list[dict]]:
    """Treffer als Verweis, nie den Loesungstext in den Steckbrief kippen."""
    text = _story(draft)
    query = (draft.title or text)[:80]
    sources: list[dict] = []
    parts: list[str] = []

    kb = cases.search(text, limit=2)
    for hit in kb:
        case = hit.case
        sources.append(
            {
                "kind": "knowledge",
                "label": f"{case.id} — {case.title}",
                "id": case.id,
            }
        )
        parts.append(f"{case.id} — {case.title}")

    tickets = find_similar(db, text, limit=2)
    for item in tickets:
        sources.append(
            {
                "kind": "ticket",
                "label": f"{item.reference} — {item.title}",
                "url": f"/workspace/{item.id}",
                "id": item.id,
            }
        )
        line = f"{item.reference} — {item.title}"
        if line not in parts:
            parts.append(line)

    for hit in web_search(query, limit=3):
        sources.append(
            {
                "kind": "web",
                "label": hit["title"],
                "url": hit["url"],
            }
        )
        if hit["title"] not in parts:
            parts.append(hit["title"])

    existing = str(draft.values.get("similar_solution") or "").strip()
    proposal = parts[0] if parts else existing
    return _clip(proposal), sources


def apply_decision(draft: Draft, step: str, text: str, proposal: str) -> Draft:
    target = TARGET[step]
    decision, extra = classify(text)
    if decision == "skip":
        return draft
    if decision == "no":
        draft.values[target] = _clip(extra)
        return draft
    chunks = []
    if proposal:
        chunks.append(proposal)
    if extra and extra not in (proposal or ""):
        chunks.append(extra)
    draft.values[target] = _clip(" ".join(chunks))
    return draft


def risks_prompt(draft: Draft, proposal: str) -> str:
    thought = _short(proposal) or _short(heuristic_risk(draft))
    return f"Ich sehe: {thought}. Passt das?"


def similar_prompt(draft: Draft, proposal: str, sources: list[dict]) -> str:
    if proposal or sources:
        return "Ähnlich. Übernehmen?"
    return "Nichts gefunden. Kennst du eine?"


def opinion_warning(draft: Draft, hits: list | None = None) -> str | None:
    text = _story(draft)
    return warning_text(match_patterns(text), hits)
