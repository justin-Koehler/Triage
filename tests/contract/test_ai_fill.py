from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.types import Priority, RequestKind, RequestStatus
from app.models import Request, RequestField
from app.triage.engine import TriageEngine
from app.triage.providers import NoLlmProvider


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "test.db"
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

    monkeypatch.setattr(
        "app.triage.providers.build_provider_from_runtime",
        lambda _runtime: NoLlmProvider(),
    )
    get_ticket_port.cache_clear()

    class FakeLoginPort:
        def search_assignable_users(self, query="", *, limit=10, user_token=None, user_email=None):
            return [
                {"name": "tester", "displayName": "Tester", "emailAddress": "t@example.com"},
            ][:limit]

    monkeypatch.setattr("app.api.auth._jira_login_port", lambda db: FakeLoginPort())

    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"account": "tester"}).status_code == 200
        yield c, Session

    get_settings.cache_clear()
    get_ticket_port.cache_clear()


def test_intake_ai_fill_preserves_other_member_fields(client):
    c, Session = client
    sid = c.post("/api/sessions").json()["sessionId"]

    c.post(
        f"/api/sessions/{sid}/message",
        json={"text": "Genehmiger ist Max Mustermann. Change-Leitung ist Frau Müller."},
    ).json()

    c.patch(f"/api/sessions/{sid}/draft", json={"fields": {"change_lead": "Frau Alte"}})

    filled = c.post(
        f"/api/sessions/{sid}/ai-fill",
        json={"fieldKey": "approver"},
    ).json()

    assert filled["draft"]["values"]["change_lead"] == "Frau Alte"
    assert "Max Mustermann" in filled["draft"]["values"]["approver"]


def test_ticket_ai_fill_preserves_other_member_fields(client):
    c, Session = client

    req = Request(
        reference="AN-9999",
        kind=RequestKind.CHANGE_REQUEST,
        status=RequestStatus.STECKBRIEF,
        priority=Priority.MEDIUM,
        title="AN-9999",
        steckbrief_name="AN-9999",
        description="Genehmiger ist Max Mustermann. Change-Leitung ist Frau Müller.",
    )
    req.fields = [
        RequestField(
            request_id=req.id,
            key="change_lead",
            label="Change-Leitung SCS",
            value="Frau Alte",
            position=0,
        )
    ]

    with Session() as db:
        db.add(req)
        db.commit()
        updated = c.post(
            f"/api/requests/{req.id}/ai-fill", json={"fieldKey": "approver"}
        ).json()

    fields = {f["key"]: f["value"] for f in updated["fields"]}
    assert fields["change_lead"] == "Frau Alte"
    assert "Max Mustermann" in fields["approver"]

