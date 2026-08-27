"""Chat, der an genau ein Ticket gebunden ist.

Kein neues Anliegen, keine fremden Referenzen. Lesen und Aendern nur hier.
"""

from __future__ import annotations

import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat import answers, intents
from app.chat.intents import (
    Action,
    Clarify,
    DuplicateChoice,
    Help,
    Navigate,
    OpenRequest,
    Query,
    find_reference,
)
from app.domain.fieldspec import get_rules
from app.domain.risks import match_patterns as match_risks
from app.domain.types import (
    PRIORITY_LABELS,
    STATUS_LABELS,
    Priority,
    RequestKind,
    RequestStatus,
    parse_kind,
)
from app.knowledge import cases
from app.models import IntakeSession, Message, Request, User
from app.services import requests_service as svc
from app.services.similarity import find_similar
from app.services.websearch import search as web_search
from app.triage.providers import LlmUnavailable

PHASE_TICKET = "ticket"
YES = {"ja", "jap", "jo", "yes", "ok", "okay", "mach", "bestätigen", "bestaetigen"}
NO = {"nein", "nö", "noe", "stopp", "stop", "abbrechen", "doch nicht", "lass"}
CONFIRM_STATUSES = {RequestStatus.DONE, RequestStatus.REJECTED}
SKIP_LLM = {"heuristik", "scripted", "none", "dead", "test"}

REFUSE_OTHER = "Nur dieser Change zum Schreiben. Andere Tickets liegen im Workspace."
REFUSE_CREATE = "Hier lege ich nichts Neues an. Sag, was an diesem Change geändert werden soll."
CAPABILITIES = (
    "Ich recherchiere Wissen, ähnliche Changes und das Web. "
    "Schreiben nur in diesen Change. Nach der Recherche frage ich, ob ich übernehmen soll."
)

RESEARCH_CUES = (
    "recherch",
    "im web",
    "im netz",
    "im internet",
    "online",
    "google",
    "am markt",
    "marktüberblick",
    "marktueberblick",
    "best practice",
    "bestpractice",
    "benchmark",
    "anbieter",
    "wie machen andere",
    "schau nach",
    "finde raus",
    "was gibt es",
    "vergleiche",
)
INSIGHT_CUES = (
    "was siehst du",
    "was erkennst du",
    "was fällt dir",
    "was faellt dir",
)
STORED_FIELD_ASK = (
    "steht im",
    "steht in",
    "was steht",
    "zeig das feld",
    "was ist das",
    "was ist die",
    "was ist der",
    "was sind die",
)
SEARCH_WEB_RE = re.compile(
    r"^\s*(?:suche|such|finde|find)\s+(?:mir\s+)?(?:bitte\s+)?(?:nach\s+)?(.+)$",
    re.I,
)
LIST_NOUNS = ("ticket", "anliegen", "vorgang", "steckbrief", "changes", "änder")
SIMILAR_CUES = (
    "ähnliche lösung",
    "aehnliche loesung",
    "ähnliche fälle",
    "aehnliche faelle",
    "ähnliche changes",
    "ähnliche tickets",
)

APPLY_CUES = (
    "trag ",
    "trag das",
    "trage ",
    "übernimm",
    "uebernimm",
    "übernehme",
    "uebernehme",
    "übernehmen",
    "uebernehmen",
    "nimm das",
    "schreib",
    "eintragen",
    "ins feld",
    "in das feld",
    "in den steckbrief",
    "in status",
    "ins status",
    "statusfeld",
)
STATUS_WRITE_CUES = (
    "statusfeld",
    "status feld",
    "statusnotiz",
    "statusupdate",
    "status-update",
    "ablauf",
    "was gerade los",
)
STATUS_WRITE_KEYS = {"status_ablauf", "current_status"}
STATUS_INTERNAL_KEYS = STATUS_WRITE_KEYS | {"status_digest", "status_summary"}
STATUS_WRITE_RE = re.compile(r"\bstatus(feld)?\b", re.I)
OFFER_FOOTER = re.compile(r"\n+Übernehmen\b.*$", re.I | re.S)
OWNER_RE = re.compile(
    r"(?i)(?:soll\s+sich\s+([A-Za-zÄÖÜäöü]{3,})\s+k[uü]mmern|"
    r"([A-Za-zÄÖÜäöü]{3,})\s+soll\s+(?:das|die|den)\b|"
    r"verantwortung\s+(?:für.{0,40})?liegt\s+bei\s+([A-Za-zÄÖÜäöü]{3,}))"
)
OWNER_SKIP = {
    "das", "der", "die", "den", "dem", "sich", "uns", "man", "jetzt",
    "darum", "ok", "okay", "bitte", "dann",
}
QUESTION_RE = re.compile(r"\b(was|wie|welcher|welche|welches|zeig|zeige)\b", re.I)
TOPIC_FIELDS = (
    (("risik", "hindernis", "widerstand", "dsgvo", "datenschutz"), "risks_obstacles"),
    (("ähnlich", "aehnlich", "vergleich"), "similar_solution"),
    (("problem", "ist-zustand", "istzustand"), "problem"),
    (("lösung", "loesung", "soll-zustand", "ziel"), "solution_goals"),
)
FIELD_ASK = (
    (("problem", "reason", "ist-zustand"), "problem"),
    (("lösung", "loesung", "soll-zustand", "ziel"), "solution_goals"),
    (("risiko", "risik", "hindernis", "widerstand"), "risks_obstacles"),
    (("ähnlich", "aehnlich"), "similar_solution"),
    (("auftraggebende", "auftraggeber", "sponsor"), "sponsor"),
    (("autor", "bearbeitende", "bearbeiter", "assignee"), "author"),
    (("genehmigende", "genehmiger"), "approver"),
    (("gesellschaft",), "company"),
    (("zeitraum", "start", "ende"), "start_date"),
    (("beschreibung",), "description"),
    (("einspar", "umsatz", "ergänz", "ergaenz"), "benefit_savings"),
    (("risikoreduktion",), "benefit_risk"),
    (("komponente",), "components"),
    (("change-leitung", "change leitung", "gesamtprojektleitung", "gesamtprojektleiter"), "change_lead"),
    (("fb-verantwortung", "verantwortlicher fb", "fachbereich"), "fb_owner"),
    (("process owner", "betriebsübernahme", "betriebsuebernahme"), "process_owner"),
    (("solution owner",), "solution_owner"),
    (("stakeholder",), "stakeholder"),
    (("t-shirt", "tshirt", "effort project"), "effort_tshirt"),
    (("kostenträger", "kostentraeger"), "cost_unit"),
    (("kostenstelle",), "cost_center"),
    (("arbeitspaket", "aufwandscontainer"), "effort_container"),
    (("zusatzkontierung", "account"), "extra_account"),
    (("personentage", " konzeption pt"), "concept_scs_pt"),
)
LABEL_SKIP = {
    "gerade", "los", "bereits", "eine", "einen", "oder", "und", "zum", "zur",
    "vom", "gibt", "ist", "das", "der", "die", "ein",
}

SYSTEM = (
    "Du berätst diesen Change. Recherchieren ist erlaubt: Wissen, ähnliche Changes, Web. "
    "Schreiben nur in DIESES Ticket, und nur wenn der Nutzer übernimmt. "
    "Im Recherche-Turn keine fields, status, priority, comment setzen. "
    "Deutsch, kurz, keine Floskel. "
    "Wissen nur als id — Titel, Lösungstext nicht abschreiben. "
    "Web: Titel, ein Satz aus dem Treffer, URL. Keine erfundenen Zahlen, keine erfundenen Quellen. "
    "Wenn nichts da ist, sag das klar. Nicht den Nutzer um Ticket-Details bitten, die schon im Steckbrief stehen. "
    "Status, Statusfeld, Ablauf: Ablauftext, nicht der Workflow (Steckbrief/QG1). "
    "Kein Platzhalter, kein test, nichts erfinden. "
    'JSON: {"reply": "...", "fields": {}, "status": null, "priority": null, "comment": null}'
)


class TicketChatService:
    def __init__(self, db: Session, provider=None):
        self.db = db
        self.provider = provider

    def ensure_session(self, request: Request, user: User | None) -> IntakeSession:
        session = self.db.scalar(
            select(IntakeSession)
            .where(
                IntakeSession.request_id == request.id,
                IntakeSession.phase == PHASE_TICKET,
            )
            .order_by(IntakeSession.updated_at.desc())
        )
        if session:
            return session
        session = IntakeSession(
            user_id=user.id if user else None,
            request_id=request.id,
            phase=PHASE_TICKET,
            draft={},
            context={"mode": PHASE_TICKET, "last_request_id": request.id},
        )
        self.db.add(session)
        self.db.flush()
        return session

    def history(self, session: IntakeSession) -> list[dict]:
        return [
            {"role": m.role, "content": m.content}
            for m in session.messages
            if m.content
        ]

    def handle(
        self,
        session: IntakeSession,
        request: Request,
        text: str,
        actor: User | None = None,
    ) -> dict:
        raw = str(text or "").strip()
        if not raw:
            return self._payload(session, request, "Sag, was an diesem Change geändert werden soll.")
        context = dict(session.context or {})
        context["mode"] = PHASE_TICKET
        context["last_request_id"] = request.id
        session.context = context
        self._log(session, "user", raw)

        pending = context.get("pending")
        if pending:
            resolved = self._resolve_pending(session, request, raw, pending, actor)
            if resolved:
                return resolved

        if self._foreign_ref(raw, request):
            return self._payload(session, request, REFUSE_OTHER)

        applied = self._apply_last(session, request, raw)
        if applied:
            return applied

        if self._wants_research(raw):
            return self._research(session, request, raw, actor)

        intent = intents.detect(raw, context)
        payload = self._route(session, request, intent, raw, actor)
        if payload is None:
            payload = self._field_answer(session, request, raw)
        if payload is None:
            payload = self._llm_turn(session, request, raw, actor)
        if payload is None:
            payload = self._payload(session, request, REFUSE_CREATE)
        return payload

    def _route(
        self,
        session: IntakeSession,
        request: Request,
        intent: object,
        text: str,
        actor: User | None,
    ) -> dict | None:
        if isinstance(intent, Help):
            return self._payload(session, request, CAPABILITIES)
        if isinstance(intent, (Navigate, DuplicateChoice)):
            return self._payload(session, request, REFUSE_OTHER)
        if isinstance(intent, OpenRequest):
            if intent.reference.upper() != request.reference.upper():
                return self._payload(session, request, REFUSE_OTHER)
            return self._about(session, request)
        if isinstance(intent, Clarify):
            return self._about(session, request)
        if isinstance(intent, Query):
            return self._query(session, request, intent, text, actor)
        if isinstance(intent, Action):
            return self._action(session, request, intent, actor)
        return None

    def _query(
        self,
        session: IntakeSession,
        request: Request,
        query: Query,
        text: str,
        actor: User | None,
    ) -> dict:
        if query.reference and query.reference.upper() != request.reference.upper():
            return self._payload(session, request, REFUSE_OTHER)
        if query.text and not query.counting:
            return self._research(session, request, text, actor)
        if query.reference or not (
            query.counting or query.statuses or query.kind or query.text or query.more
        ):
            return self._about(session, request)
        return self._payload(session, request, REFUSE_OTHER)

    def _action(
        self,
        session: IntakeSession,
        request: Request,
        action: Action,
        actor: User | None,
    ) -> dict:
        if action.reference and action.reference.upper() != request.reference.upper():
            return self._payload(session, request, REFUSE_OTHER)
        if action.comment:
            svc.add_comment(self.db, request, action.comment, actor)
            fresh = svc.get_request(self.db, request.id)
            return self._payload(session, fresh, "Kommentar geschrieben.", changed=True)
        if action.status_note:
            svc.create_status_update(
                self.db,
                request,
                {
                    "summary": action.status_note,
                    "reportedOn": date.today().isoformat(),
                    "overallRag": action.overall_rag or "green",
                },
            )
            fresh = svc.get_request(self.db, request.id)
            return self._payload(session, fresh, "Statusnotiz gespeichert.", changed=True)
        if action.status and action.status in CONFIRM_STATUSES:
            context = dict(session.context or {})
            context["pending"] = {"requestId": request.id, "status": action.status.value}
            session.context = context
            self.db.flush()
            return self._payload(
                session,
                request,
                f"Soll ich auf {STATUS_LABELS[action.status]} setzen? Ja oder nein.",
            )
        if action.status:
            svc.update_request(self.db, request, {"status": action.status.value})
            fresh = svc.get_request(self.db, request.id)
            return self._payload(
                session,
                fresh,
                f"Status ist jetzt {STATUS_LABELS[action.status]}.",
                changed=True,
            )
        if action.priority:
            svc.update_request(self.db, request, {"priority": action.priority.value})
            fresh = svc.get_request(self.db, request.id)
            return self._payload(
                session,
                fresh,
                f"Priorität ist jetzt {PRIORITY_LABELS[action.priority]}.",
                changed=True,
            )
        return self._payload(session, request, "Das habe ich nicht verstanden.")

    def _resolve_pending(
        self,
        session: IntakeSession,
        request: Request,
        text: str,
        pending: dict,
        actor: User | None,
    ) -> dict | None:
        if pending.get("requestId") != request.id:
            context = dict(session.context or {})
            context.pop("pending", None)
            session.context = context
            return None
        answer = text.strip().lower().rstrip("!.")
        context = dict(session.context or {})
        if answer in YES:
            context.pop("pending", None)
            session.context = context
            svc.update_request(self.db, request, {"status": pending["status"]})
            fresh = svc.get_request(self.db, request.id)
            label = STATUS_LABELS[RequestStatus(pending["status"])]
            return self._payload(session, fresh, f"Status ist jetzt {label}.", changed=True)
        if answer in NO:
            context.pop("pending", None)
            session.context = context
            return self._payload(session, request, "Bleibt wie es ist.")
        context.pop("pending", None)
        session.context = context
        return None

    def _wants_apply(self, text: str) -> bool:
        low = f" {text.lower()} "
        return any(cue in low or cue in text.lower() for cue in APPLY_CUES)

    def _norm_label(self, text: str) -> str:
        return " ".join(
            text.lower().replace("&", "und").replace("-", " ").replace("/", " ").split()
        )

    def _spec_fields(self, request: Request):
        kind = parse_kind(request.kind) or RequestKind.CHANGE_REQUEST
        return get_rules().spec(kind).fields

    def _rejects_status(self, text: str) -> bool:
        low = self._norm_label(text)
        return bool(
            re.search(r"nicht\s+(in\s+(den\s+|das\s+|dem\s+|ins\s+)?)?status", low)
            or "sondern" in low
        )

    def _wants_status_write(self, text: str) -> bool:
        if self._rejects_status(text):
            return False
        low = self._norm_label(text)
        if any(cue in low for cue in STATUS_WRITE_CUES):
            return True
        return bool(STATUS_WRITE_RE.search(low)) and not QUESTION_RE.search(low)

    def _match_labeled_field(self, request: Request, text: str) -> str | None:
        low = self._norm_label(text)
        ranked: list[tuple[int, str]] = []
        seen: set[str] = set()
        for field in (*request.fields, *self._spec_fields(request)):
            key = getattr(field, "key", None)
            label = self._norm_label(getattr(field, "label", "") or "")
            if not key or not label or key in seen or key in STATUS_INTERNAL_KEYS:
                continue
            seen.add(key)
            if label in low:
                ranked.append((len(label), key))
                continue
            words = [w for w in label.split() if len(w) > 4 and w not in LABEL_SKIP]
            hit = next((w for w in words if w in low or any(part.startswith(w[:5]) for part in low.split() if len(part) >= 5)), None)
            if hit:
                ranked.append((len(hit), key))
        if ranked:
            ranked.sort(reverse=True)
            return ranked[0][1]
        for needles, key in FIELD_ASK + TOPIC_FIELDS:
            if any(needle in low for needle in needles):
                return key
        return None

    def _field_key_from_text(self, request: Request, text: str) -> str | None:
        if self._wants_status_write(text):
            return "status_ablauf"
        return self._match_labeled_field(request, text)

    def _topic_field(self, text: str) -> str | None:
        low = text.lower()
        for needles, key in TOPIC_FIELDS:
            if any(needle in low for needle in needles):
                return key
        return None

    def _last_assistant(self, session: IntakeSession) -> str:
        for message in reversed(list(session.messages or [])):
            if message.role == "assistant" and (message.content or "").strip():
                return message.content.strip()
        return ""

    def _note(self, session: IntakeSession, *, offer: str | None = None, topic: str | None = None) -> None:
        context = dict(session.context or {})
        if offer is not None:
            incoming = self._clean_offer(offer)
            existing = str(context.get("last_offer") or "")
            if self._offer_weight(incoming) >= self._offer_weight(existing):
                context["last_offer"] = incoming
        if topic:
            context["last_topic_field"] = topic
        session.context = context
        self.db.flush()

    def _apply_last(self, session: IntakeSession, request: Request, text: str) -> dict | None:
        pending_apply = bool((session.context or {}).get("pending_apply"))
        wants = self._wants_apply(text)
        answer = text.strip().lower().rstrip("!.")
        if pending_apply and not wants:
            if answer in YES:
                wants = True
            elif answer in NO:
                context = dict(session.context or {})
                context.pop("pending_apply", None)
                session.context = context
                return self._payload(session, request, "Nicht übernommen.")
            else:
                context = dict(session.context or {})
                context.pop("pending_apply", None)
                session.context = context
                return None
        if not wants:
            return None
        key = self._field_key_from_text(request, text)
        if not key and not self._field_hint(text):
            key = (session.context or {}).get("last_topic_field")
        if not key:
            context = dict(session.context or {})
            context["pending_apply"] = True
            session.context = context
            return self._payload(
                session,
                request,
                "Wohin? Sag das Feld, zum Beispiel Status oder Risiken & Hindernisse.",
            )
        context = dict(session.context or {})
        context.pop("pending_apply", None)
        session.context = context
        value = self._best_offer(session)
        if not value or value in {REFUSE_OTHER, REFUSE_CREATE, CAPABILITIES}:
            return self._payload(session, request, "Nichts zum Eintragen. Erst einen Text nennen.")
        if value.lower() in {"test", "tests", "placeholder", "lorem"}:
            value = self._clean_offer(str((session.context or {}).get("last_offer") or ""))
        if not value:
            return self._payload(session, request, "Nichts zum Eintragen. Erst einen Text nennen.")
        if key in STATUS_WRITE_KEYS:
            owner = self._named_owner(session, text)
            summary = value
            next_steps = value
            if owner:
                pretty = owner[:1].upper() + owner[1:]
                summary = f"{pretty} kümmert sich um die nächsten Schritte."
            svc.create_status_update(
                self.db,
                request,
                {
                    "summary": summary,
                    "reportedOn": date.today().isoformat(),
                    "overallRag": "green",
                    "nextSteps": next_steps,
                },
            )
            fresh = svc.get_request(self.db, request.id)
            return self._payload(session, fresh, "Ins Statusfeld übernommen.", changed=True)
        svc.update_request(self.db, request, {key: value})
        fresh = svc.get_request(self.db, request.id)
        label = next((f.label for f in (fresh.fields if fresh else []) if f.key == key), key)
        return self._payload(session, fresh, f"{label} übernommen.", changed=True)

    def _clean_offer(self, value: str) -> str:
        return OFFER_FOOTER.sub("", str(value or "")).strip()

    def _offer_weight(self, text: str) -> int:
        raw = self._clean_offer(text)
        if not raw or raw in {REFUSE_OTHER, REFUSE_CREATE, CAPABILITIES}:
            return 0
        low = raw.lower()
        if low in {"test", "tests", "placeholder", "lorem"}:
            return 0
        if low.startswith("wohin?") or low.startswith("nichts zum eintragen"):
            return 0
        if low.endswith("übernommen.") or low in {"nicht übernommen.", "nicht übernommen"}:
            return 0
        score = min(len(raw), 400)
        if re.search(r"(?m)^\s*\d+[.)]", raw):
            score += 400
        if raw.count("\n") >= 2:
            score += 60
        return score

    def _best_offer(self, session: IntakeSession) -> str:
        seen: list[str] = [str((session.context or {}).get("last_offer") or "")]
        for message in reversed(list(session.messages or [])):
            if message.role == "assistant" and (message.content or "").strip():
                seen.append(message.content)
            if len(seen) >= 8:
                break
        ranked = [(self._offer_weight(item), self._clean_offer(item)) for item in seen]
        ranked.sort()
        return ranked[-1][1] if ranked and ranked[-1][0] > 0 else ""

    def _named_owner(self, session: IntakeSession, text: str) -> str:
        parts = [text]
        for message in reversed(list(session.messages or [])):
            if message.role == "user" and (message.content or "").strip():
                parts.append(message.content)
            if len(parts) >= 5:
                break
        match = OWNER_RE.search(" ".join(parts))
        if not match:
            return ""
        name = next((part for part in match.groups() if part), "")
        if not name or name.lower() in OWNER_SKIP:
            return ""
        return name

    def _field_hint(self, text: str) -> bool:
        low = self._norm_label(text)
        return "feld" in low or "steckbrief" in low or self._wants_status_write(text)

    def _asks_stored_field(self, text: str) -> bool:
        low = text.lower()
        return any(mark in low for mark in STORED_FIELD_ASK)

    def _search_is_research(self, text: str) -> bool:
        match = SEARCH_WEB_RE.match(text.strip())
        if not match:
            return False
        rem = match.group(1).lower()
        return not any(noun in rem for noun in LIST_NOUNS)

    def _offer_field(self, text: str) -> str | None:
        low = text.lower()
        for needles, key in FIELD_ASK + TOPIC_FIELDS:
            if any(needle in low for needle in needles):
                return key
        return self._topic_field(text)

    def _apply_question(self, request: Request, key: str | None) -> str:
        if key:
            label = next((f.label for f in (*request.fields, *self._spec_fields(request)) if f.key == key), key)
            return f"Übernehmen ins Feld {label}?"
        return "Übernehmen? Sag das Feld, zum Beispiel Risiken oder Einsparungen."

    def _wants_research(self, text: str) -> bool:
        low = text.lower()
        if any(cue in low for cue in RESEARCH_CUES):
            return True
        if any(cue in low for cue in INSIGHT_CUES):
            return True
        if any(cue in low for cue in SIMILAR_CUES) and not self._asks_stored_field(low):
            return True
        if self._search_is_research(text):
            return True
        if self._asks_stored_field(low):
            return False
        return bool(QUESTION_RE.search(low) and self._offer_field(text))

    def _research_query(self, request: Request, text: str) -> str:
        cleaned = text.lower()
        for cue in RESEARCH_CUES + SIMILAR_CUES + INSIGHT_CUES:
            cleaned = cleaned.replace(cue, " ")
        leftover = " ".join(cleaned.split())
        values = request.field_values()
        parts = [
            request.title,
            values.get("problem"),
            leftover if len(leftover) >= 4 else "",
        ]
        return " ".join(part for part in parts if part)[:160]

    def _gather(self, request: Request, query: str) -> list[str]:
        lines: list[str] = []
        seen: set[str] = set()
        values = request.field_values()
        blob = " ".join(
            part
            for part in (
                request.title,
                request.description,
                values.get("problem"),
                values.get("solution_goals"),
                query,
            )
            if part
        )
        for hit in match_risks(blob)[:2]:
            line = f"{hit.pattern.display} — {hit.pattern.risk[:180]}"
            if line not in seen:
                seen.add(line)
                lines.append(f"Muster: {line}")
        for hit in cases.search(query, limit=2):
            line = f"{hit.case.id} — {hit.case.title}"
            if line not in seen:
                seen.add(line)
                lines.append(f"Wissen: {line}")
        for item in find_similar(self.db, query, limit=2, exclude_id=request.id):
            line = f"{item.reference} — {item.title}"
            if line not in seen:
                seen.add(line)
                lines.append(f"Ähnlich: {line}")
        for hit in web_search(query, limit=3):
            title = str(hit.get("title") or "").strip()
            url = str(hit.get("url") or "").strip()
            snippet = str(hit.get("snippet") or "").strip()
            if not title:
                continue
            if title in seen:
                continue
            seen.add(title)
            extra = f" — {snippet[:160]}" if snippet else ""
            lines.append(f"Web: {title}{extra}" + (f" · {url}" if url else ""))
        return lines[:8]

    def _brief(self, request: Request) -> str:
        values = request.field_values()
        bits = [
            f"Titel: {request.title}",
            f"Status: {request.status}",
            f"Priorität: {request.priority}",
        ]
        for key in (
            "problem",
            "solution_goals",
            "risks_obstacles",
            "benefit_savings",
            "benefit_risk",
            "description",
        ):
            value = values.get(key) or (request.description if key == "description" else "")
            if value:
                bits.append(f"{key}: {value[:400]}")
        return "\n".join(bits)

    def _research(
        self,
        session: IntakeSession,
        request: Request,
        text: str,
        actor: User | None,
    ) -> dict:
        query = self._research_query(request, text)
        lines = self._gather(request, query)
        digest = "\n".join(lines)
        reply = digest
        name = str(getattr(self.provider, "name", "") or "").lower()
        if self.provider and name not in SKIP_LLM and not name.startswith("scripted"):
            try:
                raw = self.provider.complete_json(
                    SYSTEM,
                    (
                        f"{self._brief(request)}\n"
                        f"Recherche:\n{digest or 'keine Treffer'}\n"
                        f"Nutzer: {text}"
                    ),
                )
            except (LlmUnavailable, TypeError, ValueError):
                raw = None
            if isinstance(raw, dict):
                composed = str(raw.get("reply") or "").strip()
                if composed:
                    reply = composed
        if not reply:
            return self._payload(
                session,
                request,
                "Nichts Passendes gefunden. Anderen Suchbegriff versuchen.",
            )
        topic = self._offer_field(text)
        self._note(session, offer=reply, topic=topic)
        if not lines:
            return self._payload(session, request, reply)
        context = dict(session.context or {})
        context["pending_apply"] = True
        if topic:
            context["last_topic_field"] = topic
        session.context = context
        shown = f"{reply}\n\n{self._apply_question(request, topic)}"
        return self._payload(session, request, shown)

    def _field_answer(self, session: IntakeSession, request: Request, text: str) -> dict | None:
        low = text.lower()
        if not QUESTION_RE.search(low):
            return None
        values = request.field_values()
        hits: list[str] = []
        for needles, key in FIELD_ASK:
            if any(word in low for word in needles):
                label = next((f.label for f in request.fields if f.key == key), key)
                value = values.get(key) or (request.description if key == "description" else "")
                hits.append(f"{label}: {value}" if value else f"{label} ist leer.")
        if "priorität" in low or "prio" in low:
            prio = Priority(request.priority)
            hits.append(f"Priorität: {PRIORITY_LABELS[prio]}")
        if "status" in low and "feld" not in low:
            status = RequestStatus(request.status)
            hits.append(f"Status: {STATUS_LABELS[status]}")
        if not hits:
            return None
        return self._payload(session, request, " ".join(hits))

    def _llm_turn(
        self,
        session: IntakeSession,
        request: Request,
        text: str,
        actor: User | None,
    ) -> dict | None:
        name = str(getattr(self.provider, "name", "") or "").lower()
        if not self.provider or name in SKIP_LLM or name.startswith("scripted"):
            if intents.looks_like_issue(text):
                return self._payload(session, request, REFUSE_CREATE)
            return self._about(session, request)
        try:
            raw = self.provider.complete_json(
                SYSTEM,
                (
                    f"{self._brief(request)}\n"
                    f"Verlauf:\n{self._history_block(session)}\n"
                    f"Nutzer: {text}"
                ),
            )
        except (LlmUnavailable, TypeError, ValueError):
            return None
        if not isinstance(raw, dict):
            return None
        return self._apply_llm(session, request, raw, actor)

    def _history_block(self, session: IntakeSession) -> str:
        rows = [m for m in session.messages if (m.content or "").strip()][-8:]
        if not rows:
            return "—"
        return "\n".join(f"{m.role}: {m.content}" for m in rows)

    def _apply_llm(
        self,
        session: IntakeSession,
        request: Request,
        raw: dict,
        actor: User | None,
    ) -> dict:
        reply = str(raw.get("reply") or "").strip()
        changed = False
        fields = raw.get("fields") if isinstance(raw.get("fields"), dict) else {}
        patch: dict[str, str] = {}
        spec = get_rules().spec(parse_kind(request.kind) or RequestKind.CHANGE_REQUEST)
        allowed = set(spec.field_map()) | {"title", "description", "company", "change_lead"}
        offer = str((session.context or {}).get("last_offer") or "").strip()
        junk = {"test", "tests", "todo", "placeholder", "lorem", "n/a", "-"}
        for key, value in fields.items():
            if key not in allowed:
                continue
            text = str(value or "").strip()
            if not text:
                continue
            if text.lower() in junk and offer:
                text = offer
            patch[str(key)] = text
        if patch:
            svc.update_request(self.db, request, patch)
            changed = True
        status = str(raw.get("status") or "").strip().lower()
        priority = str(raw.get("priority") or "").strip().lower()
        extra: dict[str, str] = {}
        if status in {s.value for s in RequestStatus}:
            extra["status"] = status
        if priority in {p.value for p in Priority}:
            extra["priority"] = priority
        if extra:
            svc.update_request(self.db, request, extra)
            changed = True
        comment = str(raw.get("comment") or "").strip()
        if comment and comment.lower() not in junk:
            svc.add_comment(self.db, request, comment, actor)
            changed = True
        fresh = svc.get_request(self.db, request.id) if changed else request
        if not reply:
            reply = "Übernommen." if changed else CAPABILITIES
        if reply and reply not in {REFUSE_OTHER, REFUSE_CREATE, CAPABILITIES}:
            self._note(session, offer=reply)
        return self._payload(session, fresh, reply, changed=changed)

    def _about(self, session: IntakeSession, request: Request) -> dict:
        answer = answers.detail_answer(svc.to_detail(request))
        text = answer.text.replace("Du kannst den Status setzen oder einen Kommentar hinterlassen.", CAPABILITIES)
        return self._payload(session, request, text)

    def _foreign_ref(self, text: str, request: Request) -> bool:
        found = find_reference(text)
        return bool(found and found.upper() != request.reference.upper())

    def _payload(
        self,
        session: IntakeSession,
        request: Request | None,
        text: str,
        *,
        changed: bool = False,
    ) -> dict:
        self._log(session, "assistant", text)
        body = {"type": "answer", "text": text, "changed": changed}
        if changed and request:
            body["detail"] = svc.to_detail(request)
        return body

    def _log(self, session: IntakeSession, role: str, text: str) -> None:
        self.db.add(Message(session_id=session.id, role=role, content=text))
        self.db.flush()
