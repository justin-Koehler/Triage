"""Aufwand prüfen: Nutzer-PT bewerten, Spanne aus Detailgrad + Web vorschlagen."""

from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.domain.calc import parse_number
from app.knowledge import cases
from app.services.settings_service import get_runtime_config
from app.services.websearch import hits_block, search_effort
from app.triage.providers import LlmUnavailable, build_provider_from_runtime

SYSTEM = """Du prüfst eine vom Nutzer angegebene Aufwandsschätzung in Personentagen (PT).

Du überschreibst die Nutzer-Zahlen NICHT im Ticket. Du schlägst aber IMMER eine
eigene Spanne vor — auch wenn die Websuche dünn ist.

Grundlage der Spanne (in dieser Reihenfolge):
1) Detailgrad der Beschreibung: Scope, Systeme, Integrationen, Rollout, Schulung.
   Wenig konkret / kleiner Einstieg → engere, niedrigere Spanne.
   Viele Systeme, Campus-weit, Twin/BIM/SAP/Schnittstellen → breitere, höhere Spanne.
2) Vergleichsfälle und Webtreffer (Namen und Dauer nur, wenn sie im Prompt stehen).
3) Keine Treffer: trotzdem Spanne aus dem beschriebenen Scope ableiten — nie
   „keine Vergleichsdaten“ als einzige Antwort.

Nur JSON:
{"rating":"angemessen"|"eher_hoch"|"eher_niedrig"|"unsicher",
 "span":"<niedrig>–<hoch>",
 "why":"<kurz>"}

rating: Wie die Nutzer-Angabe zur Spanne steht.
- angemessen — liegt in/nahe der Spanne
- eher_hoch — deutlich über der Spanne
- eher_niedrig — deutlich unter der Spanne
- unsicher — nur wenn Beschreibung zu dünn für jede Einordnung

span: Gesamtschätzung in PT als Spanne, z. B. "8–15" oder "20–40".
  Nur Zahlen und Bindestrich/En-Dash. Keine Einheit in span.

why: maximal zwei kurze Sätze (~40 Wörter / ~200 Zeichen), vollständig enden.
1) Spanne nennen und warum (Detailgrad / Scope aus der Beschreibung).
2) Optional ein konkretes Projekt aus den Treffern (Name + Dauer), sonst weglassen.
Gut: „Spanne 15–30 PT: BIM und Campus-Bezug machen den Twin mittelgroß.
Ähnlich Digital Twin TUM — oft 6–12 Monate.“
Gut: „Spanne 6–12 PT: ein Formular mit Freigabe, begrenzter Scope.“
Schlecht: „Keine Vergleichsdaten“; eigene Projektnamen erfinden; Nutzer-PT überschreiben.
Nur Namen aus den Treffern. Keine Abkürzungen außer PT/Jira/SAP/BIM.
"""

HINT_DEFAULT = "Aufwand eintragen — die KI schlägt danach eine Spanne vor"
HINT_MAX = 240
RATING_LABEL = {
    "angemessen": "Angemessen",
    "eher_hoch": "Eher hoch",
    "eher_niedrig": "Eher niedrig",
    "unsicher": "Unsicher",
}
log = logging.getLogger("triage.effort")
_WEEKS = re.compile(
    r"(?i)(\d+(?:[.,]\d+)?)"
    r"(?:\s*(?:–|-|bis)\s*(\d+(?:[.,]\d+)?))?\s*"
    r"(wochen|woche|monaten|monate|monat|tagen|tage|tag|personentage|manntage|pt)\b"
)
_SPAN = re.compile(
    r"(?i)(\d+(?:[.,]\d+)?)\s*[–\-]\s*(\d+(?:[.,]\d+)?)"
)
_LEAD = re.compile(
    r"^(?:online-?vergleich|vergleich)\s*[:：'\"]*\s*",
    re.I,
)
_DROP_SENTENCE = re.compile(
    r"(?i)("
    r"keine vergleichsdaten|wenig vergleichsmaterial|"
    r"hoher aufwand für|iot-integration|echtzeit-sync|3d-visual|"
    r"it-?lastig|analog zum|datenintegration|fachliche validierung|"
    r"3d-?modellierung|kompakter campus-start|rollout-begleitung|"
    r"modellierung der|erfordert dennoch|spürbaren aufwand für"
    r")"
)
_PLAIN_SWAPS = [
    (re.compile(r"(?i)\banalog zum\b"), "ähnlich wie"),
    (re.compile(r"(?i)\bit-?lastig\b"), "technisch aufwendig"),
    (re.compile(r"(?i)\bfb\b"), "Fachbereich"),
    (re.compile(r"(?i)\bfachliche validierung\b"), "fachliche Prüfung"),
    (re.compile(r"(?i)\bdatenintegration\b"), "Daten abgleichen"),
    (re.compile(r"(?i)\b3d-?modellierung\b"), "3D-Darstellung"),
    (re.compile(r"(?i)\bkompakter campus-start\b"), "kleinerer Einstieg"),
    (re.compile(r"(?i)\bkeine vergleichsdaten verfügbar\.?\s*"), ""),
    (re.compile(r"(?i)\bwenig vergleichsmaterial gefunden\.?\s*"), ""),
]
_HEAVY = (
    "digital twin",
    "digitaler zwilling",
    "bim",
    "sap",
    "schnittstelle",
    "integration",
    "iot",
    "echtzeit",
    "3d",
    "rollout",
    "campus-weit",
    "campusweit",
    "migration",
)
_MEDIUM = (
    "formular",
    "workflow",
    "prozess",
    "portal",
    "app",
    "schulung",
    "dashboard",
    "freigabe",
    "digital",
)


def round_pt(value: float) -> float:
    if value != value:
        return 0.0
    return max(0.0, min(120.0, round(value * 2) / 2))


def format_pt(value: float) -> str:
    n = round_pt(value)
    if n == int(n):
        return f"{int(n)} PT"
    return f"{n:.1f}".replace(".", ",") + " PT"


def format_span(low: float, high: float) -> str:
    a, b = round_pt(low), round_pt(high)
    if a > b:
        a, b = b, a
    if a < 1:
        a = 1.0
    if b < a + 1:
        b = a + 2.0

    def _n(v: float) -> str:
        return str(int(v)) if v == int(v) else f"{v:.1f}".replace(".", ",")

    return f"{_n(a)}–{_n(b)}"


def tshirt_for(total: float) -> str:
    if total <= 2:
        return "XS"
    if total <= 5:
        return "S"
    if total <= 15:
        return "M"
    if total <= 40:
        return "L"
    return "XL"


def as_pt(raw: object) -> float:
    if isinstance(raw, bool):
        return 0.0
    if isinstance(raw, (int, float)):
        return round_pt(float(raw))
    return round_pt(parse_number(raw))


def heuristic_pt(text: str, is_it: bool) -> tuple[float, float]:
    """Nur noch Hilfsfunktion für Tests/Fallback — keine Auto-Schätzung mehr."""
    low, high, _ = detail_span(text, is_it)
    mid = round_pt((low + high) / 2)
    if not is_it:
        return mid, 0.0
    fb = round_pt(mid * 0.35)
    it = round_pt(mid - fb)
    return fb, it


def detail_span(text: str, is_it: bool) -> tuple[float, float, str]:
    """Spanne aus Beschreibungstiefe — unabhängig von Webtreffern."""
    blob = (text or "").lower()
    words = len((text or "").split())
    heavy = sum(1 for key in _HEAVY if key in blob)
    medium = sum(1 for key in _MEDIUM if key in blob)

    if heavy >= 2 or (heavy and words >= 60):
        low, high = (18.0, 45.0) if is_it else (12.0, 30.0)
        why = "Beschreibung nennt mehrere technische Bausteine bzw. großen Scope"
    elif heavy or (medium >= 2 and words >= 40):
        low, high = (10.0, 25.0) if is_it else (8.0, 18.0)
        why = "mittlerer Detailgrad mit klaren System- oder Prozessanteilen"
    elif medium or words >= 35:
        low, high = (6.0, 14.0) if is_it else (4.0, 10.0)
        why = "beschränkter, aus der Beschreibung greifbarer Scope"
    else:
        low, high = (3.0, 8.0) if is_it else (2.0, 6.0)
        why = "noch grobe Beschreibung, eher Einstieg"

    if "pilot" in blob or "mvp" in blob or "kleiner einstie" in blob:
        low = max(2.0, low * 0.6)
        high = max(low + 2.0, high * 0.7)
        why = "Pilot/MVP in der Beschreibung — bewusst kleinerer Einstieg"
    return round_pt(low), round_pt(high), why


def _kb_block(hits: list[cases.Hit]) -> str:
    if not hits:
        return ""
    lines: list[str] = []
    for hit in hits:
        case = hit.case
        effort = case.effort_line() or "Aufwand nicht hinterlegt"
        lines.append(f"- {case.id} — {case.title}: {effort}")
    return "Vergleichsfälle (Wissensbasis):\n" + "\n".join(lines)


def _project_label(title: str) -> str:
    raw = " ".join(str(title or "").split()).strip()
    if not raw:
        return ""
    for sep in (" | ", " – ", " — ", " - ", ": "):
        if sep in raw:
            raw = raw.split(sep, 1)[0].strip()
            break
    return raw[:48].rstrip(" .,:;")


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _plain_hint(text: str) -> str:
    raw = " ".join(str(text or "").split()).strip()
    for pat, rep in _PLAIN_SWAPS:
        raw = pat.sub(rep, raw)
    return " ".join(raw.split()).strip()


def _drop_junk(text: str) -> str:
    parts = _split_sentences(text)
    if not parts:
        return ""
    kept = [p for p in parts if not _DROP_SENTENCE.search(p)]
    if not kept:
        return ""
    raw = " ".join(kept).strip()
    if raw and raw[-1] not in ".!?":
        raw += "."
    return raw


def _clip_hint(text: str) -> str:
    raw = _plain_hint(" ".join(str(text or "").split()))
    raw = _LEAD.sub("", raw).strip()
    raw = raw.replace("„", "").replace("“", "").replace("'", "").replace('"', "")
    raw = _drop_junk(raw)
    if not raw:
        return ""
    raw = raw[0].upper() + raw[1:]
    if len(raw) <= HINT_MAX:
        return raw
    parts = _split_sentences(raw)
    if parts:
        first = parts[0]
        if first[-1] not in ".!?":
            first += "."
        if 20 <= len(first) <= HINT_MAX:
            return first
        if len(parts) >= 2:
            pair = f"{parts[0]} {parts[1]}"
            if pair[-1] not in ".!?":
                pair += "."
            if len(pair) <= HINT_MAX:
                return pair
    cut = raw[:HINT_MAX]
    for sep in (". ", " — ", " – ", "; "):
        idx = cut.rfind(sep)
        if idx >= 36:
            out = cut[:idx].rstrip(".,;: ")
            return out + "."
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(".,;:") + "."


def _normalize_rating(raw: object) -> str:
    key = str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "ok": "angemessen",
        "passend": "angemessen",
        "realistisch": "angemessen",
        "hoch": "eher_hoch",
        "zu_hoch": "eher_hoch",
        "niedrig": "eher_niedrig",
        "zu_niedrig": "eher_niedrig",
        "knapp": "eher_niedrig",
        "unklar": "unsicher",
    }
    key = aliases.get(key, key)
    if key in RATING_LABEL:
        return key
    return "unsicher"


def _parse_span(raw: object, fallback_low: float, fallback_high: float) -> tuple[float, float]:
    text = str(raw or "").strip()
    match = _SPAN.search(text.replace("—", "–").replace("−", "-"))
    if not match:
        return fallback_low, fallback_high
    low = parse_number(match.group(1))
    high = parse_number(match.group(2))
    if low <= 0 or high <= 0:
        return fallback_low, fallback_high
    return round_pt(low), round_pt(high)


def _rating_vs_span(total: float, low: float, high: float) -> str:
    if total <= 0:
        return "unsicher"
    mid = (low + high) / 2
    width = max(high - low, 2.0)
    if low * 0.85 <= total <= high * 1.15:
        return "angemessen"
    if total > high + width * 0.25 or total > mid * 1.6:
        return "eher_hoch"
    if total < low * 0.75 or total < mid * 0.55:
        return "eher_niedrig"
    return "angemessen"


def _fallback_why(
    hits: list[cases.Hit],
    web: list[dict],
    fb: float,
    it: float,
    low: float,
    high: float,
    scope_why: str,
) -> str:
    span = format_span(low, high)
    stated = format_pt(fb) if it <= 0 else f"{format_pt(fb)} FB / {format_pt(it)} IT"
    base = f"Spanne ca. {span} PT — {scope_why}. Deine Angabe {stated}."
    if hits:
        case = hits[0].case
        effort = case.effort_line()
        if effort:
            return _clip_hint(f"{base} Ähnlich wie {case.title} — dort {effort}.")
        return _clip_hint(f"{base} Ähnlich wie {case.title}.")
    for hit in web:
        name = _project_label(str(hit.get("title") or ""))
        snippet = " ".join(str(hit.get("snippet") or "").split())
        if not name:
            continue
        match = _WEEKS.search(f"{name} {snippet}")
        if match:
            return _clip_hint(f"{base} Online: {name} — oft {match.group(0)}.")
        return _clip_hint(f"{base} Online vergleichbar mit {name}.")
    return _clip_hint(base)


def review_effort(
    db: Session,
    description: str,
    *,
    title: str = "",
    kind: str = "",
    fb: object = 0,
    it: object = 0,
) -> dict:
    """Nutzer-PT prüfen: Web + Detailgrad → Spanne mit Begründung."""
    raw = (description or "").strip()
    if not raw:
        raise LlmUnavailable("keine Beschreibung")
    title = (title or "").strip()
    is_it = (kind or "").strip() == "it_request"
    fb_pt = as_pt(fb)
    it_pt = as_pt(it) if is_it else 0.0
    if fb_pt <= 0 and it_pt <= 0:
        raise LlmUnavailable("kein Aufwand eingetragen")

    seed = " ".join(part for part in (title, raw) if part)
    low, high, scope_why = detail_span(seed, is_it)
    kb_hits = cases.search(seed, limit=2)
    web = search_effort(title, raw, limit=5)
    provider = build_provider_from_runtime(get_runtime_config(db))

    parts = [f"kind: {kind or 'open'}"]
    if title:
        parts.append(f"Titel: {title}")
    parts.append(f"Beschreibung:\n{raw}")
    parts.append(
        f"Nutzer-Angabe: FB {format_pt(fb_pt)}"
        + (f", IT {format_pt(it_pt)}" if is_it else "")
    )
    parts.append(
        f"Heuristik aus Detailgrad (nur Orientierung): Spanne {format_span(low, high)} PT "
        f"— {scope_why}."
    )
    kb_text = _kb_block(kb_hits)
    if kb_text:
        parts.append(kb_text)
    web_text = hits_block(web, "Webrecherche (ähnliche Projekte / Dauer)")
    if web_text:
        parts.append(web_text)
    else:
        parts.append(
            "Webrecherche: keine brauchbaren Treffer. "
            "Spanne trotzdem aus dem Detailgrad der Beschreibung ableiten."
        )

    total = fb_pt + it_pt
    rating = _rating_vs_span(total, low, high)
    why = _fallback_why(kb_hits, web, fb_pt, it_pt, low, high, scope_why)
    span_low, span_high = low, high
    try:
        payload = provider.complete_json(SYSTEM, "\n\n".join(parts)[:5500])
        span_low, span_high = _parse_span(payload.get("span"), low, high)
        model_rating = _normalize_rating(payload.get("rating"))
        if model_rating != "unsicher" or len(raw.split()) < 12:
            rating = model_rating
        else:
            rating = _rating_vs_span(total, span_low, span_high)
        said = " ".join(str(payload.get("why") or "").split()).strip()
        if said:
            span_txt = format_span(span_low, span_high)
            if "spanne" not in said.lower() and _SPAN.search(said) is None:
                said = f"Spanne ca. {span_txt} PT. {said}"
            clipped = _clip_hint(said)
            if clipped:
                why = clipped
    except LlmUnavailable as err:
        log.warning("Aufwand-Prüfung per Modell fehlgeschlagen: %s", err)

    label = RATING_LABEL.get(rating, "Unsicher")
    body = why or HINT_DEFAULT
    if not body.lower().startswith(label.lower()):
        hint = _clip_hint(f"{label}: {body}")
    else:
        hint = body
    if not hint:
        hint = (
            f"{label}: Spanne ca. {format_span(span_low, span_high)} PT — {scope_why}."
        )

    return {
        "rating": rating,
        "hint": hint[:HINT_MAX] if len(hint) > HINT_MAX else hint,
        "span": format_span(span_low, span_high),
        "effort": tshirt_for(total),
        "fb": format_pt(fb_pt),
        "it": format_pt(it_pt),
    }


def infer_effort(
    db: Session,
    description: str,
    title: str = "",
    kind: str = "",
    fb: object = 0,
    it: object = 0,
) -> dict:
    return review_effort(db, description, title=title, kind=kind, fb=fb, it=it)
