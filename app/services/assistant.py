"""Klammer um den Chat: erst Absicht, dann Intake.

Der Intake-Pfad in `IntakeService` bleibt unangetastet. Hier faellt nur die
Entscheidung, ob ein Satz ein neues Anliegen ist oder eine Frage, ein Befehl
oder ein Sprung auf eine andere Seite.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat import answers, intents
from app.chat.answers import Answer
from app.chat.intents import (
    Action,
    Clarify,
    DuplicateChoice,
    Help,
    Navigate,
    OpenRequest,
    Query,
)
from app.domain.types import PRIORITY_LABELS, STATUS_LABELS, RequestStatus
from app.models import IntakeSession, Message, Request, User
from app.services import requests_service as svc
from app.services.intake import PHASE_COLLECT, PHASE_DONE, PHASE_UNCLEAR, IntakeService
from app.services.similarity import find_similar

log = logging.getLogger("triage.assistant")

LIST_LIMIT = 10
CONFIRM_STATUSES = {RequestStatus.DONE, RequestStatus.REJECTED}
YES = {"ja", "jap", "jo", "yes", "ok", "okay", "mach", "bestätigen", "bestaetigen"}
NO = {"nein", "nö", "noe", "stopp", "stop", "abbrechen", "doch nicht", "lass"}


@dataclass
class AssistantService:
    db: Session
    intake: IntakeService

    # --- Einstieg ---

    def handle(
        self,
        session: IntakeSession,
        text: str,
        client: dict | None = None,
        actor: User | None = None,
    ) -> dict:
        context = dict(session.context or {})
        if client:
            context["client"] = client
        session.context = context

        pending = context.get("pending")
        if pending:
            resolved = self._resolve_pending(session, text, pending)
            if resolved:
                return resolved

        intent = intents.detect(text, context)
        if intent is not None:
            self._log_turn(session, text)
            payload = self._route(session, intent, text, actor)
            self._log_answer(session, payload)
            return payload

        # Mitten in der Erfassung: Antworten auf Rueckfragen sind selten "Anliegen"-Saetze.
        if self._intake_in_progress(session):
            return self._intake(session, text, actor)

        found = self._maybe_open_existing(session, text)
        if found:
            self._log_turn(session, text)
            self._log_answer(session, found)
            return found

        # Ohne erkannte Absicht ist die Erfassung der Default. Nur Rauschen
        # (leerer Text, einzelnes Fragewort) bekommt die Faehigkeiten-Antwort.
        if not intents.looks_like_issue(text):
            self._log_turn(session, text)
            payload = self._answer(answers.capabilities_answer())
            self._log_answer(session, payload)
            return payload

        return self._intake(session, text, actor)

    def _intake_in_progress(self, session: IntakeSession) -> bool:
        if session.phase not in (PHASE_COLLECT, PHASE_UNCLEAR):
            return False
        draft = session.draft or {}
        return bool(session.questions_asked or draft.get("title") or draft.get("kind"))

    # --- Routing ---

    def _route(
        self,
        session: IntakeSession,
        intent: object,
        text: str,
        actor: User | None,
    ) -> dict:
        if isinstance(intent, Help):
            return self._answer(answers.capabilities_answer())
        if isinstance(intent, Clarify):
            if intent.reason == "target":
                return self._answer(answers.clarify_target_answer())
            return self._answer(answers.clarify_filter_answer())
        if isinstance(intent, DuplicateChoice):
            return self._duplicate_choice(session, intent)
        if isinstance(intent, Navigate):
            return {
                "type": "navigate",
                "url": intent.url,
                "label": intent.label,
                "text": f"Öffne {intent.label}.",
            }
        if isinstance(intent, OpenRequest):
            request = self._by_reference(intent.reference)
            if not request:
                return self._answer(answers.unknown_reference_answer(intent.reference))
            return self._navigate_to(session, request)
        if isinstance(intent, Query):
            return self._dispatch_query(session, intent)
        if isinstance(intent, Action):
            return self._action(session, intent, actor)
        return self._answer(answers.capabilities_answer())

    def _duplicate_choice(self, session: IntakeSession, choice: DuplicateChoice) -> dict:
        context = dict(session.context or {})
        dups = context.get("duplicate_ids") or []
        context["awaiting_duplicate"] = False
        session.context = context
        if choice.create:
            # Confirm laeuft weiter ueber den Anlegen-Button / API — hier nur freigeben.
            return self._answer(
                Answer(text="Gut. Leg mit Anlegen an — die Ähnlichen bleiben als Hinweis.")
            )
        if not dups:
            return self._answer(Answer(text="Kein ähnliches Anliegen zum Öffnen."))
        request = svc.get_request(self.db, dups[0])
        if not request:
            return self._answer(Answer(text="Das ähnliche Anliegen gibt es nicht mehr."))
        self._remember(session, request.id)
        return {
            "type": "navigate",
            "url": f"/workspace/{request.id}",
            "label": request.reference,
            "text": f"Öffne {request.reference}.",
        }

    # --- Lesen ---

    def _navigate_to(self, session: IntakeSession, request: Request) -> dict:
        self._remember(session, request.id)
        return {
            "type": "navigate",
            "url": f"/workspace/{request.id}",
            "label": request.reference,
            "text": f"Öffne {request.reference}.",
        }

    def _maybe_open_existing(self, session: IntakeSession, text: str) -> dict | None:
        if intents.looks_like_create(text):
            return None
        result = svc.list_requests(
            self.db,
            svc.RequestFilter(query=text.strip(), sort="attention", limit=5),
        )
        items = result.get("items") or []
        total = int(result.get("total") or 0)
        if total == 1 and items:
            request = svc.get_request(self.db, items[0]["id"])
            return self._navigate_to(session, request) if request else None
        if total > 1:
            similar = find_similar(self.db, text, limit=3, min_score=0.45)
            if similar and (
                len(similar) == 1
                or similar[0].score >= similar[1].score + 0.12
            ):
                request = svc.get_request(self.db, similar[0].id)
                if request:
                    return self._navigate_to(session, request)
            return self._answer(answers.list_answer(result, f"Treffer zu „{text.strip()}“"))
        similar = find_similar(self.db, text, limit=3, min_score=0.4)
        if not similar:
            return None
        if len(similar) == 1 or similar[0].score >= similar[1].score + 0.12:
            request = svc.get_request(self.db, similar[0].id)
            return self._navigate_to(session, request) if request else None
        fake = {
            "total": len(similar),
            "items": [
                {
                    "id": hit.id,
                    "reference": hit.reference,
                    "title": hit.title,
                }
                for hit in similar
            ],
        }
        return self._answer(answers.list_answer(fake, f"Treffer zu „{text.strip()}“"))

    def _dispatch_query(self, session: IntakeSession, query: Query) -> dict:
        if query.reference:
            request = self._by_reference(query.reference)
            if not request:
                return self._answer(answers.unknown_reference_answer(query.reference))
            return self._navigate_to(session, request)

        if query.counting and not (
            query.kind
            or query.statuses
            or query.priority
            or query.company
            or query.responsible
            or query.text
        ):
            return self._answer(answers.stats_answer(svc.status_counts(self.db)))

        context = dict(session.context or {})
        offset = int(context.get("last_offset") or 0)
        offset = offset + LIST_LIMIT if query.more else 0

        result = svc.list_requests(
            self.db,
            svc.RequestFilter(
                kind=query.kind,
                statuses=query.statuses,
                priority=query.priority,
                company=query.company,
                change_lead=query.responsible,
                query=query.text,
                sort="priority",
                direction="asc",
                limit=LIST_LIMIT,
                offset=offset,
            ),
        )
        self._store_filter(session, query, result, offset)
        if query.counting:
            return self._answer(answers.count_answer(result, query.label))
        items = result.get("items") or []
        total = int(result.get("total") or 0)
        if query.text and total == 1 and items:
            request = svc.get_request(self.db, items[0]["id"])
            if request:
                return self._navigate_to(session, request)
        return self._answer(answers.list_answer(result, query.label))

    def _store_filter(
        self, session: IntakeSession, query: Query, result: dict, offset: int
    ) -> None:
        items = result.get("items") or []
        context = dict(session.context or {})
        context["last_filter"] = {
            "kind": query.kind.value if query.kind else None,
            "statuses": [s.value for s in query.statuses],
            "priority": query.priority.value if query.priority else None,
            "company": query.company,
            "responsible": query.responsible,
            "query": query.text,
            "label": query.label,
        }
        context["last_list_ids"] = [item["id"] for item in items]
        context["last_offset"] = offset
        if items:
            context["last_request_id"] = items[0]["id"]
        session.context = context

    # --- Schreiben ---

    def _action(self, session: IntakeSession, action: Action, actor: User | None) -> dict:
        request = None
        if action.reference:
            request = self._by_reference(action.reference)
            if not request:
                return self._answer(answers.unknown_reference_answer(action.reference))
        else:
            last = (session.context or {}).get("last_request_id")
            request = svc.get_request(self.db, last) if last else None
            if not request:
                return self._answer(answers.clarify_target_answer())

        self._remember(session, request.id)

        if action.comment:
            svc.add_comment(self.db, request, action.comment, actor)
            return {
                "type": "action",
                "text": f"Kommentar an {request.reference} geschrieben. Jira-Sync läuft.",
                "links": [{"label": request.reference, "url": f"/workspace/{request.id}"}],
            }

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
            return {
                "type": "action",
                "text": f"Status von {request.reference} gespeichert.",
                "links": [{"label": request.reference, "url": f"/workspace/{request.id}"}],
            }

        if action.status and action.status in CONFIRM_STATUSES:
            context = dict(session.context or {})
            context["pending"] = {"requestId": request.id, "status": action.status.value}
            session.context = context
            self.db.flush()
            return {
                "type": "confirm_action",
                "text": (
                    f"Soll ich {request.reference} auf "
                    f"{STATUS_LABELS[action.status]} setzen? Antworte mit ja."
                ),
            }

        if action.status:
            return self._apply_status(request, action.status)
        if action.priority:
            svc.update_request(self.db, request, {"priority": action.priority.value})
            return {
                "type": "action",
                "text": (
                    f"{request.reference} steht jetzt auf Priorität "
                    f"{PRIORITY_LABELS[action.priority]}."
                ),
                "links": [{"label": request.reference, "url": f"/workspace/{request.id}"}],
            }
        return self._answer(Answer(text="Das habe ich nicht verstanden."))

    def _apply_status(self, request: Request, status: RequestStatus) -> dict:
        svc.update_request(self.db, request, {"status": status.value})
        return {
            "type": "action",
            "text": (
                f"{request.reference} steht jetzt auf {STATUS_LABELS[status]}. "
                "Jira-Sync läuft."
            ),
            "links": [{"label": request.reference, "url": f"/workspace/{request.id}"}],
        }

    def _resolve_pending(self, session: IntakeSession, text: str, pending: dict) -> dict | None:
        answer = text.strip().lower().rstrip("!.")
        context = dict(session.context or {})
        if answer in YES:
            context.pop("pending", None)
            session.context = context
            request = svc.get_request(self.db, pending.get("requestId", ""))
            if not request:
                return self._answer(Answer(text="Das Anliegen gibt es nicht mehr."))
            return self._apply_status(request, RequestStatus(pending["status"]))
        if answer in NO:
            context.pop("pending", None)
            session.context = context
            return self._answer(Answer(text="Gut, ich lasse alles wie es ist."))
        context.pop("pending", None)
        session.context = context
        return None

    # --- Intake ---

    def _intake(self, session: IntakeSession, text: str, actor: User | None = None) -> dict:
        if session.phase == PHASE_DONE:
            self._reset(session)

        before = session.questions_asked
        payload = self.intake.handle_message(
            session, text, prefill=self._prefill(session, actor)
        )

        # Das LLM haelt den Satz fuer eine Frage. Umleiten nur, wenn die
        # deterministische Erkennung das bestaetigt — sonst bleibt es ein Anliegen.
        if self._should_reroute(payload):
            again = intents.detect(text, session.context or {})
            if isinstance(again, Query):
                session.draft = {}
                session.questions_asked = before
                session.phase = PHASE_COLLECT
                payload = self._dispatch_query(session, again)
                self._log_answer(session, payload)
                return payload

        if payload.get("type") == "summary":
            self._attach_duplicate_prompt(session, payload)
        return payload

    def _attach_duplicate_prompt(self, session: IntakeSession, payload: dict) -> None:
        duplicates = payload.get("duplicates") or []
        if not duplicates:
            return
        context = dict(session.context or {})
        context["awaiting_duplicate"] = True
        context["duplicate_ids"] = [d["id"] for d in duplicates if d.get("id")]
        session.context = context
        prompt = answers.duplicate_prompt_answer(duplicates)
        if prompt.text:
            payload["duplicatePrompt"] = prompt.text
            payload["duplicateLinks"] = prompt.links

    def _should_reroute(self, payload: dict) -> bool:
        if payload.get("intent") != "frage":
            return False
        draft = payload.get("draft") or {}
        return not draft.get("values") and int(payload.get("questionsAsked") or 0) <= 1

    def _reset(self, session: IntakeSession) -> None:
        session.draft = {}
        session.questions_asked = 0
        session.phase = PHASE_COLLECT
        session.request_id = None
        context = dict(session.context or {})
        for key in ("awaiting_duplicate", "duplicate_ids", "pending_field", "declined"):
            context.pop(key, None)
        session.context = context
        self.db.flush()

    def _prefill(self, session: IntakeSession, actor: User | None = None) -> dict[str, str]:
        name = str(getattr(actor, "display_name", "") or "").strip()
        return {"sponsor": name} if name else {}

    # --- Hilfen ---

    def _by_reference(self, reference: str) -> Request | None:
        needle = str(reference or "").strip().upper()
        if not needle:
            return None
        request_id = self.db.scalar(select(Request.id).where(Request.reference == needle))
        if not request_id:
            from app.models import ExternalRef

            request_id = self.db.scalar(
                select(ExternalRef.request_id).where(ExternalRef.external_key == needle)
            )
        return svc.get_request(self.db, request_id) if request_id else None

    def _remember(self, session: IntakeSession, request_id: str) -> None:
        context = dict(session.context or {})
        context["last_request_id"] = request_id
        session.context = context

    def _answer(self, answer: Answer) -> dict:
        payload = {"type": "answer", "text": answer.text, "links": answer.links}
        if answer.url:
            payload["url"] = answer.url
        return payload

    def _log_turn(self, session: IntakeSession, text: str) -> None:
        self.db.add(Message(session_id=session.id, role="user", content=text))
        self.db.flush()

    def _log_answer(self, session: IntakeSession, payload: dict) -> None:
        self.db.add(
            Message(
                session_id=session.id,
                role="assistant",
                content=str(payload.get("text") or payload.get("duplicatePrompt") or ""),
            )
        )
        self.db.flush()
