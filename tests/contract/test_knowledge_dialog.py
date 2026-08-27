"""Der Chat nutzt geloeste Faelle als Hinweis, nicht als Extra-Fragen."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Request
from tests.support import COLLAB_KEYS, DIALOG_KEYS, say

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
    "benefit_risk": "Keine verlorenen Anträge",    "problem": (
        "Urlaubsanträge laufen über ein Papierformular mit zwei Unterschriften. "
        "Anträge gehen verloren, und niemand sieht den aktuellen Stand."
    ),
    "solution_goals": (
        "Ein digitales Formular mit zweistufiger Freigabe durch Führungskraft und Personal. "
        "Der Resturlaub kommt aus dem Personalsystem, die Excel-Datei entfällt. "
        "Der Betriebsrat wird vor der Einführung eingebunden."
    ),
    "risks_obstacles": "keine",
    "similar_solution": "Kein vergleichbares Formular im Einsatz",
}


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "knowledge.db"
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
    yield TestClient(app), Session
    get_settings.cache_clear()
    get_ticket_port.cache_clear()


def talk(client, sid: str, text: str) -> dict:
    response = client.post(f"/api/sessions/{sid}/message", json={"text": text})
    assert response.status_code == 200, response.text
    return response.json()


def new_session(client) -> str:
    return client.post("/api/sessions").json()["sessionId"]


FIRST = "Urlaubsanträge digitalisieren statt Papierformular"


def test_short_problem_finds_the_case_and_starts_asking(client):
    api, _ = client
    sid = new_session(api)

    first = talk(api, sid, FIRST)

    assert first["type"] == "summary"
    assert first["draft"]["kind"] == "change_request"
    assert first["draft"]["service"] == "prozess"

    hint = first["solutionHints"][0]
    assert hint["id"] == "KB-0007"
    assert "Digitales Formular" in hint["solution"]
    assert "Auftraggeber" in hint["needs"]


def test_questions_are_only_dialog_gaps(client):
    api, _ = client
    sid = new_session(api)

    keys = []
    body = talk(api, sid, FIRST)
    while body["type"] == "question":
        keys.append(body["fieldKey"])
        body = talk(api, sid, say(GAPS, body["fieldKey"], "keine Ahnung"))

    assert set(keys) <= DIALOG_KEYS | COLLAB_KEYS | {"clarify"}
    assert "target_group" not in keys
    assert "current_workaround" not in keys
    assert "concept_scs_pt" not in keys
    assert body["type"] == "summary"
    assert "Urlaubsanträge" in body["draft"]["values"].get("similar_solution", "")
    similar = body["draft"]["values"].get("similar_solution", "")
    assert "KB-0007" in similar
    assert "Erwartete Widerstände" not in similar


def test_priority_comes_from_the_case_without_keyword(client):
    api, Session = client
    sid = new_session(api)

    body = talk(api, sid, FIRST)
    while body["type"] in ("question", "unclear"):
        body = talk(api, sid, say(GAPS, body.get("fieldKey"), "keine Ahnung"))

    assert body["priority"] == "medium"
    created = api.post(f"/api/sessions/{sid}/confirm").json()
    with Session() as db:
        assert db.get(Request, created["requestId"]).priority == "medium"


def test_hint_appears_once_not_on_every_turn(client):
    api, _ = client
    sid = new_session(api)

    first = talk(api, sid, FIRST)
    second = talk(api, sid, "keine Ahnung")
    assert first["solutionHints"]
    if second["type"] == "question":
        assert second["solutionHints"] == []
    else:
        assert second["type"] == "summary"


def test_unknown_topic_gets_no_invented_case(client):
    api, _ = client
    sid = new_session(api)

    body = talk(api, sid, "Der Zebrastreifen im Innenhof ist verblasst")
    assert body["solutionHints"] == []
