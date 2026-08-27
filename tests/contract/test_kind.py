from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "kind.db"
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


def test_kind_it_from_keyword(client):
    body = client.post(
        "/api/sessions/kind",
        json={"text": "SAP-Schnittstelle für die Buchung anbinden."},
    ).json()
    assert body["kind"] == "it_request"
    assert body["label"] == "IT Request"


def test_kind_change_without_it(client):
    body = client.post(
        "/api/sessions/kind",
        json={"text": "Neue Abstimmungsrunde zwischen Bau und Event."},
    ).json()
    assert body["kind"] == "change_request"
    assert body["label"] == "Change Request"
