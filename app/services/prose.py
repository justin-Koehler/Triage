"""Prosa für Steckbrief-Felder. Sauberziehen, nicht aufblasen."""

from __future__ import annotations

import re

from app.domain.steckbrief_style import DEFAULT_CLIP, STECKBRIEF_STYLE
from app.triage.providers import LlmUnavailable

STYLE = f"""Du schreibst interne Change-Texte. Lesende: Change-Leitung, kein Marketing.

Stil: aktiv, konkret, deutsch. Wie eine Person im Team in der Akte.
Eine Aussage pro Satz. Keine Broschüre, keine Füllwörter.
Deutsche Orthografie: Umlaute und ß (Maßnahme, Lösung, für, über) —
keine ASCII-Umschreibung und kein Schweizer ss statt ß.

Geschlechtssprache: immer geschlechtsneutral.
Gut: Mitarbeitende, Personen, Leitung, Verantwortung, Team.
Schlecht: Mitarbeiter, Kollege, Nutzer, Leiter, Bearbeiter, Genehmiger
(generisches Maskulinum).

{STECKBRIEF_STYLE}

Schlecht: „Der Avatar schließt die Lücke als interaktive Schnittstelle
und verbessert die Nutzererfahrung.“
Gut: „Am Empfang bleiben Standardfragen zum Gebäude am Personal hängen.
Ein KI-Avatar beantwortet sie vor Ort.“

Verboten: signifikant, skalierbar, ermöglicht, gleichzeitig, Effizienz, Nutzererfahrung,
Lücke schließen, interaktive Schnittstelle, strukturierte Bereitstellung, Mehrwert,
ganzheitlich, nachhaltig, im Rahmen von, zielgerichtet, innovativ.

Erfinde keine Zahlen, Systeme, Namen oder Gremien.
Kein JSON, keine Überschrift, keine Anführungszeichen um den ganzen Text.
"""

_LABEL = re.compile(
    r"^(?:nutzen|begründung|begruendung|lösung(?:en)?|loesung(?:en)?|maßnahme|"
    r"massnahme|risiken|beschreibung|text)\s*[:\-–]\s*",
    re.I,
)


def clip_tight(text: str, limit: int = DEFAULT_CLIP) -> str:
    raw = " ".join((text or "").split()).strip()
    if len(raw) <= limit:
        return raw
    cut = raw[:limit]
    if ". " in cut:
        parts = [p.strip() for p in cut.split(". ") if p.strip()]
        kept = []
        size = 0
        for part in parts:
            chunk = part if part.endswith((".", "!", "?")) else f"{part}."
            extra = len(chunk) + (1 if kept else 0)
            if size + extra > limit:
                break
            kept.append(chunk.rstrip("."))
            size += extra
        if kept:
            out = ". ".join(kept)
            if out[-1] not in ".!?":
                out += "."
            return out
    cut = cut.rsplit(" ", 1)[0].rstrip(".,;:")
    return f"{cut}."


def _fold(text: str) -> str:
    return re.sub(r"[^\w]+", " ", text.lower(), flags=re.UNICODE).strip()


def _is_copy(description: str, benefit: str) -> bool:
    desc = (description or "").strip()
    text = (benefit or "").strip()
    if not desc or not text:
        return False
    if text.lower() == desc.lower():
        return True
    folded_desc, folded_text = _fold(desc), _fold(text)
    shorter, longer = (
        (folded_text, folded_desc)
        if len(folded_text) <= len(folded_desc)
        else (folded_desc, folded_text)
    )
    return len(shorter) >= 40 and shorter in longer


def clean_prose(text: str) -> str:
    raw = (text or "").strip().strip("\"'`")
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:\w+)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    raw = " ".join(raw.split()).strip().strip("\"'")
    raw = _LABEL.sub("", raw).strip().strip("\"'`")
    return raw


def complete_prose(provider, system: str, user: str) -> str:
    complete = getattr(provider, "complete_text", None)
    if callable(complete):
        out = str(complete(system, user) or "").strip()
    else:
        result = provider.complete_json(system + '\nAntwort als JSON: {"text": "..."}', user)
        out = str(result.get("text") or "").strip()
    text = clean_prose(out)
    if not text or text in {"-", "—", "–"}:
        raise LlmUnavailable("leerer Text")
    return text
