"""Steckbrief-Felder aus der Beschreibung: Nutzen, Begründung, Lösung, Risiken."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.domain.risks import field_text, match_patterns
from app.domain.steckbrief_style import CLIP, EXAMPLES
from app.services.prose import STYLE, _is_copy, clean_prose, clip_tight, complete_prose
from app.services.settings_service import get_runtime_config
from app.services.websearch import first_snippet, hits_block, search_risks
from app.triage.providers import LlmUnavailable, build_provider_from_runtime

BENEFIT_SYSTEM = f"""{STYLE}

Du schreibst das Feld Nutzen. Die Beschreibung steht schon im Ticket — nicht nacherzählen.

80–220 Zeichen. Nur die Wirkung: weniger Aufwand, weniger Fehler, bessere Qualität, weniger Risiko.
Nicht Ist, Maßnahme oder Ziel wiederholen.
Keine Labels. Nur den Text.
"""

REASON_SYSTEM = f"""{STYLE}

Du schreibst das Feld Begründung (Problem/Reason).
Beschreibung und Nutzen stehen schon — nicht nacherzählen.

100–350 Zeichen, ein dichter Absatz wie im Steckbrief.
Warum der Ist-Zustand nicht bleiben kann.
Druck, Verlust, Blockade, Mehraufwand, fehlende Übersicht.
Nicht den Nutzen und nicht die Maßnahme wiederholen.
Keine Labels. Nur den Text.
"""

SOLUTION_SYSTEM = f"""{STYLE}

Du schreibst das Feld Lösungen/Maßnahme (Lösung und Ziele).
Die anderen Felder stehen schon — nicht nacherzählen.

200–550 Zeichen. Was konkret eingeführt oder umgebaut wird;
Ziele und ggf. Abgrenzung (NICHT-Ziel).
Kein Warum, kein Nutzen, keine reine Wiederholung der Beschreibung.
Keine Labels. Nur den Text.
"""

RISKS_SYSTEM = f"""{STYLE}

Du schreibst das Feld Bekannte Risiken.
Die anderen Felder stehen schon — nicht nacherzählen.

80–350 Zeichen. Quellen: Tickettext, Maßnahme, Webrecherche.
Was bei DIESEM Change typisch schiefgeht
(Adoption, Parallelbetrieb, Schnittstellen, Akzeptanz, Datenschutz).
Webtreffer auf den Vorgang beziehen, nicht abschreiben.
Keine erfundenen Gremien oder Systeme.
Gibt es Treffer: nicht „Keine bekannten Risiken aus dem Text.“
Ohne Treffer und ohne Hinweis im Text: „Keine bekannten Risiken aus dem Text.“
Keine Wiederholung von Nutzen oder Maßnahme.
Keine Labels. Nur den Text.
"""

OVERVIEW_SYSTEM = f"""{STYLE}

Du füllst vier Felder. Jedes Feld hat eine andere Aufgabe. Kein Feld wiederholt ein anderes.

Nur JSON:
{{"benefit":"...","reason":"...","solution":"...","risks":"..."}}

benefit — Nutzen: was danach besser läuft (Aufwand, Fehler, Qualität, Risiko).
  Nicht die Maßnahme. Länge: 80–220 Zeichen.
reason — Problem/Begründung: warum der Ist-Zustand nicht bleiben kann.
  Nicht den Nutzen. Länge: 100–350 Zeichen, ein dichter Absatz wie im Steckbrief.
solution — Lösungen/Ziele: was konkret eingeführt oder umgebaut wird; ggf. Abgrenzung.
  Länge: 200–550 Zeichen. Darf länger und strukturierter sein als die anderen.
risks — bekannte Risiken aus Text, Maßnahme und Webrecherche.
  Adoption, Parallelbetrieb, Schnittstellen, Akzeptanz, Datenschutz, Betrieb.
  Länge: 80–350 Zeichen. Webtreffer nicht abschreiben, nichts erfinden.
  Gibt es Treffer: nicht „Keine bekannten Risiken aus dem Text.“
  Ohne Treffer und ohne Hinweis im Text: „Keine bekannten Risiken aus dem Text.“

{EXAMPLES}

Beispiel kompakt (Urlaubsanträge auf Papier, Verluste):
{{
  "benefit": "Weniger Handarbeit, Anträge gehen nicht verloren; Stand ist klar.",
  "reason": "Auf Papier fehlt der Stand; Nachfragen und Verluste sind Normalfall.",
  "solution": "Digitale Erfassung mit Freigabe und zentralem Ablageort. NICHT-Ziel: Auto-HR.",
  "risks": "Führung bleibt auf Papier, wenn der alte Weg offen bleibt; Löschkonzept klären."
}}
"""

EMPTY_RISK = "Keine bekannten Risiken aus dem Text."
PROMPT_VERSION = "overview.v1.1.0"
MAX_TEXT = CLIP["benefit"]
log_benefit = logging.getLogger("triage.benefit")
log_reason = logging.getLogger("triage.reason")
log_solution = logging.getLogger("triage.solution")
log_risks = logging.getLogger("triage.risks")
log_overview = logging.getLogger("triage.overview")


def infer_benefit(db: Session, description: str, title: str = "") -> str:
    raw = (description or "").strip()
    if not raw:
        raise LlmUnavailable("keine Beschreibung")
    provider = build_provider_from_runtime(get_runtime_config(db))
    title = (title or "").strip()
    user = (
        "Schreibe nur den Nutzen, nicht die Beschreibung noch einmal.\n\n"
        + (f"Titel: {title}\n\n" if title else "")
        + f"Beschreibung:\n{raw}"
    )
    try:
        out = complete_prose(provider, BENEFIT_SYSTEM, user)
    except LlmUnavailable as err:
        log_benefit.warning("Nutzen-Ermittlung fehlgeschlagen: %s", err)
        raise
    text = clip_tight(out, MAX_TEXT)
    if _is_copy(raw, text):
        log_benefit.warning("Nutzen war eine Kopie der Beschreibung")
        raise LlmUnavailable("Nutzen war eine Kopie der Beschreibung")
    return text


def infer_reason(db: Session, description: str, title: str = "", benefit: str = "") -> str:
    raw = (description or "").strip()
    if not raw:
        raise LlmUnavailable("keine Beschreibung")
    provider = build_provider_from_runtime(get_runtime_config(db))
    title = (title or "").strip()
    benefit = (benefit or "").strip()
    parts = ["Schreibe nur die Begründung, nicht Beschreibung oder Nutzen.\n"]
    if title:
        parts.append(f"Titel: {title}\n")
    parts.append(f"Beschreibung:\n{raw}")
    if benefit:
        parts.append(f"\n\nNutzen (nicht wiederholen):\n{benefit}")
    user = "\n".join(parts)
    try:
        out = complete_prose(provider, REASON_SYSTEM, user)
    except LlmUnavailable as err:
        log_reason.warning("Begründung-Ermittlung fehlgeschlagen: %s", err)
        raise
    text = clip_tight(out, CLIP["reason"])
    if _is_copy(raw, text) or (benefit and _is_copy(benefit, text)):
        log_reason.warning("Begründung war eine Kopie")
        raise LlmUnavailable("Begründung war eine Kopie")
    return text


def infer_solution(
    db: Session,
    description: str,
    title: str = "",
    benefit: str = "",
    reason: str = "",
) -> str:
    raw = (description or "").strip()
    if not raw:
        raise LlmUnavailable("keine Beschreibung")
    provider = build_provider_from_runtime(get_runtime_config(db))
    title = (title or "").strip()
    benefit = (benefit or "").strip()
    reason = (reason or "").strip()
    parts = ["Schreibe nur die Lösung/Maßnahme, nicht Beschreibung, Nutzen oder Begründung.\n"]
    if title:
        parts.append(f"Titel: {title}\n")
    parts.append(f"Beschreibung:\n{raw}")
    if benefit:
        parts.append(f"\n\nNutzen (nicht wiederholen):\n{benefit}")
    if reason:
        parts.append(f"\n\nBegründung (nicht wiederholen):\n{reason}")
    user = "\n".join(parts)
    try:
        out = complete_prose(provider, SOLUTION_SYSTEM, user)
    except LlmUnavailable as err:
        log_solution.warning("Lösung-Ermittlung fehlgeschlagen: %s", err)
        raise
    text = clip_tight(out, CLIP["solution"])
    for other in (raw, benefit, reason):
        if other and _is_copy(other, text):
            log_solution.warning("Lösung war eine Kopie")
            raise LlmUnavailable("Lösung war eine Kopie")
    return text


def infer_risks(
    db: Session,
    description: str,
    title: str = "",
    benefit: str = "",
    reason: str = "",
    solution: str = "",
) -> str:
    raw = (description or "").strip()
    if not raw:
        raise LlmUnavailable("keine Beschreibung")
    title = (title or "").strip()
    benefit = (benefit or "").strip()
    reason = (reason or "").strip()
    solution = (solution or "").strip()
    seed = field_text(match_patterns(" ".join(part for part in (title, raw) if part)))
    provider = build_provider_from_runtime(get_runtime_config(db))
    parts = ["Schreibe nur bekannte Risiken, nicht die anderen Felder.\n"]
    if title:
        parts.append(f"Titel: {title}\n")
    parts.append(f"Beschreibung:\n{raw}")
    if benefit:
        parts.append(f"\n\nNutzen (nicht wiederholen):\n{benefit}")
    if reason:
        parts.append(f"\n\nBegründung (nicht wiederholen):\n{reason}")
    if solution:
        parts.append(f"\n\nLösung (nicht wiederholen):\n{solution}")
    if seed:
        parts.append(f"\n\nStichwort-Hinweis:\n{seed}")
    hits = search_risks(title, raw)
    web = hits_block(hits, "Webrecherche (typische Risiken, auf diesen Vorgang beziehen)")
    if web:
        parts.append(f"\n\n{web}")
    user = "\n".join(parts)
    fallback = clip_tight(seed, CLIP["risks"]) or clip_tight(first_snippet(hits), CLIP["risks"])
    try:
        out = complete_prose(provider, RISKS_SYSTEM, user)
    except LlmUnavailable as err:
        if fallback:
            return fallback
        log_risks.warning("Risiko-Ermittlung fehlgeschlagen: %s", err)
        raise
    text = clip_tight(out, CLIP["risks"])
    for other in (raw, benefit, reason, solution):
        if other and _is_copy(other, text):
            if fallback:
                return fallback
            log_risks.warning("Risiken waren eine Kopie")
            raise LlmUnavailable("Risiken waren eine Kopie")
    if text == EMPTY_RISK and fallback:
        return fallback
    return text


def infer_overview(db: Session, description: str, title: str = "") -> dict[str, str]:
    raw = (description or "").strip()
    if not raw:
        raise LlmUnavailable("keine Beschreibung")
    title = (title or "").strip()
    seed = field_text(match_patterns(" ".join(part for part in (title, raw) if part)))
    provider = build_provider_from_runtime(get_runtime_config(db))
    user = (f"Titel: {title}\n\n" if title else "") + f"Beschreibung:\n{raw}"
    if seed:
        user += f"\n\nRisiko-Hinweis aus Mustern (nur nutzen wenn passend):\n{seed}"
    hits = search_risks(title, raw)
    web = hits_block(hits, "Webrecherche (typische Risiken, auf diesen Vorgang beziehen)")
    if web:
        user += f"\n\n{web}"
    try:
        payload = provider.complete_json(f"[prompt:{PROMPT_VERSION}]\n{OVERVIEW_SYSTEM}", user[:5000])
    except LlmUnavailable as err:
        log_overview.warning("Übersicht fehlgeschlagen: %s", err)
        raise
    benefit = clip_tight(clean_prose(str(payload.get("benefit") or "")), CLIP["benefit"])
    reason = clip_tight(clean_prose(str(payload.get("reason") or "")), CLIP["reason"])
    solution = clip_tight(clean_prose(str(payload.get("solution") or "")), CLIP["solution"])
    risks = clip_tight(clean_prose(str(payload.get("risks") or "")), CLIP["risks"])
    if not benefit or _is_copy(raw, benefit):
        raise LlmUnavailable("Nutzen unbrauchbar")
    if not reason or _is_copy(raw, reason) or _is_copy(benefit, reason):
        raise LlmUnavailable("Begründung unbrauchbar")
    if not solution or _is_copy(raw, solution):
        raise LlmUnavailable("Lösung unbrauchbar")
    copied = (
        not risks
        or _is_copy(raw, risks)
        or _is_copy(benefit, risks)
        or _is_copy(solution, risks)
    )
    empty = risks == EMPTY_RISK
    if copied or (empty and hits):
        risks = (
            clip_tight(seed, CLIP["risks"])
            or clip_tight(clean_prose(first_snippet(hits)), CLIP["risks"])
            or EMPTY_RISK
        )
    elif not risks:
        risks = EMPTY_RISK
    return {
        "benefit": benefit,
        "reason": reason,
        "solution": solution,
        "risks": risks,
    }
