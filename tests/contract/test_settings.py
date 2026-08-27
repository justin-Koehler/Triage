"""Settings-API: Secrets maskiert, Runtime überschreibt Env."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import AppSetting


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "settings.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("SESSION_SECRET", "test-secret-for-settings")
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
    from app.security import get_or_create_user, sign_session

    with TestClient(app) as c:
        with Session() as db:
            user = get_or_create_user(db, "dev@localhost", "Dev")
            db.commit()
            token = sign_session(user.id)
        c.cookies.set(get_settings().session_cookie, token)
        yield c, Session
    get_settings.cache_clear()
    get_ticket_port.cache_clear()


def test_settings_roundtrip_masks_secrets(client):
    c, Session = client
    got = c.get("/api/settings").json()
    assert "apiKey" not in str(got["llm"]).lower() or got["llm"]["apiKeyConfigured"] in (
        True,
        False,
    )
    assert got["llm"]["apiKeyConfigured"] is False

    saved = c.put(
        "/api/settings",
        json={
            "llm": {
                "provider": "anthropic",
                "model": "claude-sonnet-4-5",
                "apiKey": "sk-ant-secret-value",
                "timeout": 60,
            },
            "jira": {
                "enabled": True,
                "baseUrl": "https://example.atlassian.net",
                "email": "bot@example.com",
                "projectKey": "tri",
                "apiToken": "jira-secret-token",
            },
        },
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["llm"]["provider"] == "anthropic"
    assert body["llm"]["apiKeyConfigured"] is True
    assert "sk-ant" not in str(body)
    assert body["jira"]["projectKey"] == "TRI"
    assert body["jira"]["apiTokenConfigured"] is True
    assert body["runtime"]["ticketPort"] == "jira"

    with Session() as db:
        row = db.get(AppSetting, "llm.api_key")
        assert row is not None
        assert row.secret is True
        assert row.value != "sk-ant-secret-value"
        assert "sk-ant" not in row.value


def test_empty_secret_keeps_previous(client):
    c, _Session = client
    c.put(
        "/api/settings",
        json={"llm": {"provider": "openai", "apiKey": "keep-me"}},
    )
    c.put(
        "/api/settings",
        json={"llm": {"provider": "openai", "model": "gpt-4o-mini", "apiKey": ""}},
    )
    body = c.get("/api/settings").json()
    assert body["llm"]["apiKeyConfigured"] is True
    assert body["llm"]["model"] == "gpt-4o-mini"
