"""Geloeste Faelle aus Markdown als Kontext fuer Triage und Zusammenfassung.

Die Dateien liegen bewusst im Dateisystem und nicht in der Datenbank: echte
Exporte sollen den Ordner ersetzen koennen, ohne Migration. Gesucht wird mit
denselben Zeichen-Trigrammen wie bei der Duplikatspruefung — kein Vektor-Store,
keine zusaetzliche Abhaengigkeit.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.domain import text as markdown
from app.domain.fieldspec import FieldSpec
from app.domain.topics import parse_question_fields
from app.domain.types import Priority, RequestKind, parse_kind, parse_priority
from app.services.similarity import normalize, similarity

MIN_SCORE = 0.16
SOLVED = {"", "solved", "geloest", "gelöst", "done", "erledigt", "closed"}
SNIPPET = 400
MIN_TOKEN = 3
# Woerter, die in jeder zweiten Meldung stehen. Sie duerfen nichts treffen.
NOISE = {
    "problem", "problemen", "probleme", "frage", "hilfe", "bitte", "immer",
    "wieder", "seit", "heute", "gestern", "geht", "habe", "haben", "hat",
    "brauche", "braucht", "moechte", "möchte", "will", "kein", "keine", "keinen",
    "meinem", "meiner", "meine", "mein", "etwas", "irgendwie", "leider", "neue",
    "neuen", "neu", "alle", "allen", "schon", "noch", "aber", "auch", "sehr",
}


def keywords(text: str) -> set[str]:
    """Bedeutungstragende Woerter. Kurzes und Floskeln fallen raus."""
    return {
        word
        for word in normalize(text).split()
        if len(word) >= MIN_TOKEN and word not in NOISE
    }


@dataclass(frozen=True)
class Case:
    id: str
    title: str
    kind: RequestKind | None
    service: str | None
    priority: Priority | None
    responsible: str | None
    tags: tuple[str, ...]
    # Feld-Schluessel, die zur Loesung noetig waren. Steuert die Rueckfragen.
    needs: tuple[str, ...]
    # Optionale Diagnosefragen aus dem Fall (gehen vor dem Topic-Playbook).
    questions: tuple[FieldSpec, ...]
    problem: str
    cause: str
    solution: str
    # Optional: gemessener/geschätzter Aufwand aus dem echten Fall.
    effort_fb: float | None = None
    effort_it: float | None = None
    duration: str = ""

    @property
    def haystack(self) -> str:
        return " ".join([self.title, " ".join(self.tags), self.service or "", self.problem])

    @property
    def keywords(self) -> set[str]:
        """Worauf ein Fall anspringt: Tags, System und die Woerter des Titels."""
        return set(self.tags) | keywords(self.title) | ({self.service} if self.service else set())

    def effort_line(self) -> str:
        bits: list[str] = []
        if self.effort_fb is not None:
            bits.append(f"FB {self.effort_fb:g} PT")
        if self.effort_it is not None and self.effort_it > 0:
            bits.append(f"IT {self.effort_it:g} PT")
        if self.duration:
            bits.append(self.duration)
        return ", ".join(bits)

    def prompt_line(self) -> str:
        parts = [f"- {self.id}: {self.title}"]
        facts = [
            f"art = {self.kind.value}" if self.kind else "",
            f"system = {self.service}" if self.service else "",
            f"prioritaet = {self.priority.value}" if self.priority else "",
            f"aufwand = {self.effort_line()}" if self.effort_line() else "",
            f"damals gebraucht = {', '.join(self.needs)}" if self.needs else "",
            (
                f"fragen = {', '.join(f.key for f in self.questions)}"
                if self.questions
                else ""
            ),
        ]
        detail = "; ".join(p for p in facts if p)
        if detail:
            parts.append(f" ({detail})")
        return "".join(parts)


@dataclass(frozen=True)
class Hit:
    case: Case
    score: float

    def to_dict(self) -> dict:
        return {
            "id": self.case.id,
            "title": self.case.title,
            "solution": self.case.solution[:SNIPPET],
            "score": round(self.score, 3),
            "needs": list(self.case.needs),
        }


def _meta_pt(meta: dict, key: str) -> float | None:
    raw = meta.get(key)
    if raw is None or raw == "":
        return None
    try:
        value = float(str(raw).replace(",", ".").split()[0])
    except (TypeError, ValueError, IndexError):
        return None
    if value != value or value < 0:
        return None
    return value


def _parse(path: Path) -> Case | None:
    meta, body = markdown.read(path)
    status = str(meta.get("status") or "").strip().lower()
    if status not in SOLVED:
        return None
    blocks = markdown.sections(body)
    title = str(meta.get("title") or path.stem).strip()
    return Case(
        id=str(meta.get("id") or path.stem).strip(),
        title=title,
        kind=parse_kind(meta.get("kind")),
        service=str(meta.get("service")).strip().lower() if meta.get("service") else None,
        priority=parse_priority(meta.get("priority")),
        responsible=str(meta.get("responsible")).strip() if meta.get("responsible") else None,
        tags=tuple(str(t).strip().lower() for t in (meta.get("tags") or []) if str(t).strip()),
        needs=tuple(str(n).strip() for n in (meta.get("needs") or []) if str(n).strip()),
        questions=parse_question_fields(blocks.get("fragen", "")),
        problem=blocks.get("problem", ""),
        cause=blocks.get("ursache", ""),
        solution=blocks.get("lösung") or blocks.get("loesung") or "",
        effort_fb=_meta_pt(meta, "effort_fb"),
        effort_it=_meta_pt(meta, "effort_it"),
        duration=str(meta.get("duration") or "").strip(),
    )


_cache: tuple[tuple, tuple[Case, ...]] | None = None


def load_cases() -> tuple[Case, ...]:
    """Alle geloesten Faelle. Fehlender oder leerer Ordner ist kein Fehler."""
    global _cache
    directory = get_settings().knowledge_dir
    paths = sorted(directory.glob("*.md")) if directory.is_dir() else []
    stamp = markdown.signature(paths)
    if _cache and _cache[0] == stamp:
        return _cache[1]
    loaded = tuple(case for path in paths if (case := _parse(path)))
    _cache = (stamp, loaded)
    return loaded


def score_case(text: str, words: set[str], case: Case) -> float:
    """Stichwort-Treffer plus Textaehnlichkeit.

    Zeichen-Trigramme allein reichen nicht: "Problem mit meinem VPN" ist zu kurz
    gegen einen ausformulierten Fall. Ein Treffer auf das betroffene System
    zaehlt deshalb eigenstaendig.

    Ein einzelnes Randstichwort zaehlt dagegen nicht. "Excel rechnet falsch"
    traf sonst einen SAP-Fall, weil dort `excel` als Tag steht — und uebernahm
    von ihm Art und Prioritaet. Ein zweiter Treffer oder das System muss her.
    """
    overlap = words & case.keywords
    on_service = bool(case.service and case.service in words)
    if not on_service and len(overlap) < 2:
        return max(similarity(text, case.title), similarity(text, case.haystack) * 0.9)
    weight = len(overlap) + (2 if on_service else 0)
    by_word = weight / (weight + 2)
    return max(by_word, similarity(text, case.title), similarity(text, case.haystack) * 0.9)


def search(text: str, limit: int = 3, min_score: float = MIN_SCORE) -> list[Hit]:
    if not text.strip():
        return []
    words = keywords(text)
    hits = []
    for case in load_cases():
        score = score_case(text, words, case)
        if score >= min_score:
            hits.append(Hit(case=case, score=score))
    hits.sort(key=lambda hit: hit.score, reverse=True)
    return hits[:limit]


def prompt_block(hits: list[Hit]) -> str:
    if not hits:
        return "keine"
    return "\n".join(hit.case.prompt_line() for hit in hits)
