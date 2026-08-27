from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "overview.db"
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


def test_overview_splits_fields(client, monkeypatch):
    class Fake:
        name = "test"

        def complete_json(self, system, user):
            assert "benefit" in system
            assert "papier" in user.lower()
            return {
                "benefit": "Weniger Handarbeit, Anträge gehen nicht verloren.",
                "reason": "Auf Papier fehlt der Stand.",
                "solution": "Digitale Erfassung mit Freigabe.",
                "risks": "Führung bleibt auf Papier, wenn der alte Weg offen ist.",
            }

    monkeypatch.setattr(
        "app.services.fields.build_provider_from_runtime", lambda runtime: Fake()
    )
    body = client.post(
        "/api/sessions/overview",
        json={"text": "Urlaubsanträge auf Papier ersetzen.", "title": "Urlaub digital"},
    ).json()
    assert "Handarbeit" in body["benefit"]
    assert "Papier" in body["reason"]
    assert "Digitale Erfassung" in body["solution"]
    assert "Papier" in body["risks"]
    assert body["benefit"] != body["reason"]


def test_overview_uses_web_hits(client, monkeypatch):
    class Fake:
        name = "test"

        def complete_json(self, system, user):
            assert "Webrecherche" in user
            assert "Parallelbetrieb" in user
            assert "Webrecherche" in system or "Web" in system
            return {
                "benefit": "Weniger Handarbeit, Anträge gehen nicht verloren.",
                "reason": "Auf Papier fehlt der Stand.",
                "solution": "Digitale Erfassung mit Freigabe.",
                "risks": "Parallelbetrieb bleibt, wenn Papier weiter offen ist.",
            }

    monkeypatch.setattr(
        "app.services.fields.build_provider_from_runtime", lambda runtime: Fake()
    )
    monkeypatch.setattr(
        "app.services.fields.search_risks",
        lambda title, description, limit=4: [
            {
                "title": "Change-Risiken Digitalisierung",
                "url": "https://example.com/risiken",
                "snippet": "Parallelbetrieb und geringe Adoption sind typische Risiken.",
            }
        ],
    )
    body = client.post(
        "/api/sessions/overview",
        json={"text": "Urlaubsanträge auf Papier ersetzen.", "title": "Urlaub digital"},
    ).json()
    assert "Parallelbetrieb" in body["risks"]
