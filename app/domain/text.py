"""Markdown lesen, Stichwörter finden, Status in Todos umschreiben."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
BULLET = re.compile(r"^\s*[-*]\s+(.+?)\s*$")
HEADING = re.compile(r"^\s*#{1,6}\s+(.+?)\s*$")

CLAUSE = re.compile(r"[,;:.!?]")
NEGATION_WINDOW = 40
NEGATIONS = (
    "nicht",
    "nich",
    "kein",
    "keine",
    "keinen",
    "keins",
    "nie",
    "niemals",
    "ohne",
    "statt",
    "ausser",
    "außer",
)
_NEGATION_RE = re.compile(rf"(?<!\w)(?:{'|'.join(NEGATIONS)})(?!\w)")

_WAIT = re.compile(
    r"(?i)\bwarte(?:n|t)?\s+auf\s+(?:den\s+|die\s+|das\s+)?"
)
_LEAD = re.compile(
    r"(?i)^(noch\s+)?(zur|zum|zu der|zu den|zu|für|fuer|wegen)\s+"
)
_TRAIL = re.compile(r"(?i)\s+(liegt|lag|ist|sind|war|waren|steht|stehen)$")
_KUEMMERT = re.compile(r"(?i)\bkümmert\s+sich\s+um\s+")
_NEXT = re.compile(
    r"(?i)^(die\s+)?verantwortung\s+für\s+(die\s+)?nächste(?:n)?\s+schritte"
    r"|^(die\s+)?nächste(?:n)?\s+schritte$"
)
_VERB_START = re.compile(
    r"(?i)^(definiert|recherchiert|prüft|prueft|klärt|klaert|erstellt|legt)\b"
)


def split_frontmatter(text: str) -> tuple[dict, str]:
    """(Frontmatter als dict, restlicher Text). Ohne Frontmatter: leeres dict."""
    match = FRONTMATTER.match(text)
    if not match:
        return {}, text
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return data, text[match.end():]


def bullets(body: str) -> list[str]:
    return [m.group(1).strip() for line in body.splitlines() if (m := BULLET.match(line))]


def sections(body: str) -> dict[str, str]:
    """Abschnitte nach Ueberschrift, Schluessel kleingeschrieben."""
    out: dict[str, list[str]] = {}
    current = ""
    for line in body.splitlines():
        heading = HEADING.match(line)
        if heading:
            current = heading.group(1).strip().lower()
            out.setdefault(current, [])
            continue
        if current:
            out[current].append(line)
    return {key: "\n".join(lines).strip() for key, lines in out.items()}


def read(path: Path) -> tuple[dict, str]:
    return split_frontmatter(path.read_text(encoding="utf-8"))


def signature(paths: list[Path]) -> tuple:
    """Fingerabdruck fuer den Cache. Aendert sich, sobald jemand eine Datei anfasst."""
    stamped = []
    for path in sorted(paths):
        try:
            stamped.append((str(path), path.stat().st_mtime_ns, path.stat().st_size))
        except OSError:
            continue
    return tuple(stamped)


def negated(lowered: str, start: int) -> bool:
    """Steht kurz vor `start` eine Verneinung im selben Satzteil?"""
    window = lowered[max(0, start - NEGATION_WINDOW) : start]
    clause = CLAUSE.split(window)[-1]
    return _NEGATION_RE.search(clause) is not None


def spots(lowered: str, needle: str, whole_word: bool = True) -> list[int]:
    """Fundstellen eines Stichworts. Mehrteilige Werte auch als Teilstring."""
    escaped = re.escape(needle)
    pattern = rf"(?<!\w){escaped}(?!\w)" if whole_word else escaped
    return [match.start() for match in re.finditer(pattern, lowered)]


def mentions(text: str, needle: str, substring: bool | None = None) -> bool:
    """Kommt `needle` unverneint im Text vor?

    `substring=None` entscheidet nach Form: mehrteilige Werte ("zu Hause")
    treffen auch im Kompositum, einzelne Woerter nur als ganzes Wort.
    """
    needle = needle.strip().lower()
    if len(needle) < 2:
        return False
    lowered = text.lower()
    if substring is None:
        substring = any(char in needle for char in " -/")
    found = spots(lowered, needle, whole_word=not substring)
    return any(not negated(lowered, start) for start in found)


def todo_from_status(status: str, name: str) -> str:
    """Warten-auf-X-Satz → kurzer Satz. Nicht den Status spiegeln, nicht den Titel kleben."""
    text = " ".join(str(status or "").split()).strip().rstrip(".!")
    person = str(name or "").strip()
    if person:
        text = _WAIT.sub("", text)
        text = re.sub(rf"(?i)\b{re.escape(person)}\s+soll\s+", "", text)
        text = re.sub(rf"(?i)\b(?:durch|von|bei)\s+{re.escape(person)}\b", "", text)
        text = re.sub(rf"(?i)\b{re.escape(person)}\b", "", text)
    text = _KUEMMERT.sub("", text)
    text = " ".join(text.split()).strip(" ,;:-")
    text = _LEAD.sub("", text).strip(" ,;:-")
    text = _TRAIL.sub("", text).strip(" ,;:-")
    if not text:
        return "Abstimmung steht aus."
    if _NEXT.match(text):
        return "Nächste Schritte stehen aus."
    phrase = text[0].upper() + text[1:]
    if _VERB_START.match(phrase):
        return phrase + "."
    if len(phrase) > 72:
        phrase = phrase[:69].rsplit(" ", 1)[0]
    return f"{phrase} steht aus."
