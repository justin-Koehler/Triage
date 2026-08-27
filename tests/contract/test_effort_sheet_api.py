from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.services.effort_sheet import TEMPLATE_PATH


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "effort-sheet.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("LLM_PROVIDER", "none")
    monkeypatch.setenv("TICKET_PORT", "fake")

    from app.config import get_settings

    get_settings.cache_clear()

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

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
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()
    get_ticket_port.cache_clear()


def test_rejects_non_google_url(client):
    r = client.post("/api/sessions/effort-sheet", json={"url": "https://example.com/sheet"})
    assert r.status_code == 502
    assert "Google" in r.json()["detail"]


def test_import_reads_csv(client, monkeypatch):
    csv_text = Path(TEMPLATE_PATH).read_text(encoding="utf-8")

    def fake_get(url, **kwargs):
        request = httpx.Request("GET", url)
        return httpx.Response(
            200,
            text=csv_text,
            headers={"content-type": "text/csv"},
            request=request,
        )

    monkeypatch.setattr("app.services.effort_sheet.httpx.get", fake_get)
    r = client.post(
        "/api/sessions/effort-sheet",
        json={"url": "https://docs.google.com/spreadsheets/d/abc123/edit?usp=sharing"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["effort_fb"] == "5 PT"
    assert body["effort_sheet_url"].startswith("https://docs.google.com/")
    assert body["costs"] == "2500"


def test_html_response_is_not_shared(client, monkeypatch):
    def fake_get(url, **kwargs):
        request = httpx.Request("GET", url)
        return httpx.Response(
            200,
            text="<!doctype html><html><body>login</body></html>",
            headers={"content-type": "text/html"},
            request=request,
        )

    monkeypatch.setattr("app.services.effort_sheet.httpx.get", fake_get)
    r = client.post(
        "/api/sessions/effort-sheet",
        json={"url": "https://docs.google.com/spreadsheets/d/abc123/edit"},
    )
    assert r.status_code == 502
    assert "freigegeben" in r.json()["detail"]


def test_template_download(client):
    r = client.get("/api/sessions/effort-sheet/template")
    assert r.status_code == 200
    assert "Tätigkeit" in r.text
    assert "text/csv" in r.headers.get("content-type", "")


def test_commit_creates_share_link(client):
    csv_text = Path(TEMPLATE_PATH).read_text(encoding="utf-8")
    r = client.post("/api/sessions/effort-sheet/commit", json={"csv": csv_text})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["effort_fb"] == "5 PT"
    assert "/aufwand/" in body["effort_sheet_url"]
    share_id = body["share_id"]
    page = client.get(f"/aufwand/{share_id}")
    assert page.status_code == 200
    assert "Workshops" in page.text
    assert client.get("/aufwand/not-a-uuid").status_code == 404
