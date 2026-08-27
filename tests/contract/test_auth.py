"""Jira-Login: Account aus Assignable-Users, Cookie setzen."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models import User

JIRA_ACCOUNTS = [
    {
        "name": "justin",
        "displayName": "Justin",
        "emailAddress": "justin@example.com",
    },
    {
        "name": "manuel",
        "displayName": "Manuel",
        "emailAddress": "manuel@example.com",
    },
    {
        "name": "tobias",
        "displayName": "Tobias",
        "emailAddress": "tobias@example.com",
    },
]


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "auth.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("LLM_PROVIDER", "none")
    monkeypatch.setenv("TICKET_PORT", "fake")

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
    from app.ports.jira_v3 import JiraRestV3

    get_ticket_port.cache_clear()

    def fake_search(self, query="", *, limit=10, user_token=None, user_email=None):
        needle = (query or "").strip().lower()
        rows = JIRA_ACCOUNTS
        if needle:
            rows = [
                row
                for row in rows
                if needle in row["name"].lower() or needle in row["displayName"].lower()
            ]
        return rows[:limit]

    class FakePort:
        def search_assignable_users(self, query="", *, limit=10, user_token=None, user_email=None):
            return fake_search(self, query, limit=limit)

    monkeypatch.setattr("app.api.auth._jira_login_port", lambda db: FakePort())
    monkeypatch.setattr(JiraRestV3, "search_assignable_users", fake_search)

    with TestClient(app) as c:
        yield c, Session

    get_settings.cache_clear()
    get_ticket_port.cache_clear()


def test_accounts_come_from_jira(client):
    c, _ = client
    body = c.get("/api/auth/accounts").json()
    names = [row["displayName"] for row in body["accounts"]]
    assert names == ["Justin", "Manuel", "Tobias"]
    assert body["source"] == "jira"
    assert all(row["id"] for row in body["accounts"])


def test_login_sets_cookie_and_me(client):
    c, Session = client
    assert c.get("/api/auth/me").json()["authenticated"] is False
    login = c.post("/api/auth/login", json={"account": "manuel"})
    assert login.status_code == 200
    assert login.json()["user"]["displayName"] == "Manuel"
    me = c.get("/api/auth/me").json()
    assert me["authenticated"] is True
    assert me["user"]["displayName"] == "Manuel"
    assert me["user"]["jiraName"] == "manuel"
    with Session() as db:
        user = db.scalar(select(User).where(User.external_subject == "manuel"))
        assert user is not None
        assert user.display_name == "Manuel"
        assert user.email == "manuel@example.com"


def test_prefix_login_rejected(client):
    c, _ = client
    bad = c.post("/api/auth/login", json={"account": "manu"})
    assert bad.status_code == 400


def test_unknown_account_rejected(client):
    c, _ = client
    bad = c.post("/api/auth/login", json={"account": "admin"})
    assert bad.status_code == 400


def test_logout_clears_session(client):
    c, _ = client
    c.post("/api/auth/login", json={"account": "tobias"})
    assert c.get("/api/auth/me").json()["user"]["displayName"] == "Tobias"
    c.post("/api/auth/logout")
    assert c.get("/api/auth/me").json()["authenticated"] is False
