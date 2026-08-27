"""Kulturelle Risiken aus Stichwörtern, nicht aus dem Modell.

Muster liegen in config/risks/. Ein Treffer ist eine Warnung plus Text für
`risks_obstacles`. Erfundene Konflikte gibt es nicht: ohne Stichwort kein Eintrag.
Maßnahmen zusätzlich aus ähnlichen gelösten Fällen, wenn einer passt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.domain import text as markdown
from app.domain.text import mentions

EMPTY = {"", "keine", "kein", "-", "nein"}
MAX_WARNING = 420
MAX_FIELD = 1200
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class RiskPattern:
    name: str
    display: str
    match: tuple[str, ...]
    risk: str
    measures: str


@dataclass(frozen=True)
class RiskHit:
    pattern: RiskPattern
    hits: int


def _clip(text: str, limit: int) -> str:
    raw = " ".join(str(text or "").split()).strip()
    if len(raw) <= limit:
        return raw
    cut = raw[: limit - 1].rsplit(" ", 1)[0]
    return f"{cut}…"


def _first_sentence(text: str) -> str:
    parts = [p.strip() for p in _SENTENCE.split(str(text or "").strip()) if p.strip()]
    first = parts[0] if parts else str(text or "").strip()
    if first and first[-1] not in ".!?":
        first = f"{first}."
    return first


def _parse(path: Path) -> RiskPattern | None:
    meta, body = markdown.read(path)
    name = str(meta.get("name") or path.stem).strip().lower()
    if not name or name == "readme":
        return None
    match = tuple(
        str(m).strip().lower() for m in (meta.get("match") or []) if str(m).strip()
    )
    if not match:
        return None
    blocks = markdown.sections(body)
    risk = " ".join((blocks.get("risiko") or "").split())
    measures = " ".join((blocks.get("maßnahmen") or blocks.get("massnahmen") or "").split())
    if not risk:
        return None
    return RiskPattern(
        name=name,
        display=str(meta.get("display") or name).strip(),
        match=match,
        risk=risk,
        measures=measures,
    )


_cache: tuple[tuple, tuple[RiskPattern, ...]] | None = None


def load_patterns() -> tuple[RiskPattern, ...]:
    global _cache
    directory = get_settings().risks_dir
    paths = sorted(directory.glob("*.md")) if directory.is_dir() else []
    stamp = markdown.signature(paths)
    if _cache and _cache[0] == stamp:
        return _cache[1]
    loaded = tuple(p for path in paths if (p := _parse(path)))
    _cache = (stamp, loaded)
    return loaded


def match_patterns(text: str) -> list[RiskHit]:
    scored: list[RiskHit] = []
    for pattern in load_patterns():
        hits = sum(
            1
            for needle in pattern.match
            if needle and mentions(text, needle, substring=" " in needle)
        )
        if hits:
            scored.append(RiskHit(pattern=pattern, hits=hits))
    scored.sort(key=lambda item: item.hits, reverse=True)
    return scored


def _case_measure(case_hits: list | None) -> str:
    if not case_hits:
        return ""
    hit = case_hits[0]
    case = getattr(hit, "case", None)
    if case is None:
        return ""
    solution = _first_sentence(getattr(case, "solution", "") or "")
    ident = str(getattr(case, "id", "") or "").strip()
    if not solution:
        return ""
    if ident:
        return f"Aus {ident}: {solution}"
    return solution


def field_text(hits: list[RiskHit], case_hits: list | None = None) -> str:
    if not hits:
        return ""
    return _clip(hits[0].pattern.risk, MAX_FIELD)


def warning_text(hits: list[RiskHit], case_hits: list | None = None) -> str | None:
    if not hits:
        return None
    best = hits[0].pattern
    lead = _first_sentence(best.risk)
    chunks = [f"Risiko {best.display}: {lead}"]
    extra = _case_measure(case_hits)
    if extra:
        chunks.append(extra)
    elif best.measures:
        chunks.append(_first_sentence(best.measures))
    return _clip(" ".join(chunks), MAX_WARNING)


def apply_to_values(
    values: dict[str, str],
    text: str,
    case_hits: list | None = None,
) -> str | None:
    """Risiko-Feld fuellen, wenn Muster greifen. Gibt die Chat-Warnung zurueck."""
    hits = match_patterns(text)
    if not hits:
        return None
    body = field_text(hits, case_hits)
    current = str(values.get("risks_obstacles") or "").strip()
    if current.lower() in EMPTY:
        values["risks_obstacles"] = body
    elif body and body.lower() not in current.lower():
        values["risks_obstacles"] = _clip(f"{current} {body}", MAX_FIELD)
    return warning_text(hits, case_hits)
