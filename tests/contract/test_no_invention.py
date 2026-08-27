"""Im Steckbrief steht nur, was der Nutzer gesagt hat."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests.support import say

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
def api(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "invention.db"
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
        f"sqlite:///{db_path}", future=True, connect_args={"check_same_thread": False}
    )
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    Base.metadata.create_all(bind=engine)
    dbmod.engine = engine
    dbmod.SessionLocal = Session

    from app.main import app
    from app.ports import get_ticket_port

    get_ticket_port.cache_clear()
    yield TestClient(app)
    get_settings.cache_clear()
    get_ticket_port.cache_clear()


def talk(client, sid: str, text: str) -> dict:
    response = client.post(f"/api/sessions/{sid}/message", json={"text": text})
    assert response.status_code == 200, response.text
    return response.json()


def new_session(client) -> str:
    return client.post("/api/sessions").json()["sessionId"]


def test_no_idea_is_no_value(api):
    sid = new_session(api)
    body = talk(api, sid, "Urlaubsanträge sollen digital laufen")
    assert body["type"] == "summary"
    values = body["fields"]
    assert "keine Ahnung" not in " ".join(str(v) for v in values.values())
    assert values.get("Auftraggeber") == "Justin"


def test_an_answer_lands_as_the_listed_value(api):
    sid = new_session(api)
    body = talk(api, sid, "Urlaubsanträge sollen digital laufen, Gesellschaft SIT")
    assert body["type"] == "summary"


def test_a_negated_choice_does_not_fill_the_field(api):
    sid = new_session(api)
    body = talk(
        api,
        sid,
        "Urlaubsanträge sollen digital laufen, nicht für CIT sondern für SIT",
    )
    assert body["type"] == "summary"
