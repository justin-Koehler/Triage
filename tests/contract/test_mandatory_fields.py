"""Pflichtfelder: Beschreibung, Change-Leitung SCS.

Beschreibung nur nachfragen, wenn der erste Text duenn ist.
Autor nie fragen. Change-Leitung darf im Rollen-Buendel fehlen, nicht als
eigene Maske. Keyword-Dateien und Login bleiben Fallback bei der Anlage.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Request
from tests.support import COLLAB_KEYS, say

PROBLEM = (
    "Urlaubsanträge laufen über ein Papierformular mit zwei Unterschriften. "
    "Anträge gehen verloren, und niemand sieht den aktuellen Stand."
)
SOLUTION = (
    "Ein digitales Formular mit zweistufiger Freigabe durch Führungskraft und Personal. "
    "Der Resturlaub kommt aus dem Personalsystem, die Excel-Datei entfällt. "
    "Der Betriebsrat wird vor der Einführung eingebunden."
)
STORY = (
    "Wir wollen die Urlaubsanträge digitalisieren, das ist dringend. "
    "Auftraggeber ist Frau Berger. Zeitraum 1.3.2027 bis 1.9.2027, Gesellschaft SCS Gesamt. "
    f"{PROBLEM} {SOLUTION}"
)
GAPS = {
    "sponsor": "Frau Berger",
    "start_date": "1.3.2027 bis 1.9.2027",
    "end_date": "1.9.2027",
    "company": "SCS Gesamt",
    "description": (
        "Urlaubsanträge laufen über ein Papierformular mit zwei Unterschriften. "
        "Anträge gehen verloren, niemand sieht den Stand. Wir wollen ein digitales "
        "Formular mit Freigabe durch Führungskraft und Personal."
    ),
    "current_status": "Idee, noch kein Steckbrief",
    "benefit_savings": "Weniger Papier",
    "benefit_risk": "Keine verlorenen Anträge",    "problem": PROBLEM,
    "solution_goals": SOLUTION,
    "risks_obstacles": "keine",
    "similar_solution": "Kein vergleichbares Formular im Einsatz",
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
    db_path = tmp_path / "mandatory.db"
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
        return TestClient(app), Session

    yield factory

    get_settings.cache_clear()
    get_ticket_port.cache_clear()


def change_script() -> list[dict]:
    return [
        {
            "intent": "anliegen",
            "kind": "change_request",
            "title": "Urlaubsanträge digitalisieren",
            "confidence": 0.9,
            "fields": {
                "sponsor": "Frau Berger",
                "start_date": "1.3.2027",
                "end_date": "1.9.2027",
                "company": "SCS Gesamt",
                "problem": PROBLEM,
                "solution_goals": SOLUTION,
                "benefit_savings": "Weniger Papier",
                "benefit_risk": "Kein Verlust",                "current_status": "Idee",
                "risks_obstacles": "keine",
                "similar_solution": "Kein vergleichbares Formular",
            },
        }
    ]


def talk(client, sid: str, text: str) -> dict:
    response = client.post(f"/api/sessions/{sid}/message", json={"text": text})
    assert response.status_code == 200, response.text
    return response.json()


def new_session(client) -> str:
    return client.post("/api/sessions").json()["sessionId"]


def run_intake(client, sid: str, first: str) -> tuple[dict, list[str], list[int]]:
    labels: list[str] = []
    budgets: list[int] = []
    body = talk(client, sid, first)
    while body["type"] in ("question", "unclear"):
        key = body.get("fieldKey")
        if key not in COLLAB_KEYS:
            labels.append(body.get("fieldLabel"))
            budgets.append(body.get("maxQuestions"))
        body = talk(client, sid, say(GAPS, key))
    return body, labels, budgets


def test_created_request_carries_mandatory_fields(make_client):
    client, Session = make_client(change_script())
    sid = new_session(client)

    summary, *_ = run_intake(client, sid, STORY)
    assert summary["type"] == "summary"

    created = client.post(f"/api/sessions/{sid}/confirm")
    assert created.status_code == 200, created.text
    payload = created.json()

    assert payload["fields"]["Beschreibung"].startswith("Wir wollen die Urlaubsanträge")
    assert "Autor" not in payload["fields"]
    assert payload["fields"]["Change-Leitung SCS"] == "B"
    assert payload["changeLead"] == "B"
    assert payload["priority"] == "high"

    with Session() as db:
        request = db.get(Request, payload["requestId"])
        assert request.change_lead == "B"
        assert request.description.startswith("Wir wollen die Urlaubsanträge")
        assert request.author.display_name == "Justin"


def test_mandatory_fields_are_never_asked(make_client):
    client, _ = make_client(change_script())
    sid = new_session(client)

    _summary, labels, _budgets = run_intake(client, sid, STORY)
    assert "Beschreibung" not in labels
    assert "Autor" not in labels
    assert "Change-Leitung SCS" not in labels
    assert "Verantwortlich SCS" not in labels


def test_question_budget_stays_fieldwise(make_client):
    client, _ = make_client(change_script())
    sid = new_session(client)

    summary, labels, budgets = run_intake(
        client, sid, "Wir wollen die Urlaubsanträge digitalisieren"
    )
    assert not budgets or set(budgets) <= {8, 9}
    assert len(labels) <= 28
    assert summary["type"] == "summary"


def test_confirm_blocks_missing_system_mandatory_fields(make_client):
    client, _ = make_client(
        [
            {
                "intent": "anliegen",
                "kind": "change_request",
                "title": "Urlaubsanträge digitalisieren",
                "confidence": 0.9,
                "fields": {},
            }
        ]
    )
    sid = new_session(client)

    body = talk(client, sid, "Wir wollen die Urlaubsanträge digitalisieren")
    while body["type"] in ("question", "unclear"):
        body = talk(client, sid, "Weiß ich noch nicht")
    summary = body
    assert summary["type"] == "summary"

    created = client.post(f"/api/sessions/{sid}/confirm")
    assert created.status_code == 200, created.text
    payload = created.json()
    assert payload["type"] == "created"
    assert payload["incomplete"] is True


def test_fachliches_anliegen_geht_an_b(make_client):
    client, _ = make_client(change_script())
    sid = new_session(client)

    run_intake(client, sid, STORY)
    payload = client.post(f"/api/sessions/{sid}/confirm").json()
    assert payload["fields"]["Change-Leitung SCS"] == "B"


def test_chat_filters_by_responsible(make_client):
    client, _ = make_client(change_script())
    sid = new_session(client)
    run_intake(client, sid, STORY)
    created = client.post(f"/api/sessions/{sid}/confirm").json()

    mine = talk(client, sid, "welche tickets hat B?")
    assert mine["type"] == "answer"
    assert created["reference"] in mine["text"]

    others = talk(client, sid, "welche tickets hat A?")
    assert created["reference"] not in others["text"]


def test_summary_offers_a_solved_case(make_client):
    client, _ = make_client(change_script())
    sid = new_session(client)

    summary, *_ = run_intake(
        client, sid, "Urlaubsanträge digitalisieren statt Papierformular. " + STORY
    )
    hints = summary["solutionHints"]
    assert hints and hints[0]["id"] == "KB-0007"
    assert "Digitales Formular" in hints[0]["solution"]


def test_workspace_can_correct_the_responsible(make_client):
    client, Session = make_client(change_script())
    sid = new_session(client)
    run_intake(client, sid, STORY)
    created = client.post(f"/api/sessions/{sid}/confirm").json()

    patched = client.patch(
        f"/api/requests/{created['requestId']}", json={"change_lead": "A"}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["changeLead"] == "A"

    with Session() as db:
        assert db.get(Request, created["requestId"]).change_lead == "A"
