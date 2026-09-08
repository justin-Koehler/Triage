"""Cidaas OIDC: Login-Seite, PKCE-Start, Callback."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models import User
from app.services.cidaas import pkce_pair, safe_next


def test_pkce_pair_is_s256_shaped():
    verifier, challenge = pkce_pair()
    assert 43 <= len(verifier) <= 128
    assert len(challenge) == 43


def test_safe_next_blocks_open_redirect():
    assert safe_next("/workspace") == "/workspace"
    assert safe_next("https://evil.example") == "/"
    assert safe_next("//evil.example") == "/"
    assert safe_next("") == "/"


DISCOVERY = {
    "authorization_endpoint": "https://account.bildungscampus.life/authz-srv/authz",
    "token_endpoint": "https://account.bildungscampus.life/token-srv/token",
    "userinfo_endpoint": "https://account.bildungscampus.life/users-srv/userinfo",
}


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "cidaas.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("LLM_PROVIDER", "none")
    monkeypatch.setenv("TICKET_PORT", "fake")
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("CIDAAS_CLIENT_ID", "test-client")
    monkeypatch.setenv("CIDAAS_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv(
        "CIDAAS_REDIRECT_URL", "https://scscm.stackit.gg/api/auth/cidaas/callback"
    )

    from app.config import get_settings
    from app.services import cidaas as cidaas_mod

    get_settings.cache_clear()
    cidaas_mod._discovery_cached.cache_clear()
    monkeypatch.setattr(cidaas_mod, "discovery", lambda settings=None: DISCOVERY)

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

    with TestClient(app) as c:
        yield c, Session

    get_settings.cache_clear()
    cidaas_mod._discovery_cached.cache_clear()


def test_login_page_is_public(client):
    c, _ = client
    res = c.get("/login")
    assert res.status_code == 200
    assert "Cidaas anmelden" in res.text
    assert "Dummy" not in res.text


def test_auth_config_flags_cidaas(client):
    c, _ = client
    body = c.get("/api/auth/config").json()
    assert body["cidaas"] is True
    assert body["devLogin"] is False


def test_cidaas_start_redirects_with_pkce(client):
    c, _ = client
    res = c.get("/api/auth/cidaas/start?next=/workspace", follow_redirects=False)
    assert res.status_code == 302
    loc = urlparse(res.headers["location"])
    assert loc.netloc == "account.bildungscampus.life"
    qs = parse_qs(loc.query)
    assert qs["response_type"] == ["code"]
    assert qs["code_challenge_method"] == ["S256"]
    assert qs["client_id"] == ["test-client"]
    assert qs["redirect_uri"] == ["https://scscm.stackit.gg/api/auth/cidaas/callback"]
    assert "cidaas_oidc" in res.cookies


def test_cidaas_callback_sets_session(client, monkeypatch):
    c, Session = client
    start = c.get("/api/auth/cidaas/start?next=/", follow_redirects=False)
    loc = urlparse(start.headers["location"])
    state = parse_qs(loc.query)["state"][0]

    monkeypatch.setattr(
        "app.services.cidaas.exchange_code",
        lambda code, verifier, settings=None: {"access_token": "tok"},
    )
    monkeypatch.setattr(
        "app.services.cidaas.userinfo",
        lambda token, settings=None: {
            "sub": "cidaas-1",
            "email": "ada@campus.example",
            "name": "Ada Campus",
        },
    )
    res = c.get(
        f"/api/auth/cidaas/callback?code=abc&state={state}",
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert res.headers["location"] == "/"
    me = c.get("/api/auth/me").json()
    assert me["authenticated"] is True
    assert me["user"]["displayName"] == "Ada Campus"
    with Session() as db:
        user = db.scalar(select(User).where(User.email == "ada@campus.example"))
        assert user is not None


def test_protected_page_redirects_to_login(client):
    c, _ = client
    res = c.get("/workspace", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"].startswith("/login")
