"""Aehnliche Loesungen und Risiken: still in den Steckbrief, kein Chip-Dialog."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.types import Priority, RequestKind, RequestStatus
from app.models import Request, User
from tests.support import COLLAB_KEYS, say

STORY = (
    "Wir wollen die Urlaubsanträge digitalisieren. Auftraggeber ist Frau Berger. "
    "Zeitraum 1.3.2027 bis 1.9.2027, Gesellschaft SCS Gesamt. "
    "Urlaubsanträge laufen über ein Papierformular mit zwei Unterschriften. "
    "Anträge gehen verloren, niemand sieht den Stand. Wir wollen ein digitales "
    "Formular mit Freigabe durch Führungskraft und Personal."
)
GAPS = {
    "sponsor": "Frau Berger",
    "start_date": "1.3.2027 bis 1.9.2027",
    "company": "SCS Gesamt",
}
WEB = [
    {
        "title": "Digitale Urlaubsanträge im öffentlichen Dienst",
        "url": "https://example.org/urlaub-digital",
        "snippet": "Formulare statt Papier.",
    }
]


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
    db_path = tmp_path / "collab.db"
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
    monkeypatch.setattr("app.services.collab.web_search", lambda _q, limit=3: WEB[:limit])

    def factory(script: list[dict[str, Any]] | None = None):
        provider = ScriptedProvider(
            script
            or [
                {
                    "kind": "change_request",
                    "title": "Urlaubsanträge digitalisieren",
                    "confidence": 0.9,
                    "fields": {
                        "sponsor": "Frau Berger",
                        "start_date": "1.3.2027",
                        "end_date": "1.9.2027",
                        "company": "SCS Gesamt",
                    },
                }
            ]
        )
        monkeypatch.setattr(
            "app.api.sessions.build_provider_from_runtime",
            lambda _runtime: provider,
        )
        return TestClient(app), Session

    yield factory
    get_settings.cache_clear()
    get_ticket_port.cache_clear()


def talk(client, sid: str, text: str) -> dict:
    response = client.post(f"/api/sessions/{sid}/message", json={"text": text})
    assert response.status_code == 200, response.text
    return response.json()


def until_summary(client, sid: str, first: str) -> dict:
    body = talk(client, sid, first)
    while body["type"] == "question":
        assert body.get("fieldKey") not in COLLAB_KEYS
        assert not body.get("collab")
        body = talk(client, sid, say(GAPS, body["fieldKey"]))
    return body


def test_intake_does_not_ask_to_confirm_risks_or_similar(make_client):
    client, _ = make_client()
    sid = client.post("/api/sessions").json()["sessionId"]
    summary = until_summary(client, sid, STORY)
    assert summary["type"] == "summary"
    similar = summary["draft"]["values"].get("similar_solution") or ""
    assert "KB-0007" in similar
    assert "Erwartete Widerstände" not in similar
    assert "Excel-Datei" not in similar
    risks = summary["draft"]["values"].get("risks_obstacles") or ""
    assert "Besucher" not in risks
    assert "Ich sehe" not in str(summary)
    assert "Nichts gefunden" not in str(summary)


def test_similar_seeds_local_ticket_without_asking(make_client):
    client, Session = make_client()
    with Session() as db:
        user = User(email="fach@example.com", display_name="Fach")
        db.add(user)
        db.flush()
        db.add(
            Request(
                reference="AN-2040",
                kind=RequestKind.CHANGE_REQUEST,
                status=RequestStatus.DONE,
                priority=Priority.MEDIUM,
                title="Urlaubsanträge digitalisieren statt Papierformular",
                steckbrief_name="Urlaub digital",
                description="Digitales Formular, Freigabe Führungskraft und Personal.",
                created_by=user.id,
            )
        )
        db.commit()

    sid = client.post("/api/sessions").json()["sessionId"]
    summary = until_summary(client, sid, STORY)
    assert summary["type"] == "summary"
    similar = summary["draft"]["values"].get("similar_solution") or ""
    assert similar
    assert "Nichts gefunden" not in str(summary)
