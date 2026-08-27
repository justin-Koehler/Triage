"""Dialog-Ablauf und Anlage. Schreibt nur in die eigene DB, Sync laeuft ueber die Outbox."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.calc import parse_number
from app.domain.dates import parse_german_date
from app.domain.fieldspec import AI_MANUAL_ONLY, AI_SUGGEST_ONLY
from app.domain.risks import match_patterns, warning_text
from app.domain.routing import match_responsible
from app.domain.types import (
    BADGE_INCOMPLETE,
    KIND_LABELS,
    PRIORITY_LABELS,
    OutboxOperation,
    Priority,
    RequestKind,
    RequestStatus,
    SyncState,
    TriageSource,
    kind_label,
    parse_kind,
    parse_priority,
)
from app.knowledge import cases
from app.models import (
    ExternalRef,
    IdempotencyKey,
    IntakeSession,
    Message,
    Request,
    RequestField,
    TriageRun,
    User,
)
from app.ports import get_ticket_port
from app.services import collab
from app.services.settings_service import get_runtime_config
from app.services.similarity import find_similar
from app.services.suggestions import values_for
from app.sync.outbox import enqueue, process_request
from app.triage.engine import (
    BUNDLE_MEMBERS,
    EFFORT_KEY,
    EMPATHY_KEY,
    KONTO_KEY,
    PEOPLE_KEY,
    PEOPLE_KEYS,
    ROLES_KEY,
    ROLES_KEYS,
    SOLUTION_KEY,
    VALUE_KEY,
    Diagnosis,
    Draft,
    TriageEngine,
    TriageResult,
    is_unknown_answer,
)

log = logging.getLogger("triage.intake")

PHASE_COLLECT = "collect"
PHASE_UNCLEAR = "unclear"
PHASE_SUMMARY = "summary"
PHASE_DONE = "done"

# Ohne diese Felder wird nichts angelegt. Gefragt wird nie danach, das System
# leitet sie ab (config/responsibles, Verlauf, Login). Prioritaet haengt am
# Anliegen selbst und wird getrennt geprueft.
MANDATORY_KEYS = ("description", "change_lead")
MAX_HINTS = 2

KIND_TO_LEGACY_INTENT = {
    RequestKind.CHANGE_REQUEST: "request_change",
    RequestKind.IT_REQUEST: "request_it",
}

UI_FIELDS = {
    "start": "start_date",
    "end": "end_date",
    "sponsor": "sponsor",
    "components": "components",
    "nonprofit": "nonprofit_dss",
    "description": "description",
    "benefit": "benefit_savings",
    "reason": "problem",
    "solution": "solution_goals",
    "risks": "risks_obstacles",
    "approver": "approver",
    "lead": "change_lead",
    "stakeholder": "stakeholder",
    "change_team": "change_team",
    "it_owner": "responsible_sit",
    "process_owner": "process_owner",
    "solution_owner": "solution_owner",
    "costs": "costs",
    "effort_fb": "concept_scs_pt",
    "effort_it": "concept_cit_pt",
    "effort_tshirt": "effort_tshirt",
    "effort_sheet_url": "effort_sheet_url",
}
DATE_KEYS = {"start_date", "end_date"}
PT_KEYS = {"concept_scs_pt", "concept_cit_pt", "operate_scs_pt", "operate_cit_pt"}
MONEY_KEYS = {"costs"}


def _jira_identity(user: User | None) -> str:
    if not user:
        return ""
    return str(user.external_subject or user.email or user.display_name or "").strip()


@lru_cache
def _field_map_meta() -> dict:
    try:
        return yaml.safe_load(
            get_settings().field_map_path.read_text(encoding="utf-8")
        ) or {}
    except Exception:
        return {}


def _dumped_similar(text: str) -> bool:
    """Abgeschnittener Loesungstext statt Verweis."""
    compact = " ".join(str(text or "").split())
    if not compact:
        return True
    if compact.endswith(("beim", "der", "die", "das", "und", "oder", "im", "in")):
        return True
    return ":" in compact and not compact.endswith((".", "!", "?"))


class SessionNotFound(LookupError):
    pass


class NotReadyForCreation(ValueError):
    pass


@dataclass
class IntakeService:
    db: Session
    engine: TriageEngine

    # --- Session ---

    def create_session(self, user: User | None = None) -> IntakeSession:
        session = IntakeSession(user_id=user.id if user else None, draft={})
        self.db.add(session)
        self.db.flush()
        return session

    def publish_ticket(
        self,
        *,
        title: str,
        kind: str,
        priority: str,
        fields: dict[str, str],
        user: User | None = None,
        wait_for_sync: bool = True,
    ) -> dict:
        """Feldmaske → Session in Summary → Confirm (Outbox nach Jira)."""
        session = self.create_session(user)
        draft = Draft()
        draft.title = (title or "").strip()[:200]
        guessed = parse_kind(kind)
        draft.kind = (
            guessed
            if guessed in (RequestKind.CHANGE_REQUEST, RequestKind.IT_REQUEST)
            else RequestKind.CHANGE_REQUEST
        )
        draft.kind_locked = True
        draft.priority = Priority.MEDIUM
        draft.priority_locked = True
        allowed = self.engine.rules.spec(draft.kind).field_map()
        for ui_key, raw in (fields or {}).items():
            if ui_key == "author":
                continue
            key = UI_FIELDS.get(ui_key, ui_key)
            if key == "author" or key not in allowed:
                continue
            text = str(raw or "").strip()
            if not text:
                continue
            if is_unknown_answer(text):
                continue
            if key in DATE_KEYS:
                text = parse_german_date(text) or text
            elif key in PT_KEYS or key in MONEY_KEYS:
                amount = parse_number(text)
                if amount:
                    text = str(int(amount) if amount == int(amount) else amount)
            spec = allowed[key]
            draft.values[key] = spec.normalize(text) if text else ""
        self.engine._apply_computed(draft)
        author = _jira_identity(user)
        if author:
            draft.values["author"] = author
        session.draft = draft.to_dict()
        session.phase = PHASE_SUMMARY
        self.db.flush()
        return self.confirm(session, user=user, wait_for_sync=wait_for_sync)

    def load_session(self, session_id: str) -> IntakeSession:
        session = self.db.get(IntakeSession, session_id)
        if not session:
            raise SessionNotFound(session_id)
        return session

    def transcript(self, session: IntakeSession) -> list[str]:
        return [m.content for m in session.messages if m.role == "user"]

    def report(self, session: IntakeSession) -> list[str]:
        """Nur was der Nutzer von sich aus gemeldet hat.

        Antworten auf Feldfragen stehen als eigene Felder im Steckbrief. Waeren
        sie zusaetzlich in der Beschreibung, stuende jede Angabe zweimal da.
        """
        return [m.content for m in session.messages if m.role == "user" and not m.field_key]

    def _form_fields(self, draft: Draft) -> list[dict]:
        if not draft.kind:
            return []
        spec = self.engine.rules.spec(draft.kind)
        fields: list[dict] = []
        for f in spec.fields:
            if not f.applies(draft.values):
                continue
            value = str(draft.values.get(f.key) or "")
            editable = f.fill in {"dialog", "draft", "workspace", "controlling"}
            aiFillable = editable and f.fill != "computed" and f.type in {
                "text",
                "longtext",
                "choice",
                "date",
                "number",
                "money",
                "person",
            }
            fields.append(
                {
                    "key": f.key,
                    "label": f.label,
                    "value": value,
                    "type": f.type,
                    "fill": f.fill,
                    "values": list(f.values),
                    "aiFillable": aiFillable,
                    "aiMode": f.ai_mode,
                    "requiredOnConfirm": bool(f.required_on_confirm),
                    "syncMode": f.sync_mode,
                }
            )
        return fields

    # --- Dialog ---

    def handle_message(
        self,
        session: IntakeSession,
        text: str,
        prefill: dict[str, str] | None = None,
    ) -> dict:
        if session.phase == PHASE_DONE:
            return self._done_payload(session)

        pending = (session.context or {}).get("pending_field")
        if pending:
            self._remember_pending(session, None)
            pending = None
        self.db.add(
            Message(session_id=session.id, role="user", content=text, field_key=pending)
        )
        self.db.flush()
        declined = self._declined(session, pending, text)

        draft = Draft.from_dict(session.draft)
        transcript = [*self.transcript(session)]
        actor_prefill = dict(prefill or {})
        result = self.engine.run(
            draft,
            transcript,
            session.questions_asked,
            prefill=actor_prefill or None,
            answer=(pending, text) if pending else None,
            report=[*self.report(session)],
            declined=declined,
        )
        self._record_run(session, result)

        session.draft = result.draft.to_dict()
        return self._summary_after_ready(session, result)

    def override(
        self,
        session: IntakeSession,
        kind: RequestKind | None = None,
        priority: Priority | None = None,
    ) -> dict:
        if session.phase not in (PHASE_SUMMARY, PHASE_COLLECT):
            raise NotReadyForCreation("Kein Entwurf zum Ändern")

        draft = Draft.from_dict(session.draft)
        previous_kind = draft.kind
        if kind and kind is not draft.kind:
            old_keys = (
                set(self.engine.rules.spec(previous_kind).field_map())
                if previous_kind
                else set()
            )
            draft.kind = kind
            draft.kind_locked = True
            spec = self.engine.rules.spec(kind)
            allowed = set(spec.field_map())
            # Art-Felder der alten Art weg; Diagnostik und neue Art behalten.
            draft.values = {
                k: v
                for k, v in draft.values.items()
                if k in allowed or k not in old_keys
            }
            if not draft.priority_locked:
                draft.priority = spec.default_priority
            self.engine._apply_computed(draft)
        if priority:
            draft.priority = priority
            draft.priority_locked = True

        session.draft = draft.to_dict()
        self.db.add(
            TriageRun(
                session_id=session.id,
                turn=session.questions_asked,
                source=TriageSource.USER_OVERRIDE,
                kind=draft.kind,
                previous_kind=previous_kind,
                priority=draft.priority,
                confidence=draft.confidence,
                payload={
                    "override_kind": kind.value if kind else None,
                    "override_priority": priority.value if priority else None,
                },
            )
        )
        session.phase = PHASE_SUMMARY
        self.db.flush()
        return self.summary_payload(session)

    def patch_draft(self, session: IntakeSession, fields: dict[str, str]) -> dict:
        """Review: Nutzer korrigiert einen KI-Vorschlag, ohne eine Frage zu beantworten."""
        if session.phase not in (PHASE_SUMMARY, PHASE_COLLECT):
            raise NotReadyForCreation("Kein Entwurf zum Ändern")
        draft = Draft.from_dict(session.draft)
        if not draft.kind:
            raise NotReadyForCreation("Art fehlt")
        allowed = set(self.engine.rules.spec(draft.kind).field_map())
        for key, value in fields.items():
            if key == "author" or key not in allowed:
                continue
            spec = self.engine.rules.spec(draft.kind).field_map()[key]
            if spec.fill == "computed" or spec.auto:
                continue
            text = str(value or "").strip()
            draft.values[key] = spec.normalize(text) if text else ""
        self.engine._apply_computed(draft)
        session.draft = draft.to_dict()
        session.phase = PHASE_SUMMARY
        self.db.flush()
        return self.summary_payload(session)

    def summary_payload(
        self,
        session: IntakeSession,
        result_source: TriageSource | None = None,
        hits: list[cases.Hit] | None = None,
        risk_warning: str | None = None,
    ) -> dict:
        draft = Draft.from_dict(session.draft)
        diagnosis = self._diagnosis_for(draft)
        open_questions = self.engine.open_questions(draft, diagnosis)
        blocking_missing = self._required_missing_labels(draft)
        incomplete = bool(blocking_missing) or draft.kind is None
        duplicates = [item.to_dict() for item in find_similar(self.db, draft.title)]
        labeled = self.engine.labeled_fields(draft, diagnosis)
        fields = {
            row["label"]: row["value"]
            for row in labeled
            if str(row.get("value") or "").strip()
        }
        hints = self.solution_hints(draft, hits, diagnosis=diagnosis)
        impulse = self.engine.impulse_for(
            draft, hits if hits is not None else cases.search(self._draft_text(draft), limit=1)
        )
        badges = []
        if incomplete:
            badges.append(f"[{BADGE_INCOMPLETE}]")
        # Heuristik nicht als Fehler-Badge — UI sagt es leise.

        return {
            "type": "summary",
            "issueType": kind_label(draft.kind),
            "kind": draft.kind.value if draft.kind else None,
            "priority": draft.priority.value if draft.priority else None,
            "steckbriefName": self.engine.steckbrief_name(draft),
            "title": draft.title,
            "fields": fields,
            "steckbrief": labeled,
            "openQuestions": open_questions,
            "blockingQuestions": blocking_missing,
            "intake": self._legacy_intake(draft, ready=not incomplete),
            "draft": draft.to_dict(),
            "incomplete": incomplete,
            "triageSource": (
                result_source.value
                if result_source
                else None
            ),
            "badge": badges[0] if badges else None,
            "badges": badges,
            "duplicates": duplicates,
            "solutionHints": hints,
            "impulse": impulse,
            "riskWarning": risk_warning or self._risk_warning(draft, hits),
            "kindOptions": [
                {"value": k.value, "label": label} for k, label in KIND_LABELS.items()
            ],
            "priorityOptions": [
                {"value": p.value, "label": label} for p, label in PRIORITY_LABELS.items()
            ],
            "formFields": self._form_fields(draft),
        }

    def ai_fill(
        self,
        session: IntakeSession,
        *,
        field_key: str,
        overwrite: bool = False,
        user: User | None = None,
    ) -> dict:
        if session.phase == PHASE_DONE:
            return self._done_payload(session)

        draft = Draft.from_dict(session.draft)
        if not draft.kind:
            # Ohne kind kann die rules.spec nicht aufgelöst werden.
            guess = self.engine.rules.guess_kind(" ".join(self.transcript(session)))
            draft.kind = guess or RequestKind.CHANGE_REQUEST
        if draft.kind is None:
            raise NotReadyForCreation("Art fehlt")

        spec = self.engine.rules.spec(draft.kind).field_map()
        field_spec = spec.get(field_key)
        if not field_spec:
            raise NotReadyForCreation(f"Feld unbekannt: {field_key}")
        if field_spec.fill == "computed" or field_spec.auto:
            # Nicht automatisierbar.
            session.phase = PHASE_SUMMARY
            self.db.flush()
            return self.summary_payload(session)

        current = str(draft.values.get(field_key) or "").strip()
        if current and not overwrite:
            session.phase = PHASE_SUMMARY
            self.db.flush()
            return self.summary_payload(session)

        transcript = " ".join(self.transcript(session))
        if overwrite:
            draft.values[field_key] = ""

        # Heuristische Bündel-Ausfuellung: pro Feld ein Bündel ausführen.
        before = str(draft.values.get(field_key) or "").strip()
        bundle_key = next(
            (bk for bk, members in BUNDLE_MEMBERS.items() if field_key in members),
            None,
        )
        if bundle_key:
            members = BUNDLE_MEMBERS.get(bundle_key) or ()
            preserved = {
                k: str(draft.values.get(k) or "")
                for k in members
                if str(draft.values.get(k) or "").strip()
            }
            self.engine._apply_answer(
                draft,
                (bundle_key, transcript),
                diagnosis=Diagnosis(),
            )
            if not overwrite and preserved:
                for k, v in preserved.items():
                    # Ziel-Feld darf sich ändern, die anderen nicht.
                    if k != field_key:
                        draft.values[k] = v

        # Weiter nachberechnen (Summen)
        self.engine._apply_computed(draft)
        proposed = str(draft.values.get(field_key) or "").strip()

        if field_spec.ai_mode in {AI_SUGGEST_ONLY, AI_MANUAL_ONLY} or (
            before and not overwrite
        ):
            # Freitext und vorhandene Werte als Vorschlag statt stilles Überschreiben.
            session.phase = PHASE_SUMMARY
            self.db.flush()
            return {
                "type": "proposal",
                "fieldKey": field_key,
                "fieldLabel": field_spec.label,
                "proposal": proposed,
                "summary": self.summary_payload(session),
            }

        session.draft = draft.to_dict()
        session.phase = PHASE_SUMMARY
        self.db.flush()
        return self.summary_payload(session)

    # --- Anlage ---

    def confirm(
        self,
        session: IntakeSession,
        idempotency_key: str | None = None,
        user: User | None = None,
        wait_for_sync: bool = True,
    ) -> dict:
        if session.phase == PHASE_DONE:
            return self._done_payload(session)
        if session.phase != PHASE_SUMMARY:
            raise NotReadyForCreation("Zusammenfassung wurde noch nicht bestätigt")

        if idempotency_key:
            existing = self.db.get(IdempotencyKey, idempotency_key)
            if existing and existing.response:
                return existing.response

        draft = Draft.from_dict(session.draft)
        identity = _jira_identity(user)
        if identity:
            draft.values["author"] = identity
        if not draft.kind or not draft.title:
            raise NotReadyForCreation("Art oder Titel fehlt")

        missing_mandatory = self._ensure_mandatory(draft, session, user)
        if missing_mandatory:
            raise NotReadyForCreation(
                "Pflichtfelder fehlen: " + ", ".join(missing_mandatory)
            )
        session.draft = draft.to_dict()

        diagnosis = self._diagnosis_for(draft)
        open_questions = self.engine.open_questions(draft, diagnosis)
        triage_failed = any(
            run.source is TriageSource.HEURISTIC for run in session.triage_runs
        )
        request = Request(
            reference=self._next_reference(),
            kind=draft.kind,
            status=RequestStatus.STECKBRIEF,
            priority=draft.priority or self.engine.rules.spec(draft.kind).default_priority,
            title=draft.title[:200],
            steckbrief_name=self.engine.steckbrief_name(draft),
            description=draft.values.get("description") or "\n\n".join(
                self.report(session) or self.transcript(session)
            ),
            company=draft.values.get("company"),
            change_lead=draft.values.get("change_lead"),
            incomplete=bool(open_questions),
            triage_failed=triage_failed,
            confidence=draft.confidence,
            created_by=user.id if user else None,
            session_id=session.id,
        )
        self.db.add(request)
        self.db.flush()

        labeled = self.engine.labeled_fields(draft, diagnosis)
        for position, row in enumerate(labeled):
            self.db.add(
                RequestField(
                    request_id=request.id,
                    key=row["key"],
                    label=row["label"],
                    value=row["value"],
                    position=position,
                )
            )

        self.db.add(
            ExternalRef(
                request_id=request.id,
                system=get_runtime_config(self.db).ticket_port,
                sync_state=SyncState.PENDING,
            )
        )
        enqueue(self.db, request.id, OutboxOperation.CREATE_ISSUE)

        session.phase = PHASE_DONE
        session.request_id = request.id
        session.context = dict(session.context or {}) | {"last_request_id": request.id}
        self.db.flush()

        if wait_for_sync:
            process_request(self.db, get_ticket_port(), request.id)
        ref = next((item for item in request.external_refs), None)
        jira_key = (ref.external_key if ref else None) or None
        jira_url = (ref.external_url if ref else None) or None
        sync_state = (
            ref.sync_state.value
            if ref and hasattr(ref.sync_state, "value")
            else (ref.sync_state if ref else SyncState.PENDING.value)
        )
        # Nach Sync ist reference = Jira-Key; sonst lokale AN-Nummer.
        display_key = jira_key or request.reference

        payload = {
            "type": "created",
            "requestId": request.id,
            "reference": request.reference,
            "ticketKey": display_key,
            "jiraKey": jira_key,
            "jiraUrl": jira_url,
            "externalKey": jira_key,
            "externalUrl": jira_url,
            "url": f"/workspace/{request.id}",
            "steckbriefName": request.steckbrief_name,
            "title": request.title,
            "kind": request.kind.value,
            "issueType": kind_label(draft.kind),
            "priority": request.priority.value,
            "priorityLabel": PRIORITY_LABELS[Priority(request.priority)],
            "fields": {row["label"]: row["value"] for row in labeled},
            "steckbrief": labeled,
            "changeLead": request.change_lead,
            "solutionHints": self.solution_hints(draft, diagnosis=diagnosis),
            "incomplete": request.incomplete,
            "openQuestions": open_questions,
            "syncState": sync_state,
            "syncError": ref.last_error if ref else None,
            "intake": self._legacy_intake(draft, ready=not open_questions),
        }

        if idempotency_key:
            self.db.merge(
                IdempotencyKey(
                    key=idempotency_key,
                    scope="confirm",
                    request_id=request.id,
                    response=payload,
                )
            )
        self.db.flush()
        return payload

    def _summary_after_ready(
        self, session: IntakeSession, result: TriageResult | None = None
    ) -> dict:
        self._seed_optional_fields(session, result)
        session.phase = PHASE_SUMMARY
        self._remember_pending(session, None)
        self.db.flush()
        payload = self.summary_payload(
            session,
            result_source=result.source if result else None,
            hits=result.hits if result else None,
            risk_warning=result.risk_warning if result else None,
        )
        if result:
            payload["intent"] = result.intent
        payload["questionsAsked"] = session.questions_asked
        return payload

    def _seed_optional_fields(
        self, session: IntakeSession, result: TriageResult | None
    ) -> None:
        """Risiken nur aus Mustern, aehnliche Loesung nur bei Treffern. Kein Nachfragen."""
        draft = Draft.from_dict(session.draft)
        hits = result.hits if result else None
        risks, _ = collab.propose_risks(draft, hits)
        current_risks = str(draft.values.get("risks_obstacles") or "").strip()
        if risks and (
            not current_risks or current_risks.lower() in {"keine", "kein", "-", "nein"}
        ):
            draft.values["risks_obstacles"] = risks
        similar, sources = collab.propose_similar(self.db, draft)
        current_sim = str(draft.values.get("similar_solution") or "").strip()
        if sources and similar and (not current_sim or _dumped_similar(current_sim)):
            draft.values["similar_solution"] = similar
        session.draft = draft.to_dict()

    def _remember_pending(self, session: IntakeSession, key: str | None) -> None:
        """Merken, wonach gerade gefragt wurde. JSON-Spalte neu setzen, nicht mutieren."""
        context = {**(session.context or {})}
        if key:
            context["pending_field"] = key
        else:
            context.pop("pending_field", None)
        session.context = context

    def _suggestion_groups(
        self, spec, kind: str | None, actor_name: str = ""
    ) -> list[dict]:
        """Chips je Bündel: Zeitraum kommt im Frontend, Rest aus YAML/Historie."""
        if not spec or not kind:
            return []
        keys = {
            PEOPLE_KEY: PEOPLE_KEYS,
            ROLES_KEY: ROLES_KEYS,
            EFFORT_KEY: ("concept_scs_pt", "operate_scs_pt"),
            KONTO_KEY: ("company",),
            SOLUTION_KEY: ("solution_exists",),
        }.get(spec.key)
        if not keys:
            return []
        fmap = self.engine.rules.spec(RequestKind(kind)).field_map()
        groups: list[dict] = []
        for key in keys:
            field = fmap.get(key)
            items = values_for(self.db, field, kind=kind)
            groups.append(
                {
                    "key": key,
                    "label": field.label if field else key,
                    "items": items,
                }
            )
        return groups

    def _suggestions(self, spec, kind: str | None, actor_name: str = "") -> list[str]:
        groups = self._suggestion_groups(spec, kind, actor_name)
        if groups:
            out: list[str] = []
            seen: set[str] = set()
            for group in groups:
                for value in group["items"]:
                    marker = value.lower()
                    if marker in seen:
                        continue
                    seen.add(marker)
                    out.append(value)
            return out
        return values_for(self.db, spec, kind=kind)

    def _declined(
        self, session: IntakeSession, pending: str | None, text: str
    ) -> set[str]:
        """Felder, zu denen der Nutzer nichts weiss. Dieselbe Frage kommt nicht wieder."""
        context = {**(session.context or {})}
        known = set(context.get("declined") or [])
        if pending in BUNDLE_MEMBERS:
            known.update((pending, *BUNDLE_MEMBERS[pending]))
            context["declined"] = sorted(known)
            session.context = context
        elif pending == EMPATHY_KEY:
            # Empathie-Frage immer als beantwortet markieren (nie doppelt fragen).
            known.add(EMPATHY_KEY)
            known.add(VALUE_KEY)
            context["declined"] = sorted(known)
            session.context = context
        elif pending and is_unknown_answer(text):
            draft = Draft.from_dict(session.draft)
            if draft.kind:
                spec = self.engine.rules.spec(draft.kind).field_map().get(pending)
                if spec and spec.required_on_confirm:
                    skips = dict(context.get("required_skips") or {})
                    count = int(skips.get(pending, 0)) + 1
                    skips[pending] = count
                    context["required_skips"] = skips
                    session.context = context
                    if count < 3:
                        return known
            known.add(pending)
            context["declined"] = sorted(known)
            session.context = context
        return known

    # --- Pflichtfelder und Wissensbasis ---

    def _draft_text(self, draft: Draft) -> str:
        return " ".join(
            part for part in (draft.title, draft.values.get("description")) if part
        )

    def _risk_warning(self, draft: Draft, hits: list[cases.Hit] | None = None) -> str | None:
        text = self._draft_text(draft)
        found = match_patterns(text)
        if not found:
            return None
        if hits is None:
            hits = cases.search(text, limit=1)
        return warning_text(found, hits)

    def _diagnosis_for(self, draft: Draft) -> Diagnosis:
        """Thema und Fall-Fragen fuer Steckbrief und Hinweise erneut aufloesen."""
        text = self._draft_text(draft)
        return self.engine.diagnose(text, draft.service, cases.search(text, limit=1))

    def solution_hints(
        self,
        draft: Draft,
        hits: list[cases.Hit] | None = None,
        limit: int = MAX_HINTS,
        diagnosis: Diagnosis | None = None,
    ) -> list[dict]:
        """Aehnliche geloeste Faelle. Vielleicht braucht es gar kein neues Anliegen."""
        if hits is None:
            hits = cases.search(self._draft_text(draft), limit=limit)
        if diagnosis is None:
            diagnosis = self._diagnosis_for(draft)
        labels = self.engine.field_label_map(draft, diagnosis)
        out = []
        for hit in hits[:limit]:
            data = hit.to_dict()
            # Fall-Fragen zuerst, sonst needs, sonst Topic-Labels.
            if hit.case.questions:
                data["needs"] = [f.label for f in hit.case.questions]
            elif hit.case.needs:
                data["needs"] = [labels.get(key, key) for key in hit.case.needs]
            elif diagnosis.fields:
                data["needs"] = [f.label for f in diagnosis.fields]
            else:
                data["needs"] = []
            out.append(data)
        return out

    def _ensure_mandatory(
        self, draft: Draft, session: IntakeSession, user: User | None
    ) -> list[str]:
        """Pflichtfelder notfalls hier nachziehen und melden, was dann noch fehlt.

        Die Triage setzt diese Werte normalerweise schon. Hier steht der letzte
        Halt vor der Anlage — lieber ableiten als den Nutzer nochmal fragen.
        """
        spec = self.engine.rules.spec(draft.kind)
        field_map = spec.field_map()
        # Beschreibung nur aus den Meldungen, Zustaendigkeit aus allem Gesagten.
        report = "\n\n".join(self.report(session) or self.transcript(session))
        everything = "\n\n".join(self.transcript(session))

        if "description" in field_map and not draft.values.get("description"):
            draft.values["description"] = report or draft.title
        if "change_lead" in field_map and not draft.values.get("change_lead"):
            person = match_responsible(everything or draft.title, draft.kind)
            if person:
                draft.values["change_lead"] = person.name
        # start_date bewusst nicht erfinden — leeres Start bleibt offen
        if not draft.priority:
            draft.priority = spec.default_priority

        return []

    def _required_missing_labels(self, draft: Draft) -> list[str]:
        """Nur harte Confirm-Pflicht. Alles andere darf offen bleiben."""
        if not draft.kind:
            return []
        field_map = self.engine.rules.spec(draft.kind).field_map()
        required_keys = [
            key
            for key, spec_field in field_map.items()
            if spec_field.required_on_confirm and spec_field.applies(draft.values)
        ]
        if not required_keys:
            # Fallback für Altkonfiguration ohne `required_on_confirm`.
            required_meta = _field_map_meta().get("fields") or {}
            required_keys = [
                key
                for key, meta in required_meta.items()
                if meta.get("required")
                and key in field_map
                and field_map[key].applies(draft.values)
            ]
        return [
            field_map[key].label
            for key in required_keys
            if not str(draft.values.get(key) or "").strip()
        ]

    # --- Intern ---

    def _next_reference(self) -> str:
        """Naechste freie AN-Nummer. Luecken in der Folge zaehlen nicht."""
        highest = 1000
        for ref in self.db.scalars(select(Request.reference)):
            suffix = str(ref or "").removeprefix("AN-")
            try:
                highest = max(highest, int(suffix))
            except ValueError:
                continue
        n = highest + 1
        for _ in range(50):
            candidate = f"AN-{n}"
            exists = self.db.scalar(select(Request.id).where(Request.reference == candidate))
            if not exists:
                return candidate
            n += 1
        raise RuntimeError("keine freie Referenz gefunden")

    def _record_run(self, session: IntakeSession, result: TriageResult) -> None:
        self.db.add(
            TriageRun(
                session_id=session.id,
                turn=session.questions_asked,
                source=result.source,
                model=result.model,
                latency_ms=result.latency_ms,
                kind=result.draft.kind,
                previous_kind=result.previous_kind,
                priority=result.draft.priority,
                confidence=result.draft.confidence,
                question=result.question,
                error=result.error,
                payload={
                    "raw": result.raw,
                    "switched_reason": result.switched_reason,
                    "unclear": result.unclear,
                    "ready": result.ready,
                },
            )
        )

    def _legacy_intake(self, draft: Draft, ready: bool) -> dict:
        """Schema des Prototyps, damit das alte Frontend weiterlaeuft."""
        return {
            "intent": KIND_TO_LEGACY_INTENT.get(draft.kind) if draft.kind else None,
            "kind": draft.kind.value if draft.kind else None,
            "service": draft.service,
            "summary": draft.title,
            "impact": draft.values.get("scope"),
            "urgency": draft.values.get("urgency") or (
                draft.priority.value if draft.priority else None
            ),
            "confidence": draft.confidence,
            "fields": dict(draft.values),
            "missing_information": self.engine.open_questions(draft),
            "ready_for_ticket": ready,
        }

    def _done_payload(self, session: IntakeSession) -> dict:
        request = self.db.get(Request, session.request_id) if session.request_id else None
        if not request:
            return {"type": "done"}
        ref = next((r for r in request.external_refs if r.external_key), None)
        jira_key = ref.external_key if ref else None
        display_key = jira_key or request.reference
        return {
            "type": "done",
            "requestId": request.id,
            "reference": request.reference,
            "ticketKey": display_key,
            "jiraKey": jira_key,
            "jiraUrl": ref.external_url if ref else None,
            "url": f"/workspace/{request.id}",
            "steckbriefName": request.steckbrief_name,
            "title": request.title,
            "fields": {f.label: f.value for f in sorted(request.fields, key=lambda f: f.position)},
            "externalKey": jira_key,
            "externalUrl": ref.external_url if ref else None,
        }
