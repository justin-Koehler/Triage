"""Dialog fragt feldweise, nie nach fremden Feldern."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.fieldspec import get_rules
from app.domain.topics import load_topics
from tests.support import DIALOG_KEYS, fact_keys, say

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


FORBIDDEN = {"draft", "workspace", "controlling", "computed"}


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "budget.db"
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
                "fields": {},
            }
        ]
    )
    monkeypatch.setattr(
        "app.api.sessions.build_provider_from_runtime",
        lambda _runtime: provider,
    )
    yield TestClient(app)
    get_settings.cache_clear()
    get_ticket_port.cache_clear()


def _fills() -> dict[str, str]:
    fills = {}
    for spec in get_rules().kinds.values():
        for field in spec.fields:
            fills[field.key] = field.fill
    for topic in load_topics():
        for field in topic.fields:
            fills.setdefault(field.key, field.fill)
    return fills


def test_fieldwise_questions_and_only_dialog_fields(client):
    sid = client.post("/api/sessions").json()["sessionId"]
    fills = _fills()
    keys: list[str] = []
    body = client.post(
        f"/api/sessions/{sid}/message",
        json={"text": "Wir wollen die Urlaubsanträge digitalisieren"},
    ).json()
    while body["type"] == "question":
        keys.append(body["fieldKey"])
        assert body["maxQuestions"] >= 8
        if body["fieldKey"] not in {"collab_risks", "collab_similar"}:
            assert fills.get(body["fieldKey"], "dialog") not in FORBIDDEN
        body = client.post(
            f"/api/sessions/{sid}/message",
            json={"text": say(GAPS, body["fieldKey"])},
        ).json()

    assert body["type"] == "summary"
    facts = fact_keys(keys)
    assert len(facts) <= 28
    assert len(facts) == len(set(facts))
    assert set(facts) <= DIALOG_KEYS | {"clarify"}
    assert "description" not in keys
    assert "end_date" not in keys
    assert "concept_scs_pt" not in keys
    assert "concept_scs_total" not in keys
    assert "notes" not in keys
    assert "target_group" not in keys
