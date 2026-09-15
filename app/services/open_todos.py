"""Offene Todos aus Status und Kommentaren — regelbasiert, ohne KI."""

from __future__ import annotations

import re

from app.domain.text import todo_from_status
from app.models import Request

MAX_TODOS = 6
MAX_LEN = 110

_WAIT = re.compile(
    r"(?i)\bwarte(?:n|t)?\s+auf\s+(?:den\s+|die\s+|das\s+)?"
    r"(?P<who>[\wÄÖÜäöüß.\-]+)"
    r"(?:\s+(?:zur|zum|zu der|zu den|zu|für|fuer|wegen)\s+(?P<rest>.+))?"
)
_LIEGT_BEI = re.compile(
    r"(?i)\b(?:liegt|lag|ist)\s+bei\s+(?P<who>[\wÄÖÜäöüß.\-]+)"
    r"(?:\s*[:\-–,]?\s*(?P<rest>.+))?"
)
_BITTE = re.compile(r"(?i)\bbitte\s+(.+)")
_SOLL = re.compile(
    r"(?i)\b(?P<who>[\wÄÖÜäöüß.\-]{2,})\s+soll(?:te|en)?\s+(?P<rest>.+)"
)
_MUSS = re.compile(
    r"(?i)\b(?P<who>[\wÄÖÜäöüß.\-]{2,})\s+(?:muss|sollte|soll)\s+(?P<rest>.+)"
)
_NEXT_CUE = re.compile(
    r"(?i)\b(?:nächste[rn]?\s+schritte?|next\s+steps?|action\s*items?)\s*[:\-–]?\s*(.+)"
)
_TODO_CUE = re.compile(
    r"(?i)\b(?:TODO|To-?Do|Action|offen(?:er)?\s+Punkt|noch\s+offen)\s*[:\-–]\s*(.+)"
)
_AT = re.compile(r"(?i)@(?P<who>[\wÄÖÜäöüß.\-]{2,})\s+(?P<rest>.+)")
_BULLET = re.compile(r"^\s*[-*•]\s+(.+)$")
_DONE_LINE = re.compile(
    r"(?i)^(?:"
    r"ok|okay|danke|erledigt|done|gemacht|passt|alles klar|verstanden|"
    r"abgeschlossen|geschlossen|kein\s+todo|nichts\s+offen"
    r")[.!]?\s*$"
)
_DONE_PREFIX = re.compile(
    r"(?i)^(?:erledigt|done|abgeschlossen|geschlossen|gelöst|geloest)\s*[:\-–]\s*"
)
_DONE_SUFFIX = re.compile(
    r"(?i)^(?P<rest>.+?)\s+(?:ist|wurde)\s+erledigt\.?$"
)
_NOTE_PREFIX = re.compile(
    r"(?i)^(?:notiert|als\s+todo\s+notiert|offen\s+notiert)\s*[:\-–]\s*"
)
_NOISE = re.compile(
    r"(?i)^(?:"
    r"fyi|info|hinweis|update|stand|kurz\s+update|gesehen|danke\s+dir|"
    r"super|top|perfekt|noted|ack"
    r")[.!]?\s*$"
)

_NAME = r"[A-ZÄÖÜ][\wÄÖÜäöüß.\-]{1,30}"
_OWNER_VERB = re.compile(
    r"(?i)^(?:"
    r"klärt|klaert|holt|prüft|prueft|erstellt|kümmert(?:\s+sich(?:\s+um)?)?|"
    r"nimmt|sendet|meldet|bespricht|organisiert|bereitet|zieht|"
    r"recherchiert|definiert|legt|schreibt|ruft|fragt|koordiniert|"
    r"übernimmt|uebernimmt|liefert|plant|treibt|sammelt|macht|"
    r"bearbeitet|finalisiert|validiert|reviewed?|"
    r"soll(?:te)?|muss|wird|kann"
    r")\b"
)
_NOT_NAME = frozenset(
    {
        "bitte",
        "offen",
        "todo",
        "nächste",
        "naechste",
        "warten",
        "warte",
        "status",
        "kosten",
        "freigabe",
        "steckbrief",
        "finanzierung",
        "abstimmung",
        "verantwortung",
        "jemand",
        "man",
        "dann",
        "noch",
        "hier",
        "dort",
        "diese",
        "dieser",
        "dieses",
        "alles",
        "heute",
        "morgen",
        "team",
        "it",
        "scs",
        "cit",
        "qg",
        "action",
        "next",
        "update",
    }
)
_CHAIN_TAIL = re.compile(
    r"(?i)^(?:(?:dann|noch|bitte)\s+)?(?:"
    r"(?:zurück|zurueck|rück|rueck)?melden|"
    r"bescheid\s+geben|informieren|abstimmen|nachfassen|nachhaken|"
    r"bescheiden|ankündigen|ankuendigen|kurz\s+rückmelden|kurz\s+rueckmelden"
    r")\.?$"
)
_STANDALONE_ACTION = re.compile(
    r"(?i)^(?:[\wÄÖÜäöüß.\-/]+\s+){0,6}(?:"
    r"prüfen|pruefen|klären|klaeren|abklären|abklaeren|einholen|nachziehen|"
    r"erstellen|holen|besprechen|organisieren|vorbereiten|recherchieren|"
    r"definieren|legen|schreiben|nachreichen|anpassen|aktualisieren|"
    r"freigeben|abstimmen|koordinieren|liefern|planen|sammeln|"
    r"finalisieren|validieren|reviewen|nacharbeiten|ergänzen|ergaenzen|"
    r"klären|klaeren|bestätigen|bestaetigen|anstoßen|anstossen"
    r")\b"
)
_ACTION_HINT = re.compile(
    r"(?i)\b(?:"
    r"bitte|todo|to-?do|notiert|warte(?:n|t)?\s+auf|liegt\s+bei|nächste[rn]?\s+schritt|"
    r"next\s+step|action|noch\s+offen|ausstehend|muss\s+noch|soll(?:te)?\s+"
    r"|@[\wÄÖÜäöüß.\-]{2,}"
    r")\b"
)


def _clip(text: str, limit: int = MAX_LEN) -> str:
    raw = " ".join(str(text or "").split()).strip().rstrip(".,;:· ")
    if not raw:
        return ""
    if not raw.endswith((".", "!", "?")):
        raw = f"{raw}."
    if len(raw) <= limit:
        return raw
    cut = raw[:limit].rsplit(" ", 1)[0].rstrip(".,;:· ")
    return f"{cut}." if cut else raw[:limit].rstrip() + "."


def _norm_key(text: str) -> str:
    return re.sub(r"[^a-z0-9äöüß]+", "", text.lower())


def _clean_who(who: str) -> str:
    raw = str(who or "").strip(" @,;:.-")
    if len(raw) < 2 or raw.lower() in _NOT_NAME:
        return ""
    if raw.lower() in {"er", "sie", "es", "man", "jemand", "wir", "ihr"}:
        return ""
    return raw


def _add(out: list[dict], seen: set[str], text: str, *, source: str, who: str = "") -> None:
    clipped = _clip(text)
    if not clipped or len(clipped) < 8:
        return
    if _DONE_PREFIX.match(clipped) or _DONE_LINE.match(clipped.rstrip(".")):
        return
    key = _norm_key(clipped)
    if len(key) < 6 or key in seen:
        return
    for existing in list(seen):
        if key in existing or existing in key:
            return
    seen.add(key)
    item: dict[str, str] = {"text": clipped, "source": source}
    person = _clean_who(who)
    if person:
        item["who"] = person
    out.append(item)


def _person_action(chunk: str) -> tuple[str, str] | None:
    text = " ".join(str(chunk or "").split()).strip().rstrip(".")
    m = re.match(rf"^(?P<who>{_NAME})\s+(?P<rest>.+)$", text)
    if not m:
        return None
    who = _clean_who(m.group("who"))
    rest = m.group("rest").strip()
    if not who or not _OWNER_VERB.match(rest):
        return None
    return who, f"{who}: {rest}"


def _standalone_action(chunk: str) -> bool:
    text = " ".join(str(chunk or "").split()).strip().rstrip(".")
    if not text or _person_action(text):
        return False
    if _CHAIN_TAIL.match(text):
        return False
    return bool(_STANDALONE_ACTION.match(text))


def _split_und(chunk: str) -> list[str]:
    text = " ".join(str(chunk or "").split()).strip()
    if not text or not re.search(r"\sund\s", text, flags=re.I):
        return [text] if text else []
    parts = re.split(r"\s+und\s+", text, maxsplit=1, flags=re.I)
    if len(parts) != 2:
        return [text]
    left, right = parts[0].strip(), parts[1].strip()
    if not left or not right:
        return [text]
    left_pa = _person_action(left)
    right_pa = _person_action(right)
    if left_pa and right_pa:
        return [left, right]
    if _standalone_action(left) and _standalone_action(right):
        return [left, right]
    more = _split_und(right)
    if left_pa and len(more) > 1 and all(_person_action(p) for p in more):
        return [left, *more]
    return [text]


def _expand_chunks(raw: str) -> list[str]:
    parts: list[str] = []
    for line in str(raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        bullet = _BULLET.match(line)
        pieces = [bullet.group(1).strip()] if bullet else re.split(r"[;•|]", line)
        for piece in pieces:
            piece = piece.strip(" -•*")
            if not piece:
                continue
            # Komma nur bei klaren Aktionslisten (kurze Glieder)
            if "," in piece and len(piece) < 90:
                commas = [p.strip() for p in piece.split(",") if p.strip()]
                if len(commas) >= 2 and all(
                    _standalone_action(c) or _person_action(c) or _from_action(c)
                    for c in commas
                ):
                    for c in commas:
                        parts.extend(_split_und(c))
                    continue
            parts.extend(_split_und(piece))
    return parts


def _from_wait(chunk: str) -> tuple[str, str] | None:
    m = _WAIT.search(chunk)
    if not m:
        return None
    who = _clean_who(m.group("who") or "")
    return who, todo_from_status(chunk, who or m.group("who") or "")


def _from_liegt(chunk: str) -> tuple[str, str] | None:
    m = _LIEGT_BEI.search(chunk)
    if not m:
        return None
    who = _clean_who(m.group("who") or "")
    rest = (m.group("rest") or "").strip(" ,;:-")
    if rest:
        return who, todo_from_status(f"Warten auf {who} {rest}", who) if who else rest
    if who:
        return who, todo_from_status(f"Warten auf {who}", who)
    return None


def _from_action(chunk: str) -> tuple[str, str] | None:
    text = " ".join(str(chunk or "").split()).strip()
    if not text or _DONE_LINE.match(text) or _NOISE.match(text) or _DONE_PREFIX.match(text):
        return None
    if _DONE_SUFFIX.match(text):
        return None

    note = _NOTE_PREFIX.match(text)
    if note:
        rest = text[note.end() :].strip()
        if rest:
            pa = _person_action(rest)
            if pa:
                return pa
            return "", rest

    m = _AT.search(text)
    if m:
        who = _clean_who(m.group("who") or "")
        rest = m.group("rest").strip()
        pa = _person_action(rest)
        if pa:
            return pa
        if who and rest:
            return who, f"{who}: {rest}" if not rest.lower().startswith(who.lower()) else rest
        if rest:
            return who, rest

    for rx in (_TODO_CUE, _NEXT_CUE):
        m = rx.search(text)
        if m:
            rest = m.group(1).strip()
            pa = _person_action(rest)
            if pa:
                return pa
            wait = _from_wait(rest) or _from_wait(text) or _from_liegt(rest)
            if wait:
                return wait
            return "", rest

    m = _BITTE.search(text)
    if m:
        rest = m.group(1).strip()
        # „bitte Justin …“
        pa = _person_action(rest)
        if pa:
            return pa
        m2 = re.match(rf"^(?P<who>{_NAME})\s+(?P<rest>.+)$", rest)
        if m2 and _clean_who(m2.group("who")):
            who = _clean_who(m2.group("who"))
            return who, f"{who}: {m2.group('rest').strip()}"
        wait = _from_wait(rest) or _from_wait(text)
        if wait:
            return wait
        return "", rest

    for rx in (_SOLL, _MUSS):
        m = rx.search(text)
        if m:
            who = _clean_who(m.group("who") or "")
            rest = (m.group("rest") or "").strip()
            if who:
                return who, f"{who}: {rest}" if rest else ""
            if rest:
                return "", rest

    wait = _from_wait(text)
    if wait:
        return wait
    liegt = _from_liegt(text)
    if liegt:
        return liegt
    pa = _person_action(text)
    if pa:
        return pa
    return None


def _looks_like_todo(chunk: str) -> bool:
    text = " ".join(str(chunk or "").split()).strip()
    if not text or len(text) < 8:
        return False
    if _DONE_LINE.match(text) or _NOISE.match(text) or _DONE_PREFIX.match(text):
        return False
    if _from_action(text):
        return True
    if _BULLET.match(text) and (_standalone_action(text) or _ACTION_HINT.search(text)):
        return True
    if _standalone_action(text) and _ACTION_HINT.search(text):
        return True
    return False


def _pieces_from_text(text: str, *, require_cue: bool) -> list[tuple[str, str]]:
    pieces: list[tuple[str, str]] = []
    for chunk in _expand_chunks(text):
        hit = _from_action(chunk)
        if hit and hit[1]:
            pieces.append((hit[1], hit[0]))
            continue
        if require_cue:
            if _looks_like_todo(chunk):
                # Bullet/standalone ohne expliziten Parser-Hit
                pa = _person_action(chunk)
                if pa:
                    pieces.append((pa[1], pa[0]))
                elif _standalone_action(chunk) or _ACTION_HINT.search(chunk):
                    pieces.append((chunk, ""))
            continue
        # next_steps: freier Text zählt, wenn er nach Aktion aussieht oder schlicht Aufgabe ist
        if _looks_like_todo(chunk) or (chunk and len(chunk) >= 8 and not _NOISE.match(chunk)):
            pieces.append((chunk, ""))
    return pieces


def _done_keys_from_comments(request: Request) -> set[str]:
    """Spätere ‚erledigt‘-Kommentare entwerten ältere Todos grob."""
    keys: set[str] = set()
    comments = sorted(request.comments or [], key=lambda c: c.created_at or 0)
    for c in comments:
        body = " ".join(str(c.body or "").split()).strip()
        m = _DONE_PREFIX.match(body)
        if m:
            rest = body[m.end() :].strip()
            if rest:
                keys.add(_norm_key(rest))
            continue
        m = _DONE_SUFFIX.match(body)
        if m:
            rest = (m.group("rest") or "").strip()
            if rest:
                keys.add(_norm_key(rest))
    return keys


def _status_pieces(request: Request) -> list[tuple[str, str]]:
    pieces: list[tuple[str, str]] = []
    updates = list(request.status_updates or [])
    if updates:
        latest = updates[0]
        pieces.extend(_pieces_from_text(latest.next_steps or "", require_cue=False))
        pieces.extend(_pieces_from_text(latest.summary or "", require_cue=True))
    values = request.field_values() if hasattr(request, "field_values") else {}
    summary = values.get("status_summary") or ""
    pieces.extend(_pieces_from_text(summary, require_cue=True))
    return pieces


def _comment_pieces(request: Request) -> list[tuple[str, str]]:
    comments = sorted(request.comments or [], key=lambda c: c.created_at or 0)
    recent = list(reversed(comments[-16:]))
    pieces: list[tuple[str, str]] = []
    for c in recent:
        body = " ".join(str(c.body or "").split()).strip()
        if not body or _DONE_LINE.match(body) or _NOISE.match(body):
            continue
        # Reine Erzählung ohne Aktionshinweis überspringen
        if not _ACTION_HINT.search(body) and not _BULLET.search(body) and not _person_action(
            body.split(".")[0]
        ):
            # Ausnahme: klare Person-Aktion im ersten Satz
            first = body.split(".")[0].strip()
            if not _person_action(first) and not _from_action(first):
                continue
        pieces.extend(_pieces_from_text(body, require_cue=True))
    return pieces


def open_todos(request: Request | None) -> list[dict]:
    """Bis zu MAX_TODOS offene Punkte: Status zuerst, dann Kommentare."""
    if not request:
        return []
    out: list[dict] = []
    seen: set[str] = set()
    done_keys = _done_keys_from_comments(request)

    def push(text: str, who: str, source: str) -> bool:
        key = _norm_key(text)
        if any(key in d or d in key for d in done_keys if d):
            return False
        before = len(out)
        _add(out, seen, text, source=source, who=who)
        return len(out) > before

    for text, who in _status_pieces(request):
        push(text, who, "status")
        if len(out) >= MAX_TODOS:
            return out
    for text, who in _comment_pieces(request):
        push(text, who, "comment")
        if len(out) >= MAX_TODOS:
            break
    return out
