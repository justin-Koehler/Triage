"""Felder mit KI aufbereiten. Ticketkontext nutzen, dünne Entwürfe ausformulieren."""

from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.domain.description import (
    description_job,
    description_user_prompt,
    draft_is_prose,
    normalize_description,
    polish_mode,
)
from app.domain.steckbrief_style import CLIP as FIELD_CLIP
from app.services.prose import STYLE, clip_tight, complete_prose
from app.services.settings_service import get_runtime_config
from app.services.websearch import hits_block, search_risks
from app.triage.providers import LlmUnavailable, build_provider_from_runtime

_REVISE = (
    "Der Entwurf ist die verbindliche User-Fassung, oft eine Korrektur einer KI. "
    "Klarer formulieren. Inhalt, Kürzungen und Streichungen behalten. "
    "Keine frühere KI-Fassung rekonstruieren. Nicht aufblasen."
)
PROMPT_VERSION = "polish.v1.2.0"

JOBS = {
    "description": "",  # wird in polish_description per kind gesetzt
    "benefit": f"""Du schreibst das Feld Nutzen.
{_REVISE}
80–220 Zeichen. Was danach besser läuft. Nicht die Beschreibung abschreiben.
Nicht aus anderen Feldern neu ableiten.
""",
    "reason": f"""Du schreibst das Feld Begründung.
{_REVISE}
100–350 Zeichen, dichter Absatz. Warum der Ist-Zustand nicht bleiben kann.
Nicht aus anderen Feldern neu ableiten.
""",
    "solution": f"""Du schreibst das Feld Lösungen/Maßnahme.
{_REVISE}
200–550 Zeichen. Was konkret eingeführt oder umgebaut wird; ggf. Ziele/Abgrenzung.
Nicht aus anderen Feldern neu ableiten.
""",
    "risks": f"""Du schreibst das Feld Bekannte Risiken.
{_REVISE}
80–350 Zeichen. Typische Risiken dieses Changes, nur soweit der Entwurf sie trägt.
Keine erfundenen Systeme oder Namen.
""",
}

OVERVIEW_KEYS = frozenset({"benefit", "reason", "solution", "risks"})

LABELS = {
    "title": "Titel",
    "kind": "Art",
    "priority": "Priorität",
    "start": "Start",
    "end": "Ende",
    "sponsor": "Auftraggeber",
    "components": "Stichwörter / Tags",
    "nonprofit": "Ist das Projekt gemeinnützig",
    "description": "Beschreibung",
    "benefit": "Nutzen",
    "reason": "Begründung",
    "solution": "Lösungen/Maßnahme",
    "risks": "Bekannte Risiken",
    "author": "Autor",
    "approver": "Genehmigende Person",
    "lead": "Gesamtprojektleitung",
    "stakeholder": "Stakeholder",
    "change_team": "Change-Team",
    "it_owner": "Ist die verantwortliche Person aus der IT",
    "process_owner": "Process Owner",
    "solution_owner": "Solution Owner",
    "costs": "Kosten",
    "effort_fb": "Aufwand FB",
    "effort_it": "Aufwand IT",
    "effort_tshirt": "Effort Project",
}

KIND_LABELS = {
    "it_request": "IT Request",
    "change_request": "Change Request",
}

CLIP = FIELD_CLIP

log = logging.getLogger("triage.polish")

_SENT = re.compile(r"(?<=[.!?])\s+")
_META_ECHO = re.compile(
    r"auftraggeber|trägt den auftrag|auftrag für diese|"
    r"\bkomponente(?:n)?\b|"
    r"gemeinnützig|förderfähig|fördercharakter|"
    r"freigabe(?:-?\s*datum|\s+erfolgt)|"
    r"gesamtprojektleiter|\bstakeholder\b|"
    r"aufwand\s+(?:fb|it)|effort project",
    re.I,
)
_SKIP_NEEDLES = {
    "ja",
    "nein",
    "weiß ich noch nicht",
    "weiss ich noch nicht",
    "ich weiß es nicht",
    "ich weiss es nicht",
    "mittel",
    "niedrig",
    "hoch",
    "kritisch",
    "xs",
    "s",
    "m",
    "l",
    "xl",
}


def _foreign_needles(draft: str, fields: dict[str, str] | None) -> list[str]:
    blob = (draft or "").lower()
    out: list[str] = []
    for key, value in (fields or {}).items():
        if key in {"description", "title"}:
            continue
        raw = str(value or "").strip()
        if len(raw) < 3 or raw.lower() in _SKIP_NEEDLES:
            continue
        if raw.lower() in blob:
            continue
        out.append(raw)
    return out


def drop_meta_echo(draft: str, text: str, fields: dict[str, str] | None = None) -> str:
    """Sätze raus, die nur Rollen (Auftraggeber usw.), Komponenten,
    Gemeinnützigkeit usw. nacherzählen."""
    parts = [p.strip() for p in _SENT.split(str(text or "").strip()) if p.strip()]
    if not parts:
        return str(text or "").strip()
    needles = _foreign_needles(draft, fields)
    kept: list[str] = []
    for part in parts:
        sentence = part if part[-1] in ".!?" else f"{part}."
        if _META_ECHO.search(sentence):
            continue
        if any(re.search(rf"(?i)\b{re.escape(needle)}\b", sentence) for needle in needles):
            continue
        kept.append(sentence)
    if kept:
        return " ".join(kept)
    return str(draft or "").strip() or str(text or "").strip()


def _brief(title: str, kind: str, fields: dict[str, str], skip: str) -> str:
    lines: list[str] = []
    if title:
        lines.append(f"Titel: {title}")
    kind_label = KIND_LABELS.get(kind, kind)
    if kind_label and kind not in {"", "open"}:
        lines.append(f"Art: {kind_label}")
    for key, value in (fields or {}).items():
        if key in {skip, "title"} or not str(value or "").strip():
            continue
        if skip in OVERVIEW_KEYS and key in OVERVIEW_KEYS:
            continue
        label = LABELS.get(key, key)
        lines.append(f"{label}: {str(value).strip()}")
    return "\n".join(lines)


def polish_description(
    db: Session,
    text: str,
    title: str = "",
    field: str = "description",
    kind: str = "",
    fields: dict[str, str] | None = None,
) -> str:
    raw = (text or "").strip()
    if not raw:
        return raw
    key = (field or "description").strip().lower()
    if key not in JOBS:
        key = "description"
    provider = build_provider_from_runtime(get_runtime_config(db))
    title = (title or "").strip() or str((fields or {}).get("title") or "").strip()
    kind_key = (kind or "").strip()
    prose = draft_is_prose(raw)
    if key == "description":
        mode = polish_mode(raw)
        user = description_user_prompt(raw, kind_key, mode)
        job = description_job(kind_key)
    else:
        brief = _brief(title, kind_key, fields or {}, key)
        user = (
            f"Schreibe nur das Feld {(LABELS.get(key) or key)} als Klarfassung "
            "des Entwurfs. "
            "Der Entwurf ist verbindlich. Andere Felder nur zum Verständnis, "
            "nicht als Textvorlage. "
            "Keine frühere KI-Fassung wiederherstellen.\n\n"
            + (f"Ticketkontext:\n{brief}\n\n" if brief else "")
            + f"Entwurf:\n{raw}"
        )
        job = JOBS[key]
    if key == "risks" and not prose:
        description = str((fields or {}).get("description") or "").strip()
        web = hits_block(
            search_risks(title, description or raw),
            "Webrecherche (typische Risiken, auf diesen Vorgang beziehen)",
        )
        if web:
            user += f"\n\n{web}"
    system = f"[prompt:{PROMPT_VERSION}:{key}]\n{STYLE}\n\n{job}Nur den Text."
    try:
        out = complete_prose(provider, system, user)
    except LlmUnavailable as err:
        log.warning("KI-Aufwertung fehlgeschlagen: %s", err)
        raise
    if key == "description":
        out = drop_meta_echo(raw, out, fields)
        out = normalize_description(out, raw)
    return clip_tight(out, CLIP.get(key, 280))
