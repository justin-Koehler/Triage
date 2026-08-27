"""Steckbrief: Gruppen, keine Dubletten, Entwurfsfelder markiert."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Request
from tests.support import say


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
def client(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "steckbrief.db"
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

    provider = ScriptedProvider(
        [
            {
                "kind": "change_request",
                "title": "Urlaubsanträge digitalisieren",
                "confidence": 0.9,
                "fields": {
                    "sponsor": "Frau Berger",
                    "start_date": "1.3.2027",
                    "end_date": "1.9.2027",
                    "company": "SCS Gesamt",
                    "problem": (
                        "Urlaubsanträge laufen über ein Papierformular mit zwei Unterschriften. "
                        "Anträge gehen verloren, und niemand sieht den aktuellen Stand."
                    ),
                    "solution_goals": (
                        "Ein digitales Formular mit zweistufiger Freigabe durch Führungskraft "
                        "und Personal. Der Resturlaub kommt aus dem Personalsystem. "
                        "Der Betriebsrat wird vor der Einführung eingebunden."
                    ),
                    "benefit_savings": "Weniger Papier",
                    "benefit_risk": "Kein Verlust",                    "current_status": "Idee",
                    "risks_obstacles": "keine",
                    "similar_solution": "Kein vergleichbares Formular",
                },
            }
        ]
    )
    monkeypatch.setattr(
        "app.api.sessions.build_provider_from_runtime",
        lambda _runtime: provider,
    )
    yield TestClient(app), Session
    get_settings.cache_clear()
    get_ticket_port.cache_clear()


STORY = (
    "Urlaubsanträge laufen über ein Papierformular mit zwei Unterschriften. "
    "Anträge gehen verloren, niemand sieht den Stand. Wir wollen ein digitales "
    "Formular mit Freigabe. Auftraggeber ist Frau Berger. "
    "Zeitraum 1.3.2027 bis 1.9.2027, Gesellschaft SCS Gesamt."
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
    "benefit_risk": "Kein Verlust",    "problem": (
        "Urlaubsanträge laufen über ein Papierformular mit zwei Unterschriften. "
        "Anträge gehen verloren, und niemand sieht den aktuellen Stand."
    ),
    "solution_goals": (
        "Ein digitales Formular mit zweistufiger Freigabe durch Führungskraft und Personal. "
        "Der Resturlaub kommt aus dem Personalsystem, die Excel-Datei entfällt. "
        "Der Betriebsrat wird vor der Einführung eingebunden."
    ),
    "risks_obstacles": "keine",
    "similar_solution": "Kein vergleichbares Formular",
}


def talk(api, sid: str, text: str) -> dict:
    response = api.post(f"/api/sessions/{sid}/message", json={"text": text})
    assert response.status_code == 200, response.text
    return response.json()


def intake(api) -> tuple[str, dict]:
    sid = api.post("/api/sessions").json()["sessionId"]
    body = talk(api, sid, STORY)
    while body["type"] in ("question", "unclear"):
        body = talk(api, sid, say(GAPS, body.get("fieldKey")))
    assert body["type"] == "summary", body
    return sid, body


def test_steckbrief_has_groups_in_order(client):
    api, _ = client
    _sid, summary = intake(api)
    groups = [row["group"] for row in summary["steckbrief"] if row["group"]]
    seen = []
    for group in groups:
        if not seen or seen[-1] != group:
            seen.append(group)
    allowed = ["kopf", "uebersicht", "team", "finanzen", "kalkulation", "sonstiges"]
    assert all(g in allowed for g in seen)
    assert seen == sorted(seen, key=allowed.index)


def test_steckbrief_has_no_duplicate_keys(client):
    api, _ = client
    _sid, summary = intake(api)
    keys = [row["key"] for row in summary["steckbrief"]]
    assert len(keys) == len(set(keys))
    labels = list(summary["fields"])
    assert len(labels) == len(set(labels))


def test_dialog_and_draft_fields_are_marked(client):
    api, _ = client
    _sid, summary = intake(api)
    by_key = {row["key"]: row for row in summary["steckbrief"]}
    assert by_key["problem"]["fill"] == "draft"
    assert by_key["solution_goals"]["fill"] == "draft"
    assert by_key["description"]["fill"] == "draft"
    assert by_key["end_date"]["fill"] == "draft"
    assert by_key["sponsor"]["fill"] == "dialog"
    assert "assignee" not in by_key
    assert by_key["approver"]["fill"] == "dialog"
    assert by_key["fb_owner"]["fill"] == "dialog"
    assert by_key["process_owner"]["fill"] == "dialog"
    assert "effort_tshirt" not in by_key
    assert by_key["cost_unit"]["fill"] == "dialog"

    assert by_key["current_status"]["fill"] == "draft"
    assert "author" not in by_key
    assert "qg1" not in by_key
    assert "it_involvement" not in by_key


def test_description_is_the_report(client):
    api, Session = client
    sid, summary = intake(api)
    assert summary["fields"]["Beschreibung"] == STORY

    created = api.post(f"/api/sessions/{sid}/confirm")
    assert created.status_code == 200, created.text
    with Session() as db:
        request = db.get(Request, created.json()["requestId"])
        assert request.description == STORY
        keys = [f.key for f in request.fields]
        assert len(keys) == len(set(keys))


def test_created_ticket_shows_all_template_fields(client):
    api, _ = client
    sid, _ = intake(api)
    created = api.post(f"/api/sessions/{sid}/confirm")
    assert created.status_code == 200, created.text
    detail = api.get(f"/api/requests/{created.json()['requestId']}").json()
    keys = {field["key"] for group in detail["groups"] for field in group["fields"]}
    for key in (
        "approver",
        "fb_owner",
        "process_owner",
        "cost_unit",
        "change_lead",
    ):
        assert key in keys, key
    assert "assignee" not in keys
    by_key = {row["key"]: row for row in created.json()["steckbrief"]}
    assert "approval_state" not in by_key
    assert "approval_date" not in by_key
