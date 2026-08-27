from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "ai-regression.db"
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


def test_prompt_versions_are_embedded_for_core_fields(client, monkeypatch):
    seen = {}

    class Fake:
        name = "test"

        def complete_json(self, system, user):
            seen["kind_system"] = system
            return {"kind": "it_request"}

    monkeypatch.setattr("app.services.classify.build_provider_from_runtime", lambda _: Fake())
    body = client.post("/api/sessions/kind", json={"text": "Neue Abstimmungsrunde zwischen Bau und Event."}).json()
    assert body["kind"] == "it_request"
    assert "[prompt:kind.v1.1.0]" in seen["kind_system"]

    class FakeOverview:
        name = "test"

        def complete_json(self, system, user):
            seen["overview_system"] = system
            return {
                "benefit": "Weniger Wartezeit im Ablauf.",
                "reason": "Der aktuelle Papierweg verzögert Entscheidungen.",
                "solution": "Digitaler Freigabeweg mit nachvollziehbarem Status.",
                "risks": "Parallelbetrieb erzeugt Medienbrüche.",
            }

    monkeypatch.setattr("app.services.fields.build_provider_from_runtime", lambda _: FakeOverview())
    ov = client.post(
        "/api/sessions/overview",
        json={"text": "Papierfreigaben dauern zu lange.", "title": "Freigabe digital"},
    ).json()
    assert ov["benefit"]
    assert "[prompt:overview.v1.1.0]" in seen["overview_system"]


def test_polish_description_uses_prompt_version(client, monkeypatch):
    seen = {}

    class Fake:
        name = "test"

    def fake_complete(_provider, system, _user):
        seen["system"] = system
        return (
            "Heute laufen Freigaben über Papier. Das verzögert Entscheidungen. "
            "Anträge sind schwer nachzuverfolgen. Ein digitaler Ablauf soll das beheben."
        )

    monkeypatch.setattr("app.services.polish.build_provider_from_runtime", lambda _: Fake())
    monkeypatch.setattr("app.services.polish.complete_prose", fake_complete)
    body = client.post(
        "/api/sessions/polish",
        json={
            "text": "Papierfreigaben dauern lange",
            "field": "description",
            "title": "Freigabe",
            "kind": "change_request",
            "fields": {},
        },
    ).json()
    assert "digitaler ablauf" in body["text"].lower()
    assert "[prompt:polish.v1.2.0:description]" in seen["system"]
