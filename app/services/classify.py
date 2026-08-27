"""Art und Priorität aus Ticket-Kontext."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.routing import keyword_hits, match_priority
from app.domain.types import KIND_LABELS, PRIORITY_LABELS, Priority, RequestKind, parse_kind, parse_priority
from app.services.settings_service import get_runtime_config
from app.triage.providers import LlmUnavailable, build_provider_from_runtime

PROMPT_VERSION = "kind.v1.1.0"

KIND_SYSTEM = f"""[prompt:{PROMPT_VERSION}]
Du bestimmst die Art eines Tickets aus dem Gesamtkontext.

Nur JSON: {{"kind": "it_request"|"change_request"}}

it_request: IT muss fachlich mitmachen — Systeme einrichten/ändern, Software,
Schnittstellen, Zugänge, Berechtigungen, Hardware, Betrieb, Entwicklung,
CIT/SIT-Arbeit, technische Anbindung.

change_request: Organisation, Prozess, Kommunikation, Kultur, Abläufe —
ohne dass IT etwas technisch umsetzen, betreiben oder freischalten muss.

Entscheide nach Sinn des Vorhabens, nicht nach einzelnen Wörtern.
Beispiel: „Portal“ in einer reinen Prozess-/Kommunikationsbeschreibung
ohne IT-Umsetzung → change_request.
Nur wenn IT wirklich handeln muss → it_request.

Nur aus dem Text. Nichts erfinden.
"""

PRIORITY_SYSTEM = """Du stuft die Priorität eines Changes aus dem Tickettext ein.

Nur JSON: {"priority": "low"|"medium"|"high"|"critical"}

critical: Ausfall, Sicherheit, gesetzliche Frist, niemand kann arbeiten
high: dringend, Go-Live, Eskalation, enge Frist, hoher Betriebsdruck
medium: normale Verbesserung, Digitalisierung ohne Not
low: Kosmetik, nice to have, kein Termindruck

Schätze aus Inhalt und Wirkung. Nicht alles auf medium. Nichts erfinden.
"""

IT_CUES = (
    "sap",
    "schnittstelle",
    "systemanbindung",
    "api",
    "server",
    "software",
    "applikation",
    "lizenz",
    "login",
    "zugang",
    "berechtigung",
    "freischalten",
    "installieren",
    "entwickler",
    "datenbank",
    "netzwerk",
    "firewall",
    "vpn",
    "wlan",
    "active directory",
    "sharepoint",
    "hosting",
    "backup",
    "sso",
    "authentifizierung",
    "account",
    "cit",
    "sit",
    "laptop",
    "hardware",
    "browser",
    "client",
    "jira",
    "confluence",
    "azure",
    "rollout it",
)

DEFAULT_PRIORITY = Priority.MEDIUM


def match_it(text: str) -> bool:
    return keyword_hits(text, IT_CUES) > 0


def _fallback_kind(blob: str) -> RequestKind:
    if match_it(blob):
        return RequestKind.IT_REQUEST
    return RequestKind.CHANGE_REQUEST


def infer_kind(text: str, db: Session | None = None, use_llm: bool = False) -> RequestKind:
    blob = (text or "").strip()
    if not blob:
        return RequestKind.CHANGE_REQUEST

    if use_llm and db is not None:
        provider = build_provider_from_runtime(get_runtime_config(db))
        try:
            raw = provider.complete_json(KIND_SYSTEM, blob[:4000])
        except LlmUnavailable:
            return _fallback_kind(blob)
        guessed = parse_kind(str(raw.get("kind") or ""))
        if guessed in (RequestKind.IT_REQUEST, RequestKind.CHANGE_REQUEST):
            return guessed
        return _fallback_kind(blob)

    return _fallback_kind(blob)


def kind_payload(text: str, db: Session | None = None, use_llm: bool = False) -> dict:
    kind = infer_kind(text, db=db, use_llm=use_llm)
    return {"kind": kind.value, "label": KIND_LABELS[kind]}


def infer_priority(text: str, db: Session | None = None, use_llm: bool = False) -> Priority:
    blob = (text or "").strip()
    if not blob:
        return DEFAULT_PRIORITY
    hit = match_priority(blob)
    if hit:
        return hit
    if not use_llm or db is None:
        return DEFAULT_PRIORITY
    provider = build_provider_from_runtime(get_runtime_config(db))
    try:
        raw = provider.complete_json(PRIORITY_SYSTEM, blob[:4000])
    except LlmUnavailable:
        return DEFAULT_PRIORITY
    guessed = parse_priority(str(raw.get("priority") or ""))
    return guessed or DEFAULT_PRIORITY


def priority_payload(text: str, db: Session | None = None, use_llm: bool = False) -> dict:
    priority = infer_priority(text, db=db, use_llm=use_llm)
    return {"priority": priority.value, "label": PRIORITY_LABELS[priority]}
