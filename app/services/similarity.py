"""Duplikat-Vorschlaege auf eigenen Daten.

Zeichen-Trigramme mit Jaccard-Aehnlichkeit. Laeuft auf SQLite und Postgres
gleich, braucht keine Extension und findet auch umformulierte Duplikate.
Vorschlag, niemals Blockade (Fachkonzept: Duplikatspruefung vor Anlage).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.types import KIND_LABELS, RequestKind, RequestStatus
from app.models import Request

STOPWORDS = {
    "der", "die", "das", "und", "oder", "ein", "eine", "einen", "ich", "wir",
    "ist", "sind", "bei", "mit", "auf", "für", "von", "im", "in", "den", "dem",
    "nicht", "mehr", "kann", "wird", "beim", "als", "dass", "man", "es",
}
MIN_SCORE = 0.28


def normalize(text: str) -> str:
    lowered = text.lower()
    lowered = re.sub(r"[^a-z0-9äöüß ]+", " ", lowered)
    tokens = [t for t in lowered.split() if t and t not in STOPWORDS]
    return " ".join(tokens)


def trigrams(text: str) -> set[str]:
    normalized = normalize(text)
    if len(normalized) < 3:
        return {normalized} if normalized else set()
    return {normalized[i : i + 3] for i in range(len(normalized) - 2)}


def similarity(left: str, right: str) -> float:
    a, b = trigrams(left), trigrams(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass
class SimilarRequest:
    id: str
    reference: str
    title: str
    kind: RequestKind
    status: str
    score: float

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "reference": self.reference,
            "key": self.reference,
            "summary": self.title,
            "title": self.title,
            "kind": self.kind.value,
            "kindLabel": KIND_LABELS[self.kind],
            "status": self.status,
            "score": round(self.score, 3),
        }


def find_similar(
    db: Session,
    text: str,
    *,
    limit: int = 3,
    exclude_id: str | None = None,
    min_score: float = MIN_SCORE,
) -> list[SimilarRequest]:
    if not text.strip():
        return []
    candidates = db.scalars(
        select(Request).order_by(Request.created_at.desc()).limit(500)
    ).all()
    scored: list[SimilarRequest] = []
    for candidate in candidates:
        if exclude_id and candidate.id == exclude_id:
            continue
        haystack = f"{candidate.title} {candidate.description}"
        score = max(similarity(text, candidate.title), similarity(text, haystack) * 0.9)
        if score >= min_score:
            scored.append(
                SimilarRequest(
                    id=candidate.id,
                    reference=candidate.reference,
                    title=candidate.title,
                    # Aus der DB kommen die Spalten als String zurueck, nicht als Enum.
                    kind=RequestKind(candidate.kind),
                    status=RequestStatus(candidate.status).value,
                    score=score,
                )
            )
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:limit]
