"""Absicht aus dem Text lesen, ohne LLM.

Navigation, Referenzen und Status-Kommandos sind Muster, keine Sprachkunst. Das
spart pro Turn eine LLM-Runde und macht die haeufigen Faelle sofort verfuegbar.
Was hier nicht greift, laeuft weiter in die Triage — oder in eine Klarfrage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from app.domain.routing import responsible_names
from app.domain.types import (
    PRIORITY_LABELS,
    STATUS_LABELS,
    Priority,
    RequestKind,
    RequestStatus,
)
from app.services.requests_service import OPEN_STATUSES

REFERENCE = re.compile(r"\bAN-(\d{3,6})\b", re.IGNORECASE)
JIRA_KEY = re.compile(r"\b([A-Z][A-Z0-9]{1,10}-\d{1,6})\b", re.IGNORECASE)
WORDS = re.compile(r"[a-zA-Zäöüß0-9-]+")
SEARCH_LEAD = re.compile(
    r"^\s*(?:suche|such|finde|find|zeig|zeige)\s+(?:mir\s+)?(?:nach\s+)?(.+)$",
    re.IGNORECASE,
)

FILLER = {
    "bitte", "mal", "mir", "die", "der", "das", "den", "dem", "zu", "zum", "zur",
    "ins", "in", "auf", "eine", "einen", "ein", "und", "seite", "bereich", "gehe",
    "geh", "ich", "will", "möchte", "moechte", "kannst", "du", "wechsle", "öffne",
    "oeffne", "zeig", "zeige", "ruf", "bring", "mach", "gib", "nur", "davon",
    "noch", "auch", "mit", "nach", "mein", "meine", "meinen",
}
OPEN_VERBS = {
    "öffne", "oeffne", "öffnen", "oeffnen", "zeig", "zeige", "zeigen", "geh",
    "gehe", "wechsle", "wechsel", "ruf", "aufrufen", "bring", "springe", "spring",
}

NAV_TARGETS: tuple[tuple[frozenset[str], str, str], ...] = (
    (
        frozenset({"einstellung", "einstellungen", "settings", "konfiguration", "config"}),
        "/settings",
        "Einstellungen",
    ),
    (
        frozenset({"workspace", "übersicht", "uebersicht", "tabelle", "liste"}),
        "/workspace",
        "Workspace",
    ),
    (frozenset({"chat", "startseite"}), "/", "Chat"),
)

STATUS_WORDS: dict[str, tuple[RequestStatus, ...]] = {
    "offen": OPEN_STATUSES,
    "offene": OPEN_STATUSES,
    "offenen": OPEN_STATUSES,
    "laufend": OPEN_STATUSES,
    "laufende": OPEN_STATUSES,
    "laufenden": OPEN_STATUSES,
    "aktiv": OPEN_STATUSES,
    "aktive": OPEN_STATUSES,
    "entwurf": (RequestStatus.DRAFT,),
    "steckbrief": (RequestStatus.STECKBRIEF,),
    "neu": (RequestStatus.STECKBRIEF,),
    "neue": (RequestStatus.STECKBRIEF,),
    "it-abstimmung": (RequestStatus.IT_REVIEW,),
    "abstimmung": (RequestStatus.IT_REVIEW,),
    "qg1": (RequestStatus.QG1,),
    "qg2": (RequestStatus.QG2,),
    "freigegeben": (RequestStatus.APPROVED,),
    "umsetzung": (RequestStatus.IN_PROGRESS,),
    "arbeit": (RequestStatus.IN_PROGRESS,),
    "erledigt": (RequestStatus.DONE,),
    "fertig": (RequestStatus.DONE,),
    "abgeschlossen": (RequestStatus.DONE,),
    "geschlossen": (RequestStatus.DONE,),
    "abgelehnt": (RequestStatus.REJECTED,),
    "verworfen": (RequestStatus.REJECTED,),
}

KIND_WORDS: dict[str, RequestKind] = {
    "change": RequestKind.CHANGE_REQUEST,
    "changes": RequestKind.CHANGE_REQUEST,
    "änderung": RequestKind.CHANGE_REQUEST,
    "änderungen": RequestKind.CHANGE_REQUEST,
    "anpassung": RequestKind.CHANGE_REQUEST,
    "anpassungen": RequestKind.CHANGE_REQUEST,
    "it-anfrage": RequestKind.IT_REQUEST,
    "it-anfragen": RequestKind.IT_REQUEST,
    "it-request": RequestKind.IT_REQUEST,
    "itrequest": RequestKind.IT_REQUEST,
}

PRIORITY_WORDS: dict[str, Priority] = {
    "kritisch": Priority.CRITICAL,
    "kritische": Priority.CRITICAL,
    "kritischen": Priority.CRITICAL,
    "hoch": Priority.HIGH,
    "hohe": Priority.HIGH,
    "hohen": Priority.HIGH,
    "dringend": Priority.HIGH,
    "dringende": Priority.HIGH,
    "mittel": Priority.MEDIUM,
    "mittlere": Priority.MEDIUM,
    "niedrig": Priority.LOW,
    "niedrige": Priority.LOW,
}

QUESTION_WORDS = {
    "welche", "welches", "welcher", "wieviele", "wie", "was", "wer", "wann",
    "gibt", "zeig", "zeige", "liste", "such", "suche", "finde", "status",
    "übersicht", "uebersicht",
}

# Nur diese Woerter eroeffnen den Leseweg. "habe", "brauche" oder ein blosses
# Fragezeichen sind Anliegen-Sprache, keine Abfrage auf den Bestand.
READ_LEAD = {
    "welche", "welches", "welcher", "wieviele", "liste", "übersicht", "uebersicht",
    "zeig", "zeige", "zeigen", "gibt", "status",
}

# Bestandswoerter im Plural. Singular-Signale wie "fehler" oder "zugang" fehlen
# hier absichtlich: "ich habe keinen Zugang" ist ein Anliegen, keine Liste.
DOMAIN_NOUNS = {
    "ticket", "tickets", "anliegen", "vorgang", "vorgänge", "vorgaenge",
    "request", "requests", "steckbrief", "steckbriefe", "meldung", "meldungen",
    "changes", "änderungen", "aenderungen", "anpassungen", "it-anfragen",
}
DOMAIN_WORDS = {
    *DOMAIN_NOUNS,
    *STATUS_WORDS,
    *KIND_WORDS,
}
HELP_WORDS = {
    "hilfe", "help", "kannst", "fähig", "faehig", "funktionen", "befehle",
}
MORE_WORDS = {"mehr", "weiter", "nächste", "naechste", "rest"}
CREATE_ANYWAY = {
    "trotzdem", "anlegen", "trotzdem anlegen", "neu anlegen", "lege an", "anlegen trotzdem",
}
OPEN_EXISTING = {
    "bestehende", "bestehendes", "bestehenden", "duplikat", "ähnliche", "aehnliche",
}

# Ein Name allein ("a") waere zu viel Zufall. Vor kurzen Namen muss eines
# dieser Woerter stehen, damit "welche Tickets hat A" greift und "Plan a" nicht.
RESPONSIBLE_LEAD = {"von", "hat", "bei", "für", "fuer", "an", "zu", "durch", "liegen"}

SET_VERBS = {"setz", "setze", "setzen", "stell", "stelle", "stellen", "mach", "mache"}
CLOSE_VERBS = {"schließe", "schliesse", "schließ", "schliess", "erledige", "abschließen"}
COMMENT_VERBS = {
    "kommentier", "kommentiere", "kommentar", "notiere", "notier", "vermerke", "vermerk",
}
PRONOUNS = {"das", "es", "dem", "den", "dieses", "diesen", "dieser", "ihn"}
STATUS_NOTE = re.compile(
    r"(?:^|\b)(?:status|stand)\s*:\s*(.+)$",
    re.IGNORECASE | re.DOTALL,
)
RAG_WORDS = {
    "grün": "green",
    "gruen": "green",
    "green": "green",
    "gelb": "yellow",
    "yellow": "yellow",
    "amber": "yellow",
    "rot": "red",
    "red": "red",
}

SETTABLE_STATUS = {
    word: values[0]
    for word, values in STATUS_WORDS.items()
    if len(values) == 1
}

COMPANY_WORDS: dict[str, str] = {
    "scs": "SCS Gesamt",
    "sit": "SIT",
    "cit": "CIT",
}

KIND_PLURAL: dict[RequestKind, str] = {
    RequestKind.CHANGE_REQUEST: "Change Requests",
    RequestKind.IT_REQUEST: "IT Requests",
}

CREATE_CUES = {
    "brauche", "brauchen", "wünsche", "wuensche", "möchte", "moechte",
    "will", "wollen", "einführen", "einfuehren", "digitalisieren",
    "ändern", "aendern", "anlegen", "erstellen", "statt",
    "problem", "fehlt", "kaputt", "stürzt", "stuerzt", "habe", "haben",
    "soll", "sollen", "müssen", "muessen",
}


@dataclass(frozen=True)
class Navigate:
    url: str
    label: str


@dataclass(frozen=True)
class OpenRequest:
    reference: str


@dataclass(frozen=True)
class Query:
    label: str
    kind: RequestKind | None = None
    statuses: tuple[RequestStatus, ...] = ()
    priority: Priority | None = None
    company: str | None = None
    responsible: str | None = None
    reference: str | None = None
    counting: bool = False
    text: str | None = None
    more: bool = False


@dataclass(frozen=True)
class Action:
    status: RequestStatus | None = None
    priority: Priority | None = None
    comment: str | None = None
    status_note: str | None = None
    overall_rag: str | None = None
    reference: str | None = None
    words: tuple[str, ...] = field(default_factory=tuple)
    needs_target: bool = False


@dataclass(frozen=True)
class Help:
    pass


@dataclass(frozen=True)
class Clarify:
    reason: str  # "target" | "filter"


@dataclass(frozen=True)
class DuplicateChoice:
    """Nach Summary: trotzdem anlegen oder bestehendes oeffnen."""

    create: bool


Intent = Navigate | OpenRequest | Query | Action | Help | Clarify | DuplicateChoice


def tokens(text: str) -> list[str]:
    return WORDS.findall(text.lower())


def find_reference(text: str) -> str | None:
    match = REFERENCE.search(text)
    if match:
        return f"AN-{match.group(1)}"
    jira = JIRA_KEY.search(text)
    if jira:
        return jira.group(1).upper()
    return None


def looks_like_issue(text: str) -> bool:
    """Rausch-Filter, kein Torwaechter. Anlegen ist der Default.

    False nur bei Hilfe-Wunsch, leerem Text oder einem einzelnen Fragewort.
    Alles andere geht in die Erfassung — auch ein Satz mit Fragezeichen.
    """
    lowered = text.strip().lower()
    if len(lowered) < 3:
        return False
    words = tokens(lowered)
    if not words or _help(words):
        return False
    core = [w for w in words if w not in FILLER]
    if not core:
        return False
    return not (len(core) <= 2 and set(core) <= QUESTION_WORDS)


def looks_like_create(text: str) -> bool:
    """Erste Nachricht: Anlegen, nicht Bestand oeffnen.

    Such-Leads und kurze Titel-Fragmente bleiben drausen. Verben und
    laengere Saetze sind Anliegen.
    """
    words = tokens(text)
    if not words:
        return False
    if any(w in CREATE_CUES for w in words):
        return True
    core = [w for w in words if w not in FILLER]
    return len(core) >= 8


def _query_label(
    kind: RequestKind | None,
    statuses: tuple[RequestStatus, ...],
    priority: Priority | None,
    company: str | None = None,
    text: str | None = None,
    responsible: str | None = None,
) -> str:
    parts = []
    if statuses and statuses == OPEN_STATUSES:
        parts.append("offene")
    elif len(statuses) == 1:
        parts.append(STATUS_LABELS[statuses[0]].lower())
    if priority:
        parts.append(f"{PRIORITY_LABELS[priority].lower()} priorisierte")
    if company:
        parts.append(company)
    if text:
        parts.append(f"Treffer zu „{text}“")
    else:
        parts.append(KIND_PLURAL[kind] if kind else "Anliegen")
    if responsible:
        parts.append(f"von {responsible}")
    return " ".join(parts)


def _responsible(words: list[str]) -> str | None:
    names = {name.lower(): name for name in responsible_names()}
    if not names:
        return None
    for index, word in enumerate(words):
        name = names.get(word)
        if not name:
            continue
        if len(word) > 1 or (index and words[index - 1] in RESPONSIBLE_LEAD):
            return name
    return None


def _extract_filters(words: list[str]) -> tuple[
    RequestKind | None, tuple[RequestStatus, ...], Priority | None, str | None, str | None
]:
    statuses: tuple[RequestStatus, ...] = ()
    for word in words:
        if word in STATUS_WORDS:
            statuses = STATUS_WORDS[word]
            break
    kind = next((KIND_WORDS[w] for w in words if w in KIND_WORDS), None)
    priority = next((PRIORITY_WORDS[w] for w in words if w in PRIORITY_WORDS), None)
    company = next((COMPANY_WORDS[w] for w in words if w in COMPANY_WORDS), None)
    return kind, statuses, priority, company, _responsible(words)


def _search_query(text: str, words: list[str]) -> Query | None:
    match = SEARCH_LEAD.match(text.strip())
    if not match:
        return None
    remainder = match.group(1).strip().rstrip("?.!")
    if not remainder:
        return None
    rem_words = tokens(remainder)
    # Reine Filterfrage ("zeig offene tickets") bleibt bei _query.
    if set(rem_words) & DOMAIN_WORDS and not (
        set(rem_words) - DOMAIN_WORDS - FILLER - OPEN_VERBS
    ):
        return None
    kind, statuses, priority, company, responsible = _extract_filters(rem_words)
    drop = set(STATUS_WORDS) | set(KIND_WORDS) | set(PRIORITY_WORDS) | FILLER | OPEN_VERBS
    needle_parts = [w for w in rem_words if w not in drop]
    needle = " ".join(needle_parts) if needle_parts else None
    if not needle and not (kind or statuses or priority or company):
        return None
    aliases = {k for k, v in COMPANY_WORDS.items() if v == company}
    if company and needle and needle.lower() in {company.lower(), *aliases}:
        company_keep = company
        if needle.lower() == company.lower() or needle.lower() in COMPANY_WORDS:
            company = company_keep
            drop_needle = needle.lower() in COMPANY_WORDS or needle.lower() == company.lower()
            needle = None if drop_needle else needle
    label = _query_label(kind, statuses, priority, company, needle, responsible)
    return Query(
        label=label,
        kind=kind,
        statuses=statuses,
        priority=priority,
        company=company,
        responsible=responsible,
        text=needle,
    )


def _help(words: list[str]) -> Help | None:
    joined = " ".join(words)
    if joined in {"hilfe", "help", "was kannst du", "was kannst du?"}:
        return Help()
    if "hilfe" in words or "help" in words:
        return Help()
    if "was" in words and ("kannst" in words or "fähig" in words or "faehig" in words):
        return Help()
    return None


def _navigation(text: str, words: list[str]) -> Navigate | None:
    core = [w for w in words if w not in FILLER]
    has_verb = any(w in OPEN_VERBS for w in words)
    for keys, url, label in NAV_TARGETS:
        if not keys.intersection(core):
            continue
        if has_verb or len(core) <= 3:
            return Navigate(url=url, label=label)
    return None


def _comment_body(text: str) -> str | None:
    if ":" in text:
        body = text.split(":", 1)[1].strip()
        return body or None
    match = REFERENCE.search(text)
    if match:
        body = text[match.end():].strip(" ,.-")
        return body or None
    return None


def _status_note_body(text: str) -> str | None:
    match = STATUS_NOTE.search(text)
    if not match:
        return None
    body = " ".join(match.group(1).split())
    return body or None


def _rag_from_words(words: list[str]) -> str | None:
    for word in words:
        if word in RAG_WORDS:
            return RAG_WORDS[word]
    return None


def _action(text: str, words: list[str], has_last: bool) -> Action | Clarify | None:
    reference = find_reference(text)
    word_set = set(words)
    has_target = bool(reference) or bool(word_set & PRONOUNS)
    commanding = (
        bool(word_set & SET_VERBS)
        or bool(word_set & CLOSE_VERBS)
        or bool(word_set & COMMENT_VERBS)
        or "auf" in word_set
    )
    note = _status_note_body(text)
    if not has_target and not commanding and not note:
        return None
    if not reference and not note and ("?" in text or (words and words[0] in QUESTION_WORDS)):
        return None

    if word_set & COMMENT_VERBS:
        body = _comment_body(text)
        if body and not has_target and not has_last:
            return Clarify(reason="target")
        if body:
            return Action(comment=body, reference=reference, words=tuple(words))

    if note:
        if not has_target and not has_last:
            return Clarify(reason="target")
        return Action(
            status_note=note,
            overall_rag=_rag_from_words(words),
            reference=reference,
            words=tuple(words),
        )

    status_word = next((w for w in words if w in SETTABLE_STATUS), None)
    priority_word = next((w for w in words if w in PRIORITY_WORDS), None)

    if (
        not has_target
        and commanding
        and (status_word or priority_word or word_set & CLOSE_VERBS)
        and not has_last
    ):
        return Clarify(reason="target")

    if word_set & CLOSE_VERBS and not status_word:
        return Action(status=RequestStatus.DONE, reference=reference, words=tuple(words))
    if status_word and commanding:
        return Action(
            status=SETTABLE_STATUS[status_word], reference=reference, words=tuple(words)
        )
    if priority_word and commanding:
        return Action(
            priority=PRIORITY_WORDS[priority_word], reference=reference, words=tuple(words)
        )
    return None


def _counting(word_set: set[str]) -> bool:
    return "wieviele" in word_set or ("wie" in word_set and "viele" in word_set)


def _query(text: str, words: list[str]) -> Query | Clarify | None:
    reference = find_reference(text)
    if reference and len(words) <= 4:
        return Query(label=reference, reference=reference)

    word_set = set(words)
    counting = _counting(word_set)
    kind, statuses, priority, company, responsible = _extract_filters(words)
    nouns = bool(word_set & DOMAIN_NOUNS)
    # "Anliegen von A" ist auch ohne Fragewort eine Abfrage auf den Bestand.
    if not (word_set & READ_LEAD or counting or (responsible and nouns)):
        return None
    if not nouns:
        # "welche?" allein — kurz nachfragen. Laengere Saetze sind Anliegen.
        if len(words) <= 3:
            return Clarify(reason="filter")
        return None

    return Query(
        label=_query_label(kind, statuses, priority, company, None, responsible),
        kind=kind,
        statuses=statuses,
        priority=priority,
        company=company,
        responsible=responsible,
        reference=reference,
        counting=counting,
    )


def _follow_up(text: str, words: list[str], last_filter: dict | None) -> Query | None:
    if not last_filter:
        return None
    word_set = set(words)
    # Kurzer Nachsatz: Filter aendern oder Seite weiter.
    if len(words) > 8 and not (word_set & {"und", "nur", "davon", "mehr", "weiter"}):
        return None
    if not (
        word_set & (set(KIND_WORDS) | set(STATUS_WORDS) | set(PRIORITY_WORDS) | MORE_WORDS)
        or "und" in word_set
        or "nur" in word_set
        or "davon" in word_set
    ):
        return None

    kind = RequestKind(last_filter["kind"]) if last_filter.get("kind") else None
    statuses = tuple(RequestStatus(s) for s in (last_filter.get("statuses") or ()))
    priority = Priority(last_filter["priority"]) if last_filter.get("priority") else None
    company = last_filter.get("company")
    responsible = last_filter.get("responsible")
    needle = last_filter.get("query")
    more = bool(word_set & MORE_WORDS)

    new_kind, new_statuses, new_priority, new_company, new_responsible = _extract_filters(words)
    if new_kind:
        kind = new_kind
    if new_statuses:
        statuses = new_statuses
    if new_priority:
        priority = new_priority
    if new_company:
        company = new_company
    if new_responsible:
        responsible = new_responsible

    return Query(
        label=_query_label(kind, statuses, priority, company, needle, responsible),
        kind=kind,
        statuses=statuses,
        priority=priority,
        company=company,
        responsible=responsible,
        text=needle,
        more=more,
    )


def _duplicate_choice(text: str, words: list[str], awaiting: bool) -> DuplicateChoice | None:
    if not awaiting:
        return None
    lowered = text.strip().lower()
    if "trotzdem" in lowered or lowered in {"anlegen", "neu", "lege an", "ja anlegen"}:
        return DuplicateChoice(create=True)
    if any(w in words for w in OPEN_EXISTING) or "öffne" in words or "oeffne" in words:
        return DuplicateChoice(create=False)
    return None


def detect(text: str, context: dict | None = None) -> Intent | None:
    """Erste passende Absicht. Context liefert last_filter und Duplikat-Wartezustand."""
    context = context or {}
    words = tokens(text)
    if not words:
        return None

    dup = _duplicate_choice(text, words, bool(context.get("awaiting_duplicate")))
    if dup:
        return dup

    help_intent = _help(words)
    if help_intent:
        return help_intent

    has_last = bool(context.get("last_request_id"))
    action = _action(text, words, has_last)
    if isinstance(action, Clarify):
        return action
    if action:
        return action

    reference = find_reference(text)
    if reference and any(w in OPEN_VERBS for w in words):
        return OpenRequest(reference=reference)

    navigation = _navigation(text, words)
    if navigation:
        return navigation

    search = _search_query(text, words)
    if search:
        return search

    follow = _follow_up(text, words, context.get("last_filter"))
    if follow:
        return follow

    return _query(text, words)


def merge_query(base: Query, overlay: Query) -> Query:
    """Tests und Assistent: Overlay gewinnt, wo gesetzt."""
    return replace(
        base,
        kind=overlay.kind or base.kind,
        statuses=overlay.statuses or base.statuses,
        priority=overlay.priority or base.priority,
        company=overlay.company or base.company,
        responsible=overlay.responsible or base.responsible,
        text=overlay.text if overlay.text is not None else base.text,
        more=overlay.more or base.more,
        label=overlay.label or base.label,
    )
