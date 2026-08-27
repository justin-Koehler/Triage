"""Gemeinsame Spec für Beschreibungs-KI: Intake + Polish."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Satzzahl und Eingabe-Schwellen — Intake und Polish teilen dieselben Regeln.
# Beschreibung oft 200–450 Zeichen.
MIN_SENTENCES = 2
MAX_SENTENCES = 6
EXPAND_SENTENCES = (3, 5)
REVISE_SENTENCES = (2, 5)
THIN_CHARS = 80
PROSE_CHARS = 200

_SENT = re.compile(r"(?<=[.!?])\s+")
_ENDS = re.compile(r"[.!?…]")

_IST = re.compile(
    r"\b("
    r"heute|aktuell|derzeit|momentan|laufen|läuft|papier|manuell|per\s+hand|"
    r"fehlen|fehlt|hängen|hängt|verloren|unklar|stockt|bricht|dauert|"
    r"aufwendig|umständlich|excel|e-?mail|telefon"
    r")\b",
    re.I,
)
_PROBLEM = re.compile(
    r"\b("
    r"problem|fehler|verlust|nachfragen|wartezeit|engpass|risiko|"
    r"wenn\s+nichts|sonst|dadurch|deshalb|folgen"
    r")\b",
    re.I,
)
_SOLL = re.compile(
    r"\b("
    r"soll|sollen|wird|werden|digital|einführen|ersetzen|umstellen|"
    r"automatisieren|bereitstellen|ziel|danach|künftig|neu"
    r")\b",
    re.I,
)
_BANNED = re.compile(
    r"\b("
    r"signifikant|skalierbar|effizienz|nutzererfahrung|ganzheitlich|"
    r"nachhaltig|innovativ|mehrwert|zielgerichtet|interaktive\s+schnittstelle|"
    r"lücke\s+schließen|strukturierte\s+bereitstellung"
    r")\b",
    re.I,
)
_META = re.compile(
    r"auftraggeber|trägt den auftrag|"
    r"\bkomponente(?:n)?\b|"
    r"gemeinnützig|förderfähig|fördercharakter|"
    r"freigabe(?:-?\s*datum|\s+erfolgt)|"
    r"gesamtprojektleiter|\bstakeholder\b|"
    r"aufwand\s+(?:fb|it)|effort project",
    re.I,
)

CHANGE_FOCUS = (
    "Schwerpunkt Change Request: Prozess, Organisation, Einführung, "
    "Kommunikation, Schulung, betroffene Rollen/Gruppen, Widerstände."
)
IT_FOCUS = (
    "Schwerpunkt IT Request: Systeme, Software, Schnittstellen, Zugänge, "
    "Login, Browser/Client, technische Umsetzung — ohne erfundene Produktnamen."
)

DESCRIPTION_RULES = """Beschreibung = was der Change ist und worum es geht (Steckbrief-Stil).
Orientierung: reale SCS-Steckbriefe, typisch 200–450 Zeichen.
- Worum geht es? Was soll sich ändern? Wer/was ist betroffen?
- Kontext, Phasen oder Abgrenzung dürfen kurz vorkommen.
- Bei dünner Eingabe: Ist → Problem → Soll in zwei bis vier Sätzen.
Zwei bis sechs Sätze. Keine Broschüre, keine Füllwörter, nichts erfinden.
Verboten in der Beschreibung: Auftraggeber, Komponenten,
Gemeinnützigkeit/DSS, Freigabe, Termine, Team, Aufwand.
"""


@dataclass(frozen=True)
class DescriptionScore:
    ok: bool
    sentences: int
    has_ist: bool
    has_problem: bool
    has_soll: bool
    issues: tuple[str, ...]


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENT.split(str(text or "").strip()) if p.strip()]
    out: list[str] = []
    for part in parts:
        sentence = part if part[-1:] in ".!?" else f"{part}."
        out.append(sentence)
    return out


def draft_is_prose(raw: str) -> bool:
    text = " ".join((raw or "").split())
    if len(text) >= PROSE_CHARS:
        return True
    return len(_ENDS.findall(text)) >= 2


def draft_is_thin(raw: str) -> bool:
    text = " ".join((raw or "").split())
    if not text:
        return True
    return len(text) < THIN_CHARS and not draft_is_prose(text)


def polish_mode(raw: str) -> str:
    """expand = ausformulieren, revise = nur klarziehen."""
    if draft_is_thin(raw):
        return "expand"
    if draft_is_prose(raw):
        return "revise"
    return "expand"


def kind_focus(kind: str) -> str:
    key = (kind or "").strip().lower()
    if key == "it_request":
        return IT_FOCUS
    if key == "change_request":
        return CHANGE_FOCUS
    return "Art noch offen — Ton aus dem Inhalt wählen (Prozess vs. IT)."


def description_job(kind: str = "") -> str:
    return (
        "Du schreibst die Beschreibung eines Change-/IT-Tickets.\n\n"
        f"{DESCRIPTION_RULES}\n"
        f"{kind_focus(kind)}\n\n"
        "Quelle ist allein der Entwurf. Keine anderen Ticketfelder."
    )


_NO_META = (
    "Keine Sätze zu Auftraggeber, Komponenten, "
    "Gemeinnützigkeit, Freigabe, Team oder Aufwand."
)


def description_user_prompt(raw: str, kind: str = "", mode: str | None = None) -> str:
    mode = mode or polish_mode(raw)
    focus = kind_focus(kind)
    if mode == "revise":
        return (
            "Modus: Klarziehen. Der Entwurf ist verbindliche User-Prosa.\n"
            "Inhalt und Kürzungen behalten. Nicht aufblasen, nichts rekonstruieren.\n"
            f"Ziel: {REVISE_SENTENCES[0]}–{REVISE_SENTENCES[1]} Sätze, Steckbrief-Stil "
            "(200–450 Zeichen typisch; bei dünnem Entwurf Ist → Problem → Soll).\n"
            f"{focus}\n"
            f"{_NO_META}\n\n"
            f"Entwurf:\n{raw}"
        )
    lo, hi = EXPAND_SENTENCES
    if draft_is_thin(raw):
        lo, hi = MIN_SENTENCES, 3
    return (
        "Modus: Ausformulieren. Formuliere nur aus, was im Entwurf steckt.\n"
        f"Ziel: {lo}–{hi} Sätze, Steckbrief-Stil (200–450 Zeichen typisch).\n"
        f"{focus}\n"
        f"{_NO_META}\n\n"
        f"Entwurf:\n{raw}"
    )


def intake_description_block(kind: str | None = None) -> str:
    """Block für de_intake.md — kind-spezifisch."""
    key = (kind.value if hasattr(kind, "value") else kind) or ""
    return (
        f"{DESCRIPTION_RULES}\n"
        f"{kind_focus(str(key))}\n"
        "`description` folgt diesem Steckbrief-Stil. "
        "Ist der Nutzersatz sehr dünn: zwei knappe Sätze Ist → Problem → Soll, "
        "sonst drei bis fünf Sätze (ca. 200–450 Zeichen)."
    )


def score_description(text: str, draft: str = "") -> DescriptionScore:
    """Heuristik: Satzzahl + Ist/Problem/Soll-Signale + Verbote."""
    cleaned = " ".join((text or "").split()).strip()
    sents = split_sentences(cleaned)
    n = len(sents)
    blob = cleaned.lower()
    has_ist = bool(_IST.search(blob))
    has_problem = bool(_PROBLEM.search(blob)) or (n >= 2 and has_ist)
    has_soll = bool(_SOLL.search(blob))
    issues: list[str] = []
    if n < MIN_SENTENCES:
        issues.append("zu_wenige_saetze")
    if n > MAX_SENTENCES:
        issues.append("zu_viele_saetze")
    if not has_ist and n >= 2:
        issues.append("kein_ist")
    if not has_soll and n >= 2:
        issues.append("kein_soll")
    if _BANNED.search(cleaned):
        issues.append("marketing")
    if _META.search(cleaned):
        issues.append("meta_echo")
    draft_len = len(" ".join((draft or "").split()))
    if draft_len and draft_len < THIN_CHARS and len(cleaned) > max(220, draft_len * 4):
        issues.append("aufgeblasen")
    # Weiches Ist: Soll klar + Satzzahl ok → fehlendes Ist-Signalwort kein Fail.
    soft = issues == ["kein_ist"] and has_soll and MIN_SENTENCES <= n <= MAX_SENTENCES
    if soft:
        issues = []
    ok = not issues and MIN_SENTENCES <= n <= MAX_SENTENCES
    return DescriptionScore(
        ok=ok,
        sentences=n,
        has_ist=has_ist,
        has_problem=has_problem,
        has_soll=has_soll,
        issues=tuple(issues),
    )


def normalize_description(text: str, draft: str = "", *, max_sentences: int = MAX_SENTENCES) -> str:
    """Nachbearbeitung: Satzzahl kappen, Meta/Marketing-Sätze streichen."""
    sents = split_sentences(text)
    kept: list[str] = []
    for sentence in sents:
        if _META.search(sentence) or _BANNED.search(sentence):
            continue
        kept.append(sentence)
    if not kept:
        kept = split_sentences(draft) or sents
    if len(kept) > max_sentences:
        kept = kept[:max_sentences]
    return " ".join(kept).strip()
