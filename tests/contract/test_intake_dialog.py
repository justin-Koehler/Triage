"""Dialog: Satz → Beschreibung, feldweise Rueckfragen."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models import Request
from tests.support import COLLAB_KEYS, DIALOG_KEYS, fact_keys, say

PROBLEM = (
    "Urlaubsanträge laufen über ein Papierformular mit zwei Unterschriften. "
    "Anträge gehen verloren, und niemand sieht den aktuellen Stand."
)
SOLUTION = (
    "Ein digitales Formular mit zweistufiger Freigabe durch Führungskraft und Personal. "
    "Der Resturlaub kommt aus dem Personalsystem, die Excel-Datei entfällt. "
    "Der Betriebsrat wird vor der Einführung eingebunden."
)
DESCRIPTION = (
    "Urlaubsanträge laufen über ein Papierformular mit zwei Unterschriften. "
    "Anträge gehen verloren, niemand sieht den Stand. Wir wollen ein digitales "
    "Formular mit Freigabe durch Führungskraft und Personal."
)
STORY = (
    f"{DESCRIPTION} Auftraggeber ist Frau Berger. "
    "Zeitraum 1.3.2027 bis 1.9.2027, Gesellschaft SCS Gesamt. "
    f"Problem: {PROBLEM} Lösung: {SOLUTION} "
    "Nutzen: weniger Papier, kein Verlust, sichtbarer Stand, einheitlicher Weg."
)
GAPS = {
    "sponsor": "Frau Berger",
    "approver": "Frau Berger",
    "start_date": "1.3.2027 bis 1.9.2027",
    "company": "SCS Gesamt",
    "cost_unit": "X",
    "description": DESCRIPTION,
    "effort_tshirt": "M",
    "components": "Schul-App",
    "change_lead": "A",
    "fb_owner": "B",
    "process_owner": "A",
    "stakeholder": "Personal, Führung",
    "solution_exists": "nein",
}


class ScriptedProvider:
    name = "scripted"

    def __init__(self, script: list[dict[str, Any]]) -> None:
        self.script = script
        self.calls = 0

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        index = min(self.calls, len(self.script) - 1)
        self.calls += 1
        return dict(self.script[index])


@pytest.fixture()
def make_client(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "dialog.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("LLM_PROVIDER", "none")
    monkeypatch.setenv("TICKET_PORT", "fake")
    monkeypatch.setenv("APP_ENV", "dev")

    from app.config import get_settings

    get_settings.cache_clear()

    import app.db as dbmod
    import app.models  # noqa: F401
    from app.db import Base

    engine = create_engine(
        f"sqlite:///{db_path}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    Base.metadata.create_all(bind=engine)
    dbmod.engine = engine
    dbmod.SessionLocal = Session

    from app.main import app
    from app.ports import get_ticket_port

    get_ticket_port.cache_clear()

    def factory(script: list[dict[str, Any]]):
        provider = ScriptedProvider(script)
        monkeypatch.setattr(
            "app.api.sessions.build_provider_from_runtime",
            lambda _runtime: provider,
        )
        client = TestClient(app)
        return client, Session

    yield factory

    get_settings.cache_clear()
    get_ticket_port.cache_clear()


def change_script(extra: dict | None = None) -> list[dict]:
    fields = {
        "sponsor": "Frau Berger",
        "start_date": "1.3.2027",
        "end_date": "1.9.2027",
        "company": "SCS Gesamt",
        "problem": PROBLEM,
        "solution_goals": SOLUTION,
        "benefit_savings": "Weniger Papier",
        "benefit_risk": "Keine verlorenen Anträge",        "current_status": "Idee, noch kein Steckbrief",
        "risks_obstacles": "keine",
        "similar_solution": "Kein vergleichbares Formular im Einsatz",
    }
    if extra:
        fields.update(extra)
    return [
        {
            "kind": "change_request",
            "title": "Urlaubsanträge digitalisieren",
            "confidence": 0.9,
            "fields": fields,
        }
    ]


def talk(client, session_id: str, text: str) -> dict:
    response = client.post(f"/api/sessions/{session_id}/message", json={"text": text})
    assert response.status_code == 200, response.text
    return response.json()


def new_session(client) -> str:
    return client.post("/api/sessions").json()["sessionId"]


def run_until_summary(client, sid: str, first: str) -> dict:
    body = talk(client, sid, first)
    while body["type"] == "question":
        assert body["maxQuestions"] >= 8
        body = talk(client, sid, say(GAPS, body["fieldKey"]))
    return body


def test_change_stays_within_three_questions(make_client):
    base = {"kind": "change_request", "title": "Urlaubsanträge digitalisieren", "confidence": 0.9}
    client, _ = make_client([base | {"fields": {}}])
    sid = new_session(client)

    labels = []
    keys = []
    body = talk(client, sid, "Wir wollen die Urlaubsanträge digitalisieren")
    while body["type"] == "question":
        labels.append(body["fieldLabel"])
        keys.append(body["fieldKey"])
        assert body["maxQuestions"] >= 8
        body = talk(client, sid, say(GAPS, body["fieldKey"]))

    assert body["type"] == "summary"
    facts = fact_keys(keys)
    assert len(facts) <= 28
    assert len(facts) == len(set(facts))
    assert set(facts) <= DIALOG_KEYS


def test_sap_change_becomes_it_request(make_client):
    base = {"kind": "it_request", "title": "Schnittstelle nach SAP", "confidence": 0.9}
    client, _ = make_client([base | {"fields": {}}])
    sid = new_session(client)

    asked = 0
    body = talk(client, sid, "Wir brauchen eine Schnittstelle nach SAP")
    while body["type"] == "question":
        if body["fieldKey"] not in COLLAB_KEYS:
            asked += 1
        assert body["maxQuestions"] >= 8
        assert body["draft"]["kind"] == "it_request"
        body = talk(client, sid, say(GAPS, body["fieldKey"]))

    assert asked <= 32
    assert body["type"] == "summary"
    assert body["kind"] == "it_request"


def test_rich_text_fills_problem_without_asking(make_client):
    client, _ = make_client(change_script())
    sid = new_session(client)
    body = talk(client, sid, STORY)
    keys = []
    while body["type"] == "question":
        keys.append(body["fieldKey"])
        body = talk(client, sid, say(GAPS, body["fieldKey"]))
    assert body["type"] == "summary"
    assert "problem" not in keys
    assert "benefit_savings" not in keys
    assert body["draft"]["values"]["problem"].startswith("Urlaubsanträge")
    assert body["draft"]["values"]["benefit_savings"]


def test_unmentioned_dates_are_asked_once(make_client):
    base = {"kind": "change_request", "title": "Urlaubsanträge digitalisieren", "confidence": 0.9}
    client, _ = make_client([base | {"fields": {}}])
    sid = new_session(client)
    body = talk(client, sid, "Wir wollen die Urlaubsanträge digitalisieren")
    assert body["type"] == "summary"


def test_invented_pt_does_not_land(make_client):
    client, _ = make_client(change_script({"concept_scs_pt": "5"}))
    sid = new_session(client)
    body = run_until_summary(client, sid, STORY)
    assert body["draft"]["values"].get("concept_scs_pt") in (None, "")


def test_short_sentence_never_asks_description_or_benefits(make_client):
    expanded = (
        "Urlaubsanträge sollen digitalisiert werden. Papierformulare entfallen. "
        "Freigabe und Stand sollen nachvollziehbar sein."
    )
    base = {
        "kind": "change_request",
        "title": "Urlaub digitalisieren",
        "confidence": 0.9,
        "fields": {"description": expanded, "problem": expanded, "solution_goals": expanded},
    }
    client, _ = make_client([base])
    sid = new_session(client)
    body = talk(client, sid, "Urlaub digitalisieren")
    keys = []
    while body["type"] == "question":
        keys.append(body["fieldKey"])
        assert body["fieldKey"] != "description"
        assert body["maxQuestions"] >= 8
        body = talk(client, sid, say(GAPS, body["fieldKey"]))
    assert "description" not in keys
    assert "benefit_savings" not in keys
    assert "end_date" not in keys
    assert "concept_scs_pt" not in keys
    assert set(fact_keys(keys)) <= DIALOG_KEYS
    assert len(fact_keys(keys)) <= 28
    assert body["type"] == "summary"
    assert body["draft"]["values"]["description"] == expanded


def test_ambiguous_sentence_gets_one_clarify(make_client):
    script = [
        {
            "kind": "change_request",
            "title": "SAP",
            "confidence": 0.3,
            "fields": {"description": "SAP ändern"},
            "question": "Geht es um eine Schnittstelle oder um Berechtigungen?",
        }
    ]
    client, _ = make_client(script)
    sid = new_session(client)
    body = talk(client, sid, "SAP ändern")
    assert body["type"] == "summary"


def test_idea_only_clarify_carries_an_impulse(make_client):
    story = "Es ist geplant, einen KI-Avatar im Standort Heilbronn einzuführen."
    script = [
        {
            "kind": "change_request",
            "title": "KI-Avatar Heilbronn",
            "confidence": 0.9,
            "fields": {"description": story},
        }
    ]
    client, _ = make_client(script)
    sid = new_session(client)
    body = talk(client, sid, story)
    assert body["type"] == "summary"


def test_start_range_sets_end_without_second_ask(make_client):
    base = {"kind": "change_request", "title": "Urlaubsanträge digitalisieren", "confidence": 0.9}
    client, _ = make_client([base | {"fields": {}}])
    sid = new_session(client)
    body = talk(client, sid, "Urlaub digitalisieren")
    assert body["type"] == "summary"


def test_empty_benefits_stay_visible_in_review(make_client):
    base = {"kind": "change_request", "title": "Urlaubsanträge digitalisieren", "confidence": 0.9}
    client, _ = make_client([base | {"fields": {}}])
    sid = new_session(client)
    body = run_until_summary(client, sid, STORY)
    by_key = {row["key"]: row for row in body["steckbrief"]}
    assert by_key["benefit_savings"]["fill"] == "dialog"
    assert by_key["benefit_savings"]["value"]
    assert by_key["benefit_risk"]["value"]
    assert by_key["problem"]["value"]
    assert by_key["stakeholder"]["fill"] == "dialog"
    assert "assignee" not in by_key
    assert "approver" in by_key
    assert "fb_owner" in by_key
    assert "process_owner" in by_key
    assert "effort_tshirt" not in by_key
    assert "cost_unit" in by_key
    assert not any("Einsparungen" in item for item in body["openQuestions"])


def test_summary_and_ticket_carry_german_labels_and_steckbrief(make_client):
    client, Session = make_client(change_script())
    sid = new_session(client)

    body = run_until_summary(client, sid, STORY)
    assert body["type"] == "summary"
    assert body["steckbriefName"] == "Urlaubsanträge digitalisieren"
    assert body["fields"]["Auftraggeber"] == "Frau Berger"
    assert body["fields"]["Start"] == "2027-03-01"
    assert body["fields"]["Gesellschaft"] == "SCS Gesamt"

    created = client.post(f"/api/sessions/{sid}/confirm")
    assert created.status_code == 200, created.text
    payload = created.json()
    assert payload["steckbriefName"] == body["steckbriefName"]
    assert payload["fields"]["Auftraggeber"] == "Frau Berger"
    assert payload["reference"]  # lokal AN-… oder nach Sync Jira-Key
    assert payload["kind"] == "change_request"

    with Session() as db:
        request = db.scalar(select(Request).where(Request.id == payload["requestId"]))
        assert request.change_lead
        assert request.company == "SCS Gesamt"


def test_second_request_lists_the_first_as_duplicate(make_client):
    client, _ = make_client(change_script())

    first = new_session(client)
    run_until_summary(client, first, STORY)
    assert client.post(f"/api/sessions/{first}/confirm").status_code == 200

    second = new_session(client)
    body = run_until_summary(client, second, STORY)

    duplicates = body["duplicates"]
    assert duplicates and duplicates[0]["reference"]
    assert duplicates[0]["kindLabel"] == "Change Request"


def test_override_kind_switches_and_priority_stays(make_client):
    client, _ = make_client(change_script())
    sid = new_session(client)

    body = run_until_summary(client, sid, STORY)
    assert body["kind"] == "change_request"

    to_it = client.post(f"/api/sessions/{sid}/override", json={"kind": "it_request"})
    assert to_it.status_code == 200, to_it.text
    assert to_it.json()["kind"] == "it_request"

    prio = client.post(f"/api/sessions/{sid}/override", json={"priority": "high"})
    assert prio.status_code == 200, prio.text
    assert prio.json()["kind"] == "it_request"
    assert prio.json()["priority"] == "high"


def test_missing_konto_asks_company_field(make_client):
    base = {"kind": "change_request", "title": "Urlaubsanträge digitalisieren", "confidence": 0.9}
    client, _ = make_client([base | {"fields": {}}])
    sid = new_session(client)
    body = talk(client, sid, "Wir wollen die Urlaubsanträge digitalisieren")
    assert body["type"] == "summary"


def test_field_question_beats_the_model_text(make_client):
    base = {
        "kind": "change_request",
        "title": "Urlaubsanträge digitalisieren",
        "confidence": 0.9,
        "question": "Wie dringlich ist das Problem (niedrig, mittel, hoch, kritisch)?",
        "fields": {},
    }
    client, _ = make_client([base])
    sid = new_session(client)

    body = talk(client, sid, "Wir wollen die Urlaubsanträge digitalisieren")
    assert body["type"] == "summary"
    assert "dringlich" not in (body.get("prompt") or "").lower()


def test_company_question_offers_company_suggestions(make_client):
    base = {"kind": "change_request", "title": "Urlaubsanträge digitalisieren", "confidence": 0.9}
    client, _ = make_client([base | {"fields": {}}])
    sid = new_session(client)
    body = talk(client, sid, "Wir wollen die Urlaubsanträge digitalisieren")
    assert body["type"] == "summary"


def test_first_question_is_a_single_field(make_client):
    base = {"kind": "change_request", "title": "Urlaubsanträge digitalisieren", "confidence": 0.9}
    client, _ = make_client([base | {"fields": {}}])
    sid = new_session(client)
    body = talk(client, sid, "Wir wollen die Urlaubsanträge digitalisieren")
    assert body["type"] == "summary"
