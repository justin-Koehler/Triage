"""Klammer um den Chat: erst Absicht, dann Intake.

Der Intake-Pfad in `IntakeService` bleibt unangetastet. Hier faellt nur die
Entscheidung, ob ein Satz ein neues Anliegen ist oder eine Frage, ein Befehl
oder ein Sprung auf eine andere Seite.
"""

from __future__ import annotations

import json
import logging
import re
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
from app.triage.providers import LlmUnavailable
from app.services.similarity import find_similar

log = logging.getLogger("triage.assistant")

LIST_LIMIT = 10
CONFIRM_STATUSES = {RequestStatus.DONE, RequestStatus.REJECTED}
YES = {"ja", "jap", "jo", "yes", "ok", "okay", "mach", "bestätigen", "bestaetigen"}
NO = {"nein", "nö", "noe", "stopp", "stop", "abbrechen", "doch nicht", "lass"}


HUB_SYSTEM = (
    "Du bist Qwen, der Workspace-Assistent von CRITR (Change-Management). "
    "Du schreibst direkt mit dem Nutzer — prüfe Aussagen am Workspace-Kontext. "
    "Deutsch, klar, 2–5 Sätze. Keine Floskeln, kein Smalltalk. "
    "Erfinde keine Ticketnummern, Freigaben, Links oder Status. "
    "Nutze nur den mitgelieferten Workspace-Kontext und den Chatverlauf. "
    "Wenn der Nutzer etwas behauptet, das nicht zum Kontext passt: widersprich klar "
    "und nenne die passende Info aus dem Kontext. "
    "Geh auf die letzte Aussage ein; bei Lücken sag, was fehlt — rate nicht. "
    "Wenn die Absicht unklar ist: eine kurze Rückfrage und 2–3 Optionen. "
    "Wenn jemand einen neuen Change anlegen will: bestätige kurz und starte die "
    "geführte Anlage (der Workspace übernimmt die Fragen). "
    "Keine stillen Schreibaktionen in Jira oder Felder."
)

HUB_CLARIFY_ACTIONS = (
    {
        "id": "inbox",
        "label": "Was wartet auf mich?",
        "prompt": "Was wartet gerade auf mich?",
    },
    {
        "id": "create",
        "label": "Change anlegen",
        "prompt": "Ich benötige Unterstützung beim Erstellen eines Changes",
    },
    {
        "id": "open",
        "label": "Offene Changes",
        "prompt": "Welche Changes sind offen?",
    },
)
VAGUE_HUB = re.compile(
    r"^(?:\?+|hmm+|ähm+|äh+|ok|okay|und\??|weiter\??|hilfe\??|hallo|hey|hi|"
    r"was\??|wie\??|nä\??|na\??|yo|test|bitte\??)$",
    re.IGNORECASE,
)

# Slot-Filling für Change-Anlage (Dialog-State, nicht starres Skript).
# Pro Turn: Werte speichern → nächster leerer Slot → fertig = bestätigen.
HUB_CREATE_EXTRACT = (
    "Du extrahierst Steckbrief-Felder für einen Change Request. "
    "Nur aus Nutzertext + bisherigem Entwurf. Erfinde nichts. Keine Rückfrage.\n"
    "Fülle JEDE erkennbare Angabe (auch mehrere auf einmal):\n"
    "- problem: Problem / was heute schief läuft\n"
    "- solution_goals: Lösung und Ziele / Erfolgskriterium\n"
    "- benefit_savings: Nutzen (Zeit, Geld, Qualität, Umsatz)\n"
    "- benefit_risk: welches Risiko dadurch sinkt\n"
    "- risks_obstacles: was scheitern oder blockieren kann\n"
    "- similar_solution: ähnliche bekannte Lösungen (oder „keine bekannt“)\n"
    "- current_status: wo der Change gerade steht\n"
    "- sponsor: Auftraggeber (Person)\n"
    "- change_lead: wer den Change führt\n"
    "- components: Stichwörter/Tags, kommasepariert\n"
    "- help_needed: genau eines von Projektmanagement|Methodisch|Personell\n"
    "- start_date / end_date: Start bzw. Ende in Alltagssprache\n"
    "- title: kurze Überschrift (max. 8 Wörter)\n"
    "- description: 3–6 Sätze aus Problem + Lösung + Nutzen\n"
    "„bald/asap/schnell“ → start_date=bald. "
    "„weiß nicht/egal/überspringen/keine“ bei optionalen Feldern → passenden Default.\n"
    "abort=true nur bei klarem Abbruch.\n\n"
    "Antwort NUR JSON ohne Markdown:\n"
    '{"draft":{"title":"","description":"","problem":"","solution_goals":"",'
    '"benefit_savings":"","benefit_risk":"","risks_obstacles":"","similar_solution":"",'
    '"current_status":"","sponsor":"","change_lead":"","components":"","help_needed":"",'
    '"start_date":"","end_date":""},"abort":false}'
)


HUB_CREATE_COACH = (
    "Du bist Qwen und prüfst Steckbrief-Antworten für einen Change. "
    "Deutsch, konkret, max. 3 Sätze. Keine Floskeln. Erfinde nichts.\n"
    "1) Greife den Inhalt der letzten Nutzerantwort auf (nicht nur „ok“).\n"
    "2) Prüfe streng: Reicht die Antwort für den aktuellen Slot? "
    "Zu dünn, unklar, ausweichend oder ohne Substanz → enough=false, "
    "sage was fehlt, eine gezielte Nachfrage zum gleichen Slot.\n"
    "3) Nur wenn Inhalt und Detail reichen → enough=true, kurze Würdigung "
    "+ die mitgelieferte nächste Frage.\n"
    "Antwort NUR JSON ohne Markdown:\n"
    '{"enough":true,"reply":"..."}'
)

CREATE_START = re.compile(
    r"(unterstützung|hilfe).{0,40}(erstellen|anlegen).{0,20}(change|ticket)"
    r"|(change|ticket).{0,20}(erstellen|anlegen).{0,40}(unterstützung|hilfe)"
    r"|benötige\s+(?:hilfe|unterstützung)"
    r"|brauche\s+(?:hilfe|unterstützung)"
    r"|change\s+gemeinsam\s+(erarbeiten|erstellen)"
    r"|^(?:neuen?\s+)?(?:change|ticket)\s+(?:anlegen|erstellen)\b"
    r"|^(?:ich\s+)?(?:will|möchte|brauch(?:e)?)\s+(?:einen?\s+)?(?:neuen?\s+)?"
    r"(?:change|ticket)\b"
    r"|^(?:change|ticket)\s+(?:bitte\s+)?(?:anlegen|erstellen)\b",
    re.IGNORECASE,
)
CREATE_JSON = re.compile(r"\{[\s\S]*\}")
CREATE_CONFIRM = {
    "anlegen",
    "erstellen",
    "leg an",
    "lege an",
    "ja anlegen",
    "ja, anlegen",
    "mach das",
    "leg los",
    "change anlegen",
    "ticket anlegen",
}
CREATE_SOFT_CONFIRM = {
    "ja",
    "ok",
    "okay",
    "passt",
    "passt so",
    "genau",
    "yes",
    "y",
}
CREATE_SKIP = {
    "überspringen",
    "ueberspringen",
    "skip",
    "egal",
    "weiß nicht",
    "weiss nicht",
    "weiß ich nicht",
    "weiss ich nicht",
    "weiß ich noch nicht",
    "weiss ich noch nicht",
    "keine ahnung",
    "noch offen",
    "offen",
    "bald",
    "asap",
    "schnell",
    "sofort",
    "keine besonderen",
    "keine bekannt",
}
CREATE_DRAFT_KEYS = (
    "title",
    "description",
    "problem",
    "solution_goals",
    "benefit_savings",
    "benefit_risk",
    "risks_obstacles",
    "similar_solution",
    "current_status",
    "sponsor",
    "change_lead",
    "components",
    "help_needed",
    "start_date",
    "end_date",
)
# Reihenfolge = Slot-Spine. required=True muss vor Anlegen stehen.
CREATE_SLOTS: tuple[dict[str, object], ...] = (
    {
        "key": "problem",
        "label": "Problem",
        "required": True,
        "ask": "Welches Problem löst der Change — was läuft heute schief?",
    },
    {
        "key": "solution_goals",
        "label": "Lösung",
        "required": True,
        "ask": "Was ist die Lösung — und wann ist sie erfolgreich?",
    },
    {
        "key": "benefit_savings",
        "label": "Nutzen",
        "required": True,
        "ask": "Welcher konkrete Nutzen entsteht (Zeit, Geld, Qualität)?",
    },
    {
        "key": "risks_obstacles",
        "label": "Risiken",
        "required": True,
        "ask": "Was könnte scheitern oder den Change blockieren?",
        "skip_default": "Keine besonderen Risiken genannt.",
        "chips": (
            ("Keine besonderen", "Keine besonderen"),
            ("Zeitdruck", "Zeitdruck"),
            ("Abhängigkeiten", "Abhängigkeiten zu anderen Systemen"),
        ),
    },
    {
        "key": "benefit_risk",
        "label": "Risiko↓",
        "required": True,
        "ask": "Welches Risiko sinkt dadurch klar?",
        "skip_default": "Risiken aus dem beschriebenen Problem werden reduziert.",
        "chips": (
            ("Aus dem Problem", "Risiken aus dem beschriebenen Problem werden reduziert."),
            ("Weiß ich nicht", "Weiß ich noch nicht"),
        ),
    },
    {
        "key": "people",
        "label": "Wer",
        "required": True,
        "ask": "Wer beauftragt den Change — und wer führt ihn?",
        "fills": ("sponsor", "change_lead"),
    },
    {
        "key": "schedule",
        "label": "Zeit",
        "required": True,
        "ask": "Wann ungefähr starten — und wann fertig?",
        "fills": ("start_date", "end_date"),
        "chips": (
            ("Bald starten", "bald starten, Ende noch offen"),
            ("Dieses Quartal", "Start dieses Quartal"),
            ("Weiß ich nicht", "Weiß ich noch nicht"),
        ),
    },
    {
        "key": "components",
        "label": "Tags",
        "required": False,
        "ask": "Welche Stichwörter passen? (z. B. SAP, Schul-App)",
        "skip_default": "Change",
        "chips": (
            ("Überspringen", "Überspringen"),
            ("SAP", "SAP"),
            ("App", "App"),
        ),
    },
    {
        "key": "current_status",
        "label": "Stand",
        "required": False,
        "ask": "Wo steht der Change gerade?",
        "skip_default": "Idee / in Klärung",
        "chips": (
            ("Idee", "Idee / in Klärung"),
            ("In Planung", "In Planung"),
            ("Gestartet", "Bereits gestartet"),
        ),
    },
    {
        "key": "similar_solution",
        "label": "Bezug",
        "required": False,
        "ask": "Kennst du ähnliche Lösungen bei Schwarz?",
        "skip_default": "Keine bekannt",
        "chips": (
            ("Keine bekannt", "Keine bekannt"),
            ("Weiß ich nicht", "Weiß ich noch nicht"),
        ),
    },
    {
        "key": "help_needed",
        "label": "Hilfe",
        "required": False,
        "ask": "Benötigst du Unterstützung bei dem Projekt? Wenn ja welche?",
        "skip_default": "",
        "chips": (
            ("Projektmanagement", "Projektmanagement"),
            ("Methodisch", "Methodisch"),
            ("Personell", "Personell"),
        ),
    },
)
CREATE_MAX_QUESTIONS = 10
CREATE_PROGRESS = tuple(
    (str(slot["key"]), str(slot["label"])) for slot in CREATE_SLOTS
)

SKIP_LLM = {"heuristik", "scripted", "none", "dead", "test"}


@dataclass
class AssistantService:
    db: Session
    intake: IntakeService
    provider: object | None = None

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
        hub_mode = str((context.get("client") or {}).get("mode") or "") == "hub"
        if hub_mode:
            context["hub_chat"] = True
        session.context = context

        pending = context.get("pending")
        if pending:
            # Im Hub nur Schreib-Bestätigungen (Stand/Status), sonst wie bisher.
            if hub_mode and pending.get("kind") in {"status_note", "comment", "status"}:
                resolved = self._resolve_pending(session, text, pending, actor)
                if resolved:
                    return self._finish_hub(session, resolved, hub_mode)
            elif not hub_mode:
                resolved = self._resolve_pending(session, text, pending, actor)
                if resolved:
                    return resolved

        if hub_mode:
            return self._finish_hub(session, self._hub_turn(session, text, actor), True)

        if hub_mode and (
            context.get("hub_assist_create") or CREATE_START.search(text or "")
        ):
            # Während Sparring: ähnlichen Change öffnen statt weiterfragen.
            ref = intents.find_reference(text or "")
            if ref and any(
                w in (text or "").lower()
                for w in ("öffne", "oeffne", "zeig", "bestehend", "nimm", "nutze")
            ):
                found = self._by_reference(ref)
                if found:
                    context.pop("hub_assist_create", None)
                    context.pop("hub_create_draft", None)
                    context.pop("hub_create_ready", None)
                    session.context = context
                    self._log_turn(session, text)
                    payload = self._navigate_to(session, found)
                    return self._finish_hub(session, payload, True)
            self._log_turn(session, text)
            payload = self._hub_create_assist(session, text, actor)
            return self._finish_hub(session, payload, True)

        intent = intents.detect(text, context)
        if intent is not None:
            # Hub: strukturierte Daten (Counts/Refs) behalten — freier Dialog → Qwen.
            hub_keep = (OpenRequest, Query, Navigate, Action, DuplicateChoice)
            if hub_mode and not isinstance(intent, hub_keep):
                intent = None
            else:
                self._log_turn(session, text)
                payload = self._route(session, intent, text, actor)
                return self._finish_hub(session, payload, hub_mode)

        # Mitten in der Erfassung: Antworten auf Rueckfragen sind selten "Anliegen"-Saetze.
        if self._intake_in_progress(session) and not hub_mode:
            return self._intake(session, text, actor)

        found = self._maybe_open_existing(session, text)
        if found:
            self._log_turn(session, text)
            return self._finish_hub(session, found, hub_mode)

        if hub_mode:
            # Leere Eingabe → kurze Optionen; alles andere geht an Qwen.
            if not (text or "").strip():
                self._log_turn(session, text)
                return self._finish_hub(session, self._hub_clarify(), True)
            self._log_turn(session, text)
            payload = self._hub_chat(session, text, actor)
            return self._finish_hub(session, payload, True)

        # Ohne erkannte Absicht ist die Erfassung der Default. Nur Rauschen
        # (leerer Text, einzelnes Fragewort) bekommt die Faehigkeiten-Antwort.
        if not intents.looks_like_issue(text):
            self._log_turn(session, text)
            payload = self._answer(answers.capabilities_answer())
            self._log_answer(session, payload)
            return payload

        return self._intake(session, text, actor)

    def handle_stream(
        self,
        session: IntakeSession,
        text: str,
        client: dict | None = None,
        actor: User | None = None,
    ):
        """SSE-Events: token / done. Nicht-LLM-Pfade liefern nur done."""
        context = dict(session.context or {})
        if client:
            context["client"] = client
        hub_mode = str((context.get("client") or {}).get("mode") or "") == "hub"
        if hub_mode:
            context["hub_chat"] = True
        session.context = context

        # Schreib-Bestätigung, Create-Assist, Intents: einmalig fertig antworten.
        pending = context.get("pending")
        if pending and hub_mode and pending.get("kind") in {"status_note", "comment", "status"}:
            resolved = self._resolve_pending(session, text, pending, actor)
            if resolved:
                yield {"event": "done", "payload": self._finish_hub(session, resolved, True)}
                return

        if hub_mode:
            turn = str((context.get("client") or {}).get("turn") or "")
            if turn == "edit":
                self._rewind_last_user(session)
            elif turn == "regenerate":
                self._drop_last_assistant(session)
            if self._hub_should_stream(session, text):
                yield from self._stream_hub_question(
                    session,
                    text,
                    actor,
                    log_user=turn != "regenerate",
                )
                return
            yield {
                "event": "done",
                "payload": self._finish_hub(
                    session, self._hub_turn(session, text, actor), True
                ),
            }
            return

        if hub_mode and (
            context.get("hub_assist_create") or CREATE_START.search(text or "")
        ):
            # Wie in handle(): bestehendes Ticket öffnen statt weiterfragen.
            ref = intents.find_reference(text or "")
            if ref and any(
                w in (text or "").lower()
                for w in ("öffne", "oeffne", "zeig", "bestehend", "nimm", "nutze")
            ):
                found = self._by_reference(ref)
                if found:
                    context.pop("hub_assist_create", None)
                    context.pop("hub_create_draft", None)
                    context.pop("hub_create_ready", None)
                    session.context = context
                    self._log_turn(session, text)
                    payload = self._navigate_to(session, found)
                    yield {"event": "done", "payload": self._finish_hub(session, payload, True)}
                    return
            self._log_turn(session, text)
            payload = self._hub_create_assist(session, text, actor)
            yield {"event": "done", "payload": self._finish_hub(session, payload, True)}
            return

        intent = intents.detect(text, context)
        if intent is not None:
            hub_keep = (OpenRequest, Query, Navigate, Action, DuplicateChoice)
            if not (hub_mode and not isinstance(intent, hub_keep)):
                self._log_turn(session, text)
                payload = self._route(session, intent, text, actor)
                yield {"event": "done", "payload": self._finish_hub(session, payload, hub_mode)}
                return
            intent = None

        found = self._maybe_open_existing(session, text)
        if found:
            self._log_turn(session, text)
            yield {"event": "done", "payload": self._finish_hub(session, found, hub_mode)}
            return

        if not hub_mode:
            payload = self.handle(session, text, client, actor)
            yield {"event": "done", "payload": payload}
            return

        if not (text or "").strip():
            self._log_turn(session, text)
            yield {"event": "done", "payload": self._finish_hub(session, self._hub_clarify(), True)}
            return

        self._log_turn(session, text)
        parts: list[str] = []
        try:
            for chunk in self._hub_chat_stream(session, text, actor):
                parts.append(chunk)
                yield {"event": "token", "text": chunk}
        except LlmUnavailable as err:
            payload = self._answer(
                Answer(text=f"KI gerade nicht erreichbar ({err}). Versuch es gleich nochmal.")
            )
            yield {"event": "done", "payload": self._finish_hub(session, payload, True)}
            return
        reply = "".join(parts).strip()
        if not reply:
            payload = self._answer(Answer(text="Keine Antwort vom Modell."))
        else:
            payload = self._answer(Answer(text=reply))
            lowered = reply.lower()
            if "?" in reply or "unklar" in lowered or "meinst du" in lowered:
                payload["actions"] = [dict(item) for item in HUB_CLARIFY_ACTIONS]
        yield {"event": "done", "payload": self._finish_hub(session, payload, True)}

    def _finish_hub(self, session: IntakeSession, payload: dict, hub_mode: bool) -> dict:
        if hub_mode:
            payload = self._enrich_hub_payload(payload)
        self._log_answer(session, payload)
        return payload

    def _hub_is_vague(self, text: str) -> bool:
        raw = (text or "").strip()
        if not raw:
            return True
        if intents.find_reference(raw):
            return False
        if VAGUE_HUB.match(raw):
            return True
        words = intents.tokens(raw)
        if len(words) <= 2 and not (set(words) & intents.DOMAIN_NOUNS):
            # Kurze Sätze ohne Domänenwort → lieber nachfragen.
            if any(w in {"welche", "was", "wie", "wer", "wo"} for w in words):
                return True
            if len(words) == 1:
                return True
        return False

    HUB_CORE_GAPS = (
        ("problem", "Welches Problem soll der Change lösen?"),
        ("solution_goals", "Was soll sich ändern, und woran merkt man, dass es sitzt?"),
        ("benefit_savings", "Welchen Nutzen bringt das — Zeit, Geld oder Qualität?"),
        ("start_date", "Wann soll es ungefähr starten?"),
        ("end_date", "Bis wann soll es fertig sein?"),
    )
    HUB_PROBES = {
        "problem": (
            "Das ist ein guter Anfang. Für wen ist das gerade ein Problem?",
            "Und was passiert dadurch im Alltag?",
        ),
        "solution_goals": (
            "Die Richtung ist klar. Was soll sich konkret ändern?",
            "Woran merkt ihr, dass die Lösung sitzt?",
        ),
        "benefit_savings": (
            "Welcher Nutzen ist das konkret — Zeit, Geld oder Qualität?",
        ),
    }
    HUB_MUSTER = {
        "problem": (
            "Zwei bis vier Sätze: was heute schief läuft, für wen, mit welchem Effekt. "
            "Keine Lösung, kein Datum, nichts erfinden."
        ),
        "solution_goals": (
            "Zwei bis vier Sätze: was sich ändert und woran man den Erfolg merkt. "
            "Nichts erfinden."
        ),
        "benefit_savings": (
            "Ein bis drei Sätze: Nutzen in Zeit, Geld oder Qualität, nur aus der Angabe."
        ),
    }

    def _hub_should_stream(self, session: IntakeSession, text: str) -> bool:
        raw = (text or "").strip()
        if not raw:
            return False
        context = session.context or {}
        if context.get("hub_assist_create") or CREATE_START.search(raw):
            return False
        if not self._hub_is_question(raw) and len(raw.split()) >= 6:
            return False
        name = str(getattr(self.provider, "name", "") or "").lower()
        if (
            not self.provider
            or name in SKIP_LLM
            or name.startswith("scripted")
            or not hasattr(self.provider, "complete_text")
        ):
            return False
        return True

    def _trim_hub_messages(self, session: IntakeSession, start: int) -> None:
        rows = list(session.messages or [])
        if start < 0 or start >= len(rows):
            return
        for row in rows[start:]:
            self.db.delete(row)
        self.db.flush()
        self.db.expire(session, ["messages"])

    def _rewind_last_user(self, session: IntakeSession) -> None:
        rows = list(session.messages or [])
        idx = next(
            (i for i in range(len(rows) - 1, -1, -1) if rows[i].role == "user"),
            None,
        )
        if idx is not None:
            self._trim_hub_messages(session, idx)

    def _drop_last_assistant(self, session: IntakeSession) -> None:
        rows = list(session.messages or [])
        idx = next(
            (
                i
                for i in range(len(rows) - 1, -1, -1)
                if rows[i].role == "assistant"
            ),
            None,
        )
        if idx is not None:
            self._trim_hub_messages(session, idx)

    def _stream_hub_question(
        self,
        session: IntakeSession,
        text: str,
        actor: User | None,
        log_user: bool,
    ):
        raw = (text or "").strip()
        found = self._maybe_open_existing(session, raw)
        if found:
            if log_user:
                self._log_turn(session, raw)
            yield {
                "event": "done",
                "payload": self._finish_hub(session, found, True),
            }
            return
        if log_user:
            self._log_turn(session, raw)
        parts: list[str] = []
        try:
            for chunk in self._hub_chat_stream(session, raw, actor):
                parts.append(chunk)
                yield {"event": "token", "text": chunk}
        except LlmUnavailable as err:
            payload = self._answer(
                Answer(
                    text=(
                        f"KI gerade nicht erreichbar ({err}). "
                        "Versuch es gleich nochmal."
                    )
                )
            )
            yield {
                "event": "done",
                "payload": self._finish_hub(session, payload, True),
            }
            return
        reply = "".join(parts).strip() or "Keine Antwort vom Modell."
        payload = self._answer(Answer(text=reply))
        payload.pop("actions", None)
        yield {
            "event": "done",
            "payload": self._finish_hub(session, payload, True),
        }

    def _hub_is_question(self, text: str) -> bool:
        raw = (text or "").strip()
        low = raw.lower()
        if raw.endswith("?"):
            return True
        return low.startswith(
            (
                "wie ",
                "was ",
                "welche ",
                "welcher ",
                "wer ",
                "wo ",
                "wann ",
                "zeig",
                "öffne",
                "oeffne",
                "erklär",
                "erklaer",
                "liste ",
                "nenn",
            )
        )

    def _hub_turn(self, session: IntakeSession, text: str, actor: User | None) -> dict:
        """Eine Entscheidung: Frage zum Workspace oder Entwurf mit höchstens einer Lücke."""
        raw = (text or "").strip()
        if not raw:
            return self._answer(Answer(text="Schreib einen Satz oder wähl einen Vorschlag."))
        context = dict(session.context or {})
        creating = bool(context.get("hub_assist_create"))
        start = bool(CREATE_START.search(raw))
        if creating or start or (not self._hub_is_question(raw) and len(raw.split()) >= 6):
            self._log_turn(session, raw)
            return self._hub_simple_create(session, raw, actor)
        found = self._maybe_open_existing(session, raw)
        if found:
            self._log_turn(session, raw)
            return found
        self._log_turn(session, raw)
        payload = self._hub_chat(session, raw, actor)
        payload.pop("actions", None)
        return payload

    def _hub_core_gap(self, draft: dict) -> tuple[str, str] | None:
        for key, ask in self.HUB_CORE_GAPS:
            if not str(draft.get(key) or "").strip():
                return key, ask
        return None

    def _simple_create_payload(self, text: str, draft: dict, ready: bool) -> dict:
        payload = self._answer(Answer(text=text))
        payload["createAssist"] = True
        payload["createReady"] = bool(ready)
        payload["createProgress"] = []
        payload["createDraft"] = {
            key: str(draft.get(key) or "").strip()
            for key in (
                "title",
                "problem",
                "solution_goals",
                "benefit_savings",
                "start_date",
                "end_date",
            )
            if str(draft.get(key) or "").strip()
        }
        if ready:
            payload["actions"] = [
                {"id": "create", "label": "Change anlegen", "prompt": "Change anlegen"}
            ]
        return payload

    def _hub_simple_create(
        self, session: IntakeSession, text: str, actor: User | None
    ) -> dict:
        context = dict(session.context or {})
        raw = (text or "").strip()
        lowered = raw.lower()
        starting = not context.get("hub_assist_create")
        if starting:
            context["hub_assist_create"] = True
            context["hub_create_draft"] = {}
            context["hub_create_ready"] = False
            session.context = context
            if CREATE_START.search(raw) and len(raw.split()) <= 12:
                return self._simple_create_payload(
                    "Welches Problem soll der Change lösen?",
                    {},
                    False,
                )

        if lowered in {"abbrechen", "stopp", "cancel"}:
            return self._end_create_assist(
                session,
                "Abgebrochen. Schreib einfach, wenn du neu anfangen willst.",
            )

        draft = dict(context.get("hub_create_draft") or {})
        ready_now = context.get("hub_create_ready") and self._hub_core_gap(draft) is None
        if ready_now and (
            lowered in CREATE_CONFIRM
            or lowered in YES
            or lowered in CREATE_SOFT_CONFIRM
            or lowered.startswith("change anlegen")
        ):
            return self._publish_hub_draft(session, draft, actor)

        gap = self._hub_core_gap(draft)
        probe = str(context.get("hub_create_probe") or "")
        starter = bool(CREATE_START.search(raw) and len(raw.split()) <= 12)
        skip_fill = (
            starter
            or self._hub_is_question(raw)
            or lowered in CREATE_CONFIRM
            or lowered in YES
            or lowered in CREATE_SOFT_CONFIRM
            or lowered in {"abbrechen", "stopp", "cancel"}
        )
        focus = probe or (gap[0] if gap else "")
        if focus and not skip_fill and len(raw) >= 2:
            if lowered in CREATE_SKIP and focus in {"start_date", "end_date"}:
                draft[focus] = "noch offen"
            elif probe:
                prev = str(draft.get(probe) or "").strip()
                draft[probe] = f"{prev} {raw}".strip()[:800] if raw not in prev else prev
            elif len(raw) >= 3:
                draft[focus] = raw[:800]
        extracted = self._extract_create_draft(draft, raw, session)
        if extracted.get("abort"):
            return self._end_create_assist(session, "Abgebrochen.")
        draft = self._ensure_create_draft(extracted.get("draft") or draft, actor)
        focus = probe or focus
        if focus in self.HUB_PROBES and str(draft.get(focus) or "").strip():
            thin = self._hub_field_thin(focus, str(draft.get(focus) or ""))
            asked = int(context.get("hub_create_probe_n") or 0)
            probes = self.HUB_PROBES[focus]
            if thin and asked < len(probes):
                context["hub_create_probe"] = focus
                context["hub_create_probe_n"] = asked + 1
                context["hub_create_draft"] = draft
                context["hub_create_ready"] = False
                context["hub_create_step"] = focus
                session.context = context
                return self._simple_create_payload(probes[asked], draft, False)
            before = str(draft.get(focus) or "")
            draft[focus] = self._polish_create_field(focus, before)
            if focus == "problem":
                title = str(draft.get("title") or "").strip()
                if not title or title in before or before.startswith(title):
                    draft["title"] = " ".join(draft[focus].split())[:80]
            context.pop("hub_create_probe", None)
            context["hub_create_probe_n"] = 0
        elif focus in {"start_date", "end_date"} and str(draft.get(focus) or "").strip():
            context.pop("hub_create_probe", None)
            context["hub_create_probe_n"] = 0
        context["hub_create_draft"] = draft
        missing = self._hub_core_gap(draft)
        if missing:
            context["hub_create_ready"] = False
            context["hub_create_step"] = missing[0]
            context.pop("hub_create_probe", None)
            session.context = context
            return self._simple_create_payload(missing[1], draft, False)
        context["hub_create_ready"] = True
        context.pop("hub_create_probe", None)
        session.context = context
        title = str(draft.get("title") or "Change").strip()
        return self._simple_create_payload(
            f"„{title}“ kann angelegt werden.",
            draft,
            True,
        )

    def _hub_field_thin(self, key: str, text: str) -> bool:
        clean = " ".join((text or "").split()).strip()
        if self._create_thin_reason(clean, key, {key: clean}):
            return True
        if key == "problem":
            who = re.search(
                r"\b(für|lehrer\w*|nutzer\w*|mitarbeiter\w*|team|personen|alle)\b",
                clean,
                re.IGNORECASE,
            )
            effect = re.search(
                r"\b(nicht|fehlt|dauert|fehler|kaputt|warten|block\w*|spät|"
                r"verlust|ausfall|hängen|hängt)\b",
                clean,
                re.IGNORECASE,
            )
            return not (who and effect)
        if key == "solution_goals":
            return not re.search(
                r"\b(soll\w*|wird|werden|ändern|änderung|einführen|ersetzen|"
                r"ziel|erfolg)\b",
                clean,
                re.IGNORECASE,
            )
        if key == "benefit_savings":
            return not re.search(
                r"\b(zeit|geld|stunde\w*|euro|qualität|weniger|sparen|schneller)\b",
                clean,
                re.IGNORECASE,
            )
        return False

    def _polish_create_field(self, key: str, text: str) -> str:
        """Angabe in den Steckbrief-Ton bringen, ohne neue Fakten."""
        clean = " ".join((text or "").split()).strip()
        if not clean:
            return ""
        muster = self.HUB_MUSTER.get(key)
        if not muster:
            return clean
        name = str(getattr(self.provider, "name", "") or "").lower()
        if (
            not self.provider
            or name in SKIP_LLM
            or name.startswith("scripted")
            or not hasattr(self.provider, "complete_text")
        ):
            return clean if clean[-1:] in ".!?" else f"{clean}."
        system = (
            "Du formulierst eine Steckbrief-Angabe um. Deutsch, konkret, "
            "keine Floskeln, nichts erfinden, keine Überschrift. Nur den Feldtext."
        )
        user_block = f"Feld: {key}\nMuster: {muster}\nAngabe: {clean}"
        try:
            out = str(self.provider.complete_text(system, user_block) or "").strip()
        except (LlmUnavailable, TypeError, ValueError):
            out = ""
        out = " ".join(out.split())
        if not out or len(out) < 12 or out.startswith("{") or out.startswith("Feld:"):
            return clean if clean[-1:] in ".!?" else f"{clean}."
        return out[:800]

    def _hub_clarify(self) -> dict:
        return {
            "type": "answer",
            "text": "Worauf genau? Wähl eine Option oder schreib einen Satz mehr.",
            "actions": [dict(item) for item in HUB_CLARIFY_ACTIONS],
        }

    def _enrich_hub_payload(self, payload: dict) -> dict:
        data = dict(payload or {})
        # Während Change-Sparring keine Inbox-/Öffnen-Chips unterschieben.
        if data.get("createAssist"):
            return data
        actions = list(data.get("actions") or [])
        seen = {str(a.get("prompt") or a.get("label") or "").strip().lower() for a in actions}

        def add(action: dict) -> None:
            key = str(action.get("prompt") or action.get("label") or "").strip().lower()
            if not key or key in seen:
                return
            seen.add(key)
            actions.append(action)

        for link in data.get("links") or []:
            label = str(link.get("label") or "").strip()
            url = str(link.get("url") or "").strip()
            if not label or not url:
                continue
            add(
                {
                    "id": "open",
                    "label": f"Öffne {label.split(':')[0].strip()}",
                    "prompt": f"Öffne {label.split(':')[0].strip()}",
                    "url": url,
                }
            )

        text = str(data.get("text") or "")
        for digits in intents.REFERENCE.findall(text)[:3]:
            full = f"AN-{digits}"
            add({"id": "open", "label": f"Öffne {full}", "prompt": f"Öffne {full}"})

        if data.get("type") == "list" and data.get("items"):
            for item in (data.get("items") or [])[:3]:
                ref = item.get("reference") or item.get("key")
                rid = item.get("id")
                if not ref:
                    continue
                action = {"id": "open", "label": f"Öffne {ref}", "prompt": f"Öffne {ref}"}
                if rid:
                    action["url"] = f"/workspace/{rid}"
                add(action)

        if data.get("hubView") == "inbox":
            add(
                {
                    "id": "inbox",
                    "label": "Inbox öffnen",
                    "prompt": "__open_inbox__",
                }
            )

        if actions:
            data["actions"] = actions
        return data

    def _hub_create_assist(
        self, session: IntakeSession, text: str, actor: User | None
    ) -> dict:
        """Slot-Filling: Werte speichern → nächsten leeren Slot fragen → bestätigen."""
        context = dict(session.context or {})
        starting = not context.get("hub_assist_create")
        raw_text = (text or "").strip()
        if starting:
            context["hub_assist_create"] = True
            context["hub_create_draft"] = {}
            context["hub_create_ready"] = False
            context["hub_create_q"] = 0
            context["hub_create_step"] = "problem"
            session.context = context
            if CREATE_START.search(raw_text) and len(raw_text.split()) <= 10:
                first = self._slot_by_key("problem") or {}
                return self._create_chat_answer(
                    "Wir füllen den Steckbrief Schritt für Schritt — "
                    "du kannst auch mehrere Punkte in einer Antwort nennen.\n\n"
                    f"{first.get('ask') or 'Welches Problem löst der Change?'}",
                    draft={},
                    ready=False,
                    question=0,
                    step="problem",
                )

        lowered = raw_text.lower()
        if lowered in NO or lowered in {"abbrechen", "stopp", "cancel"}:
            return self._end_create_assist(
                session,
                "Alles klar, abgebrochen. Sag einfach „Change anlegen“, wenn du neu starten willst.",
            )

        draft = dict(context.get("hub_create_draft") or {})
        hard_create = (
            lowered in CREATE_CONFIRM
            or lowered.startswith("anlegen")
            or lowered.startswith("change anlegen")
            or lowered.startswith("ticket anlegen")
        )
        soft_create = lowered in YES | CREATE_SOFT_CONFIRM
        if context.get("hub_create_ready") and (hard_create or soft_create) and self._create_draft_ready(draft):
            return self._publish_hub_draft(session, draft, actor)
        if hard_create and self._create_draft_ready(draft) and self._next_create_step(draft) is None:
            return self._publish_hub_draft(session, draft, actor)

        if lowered in {"noch anpassen", "anpassen", "ändern", "aendern", "weiter ergänzen"}:
            context["hub_create_ready"] = False
            missing = self._next_create_step(draft) or "problem"
            context["hub_create_step"] = missing
            session.context = context
            ask, step = self._create_question_for(missing)
            return self._create_chat_answer(
                f"Okay — {ask}",
                draft=draft,
                ready=False,
                question=int(context.get("hub_create_q") or 0),
                step=step,
            )

        step = str(context.get("hub_create_step") or self._next_create_step(draft) or "problem")
        if self._apply_create_skip(draft, step, lowered):
            draft = self._ensure_create_draft(draft, actor)
        else:
            extracted = self._extract_create_draft(draft, raw_text, session)
            if extracted.get("abort"):
                return self._end_create_assist(session, "Alles klar, abgebrochen.")
            draft = self._ensure_create_draft(extracted.get("draft") or draft, actor)
            draft = self._heuristic_fill_create(draft, raw_text, step)
            draft = self._ensure_create_draft(draft, actor)

        just_skipped = lowered in CREATE_SKIP
        slot_meta = self._slot_by_key(step) or {"key": step}
        thin_reason = ""
        if not just_skipped:
            if self._slot_filled(draft, slot_meta):
                thin_reason = self._create_thin_reason(raw_text, step, draft) or ""
            else:
                # Antwort hat den Slot nicht gefüllt → nachfragen statt weiter
                thin_reason = (
                    "Daraus kann ich den Punkt noch nicht zuverlässig übernehmen."
                )
        if thin_reason:
            draft = self._clear_create_step(draft, step)
            q = int(context.get("hub_create_q") or 0) + 1
            context["hub_create_q"] = q
            context["hub_create_draft"] = draft
            context["hub_create_ready"] = False
            context["hub_create_step"] = step
            session.context = context
            ask, _ = self._create_question_for(step)
            reply, _enough = self._create_coach_reply(
                user_text=raw_text,
                draft=draft,
                step=step,
                next_ask=ask,
                thin_hint=thin_reason,
                force_retry=True,
            )
            return self._create_chat_answer(
                reply, draft=draft, ready=False, question=q, step=step
            )

        ask, step_id = self._create_question_for(
            self._next_create_step(draft) or "problem"
        )
        reply, enough = self._create_coach_reply(
            user_text=raw_text,
            draft=draft,
            step=step,
            next_ask=ask,
            thin_hint="",
            force_retry=False,
        )
        # Qwen sagt: Antwort reicht nicht → beim aktuellen Slot bleiben.
        if not enough:
            draft = self._clear_create_step(draft, step)
            q = int(context.get("hub_create_q") or 0) + 1
            context["hub_create_q"] = q
            context["hub_create_draft"] = draft
            context["hub_create_ready"] = False
            context["hub_create_step"] = step
            session.context = context
            return self._create_chat_answer(
                reply, draft=draft, ready=False, question=q, step=step
            )

        q = int(context.get("hub_create_q") or 0) + 1
        context["hub_create_q"] = q
        if q >= CREATE_MAX_QUESTIONS:
            draft = self._fill_remaining_create_defaults(draft, actor)
        next_step = self._next_create_step(draft)
        ready = next_step is None and self._create_draft_ready(draft)

        if ready:
            draft = self._ensure_create_draft(draft, actor)
            reply = self._create_summary_text(draft)
            context["hub_create_draft"] = draft
            context["hub_create_ready"] = True
            context["hub_create_step"] = "ready"
            session.context = context
            return self._create_chat_answer(
                reply, draft=draft, ready=True, question=q, step="ready"
            )

        ask, step_id = self._create_question_for(next_step or "problem")
        context["hub_create_draft"] = draft
        context["hub_create_ready"] = False
        context["hub_create_step"] = step_id
        session.context = context
        payload = self._create_chat_answer(
            reply, draft=draft, ready=False, question=q, step=step_id
        )
        similar = self._similar_for_draft(draft)
        if similar and step_id in {"problem", "solution_goals"}:
            payload["links"] = [
                {
                    "label": f"{item.reference}: {item.title}",
                    "url": f"/workspace/{item.id}",
                }
                for item in similar
            ]
            if "ähnlich" not in reply.lower():
                names = ", ".join(item.reference for item in similar[:2])
                payload["text"] = (
                    f"{reply.rstrip()} Ähnlich: {names} — öffnen oder weiter?"
                )
        return payload

    def _slot_by_key(self, key: str) -> dict[str, object] | None:
        for slot in CREATE_SLOTS:
            if slot.get("key") == key:
                return slot
        return None

    def _slot_filled(self, draft: dict, slot: dict[str, object]) -> bool:
        fills = slot.get("fills")
        if isinstance(fills, (tuple, list)) and fills:
            if slot.get("key") == "people":
                # Sponsor reicht; Lead wird ggf. aus Sponsor abgeleitet.
                return bool(str(draft.get("sponsor") or "").strip())
            if slot.get("key") == "schedule":
                return bool(str(draft.get("start_date") or "").strip())
            return all(str(draft.get(str(k)) or "").strip() for k in fills)
        return bool(str(draft.get(str(slot.get("key"))) or "").strip())

    def _next_create_step(self, draft: dict) -> str | None:
        for slot in CREATE_SLOTS:
            if slot.get("required") and not self._slot_filled(draft, slot):
                return str(slot["key"])
        for slot in CREATE_SLOTS:
            if not slot.get("required") and not self._slot_filled(draft, slot):
                return str(slot["key"])
        return None

    def _create_question_for(self, step: str) -> tuple[str, str]:
        slot = self._slot_by_key(step) or {}
        ask = str(slot.get("ask") or "Erzähl kurz weiter.")
        return ask, step

    def _apply_create_skip(self, draft: dict, step: str, lowered: str) -> bool:
        if lowered not in CREATE_SKIP:
            return False
        slot = self._slot_by_key(step) or {}
        default = str(slot.get("skip_default") or "").strip()
        if step == "schedule":
            from datetime import date

            draft["start_date"] = draft.get("start_date") or date.today().isoformat()
            # Ende offen → Feld weglassen (kein ungültiger Jira-String)
            if str(draft.get("end_date") or "").strip().lower() in {"", "offen", "egal"}:
                draft.pop("end_date", None)
            return True
        if step == "people":
            # Skip people → Sponsor bleibt Actor-Default in _ensure_create_draft
            if not str(draft.get("sponsor") or "").strip():
                draft["sponsor"] = "noch festzulegen"
            if not str(draft.get("change_lead") or "").strip():
                draft["change_lead"] = draft["sponsor"]
            return True
        if default:
            key = str(slot.get("key") or step)
            if key in CREATE_DRAFT_KEYS:
                draft[key] = default
            return True
        return False

    def _fill_remaining_create_defaults(self, draft: dict, actor: User | None) -> dict:
        data = dict(draft or {})
        for slot in CREATE_SLOTS:
            if self._slot_filled(data, slot):
                continue
            default = str(slot.get("skip_default") or "").strip()
            key = str(slot.get("key"))
            if key == "schedule":
                from datetime import date

                data.setdefault("start_date", date.today().isoformat())
            elif key == "people":
                if not str(data.get("sponsor") or "").strip() and actor:
                    data["sponsor"] = str(getattr(actor, "display_name", "") or "").strip()
                if not str(data.get("change_lead") or "").strip():
                    data["change_lead"] = str(data.get("sponsor") or "noch festzulegen")
            elif default and key in CREATE_DRAFT_KEYS:
                data[key] = default
            elif key == "benefit_savings" and str(data.get("solution_goals") or "").strip():
                data["benefit_savings"] = (
                    f"Nutzen aus der Lösung: {str(data['solution_goals'])[:160]}"
                )
            elif key == "benefit_risk" and str(data.get("problem") or "").strip():
                data["benefit_risk"] = (
                    "Risiken aus dem beschriebenen Problem werden reduziert."
                )
        return self._ensure_create_draft(data, actor)

    def _create_ack(self, draft: dict, answered_step: str) -> str:
        if answered_step == "problem":
            problem = str(draft.get("problem") or "").strip()
            title = str(draft.get("title") or "").strip()
            if problem:
                short = " ".join(problem.split())[:120]
                return f"Verstehe — heute scheitert es an: {short}."
            return f"Verstanden — „{title}“." if title else "Verstanden."
        if answered_step == "solution_goals":
            goals = str(draft.get("solution_goals") or "").strip()
            if goals:
                short = " ".join(goals.split())[:120]
                return f"Lösung notiert: {short}."
            return "Lösung notiert."
        if answered_step == "benefit_savings":
            benefit = str(draft.get("benefit_savings") or "").strip()
            if benefit:
                short = " ".join(benefit.split())[:120]
                return f"Nutzen klar: {short}."
            return "Nutzen notiert."
        if answered_step == "risks_obstacles":
            risks = str(draft.get("risks_obstacles") or "").strip()
            if risks:
                short = " ".join(risks.split())[:120]
                return f"Risiken mitgedacht: {short}."
            return "Risiken notiert."
        if answered_step == "schedule":
            start = str(draft.get("start_date") or "").strip()
            end = str(draft.get("end_date") or "").strip()
            if start and end:
                return f"Zeitfenster: {start} bis {end}."
            return f"Zeitfenster: {start}." if start else "Okay."
        if answered_step == "people":
            who = str(draft.get("sponsor") or "").strip()
            lead = str(draft.get("change_lead") or "").strip()
            if who and lead and lead.lower() != who.lower():
                return f"Auftrag: {who}, Führung: {lead}."
            return f"Auftrag: {who}." if who else "Okay."
        return "Notiert."

    def _clear_create_step(self, draft: dict, step: str) -> dict:
        data = dict(draft or {})
        slot = self._slot_by_key(step) or {}
        fills = slot.get("fills")
        keys: list[str]
        if isinstance(fills, (tuple, list)) and fills:
            keys = [str(k) for k in fills]
        else:
            keys = [str(slot.get("key") or step)]
        for key in keys:
            data.pop(key, None)
        if step == "problem":
            # Titel/Beschreibung oft aus dünnem Problem abgeleitet
            if not str(data.get("solution_goals") or "").strip():
                data.pop("title", None)
                data.pop("description", None)
        return data

    def _create_thin_reason(self, text: str, step: str, draft: dict) -> str | None:
        """None = ausreichend; sonst Hinweis, was fehlt."""
        clean = " ".join((text or "").split()).strip()
        low = clean.lower()
        if not clean:
            return "Die Antwort ist leer."
        if low in CREATE_SKIP | CREATE_CONFIRM | YES | NO | CREATE_SOFT_CONFIRM:
            return None
        slot = self._slot_by_key(step) or {}
        for label, prompt in slot.get("chips") or ():
            if low in {
                str(prompt).strip().lower(),
                str(label).strip().lower(),
            }:
                return None
        words = clean.split()
        depth_steps = {
            "problem",
            "solution_goals",
            "benefit_savings",
            "risks_obstacles",
            "benefit_risk",
        }
        vague = {
            "irgendwas",
            "etwas",
            "dings",
            "bla",
            "test",
            "xyz",
            "keine ahnung",
            "weiß nicht",
            "weiss nicht",
            "normal",
            "standard",
            "wie immer",
            "eben",
            "halt",
            "so",
            "ja irgendwie",
        }
        if low in vague or (
            len(words) <= 2
            and low in {"problem", "lösung", "nutzen", "risiko", "risiken"}
        ):
            return "Die Antwort ist zu unspezifisch."
        if step in depth_steps:
            value = str(draft.get(step) or clean).strip()
            vwords = value.split()
            hints = {
                "problem": (
                    "Was genau läuft heute schief — für wen, und mit welchem Effekt?"
                ),
                "solution_goals": (
                    "Welche konkrete Lösung — und woran merkt man den Erfolg?"
                ),
                "benefit_savings": "Welcher Nutzen in Zeit, Geld oder Qualität?",
                "risks_obstacles": "Was kann konkret scheitern oder blockieren?",
                "benefit_risk": "Welches Risiko sinkt dadurch klar?",
            }
            if len(vwords) < 4:
                return hints.get(step, "Bitte etwas konkreter.")
            if len(vwords) <= 4 and not re.search(
                r"\b(weil|dadurch|aktuell|heute|wenn|ohne|mit|für|soll|"
                r"müssen|kann|nicht|zu|wird|ist|sind)\b",
                value,
                re.IGNORECASE,
            ):
                return "Mir fehlt noch der konkrete Bezug — Situation und Wirkung."
        if step == "people":
            if not str(draft.get("sponsor") or "").strip():
                return "Wer beauftragt den Change — Name oder Rolle?"
        if step == "schedule":
            if not str(draft.get("start_date") or "").strip():
                return "Wann ungefähr starten — Monat, Quartal oder Datum?"
        return None

    def _create_coach_reply(
        self,
        *,
        user_text: str,
        draft: dict,
        step: str,
        next_ask: str,
        thin_hint: str,
        force_retry: bool,
    ) -> tuple[str, bool]:
        """Antworttext + whether enough (True = Slot ok, weiter)."""
        fallback_ack = self._create_ack(draft, step) if not force_retry else ""
        if force_retry:
            fallback = (
                f"{thin_hint} Das reicht noch nicht. {next_ask}"
                if thin_hint
                else f"Das reicht noch nicht an Information. {next_ask}"
            )
            fallback_enough = False
        else:
            fallback = f"{fallback_ack} {next_ask}".strip() if fallback_ack else next_ask
            fallback_enough = True

        name = str(getattr(self.provider, "name", "") or "").lower()
        if (
            not self.provider
            or name in SKIP_LLM
            or name.startswith("scripted")
            or not hasattr(self.provider, "complete_text")
        ):
            return fallback, fallback_enough

        slot = self._slot_by_key(step) or {}
        label = str(slot.get("label") or step)
        mode = (
            "Die Antwort reicht NICHT. Bleibe beim gleichen Slot, "
            "sage klar was fehlt, stelle eine gezielte Nachfrage. enough muss false sein."
            if force_retry
            else (
                "Prüfe streng: nur bei ausreichendem Inhalt enough=true und nächste Frage; "
                "sonst enough=false und Nachfrage zum gleichen Slot."
            )
        )
        user_block = (
            f"Aktueller Slot: {label} ({step})\n"
            f"{mode}\n"
            f"Hinweis Qualität: {thin_hint or 'ok'}\n"
            f"Nächste Frage (wenn enough): {next_ask}\n"
            f"Entwurf: {json.dumps({k: draft.get(k) for k in CREATE_DRAFT_KEYS if draft.get(k)}, ensure_ascii=False)}\n"
            f"Nutzer gerade: {user_text}"
        )
        try:
            raw = str(
                self.provider.complete_text(HUB_CREATE_COACH, user_block) or ""
            ).strip()
        except (LlmUnavailable, TypeError, ValueError):
            return fallback, fallback_enough
        parsed = self._parse_create_payload(raw) or {}
        reply = str(parsed.get("reply") or "").strip()
        if not reply:
            reply = raw.strip().strip('"')
        if not reply or len(reply) < 8 or reply.lstrip().startswith("{"):
            return fallback, fallback_enough
        if force_retry:
            return reply[:600], False
        raw_enough = parsed.get("enough")
        if isinstance(raw_enough, str):
            enough = raw_enough.strip().lower() in {"1", "true", "yes", "ja"}
        elif raw_enough is None:
            enough = True
        else:
            enough = bool(raw_enough)
        return reply[:600], enough

    def _extract_create_draft(self, draft: dict, text: str, session: IntakeSession) -> dict:
        name = str(getattr(self.provider, "name", "") or "").lower()
        if (
            not self.provider
            or name in SKIP_LLM
            or name.startswith("scripted")
            or not hasattr(self.provider, "complete_text")
        ):
            return {"draft": draft, "abort": False}
        user_block = (
            "Extrahiere alle erkennbaren Steckbrief-Felder. "
            "Bestehende Werte behalten, außer der Nutzer korrigiert sie klar. "
            "Leere Strings weglassen.\n\n"
            f"Bisheriger Entwurf:\n{json.dumps(draft, ensure_ascii=False)}\n\n"
            f"Nutzer: {text}"
        )
        try:
            raw = str(
                self.provider.complete_text(HUB_CREATE_EXTRACT, user_block) or ""
            ).strip()
        except (LlmUnavailable, TypeError, ValueError):
            return {"draft": draft, "abort": False}
        parsed = self._parse_create_payload(raw)
        if not parsed:
            return {"draft": draft, "abort": False}
        if parsed.get("abort"):
            return {"draft": draft, "abort": True}
        merged = {
            **draft,
            **{
                k: v
                for k, v in (parsed.get("draft") or {}).items()
                if k in CREATE_DRAFT_KEYS and str(v or "").strip()
            },
        }
        return {"draft": merged, "abort": False}

    def _heuristic_fill_create(self, draft: dict, text: str, step: str) -> dict:
        data = dict(draft or {})
        clean = " ".join((text or "").split()).strip()
        if not clean:
            return data
        low = clean.lower()
        if low in CREATE_CONFIRM | YES | NO:
            return data
        slot = self._slot_by_key(step) or {}
        if step == "people":
            # „A / B“ oder „A und B“
            parts = re.split(r"\s*(?:/|,| und | & )\s*", clean, maxsplit=1)
            if parts:
                data["sponsor"] = parts[0][:120]
                data["change_lead"] = (parts[1] if len(parts) > 1 else parts[0])[:120]
            return data
        if step == "schedule":
            from datetime import date

            from app.domain.dates import parse_german_date, parse_german_period

            start, end = parse_german_period(clean)
            if not start:
                start = parse_german_date(clean)
            if low in CREATE_SKIP or (not start and any(w in low for w in ("bald", "asap", "schnell"))):
                start = date.today().isoformat()
            if start:
                data["start_date"] = start
            if end:
                data["end_date"] = end
            elif len(re.split(r"\s*(?:/|,| bis | – | - )\s*", clean, maxsplit=1)) > 1:
                # Freitext-Ende nur wenn parsebar
                pass
            return data
        key = str(slot.get("key") or step)
        if key in CREATE_DRAFT_KEYS:
            data[key] = clean[:500]
        return data

    def _create_draft_ready(self, draft: dict) -> bool:
        required_ok = all(
            self._slot_filled(draft, slot)
            for slot in CREATE_SLOTS
            if slot.get("required")
        )
        title = str(draft.get("title") or "").strip()
        body = str(draft.get("description") or "").strip() or str(draft.get("problem") or "").strip()
        return bool(required_ok and title and body)

    def _ensure_create_draft(self, draft: dict, actor: User | None) -> dict:
        data = dict(draft or {})
        problem = str(data.get("problem") or "").strip()
        goals = str(data.get("solution_goals") or "").strip()
        benefit = str(data.get("benefit_savings") or "").strip()
        risks = str(data.get("risks_obstacles") or "").strip()
        description = str(data.get("description") or "").strip()
        title = str(data.get("title") or "").strip()
        if not description:
            bits = [b for b in (problem, goals, benefit, risks) if b]
            if bits:
                data["description"] = "\n\n".join(bits)
        if not title:
            seed = problem or description or goals
            if seed:
                data["title"] = " ".join(seed.split())[:80]
        if actor and not str(data.get("sponsor") or "").strip():
            name_actor = str(getattr(actor, "display_name", "") or "").strip()
            if name_actor:
                data["sponsor"] = name_actor
        if str(data.get("sponsor") or "").strip() and not str(data.get("change_lead") or "").strip():
            data["change_lead"] = str(data.get("sponsor") or "").strip()
        if not str(data.get("help_needed") or "").strip():
            # erst setzen, wenn Slot übersprungen/Default — nicht vorzeitig
            pass
        return data

    def _create_summary_text(self, draft: dict) -> str:
        title = str(draft.get("title") or "Change").strip()
        lines = []
        for key, label in (
            ("problem", "Problem"),
            ("solution_goals", "Lösung"),
            ("benefit_savings", "Nutzen"),
            ("risks_obstacles", "Risiken"),
            ("sponsor", "Auftrag"),
            ("change_lead", "Lead"),
            ("start_date", "Start"),
            ("end_date", "Ende"),
            ("components", "Tags"),
            ("current_status", "Stand"),
            ("help_needed", "Unterstützung"),
        ):
            val = str(draft.get(key) or "").strip()
            if val:
                lines.append(f"• {label}: {val}")
        body = "\n".join(lines[:10]) if lines else str(draft.get("description") or "").strip()
        return (
            f"Steckbrief „{title}“ — so würde ich anlegen:\n{body}\n\n"
            "Passt das? Dann Change anlegen — oder sag, was noch anders soll."
        ).strip()

    def _similar_for_draft(self, draft: dict) -> list:
        needle = " ".join(
            str(draft.get(k) or "").strip()
            for k in ("title", "description", "problem")
            if str(draft.get(k) or "").strip()
        )
        if len(needle) < 12:
            return []
        return find_similar(self.db, needle, limit=3, min_score=0.42)

    def _create_progress(self, draft: dict | None, question: int = 0) -> list[dict]:
        data = draft or {}
        rows = []
        for slot in CREATE_SLOTS:
            key = str(slot["key"])
            label = str(slot["label"])
            done = self._slot_filled(data, slot)
            preview = ""
            fills = slot.get("fills")
            if isinstance(fills, (tuple, list)) and fills:
                preview = " / ".join(
                    str(data.get(str(k)) or "").strip() for k in fills if str(data.get(str(k)) or "").strip()
                )[:80]
            else:
                preview = str(data.get(key) or "").strip()[:80]
            rows.append({"key": key, "label": label, "done": done, "value": preview})
        return rows

    def _create_chat_answer(
        self,
        text: str,
        *,
        draft: dict,
        ready: bool,
        question: int = 0,
        step: str | None = None,
    ) -> dict:
        payload = self._answer(Answer(text=text))
        payload["createAssist"] = True
        payload["createReady"] = bool(ready)
        payload["createQuestion"] = int(question or 0)
        payload["createQuestionMax"] = CREATE_MAX_QUESTIONS
        payload["createStep"] = step or ""
        payload["createDraft"] = {
            key: str(draft.get(key) or "").strip()
            for key in CREATE_DRAFT_KEYS
            if str(draft.get(key) or "").strip()
        }
        payload["createProgress"] = self._create_progress(draft, question)
        if ready:
            payload["actions"] = [
                {"id": "create", "label": "Change anlegen", "prompt": "Change anlegen"},
                {"id": "edit", "label": "Noch anpassen", "prompt": "Noch anpassen"},
                {"id": "cancel", "label": "Abbrechen", "prompt": "Abbrechen"},
            ]
        else:
            slot = self._slot_by_key(step or "") or {}
            chips = slot.get("chips") or ()
            actions = []
            for label, prompt in chips:
                actions.append({"id": str(label), "label": str(label), "prompt": str(prompt)})
            actions.append({"id": "cancel", "label": "Abbrechen", "prompt": "Abbrechen"})
            payload["actions"] = actions
        return payload

    def _end_create_assist(self, session: IntakeSession, text: str) -> dict:
        context = dict(session.context or {})
        context.pop("hub_assist_create", None)
        context.pop("hub_create_draft", None)
        context.pop("hub_create_ready", None)
        context.pop("hub_create_q", None)
        context.pop("hub_create_step", None)
        session.context = context
        payload = self._answer(Answer(text=text))
        payload["createAssist"] = False
        payload["createReady"] = False
        payload["createDraft"] = {}
        payload["createProgress"] = []
        return payload

    def _publish_hub_draft(
        self, session: IntakeSession, draft: dict, actor: User | None
    ) -> dict:
        draft = self._ensure_create_draft(draft, actor)
        title = str(draft.get("title") or "").strip()
        description = str(draft.get("description") or "").strip()
        if not title or not description:
            return self._create_chat_answer(
                "Mir fehlt noch Titel oder Beschreibung — ergänz das kurz, dann lege ich an.",
                draft=draft,
                ready=False,
                question=int((session.context or {}).get("hub_create_q") or 0),
            )

        fields = {
            key: str(draft.get(key) or "").strip()
            for key in (
                "description",
                "sponsor",
                "change_lead",
                "start_date",
                "end_date",
                "problem",
                "solution_goals",
                "benefit_savings",
                "benefit_risk",
                "risks_obstacles",
                "similar_solution",
                "current_status",
                "components",
                "help_needed",
            )
            if str(draft.get(key) or "").strip()
        }
        ai_note = "Dieser Change wurde mit KI aufgewertet."
        desc = str(fields.get("description") or description or "").strip()
        if "mit ki aufgewertet" not in desc.lower() and "mithilfe von ki" not in desc.lower():
            fields["description"] = f"{desc}\n\n{ai_note}".strip() if desc else ai_note
        if actor and not fields.get("sponsor"):
            name_actor = str(getattr(actor, "display_name", "") or "").strip()
            if name_actor:
                fields["sponsor"] = name_actor

        try:
            created = self.intake.publish_ticket(
                title=title,
                kind="change_request",
                priority="medium",
                fields=fields,
                user=actor,
                wait_for_sync=True,
            )
        except Exception as err:  # noqa: BLE001 — Nutzerfreundliche Chat-Antwort
            log.exception("hub create failed")
            return self._create_chat_answer(
                f"Anlegen hat nicht geklappt ({err}). Versuch es nochmal oder kürz die Angaben.",
                draft=draft,
                ready=True,
                question=int((session.context or {}).get("hub_create_q") or 0),
            )

        context = dict(session.context or {})
        context.pop("hub_assist_create", None)
        context.pop("hub_create_draft", None)
        context.pop("hub_create_ready", None)
        context.pop("hub_create_q", None)
        context.pop("hub_create_step", None)
        session.context = context
        jira_key = str(created.get("jiraKey") or created.get("externalKey") or "").strip()
        local_ref = str(created.get("reference") or created.get("ticketKey") or "Change").strip()
        ref = jira_key or local_ref
        sync_state = str(created.get("syncState") or "").strip().lower()
        sync_err = str(created.get("syncError") or "").strip()
        gaps = []
        for label in created.get("missingFields") or []:
            if label:
                gaps.append(str(label))
        for q in created.get("openQuestions") or []:
            text_q = q if isinstance(q, str) else (q.get("question") or q.get("label") or "")
            if text_q and text_q not in gaps:
                gaps.append(str(text_q))
        if not gaps and created.get("requestId"):
            request = svc.get_request(self.db, created["requestId"])
            if request:
                gaps = list(svc._missing_labels(request) or [])
        gap_line = ""
        if gaps:
            shown = ", ".join(gaps[:5])
            more = f" (+{len(gaps) - 5})" if len(gaps) > 5 else ""
            gap_line = f" Noch offen im Steckbrief: {shown}{more}."
        if jira_key:
            created["text"] = (
                f"{jira_key} ist in Jira angelegt. Ich öffne den Steckbrief — "
                f"die wichtigsten Infos sind schon drin.{gap_line}"
            )
        elif sync_state in {"dead", "failed"} and sync_err:
            created["text"] = (
                f"{local_ref} ist lokal angelegt, der Jira-Sync ist fehlgeschlagen "
                f"({sync_err}). Ich öffne den Steckbrief.{gap_line}"
            )
        else:
            created["text"] = (
                f"{local_ref} ist angelegt, die Jira-Nummer folgt gleich. "
                f"Ich öffne den Steckbrief.{gap_line}"
            )
        created["gaps"] = gaps
        created["highlightGaps"] = True
        if not created.get("links") and created.get("url"):
            created["links"] = [{"label": ref, "url": created["url"]}]
        created["createAssist"] = False
        created["createReady"] = False
        created["createDraft"] = {}
        created["createProgress"] = []
        return created

    def _parse_create_payload(self, raw: str) -> dict | None:
        text = (raw or "").strip()
        if not text:
            return None
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
        match = CREATE_JSON.search(text)
        if not match:
            return {"reply": text, "draft": {}, "ready": False, "create": False}
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {"reply": text, "draft": {}, "ready": False, "create": False}
        return data if isinstance(data, dict) else None

    def _hub_chat(self, session: IntakeSession, text: str, actor: User | None) -> dict:
        """Freier Chat im Hub über das konfigurierte LLM (z. B. Qwen)."""
        name = str(getattr(self.provider, "name", "") or "").lower()
        if (
            not self.provider
            or name in SKIP_LLM
            or name.startswith("scripted")
            or not hasattr(self.provider, "complete_text")
        ):
            return self._answer(
                Answer(
                    text=(
                        "KI ist gerade nicht konfiguriert. "
                        "Frag nach offenen Tickets oder einer Referenz — "
                        "oder prüfe LLM in den Einstellungen."
                    )
                )
            )
        user_block = (
            f"Workspace-Kontext:\n{self._hub_context(actor)}\n\n"
            f"Verlauf:\n{self._hub_history(session)}\n\n"
            f"Nutzer: {text}"
        )
        try:
            reply = str(self.provider.complete_text(HUB_SYSTEM, user_block) or "").strip()
        except (LlmUnavailable, TypeError, ValueError) as err:
            return self._answer(
                Answer(
                    text=f"KI gerade nicht erreichbar ({err}). Versuch es gleich nochmal."
                )
            )
        if not reply:
            return self._answer(Answer(text="Keine Antwort vom Modell."))
        payload = self._answer(Answer(text=reply))
        # Kurze Folgeoptionen, wenn das Modell keine klare Aktion nahelegt.
        lowered = reply.lower()
        if "?" in reply or "unklar" in lowered or "meinst du" in lowered:
            payload["actions"] = [dict(item) for item in HUB_CLARIFY_ACTIONS]
        return payload

    def _hub_chat_stream(self, session: IntakeSession, text: str, actor: User | None):
        name = str(getattr(self.provider, "name", "") or "").lower()
        if (
            not self.provider
            or name in SKIP_LLM
            or name.startswith("scripted")
        ):
            raise LlmUnavailable("kein LLM konfiguriert")
        user_block = (
            f"Workspace-Kontext:\n{self._hub_context(actor)}\n\n"
            f"Verlauf:\n{self._hub_history(session)}\n\n"
            f"Nutzer: {text}"
        )
        stream_fn = getattr(self.provider, "stream_text", None)
        if callable(stream_fn):
            yield from stream_fn(HUB_SYSTEM, user_block)
            return
        # Fallback: einmalige Antwort als ein Chunk
        yield str(self.provider.complete_text(HUB_SYSTEM, user_block) or "")

    def hub_history_payload(self, session: IntakeSession) -> dict:
        rows = [
            {"role": m.role, "text": m.content}
            for m in (session.messages or [])
            if (m.content or "").strip() and m.role in {"user", "assistant"}
        ]
        return {"sessionId": session.id, "messages": rows}

    def list_hub_chats(self, actor: User | None, limit: int = 8) -> list[dict]:
        if not actor:
            return []
        sessions = self.db.scalars(
            select(IntakeSession)
            .where(IntakeSession.user_id == actor.id)
            .order_by(IntakeSession.updated_at.desc())
            .limit(40)
        ).all()
        out: list[dict] = []
        for session in sessions:
            ctx = session.context or {}
            client = ctx.get("client") or {}
            if not (ctx.get("hub_chat") or client.get("mode") == "hub"):
                continue
            msgs = [m for m in (session.messages or []) if (m.content or "").strip()]
            if not msgs:
                continue
            preview = next(
                (m.content for m in reversed(msgs) if m.role == "user"),
                msgs[-1].content,
            )
            out.append(
                {
                    "sessionId": session.id,
                    "preview": str(preview or "")[:120],
                    "updatedAt": session.updated_at.isoformat()
                    if session.updated_at
                    else None,
                    "messages": len(msgs),
                }
            )
            if len(out) >= limit:
                break
        return out

    def _hub_history(self, session: IntakeSession) -> str:
        rows = [m for m in (session.messages or []) if (m.content or "").strip()][-10:]
        if not rows:
            return "—"
        return "\n".join(f"{m.role}: {m.content}" for m in rows)

    def _hub_context(self, actor: User | None) -> str:
        counts = svc.status_counts(self.db)
        lines = [f"Statuszahlen: {counts}"]
        filt = svc.RequestFilter(sort="attention", limit=8)
        result = svc.list_requests(self.db, filt)
        items = result.get("items") or []
        if actor:
            name = str(getattr(actor, "display_name", "") or "").strip()
            if name:
                lines.append(f"Aktueller Nutzer: {name}")
        if not items:
            lines.append("Keine Tickets in der Liste.")
            return "\n".join(lines)
        lines.append("Aktuelle Changes (Kurz):")
        for item in items[:8]:
            ref = item.get("reference") or item.get("id")
            title = item.get("title") or "—"
            status = item.get("statusLabel") or item.get("status") or ""
            waiting = item.get("nextStep") or item.get("waitingTodo") or ""
            bit = f"- {ref}: {title} [{status}]"
            if waiting:
                bit += f" — {waiting}"
            lines.append(bit)
        return "\n".join(lines)

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
                payload = self._answer(answers.clarify_target_answer())
                payload["actions"] = [
                    {
                        "id": "open",
                        "label": "Offene Changes",
                        "prompt": "Welche Changes sind offen?",
                    },
                    {
                        "id": "inbox",
                        "label": "Was wartet auf mich?",
                        "prompt": "Was wartet gerade auf mich?",
                    },
                ]
                return payload
            payload = self._answer(answers.clarify_filter_answer())
            payload["actions"] = [dict(item) for item in HUB_CLARIFY_ACTIONS]
            return payload
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
            return self._dispatch_query(session, intent, actor)
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

    def _dispatch_query(self, session: IntakeSession, query: Query, actor: User | None = None) -> dict:
        if query.reference:
            request = self._by_reference(query.reference)
            if not request:
                return self._answer(answers.unknown_reference_answer(query.reference))
            return self._navigate_to(session, request)

        if query.waiting_on_me:
            result = svc.list_requests(
                self.db,
                svc.RequestFilter(sort="attention", limit=40),
                actor=actor,
            )
            items = [
                item
                for item in (result.get("items") or [])
                if item.get("waitingOnMe")
            ]
            filtered = {
                **result,
                "items": items[:LIST_LIMIT],
                "total": len(items),
            }
            if not items:
                payload = self._answer(
                    Answer(text="Gerade wartet nichts explizit auf dich.")
                )
            else:
                payload = self._answer(answers.list_answer(filtered, "was auf dich wartet"))
            payload["hubView"] = "inbox"
            return payload

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
            actor=actor,
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
        hub_mode = str(((session.context or {}).get("client") or {}).get("mode") or "") == "hub"

        if action.comment:
            if hub_mode:
                return self._ask_write_confirm(
                    session,
                    kind="comment",
                    request=request,
                    payload={"comment": action.comment},
                    text=(
                        f"Kommentar an {request.reference}: „{action.comment}“. "
                        "Soll ich speichern? Antworte mit ja."
                    ),
                )
            svc.add_comment(self.db, request, action.comment, actor)
            return {
                "type": "action",
                "text": f"Kommentar an {request.reference} geschrieben. Jira-Sync läuft.",
                "links": [{"label": request.reference, "url": f"/workspace/{request.id}"}],
            }

        if action.status_note:
            rag = action.overall_rag or "green"
            rag_label = {"green": "grün", "yellow": "gelb", "red": "rot"}.get(rag, rag)
            if hub_mode:
                return self._ask_write_confirm(
                    session,
                    kind="status_note",
                    request=request,
                    payload={
                        "summary": action.status_note,
                        "overallRag": rag,
                        "risks": action.status_note if rag in {"yellow", "red"} else None,
                    },
                    text=(
                        f"Stand für {request.reference} ({rag_label}): „{action.status_note}“. "
                        "Soll ich speichern? Antworte mit ja."
                    ),
                )
            svc.create_status_update(
                self.db,
                request,
                {
                    "summary": action.status_note,
                    "reportedOn": date.today().isoformat(),
                    "overallRag": rag,
                    "risks": action.status_note if rag in {"yellow", "red"} else None,
                },
            )
            return {
                "type": "action",
                "text": f"Status von {request.reference} gespeichert.",
                "links": [{"label": request.reference, "url": f"/workspace/{request.id}"}],
            }

        if action.status and action.status in CONFIRM_STATUSES:
            context = dict(session.context or {})
            context["pending"] = {
                "kind": "status",
                "requestId": request.id,
                "status": action.status.value,
            }
            session.context = context
            self.db.flush()
            return {
                "type": "confirm_action",
                "text": (
                    f"Soll ich {request.reference} auf "
                    f"{STATUS_LABELS[action.status]} setzen? Antworte mit ja."
                ),
                "actions": [
                    {"id": "yes", "label": "Ja", "prompt": "ja"},
                    {"id": "no", "label": "Nein", "prompt": "nein"},
                ],
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

    def _ask_write_confirm(
        self,
        session: IntakeSession,
        *,
        kind: str,
        request: Request,
        payload: dict,
        text: str,
    ) -> dict:
        context = dict(session.context or {})
        context["pending"] = {
            "kind": kind,
            "requestId": request.id,
            "payload": payload,
        }
        session.context = context
        self.db.flush()
        return {
            "type": "confirm_action",
            "text": text,
            "links": [{"label": request.reference, "url": f"/workspace/{request.id}"}],
            "actions": [
                {"id": "yes", "label": "Ja, speichern", "prompt": "ja"},
                {"id": "no", "label": "Nein", "prompt": "nein"},
            ],
        }

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

    def _resolve_pending(self, session: IntakeSession, text: str, pending: dict, actor: User | None = None) -> dict | None:
        answer = text.strip().lower().rstrip("!.")
        context = dict(session.context or {})
        kind = str(pending.get("kind") or "status")
        if answer in YES:
            context.pop("pending", None)
            session.context = context
            request = svc.get_request(self.db, pending.get("requestId", ""))
            if not request:
                return self._answer(Answer(text="Das Anliegen gibt es nicht mehr."))
            if kind == "comment":
                body = str((pending.get("payload") or {}).get("comment") or "").strip()
                if not body:
                    return self._answer(Answer(text="Kein Kommentar-Text."))
                svc.add_comment(self.db, request, body, actor)
                return {
                    "type": "action",
                    "text": f"Kommentar an {request.reference} geschrieben.",
                    "links": [{"label": request.reference, "url": f"/workspace/{request.id}"}],
                }
            if kind == "status_note":
                payload = dict(pending.get("payload") or {})
                payload.setdefault("reportedOn", date.today().isoformat())
                svc.create_status_update(self.db, request, payload)
                return {
                    "type": "action",
                    "text": f"Stand von {request.reference} gespeichert.",
                    "links": [{"label": request.reference, "url": f"/workspace/{request.id}"}],
                }
            return self._apply_status(request, RequestStatus(pending["status"]))
        if answer in NO:
            context.pop("pending", None)
            session.context = context
            return self._answer(Answer(text="Gut, ich lasse alles wie es ist."))
        # Unklare Antwort: Pending behalten bei Hub-Schreibbestätigung
        if kind in {"status_note", "comment"}:
            return self._answer(
                Answer(text="Bitte mit ja oder nein bestätigen — oder formuliere neu.")
            )
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
                payload = self._dispatch_query(session, again, actor)
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
        from app.models import utcnow

        session.updated_at = utcnow()
        self.db.flush()
