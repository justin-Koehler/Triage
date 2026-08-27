"""Proaktive Risikoanalyse: Warnung im Chat, Eintrag im Steckbrief."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models import Request
from tests.support import say

MERGE = (
    "Wir legen Verkauf und Einkauf zusammen. Zwei Abteilungen fusionieren, "
    "die Prozesse müssen harmonisiert werden. Auftraggeber ist Frau Berger. "
    "Zeitraum 1.3.2027 bis 1.9.2027, Gesellschaft SCS Gesamt."
)
GAPS = {
    "sponsor": "Frau Berger",
    "start_date": "1.3.2027 bis 1.9.2027",
    "company": "SCS Gesamt",
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
    db_path = tmp_path / "risks.db"
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


def merge_script() -> list[dict]:
    return [
        {
            "kind": "change_request",
            "title": "Verkauf und Einkauf zusammenlegen",
            "confidence": 0.9,
            "fields": {
                "sponsor": "Frau Berger",
                "start_date": "1.3.2027",
                "end_date": "1.9.2027",
                "company": "SCS Gesamt",
                "problem": "Zwei Abteilungen, doppelte Abläufe.",
                "solution_goals": "Eine Linie, harmonisierte Prozesse.",
                "risks_obstacles": "keine",
            },
        }
    ]


def talk(client, session_id: str, text: str) -> dict:
    response = client.post(f"/api/sessions/{session_id}/message", json={"text": text})
    assert response.status_code == 200, response.text
    return response.json()


def new_session(client) -> str:
    return client.post("/api/sessions").json()["sessionId"]


def test_merge_gets_a_risk_warning_on_the_first_turn(make_client):
    client, _ = make_client(merge_script())
    sid = new_session(client)
    body = talk(client, sid, MERGE)
    warning = body.get("riskWarning") or ""
    assert warning
    assert "Risiko" in warning
    assert body["type"] in ("question", "summary")
    if body["type"] == "question":
        assert body["fieldKey"] in {"start_date", "company", "facts", "people", "components", "roles", "value", "effort", "konto", "solution", "clarify"}


def test_merge_writes_risks_into_the_steckbrief(make_client):
    client, Session = make_client(merge_script())
    sid = new_session(client)
    body = talk(client, sid, MERGE)
    while body["type"] == "question":
        body = talk(client, sid, say(GAPS, body["fieldKey"]))
    assert body["type"] == "summary"
    assert body.get("riskWarning")
    risks = body["fields"].get("Risiken & Hindernisse") or ""
    assert "Betriebsrat" in risks or "Kultur" in risks
    assert risks.strip().lower() not in {"keine", "kein", ""}

    created = client.post(f"/api/sessions/{sid}/confirm")
    assert created.status_code == 200, created.text
    with Session() as db:
        request = db.scalar(select(Request).where(Request.id == created.json()["requestId"]))
        assert "Betriebsrat" in request.field_values().get("risks_obstacles", "") or "Kultur" in (
            request.field_values().get("risks_obstacles") or ""
        )


def test_urlaub_does_not_invent_a_cultural_risk(make_client):
    client, _ = make_client(
        [
            {
                "kind": "change_request",
                "title": "Urlaubsanträge digitalisieren",
                "confidence": 0.9,
                "fields": {"risks_obstacles": "keine"},
            }
        ]
    )
    sid = new_session(client)
    body = talk(
        client,
        sid,
        "Urlaubsanträge sollen digital laufen, der Prozess ist Papier",
    )
    assert not body.get("riskWarning")
    draft_risks = (body.get("draft") or {}).get("values", {}).get("risks_obstacles", "")
    assert "nicht genannt" not in draft_risks.lower()
    assert "nicht spezifiziert" not in draft_risks.lower()
