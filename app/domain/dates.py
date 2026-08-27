"""Deutsche Datumsangaben aus dem Chat auf ISO bringen (US-003).

Jira erwartet ein Datum, kein Satz. Was sich nicht sicher lesen laesst, bleibt
Freitext — lieber eine unscharfe Angabe im Steckbrief als ein geratenes Datum.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

MONTHS = {
    "januar": 1, "jan": 1,
    "februar": 2, "feb": 2,
    "maerz": 3, "märz": 3, "mrz": 3, "mar": 3,
    "april": 4, "apr": 4,
    "mai": 5,
    "juni": 6, "jun": 6,
    "juli": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "oktober": 10, "okt": 10,
    "november": 11, "nov": 11,
    "dezember": 12, "dez": 12,
}

ISO = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
NUMERIC = re.compile(r"\b(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{2,4})?")
NAMED = re.compile(r"\b(\d{1,2})\.?\s*([A-Za-zÄÖÜäöü]+)\s*(\d{4})?")
RELATIVE = re.compile(
    r"(?i)\b(übermorgen|uebermorgen|heute|sofort|jetzt|morgen|gestern)\b"
)
SPAN = re.compile(
    r"(?i)\b(dieses|aktuelles|nächstes|naechstes)\s+(quartal|jahr)\b"
)
OPEN_END = re.compile(
    r"(?i)\bbis\s+(offen|unbefristet|ohne\s+ende|kein\s+ende)\b"
)
PERSON = re.compile(r"(?i)\b(?:frau|herr|dr|prof)\.?\s+\S+")
FILLER = re.compile(
    r"(?i)\b(ab|bis|von|dem|der|den|am|im|zum|zur|offen|unbefristet|"
    r"auftraggeber|gesellschaft|zeitraum|start|ende|für|fuer)\b"
)
RELATIVE_OFFSET = {
    "heute": 0,
    "sofort": 0,
    "jetzt": 0,
    "morgen": 1,
    "übermorgen": 2,
    "uebermorgen": 2,
    "gestern": -1,
}


def _build(day: int, month: int, year: int | None, today: date) -> str | None:
    if year is None:
        year = today.year
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
        if candidate < today:
            year += 1
    elif year < 100:
        year += 2000
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _shift(today: date, days: int) -> str:
    return (today + timedelta(days=days)).isoformat()


def _quarter(today: date) -> tuple[date, date]:
    start_month = ((today.month - 1) // 3) * 3 + 1
    start = date(today.year, start_month, 1)
    end_month = start_month + 2
    end = date(today.year, end_month, calendar.monthrange(today.year, end_month)[1])
    return start, end


def _calendar_hits(raw: str, today: date) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for match in ISO.finditer(raw):
        year, month, day = (int(part) for part in match.groups())
        try:
            hits.append((match.start(), date(year, month, day).isoformat()))
        except ValueError:
            continue
    for match in NUMERIC.finditer(raw):
        day, month, year = match.group(1), match.group(2), match.group(3)
        parsed = _build(int(day), int(month), int(year) if year else None, today)
        if parsed:
            hits.append((match.start(), parsed))
    for match in NAMED.finditer(raw):
        month = MONTHS.get(match.group(2).lower())
        if not month:
            continue
        year = match.group(3)
        parsed = _build(int(match.group(1)), month, int(year) if year else None, today)
        if parsed:
            hits.append((match.start(), parsed))
    return hits


def _unique_ordered(hits: list[tuple[int, str]]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for _pos, value in sorted(hits, key=lambda item: item[0]):
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def parse_german_date(text: str, today: date | None = None) -> str | None:
    """Erkennt 2026-03-01, 01.03.2026, 1.3.26, 01.03., 1. März 2026 und heute."""
    raw = (text or "").strip()
    if not raw:
        return None
    today = today or date.today()

    iso = ISO.search(raw)
    if iso:
        year, month, day = (int(part) for part in iso.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None

    numeric = NUMERIC.search(raw)
    if numeric:
        day, month, year = numeric.group(1), numeric.group(2), numeric.group(3)
        return _build(int(day), int(month), int(year) if year else None, today)

    named = NAMED.search(raw)
    if named:
        month = MONTHS.get(named.group(2).lower())
        if month:
            year = named.group(3)
            return _build(int(named.group(1)), month, int(year) if year else None, today)

    relative = RELATIVE.search(raw)
    if relative:
        return _shift(today, RELATIVE_OFFSET[relative.group(1).lower()])

    return None


def parse_german_dates(text: str, today: date | None = None) -> list[str]:
    """Kalenderdaten in Textreihenfolge. Kein 'heute' — das steht in Beschreibungen."""
    raw = (text or "").strip()
    if not raw:
        return []
    today = today or date.today()
    return _unique_ordered(_calendar_hits(raw, today))


def parse_german_period(text: str, today: date | None = None) -> tuple[str | None, str | None]:
    """Zeitraum aus Chat: 'ab heute bis offen', 'dieses Quartal', zwei Daten."""
    raw = (text or "").strip()
    if not raw:
        return None, None
    today = today or date.today()
    hits = _calendar_hits(raw, today)
    for match in RELATIVE.finditer(raw):
        hits.append((match.start(), _shift(today, RELATIVE_OFFSET[match.group(1).lower()])))
    for match in SPAN.finditer(raw):
        which = match.group(1).lower().replace("ä", "ae")
        unit = match.group(2).lower()
        if unit == "jahr":
            year = today.year + (1 if which.startswith("naechst") else 0)
            hits.append((match.start(), date(year, 1, 1).isoformat()))
            hits.append((match.start() + 1, date(year, 12, 31).isoformat()))
        else:
            start, end = _quarter(today)
            if which.startswith("naechst"):
                nxt = start.month + 3
                year = start.year + (1 if nxt > 12 else 0)
                month = nxt - 12 if nxt > 12 else nxt
                start = date(year, month, 1)
                end_month = month + 2
                if end_month > 12:
                    end = date(year + 1, end_month - 12, calendar.monthrange(year + 1, end_month - 12)[1])
                else:
                    end = date(year, end_month, calendar.monthrange(year, end_month)[1])
            hits.append((match.start(), start.isoformat()))
            hits.append((match.start() + 1, end.isoformat()))
    dates = _unique_ordered(hits)
    start = dates[0] if dates else None
    end = dates[1] if len(dates) > 1 else None
    if OPEN_END.search(raw) and not end:
        end = "offen"
    return start, end


def leftover_after_period(text: str) -> str:
    """Was nach Zeitraum und Anrede noch als Gesellschaft stehen kann."""
    leftover = PERSON.sub(" ", text or "")
    leftover = ISO.sub(" ", leftover)
    leftover = NUMERIC.sub(" ", leftover)
    leftover = NAMED.sub(" ", leftover)
    leftover = RELATIVE.sub(" ", leftover)
    leftover = SPAN.sub(" ", leftover)
    leftover = OPEN_END.sub(" ", leftover)
    leftover = FILLER.sub(" ", leftover)
    leftover = leftover.replace(",", " ")
    return " ".join(leftover.split()).strip(" ,.;:-")


def normalize_date_value(text: str, today: date | None = None) -> str:
    """ISO wenn erkennbar, sonst der urspruengliche Text."""
    return parse_german_date(text, today) or text
