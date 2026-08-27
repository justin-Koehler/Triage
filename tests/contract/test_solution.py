from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "solution.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("LLM_PROVIDER", "none")
    monkeypatch.setenv("TICKET_PORT", "fake")

    from app.config import get_settings

    get_settings.cache_clear()

    import app.db as dbmod
    import app.models  # noqa: F401
    from app.db import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

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
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()
    get_ticket_port.cache_clear()


def test_solution_uses_model_text(client, monkeypatch):
    class Fake:
        name = "test"

        def complete_text(self, system, user):
            assert "papier" in user.lower()
            assert "Maßnahme" in system or "Lösung" in system
            return "Digitale Erfassung der Anträge in einem zentralen System."

    monkeypatch.setattr("app.services.fields.build_provider_from_runtime", lambda runtime: Fake())
    body = client.post(
        "/api/sessions/solution",
        json={
            "text": "Urlaubsanträge auf Papier ersetzen.",
            "title": "Urlaub digital",
            "benefit": "Weniger Aufwand.",
            "reason": "Anträge gehen verloren.",
        },
    ).json()
    assert "Erfassung" in body["text"]
    assert "Urlaubsanträge auf Papier ersetzen" not in body["text"]


def test_solution_drops_copy_of_description(client, monkeypatch):
    description = "Urlaubsanträge sollen digital erfasst werden."

    class Fake:
        name = "test"

        def complete_text(self, system, user):
            return description

    monkeypatch.setattr("app.services.fields.build_provider_from_runtime", lambda runtime: Fake())
    r = client.post(
        "/api/sessions/solution",
        json={"text": description, "title": "Urlaub digital"},
    )
    assert r.status_code == 503


def test_solution_without_llm_returns_error(client):
    r = client.post(
        "/api/sessions/solution",
        json={"text": "Urlaubsanträge digitalisieren.", "title": "Urlaub"},
    )
    assert r.status_code == 503
