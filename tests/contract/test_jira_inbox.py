from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.models import FakeExternalIssue, User


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "jira-inbox.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("LLM_PROVIDER", "none")
    monkeypatch.setenv("TICKET_PORT", "fake")
    monkeypatch.setenv("JIRA_BASE_URL", "")
    monkeypatch.setenv("JIRA_API_TOKEN", "")
    monkeypatch.setenv("JIRA_API_KEY", "")

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

    class FakeLoginPort:
        def search_assignable_users(self, query="", *, limit=10, user_token=None, user_email=None):
            return [
                {
                    "name": "fach",
                    "displayName": "Fachbereich",
                    "emailAddress": "fach@example.com",
                }
            ]

    monkeypatch.setattr("app.api.auth._jira_login_port", lambda db: FakeLoginPort())

    with Session() as db:
        db.add(User(email="fach@example.com", display_name="Fachbereich"))
        db.add(
            FakeExternalIssue(
                key="TRI-42",
                issue_type="Change request",
                summary="SAP-Schnittstelle",
                description="Anbindung Buchhaltung",
                priority="High",
                fields={"status": "In Progress", "sponsor": "SCS - CSM", "start": "2026-09-01"},
            )
        )
        db.commit()
    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"account": "fach"}).status_code == 200
        yield c
    get_settings.cache_clear()
    get_ticket_port.cache_clear()


def test_lists_jira_tickets_in_hub(client):
    body = client.get("/api/jira/issues").json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["key"] == "TRI-42"
    assert item["title"] == "SAP-Schnittstelle"
    assert "Progress" in item["status"]


def test_import_mirrors_ticket_into_workspace(client):
    created = client.post("/api/jira/issues/TRI-42/import")
    assert created.status_code == 200
    detail = created.json()
    assert detail["title"] == "SAP-Schnittstelle"
    assert detail["sync"]["externalKey"] == "TRI-42"
    assert any(f["key"] == "sponsor" and f["value"] == "SCS - CSM" for f in detail["fields"])

    again = client.post("/api/jira/issues/TRI-42/import").json()
    assert again["id"] == detail["id"]
    listed = client.get("/api/jira/issues").json()["items"][0]
    assert listed["requestId"] == detail["id"]


def test_patch_syncs_field_back_to_jira(client):
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.domain.types import SyncState
    from app.models import FakeExternalIssue, OutboxJob
    from app.ports import get_ticket_port
    from app.sync.outbox import process_pending

    detail = client.post("/api/jira/issues/TRI-42/import").json()
    patched = client.patch(
        f"/api/requests/{detail['id']}",
        json={"fields": {"sponsor": "SCS - Bau"}},
    )
    assert patched.status_code == 200
    assert any(
        f["key"] == "sponsor" and f["value"] == "SCS - Bau" for f in patched.json()["fields"]
    )

    with SessionLocal() as db:
        jobs = db.scalars(select(OutboxJob).where(OutboxJob.request_id == detail["id"])).all()
        assert jobs
        assert jobs[0].payload["fields"]["sponsor"] == "SCS - Bau"
        for job in jobs:
            job.state = SyncState.PENDING
            job.next_attempt_at = datetime.now(UTC)
            job.last_error = None
            job.attempts = 0
        db.commit()

    with SessionLocal() as db:
        stats = process_pending(db, get_ticket_port())
        db.commit()
        assert stats["done"] >= 1

    with SessionLocal() as db:
        issue = db.get(FakeExternalIssue, "TRI-42")
        assert issue is not None
        assert issue.fields.get("sponsor") == "SCS - Bau"