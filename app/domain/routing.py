"""Zustaendigkeit und Dringlichkeit aus Keyword-Dateien.

Wer ein Anliegen bekommt und wie dringend es ist, steht als Markdown in
`config/responsibles/` und `config/priority_keywords.md`. Ein Treffer schlaegt
die Schaetzung des Modells: Zustaendigkeit ist eine Festlegung, keine Meinung.
Neue Person heisst neue Datei, kein Deploy.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.domain import text as markdown
from app.domain.text import mentions
from app.domain.types import Priority, RequestKind, parse_kind, parse_priority

# Kurze Woerter nur als ganzes Wort, laengere auch im Kompositum:
# "vpn" darf nicht in "vpns" zufaellig treffen, "freigabe" soll aber
# "Rechnungsfreigabe" finden.
SUBSTRING_FROM = 6

# Reihenfolge = Rangfolge. Der erste Treffer gewinnt.
SEVERITY: tuple[Priority, ...] = (
    Priority.CRITICAL,
    Priority.HIGH,
    Priority.MEDIUM,
    Priority.LOW,
)


@dataclass(frozen=True)
class Responsible:
    name: str
    display: str
    kinds: tuple[RequestKind, ...]
    keywords: tuple[str, ...]

    def hits(self, text: str) -> int:
        return keyword_hits(text, self.keywords)


def keyword_hits(text: str, keywords: tuple[str, ...] | list[str]) -> int:
    """Treffer zaehlen. Verneintes zaehlt nicht: "nicht dringend" ist nicht hoch."""
    hits = 0
    for keyword in keywords:
        needle = keyword.strip().lower()
        if not needle:
            continue
        substring = " " in needle or len(needle) >= SUBSTRING_FROM
        if mentions(text, needle, substring=substring):
            hits += 1
    return hits


# --- Verantwortliche ---


_responsibles: tuple[tuple, tuple[Responsible, ...]] | None = None


def _parse_responsible(path: Path) -> Responsible:
    meta, body = markdown.read(path)
    name = str(meta.get("name") or path.stem).strip()
    kinds = tuple(
        kind for kind in (parse_kind(k) for k in (meta.get("kinds") or [])) if kind
    )
    return Responsible(
        name=name,
        display=str(meta.get("display") or name).strip(),
        kinds=kinds,
        keywords=tuple(markdown.bullets(body)),
    )


def load_responsibles() -> tuple[Responsible, ...]:
    global _responsibles
    directory = get_settings().responsibles_dir
    paths = sorted(directory.glob("*.md")) if directory.is_dir() else []
    stamp = markdown.signature(paths)
    if _responsibles and _responsibles[0] == stamp:
        return _responsibles[1]
    loaded = tuple(_parse_responsible(path) for path in paths)
    _responsibles = (stamp, loaded)
    return loaded


def responsible_names() -> list[str]:
    return [r.name for r in load_responsibles()]


def find_responsible(name: str) -> Responsible | None:
    wanted = name.strip().lower()
    return next(
        (r for r in load_responsibles() if wanted in (r.name.lower(), r.display.lower())),
        None,
    )


def keyword_match(text: str) -> Responsible | None:
    """Nur echte Keyword-Treffer. Kein Fallback, damit Aufrufer das unterscheiden."""
    scored = [(person.hits(text), person) for person in load_responsibles()]
    best = max(scored, key=lambda item: item[0], default=(0, None))
    return best[1] if best[0] > 0 else None


def match_responsible(text: str, kind: RequestKind | None = None) -> Responsible | None:
    """Keyword-Treffer zuerst, dann Zustaendigkeit nach Art, dann die erste Datei.

    Liefert immer jemanden, solange mindestens eine Datei existiert. Ein leeres
    Pflichtfeld waere schlimmer als eine Zuordnung, die im Workspace korrigiert
    werden kann.
    """
    people = load_responsibles()
    if not people:
        return None
    scored = [(person.hits(text), person) for person in people]
    best = max(scored, key=lambda item: item[0])
    if best[0] > 0:
        return best[1]
    if kind:
        by_kind = next((person for person in people if kind in person.kinds), None)
        if by_kind:
            return by_kind
    return people[0]


# --- Prioritaeten ---


_priorities: tuple[tuple, dict[Priority, tuple[str, ...]]] | None = None


def load_priority_keywords() -> dict[Priority, tuple[str, ...]]:
    global _priorities
    path = get_settings().priority_keywords_path
    paths = [path] if path.is_file() else []
    stamp = markdown.signature(paths)
    if _priorities and _priorities[0] == stamp:
        return _priorities[1]

    table: dict[Priority, tuple[str, ...]] = {}
    if paths:
        _meta, body = markdown.read(path)
        for heading, section in markdown.sections(body).items():
            priority = parse_priority(heading)
            if priority:
                table[priority] = tuple(markdown.bullets(section))
    _priorities = (stamp, table)
    return table


def match_priority(text: str) -> Priority | None:
    table = load_priority_keywords()
    for priority in SEVERITY:
        if keyword_hits(text, table.get(priority, ())):
            return priority
    return None
