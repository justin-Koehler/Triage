"""Status-Update: Anlegen, PLAN/IST, Historie. Kein Chat."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.types import Priority, RequestKind, RequestStatus
from app.models import Request, User

BASE = datetime(2026, 3, 1, 8, 0, tzinfo=UTC)


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "status.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("LLM_PROVIDER", "none")
    monkeypatch.setenv("TICKET_PORT", "fake")

    from app.config import get_settings
    from app.domain.fieldspec import get_rules

    get_settings.cache_clear()
    get_rules.cache_clear()

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
                {"name": "fach", "displayName": "Fachbereich", "emailAddress": "fach@example.com"},
            ][:limit]

    monkeypatch.setattr("app.api.auth._jira_login_port", lambda db: FakeLoginPort())

    with Session() as db:
        user = User(email="fach@example.com", display_name="Fachbereich")
        db.add(user)
        db.flush()
        request = Request(
            reference="AN-2001",
            kind=RequestKind.CHANGE_REQUEST,
            status=RequestStatus.STECKBRIEF,
            priority=Priority.MEDIUM,
            title="Urlaubsanträge digitalisieren",
            steckbrief_name="Change Request: Urlaubsanträge digitalisieren",
            description="Papier raus",
            created_by=user.id,
            created_at=BASE,
            updated_at=BASE,
        )
        db.add(request)
        db.commit()
        request_id = request.id

    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"account": "fach"}).status_code == 200
        yield c, request_id

    get_settings.cache_clear()
    get_ticket_port.cache_clear()


def test_create_status_update_with_plan_and_actual(client):
    c, request_id = client
    created = c.post(
        f"/api/requests/{request_id}/status-updates",
        json={
            "reportedOn": "2026-04-01",
            "overallRag": "yellow",
            "summary": "Konzept steht, Freigabe offen",
            "decisions": "QG1 auf Mai",
            "risks": "Betriebsrat",
            "nextSteps": "Steckbrief nachziehen",
            "scheduleRag": "yellow",
            "planStart": "2026-03-01",
            "planEnd": "2026-09-01",
            "actualStart": "2026-03-15",
            "actualEnd": "",
            "milestones": [
                {"name": "MS1", "plan": "2026-04-01", "actual": "2026-04-08"},
                {"name": "MS2", "plan": "2026-06-01", "actual": ""},
            ],
            "costRag": "green",
            "costPlanFb": "15000",
            "costPlanIt": "8000",
            "costActualFb": "4200",
            "costActualIt": "0",
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["overallRag"] == "yellow"
    assert body["planStart"] == "2026-03-01"
    assert body["actualStart"] == "2026-03-15"
    assert body["milestones"][0]["name"] == "MS1"
    assert body["costPlanFb"] == "15000"
    assert body["costActualFb"] == "4200"


def test_status_update_keeps_rag_and_next_step(client):
    c, request_id = client
    created = c.post(
        f"/api/requests/{request_id}/status-updates",
        json={
            "reportedOn": "2026-08-17",
            "summary": "QG1 durch, warte auf Justin",
            "overallRag": "yellow",
            "nextSteps": "Justin anrufen",
            "risks": "Termin rutscht",
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["overallRag"] == "yellow"
    assert body["nextSteps"] == "Justin anrufen"
    assert body["risks"] == "Termin rutscht"

    detail = c.get(f"/api/requests/{request_id}").json()
    hit = detail["statusUpdates"][0]
    assert hit["overallRag"] == "yellow"
    assert hit["nextSteps"] == "Justin anrufen"
    assert "Justin" in hit["summary"]


def test_status_update_history_is_kept(client):
    c, request_id = client
    first = c.post(
        f"/api/requests/{request_id}/status-updates",
        json={"reportedOn": "2026-04-01", "summary": "Stand April", "overallRag": "green"},
    ).json()
    second = c.post(
        f"/api/requests/{request_id}/status-updates",
        json={"reportedOn": "2026-05-01", "summary": "Stand Mai", "overallRag": "yellow"},
    ).json()
    assert first["id"] != second["id"]

    detail = c.get(f"/api/requests/{request_id}").json()
    summaries = [item["summary"] for item in detail["statusUpdates"]]
    assert "Stand April" in summaries
    assert "Stand Mai" in summaries
    assert len(detail["statusUpdates"]) == 2


def test_patch_status_update(client):
    c, request_id = client
    created = c.post(
        f"/api/requests/{request_id}/status-updates",
        json={"reportedOn": "2026-04-01", "summary": "Entwurf", "overallRag": "green"},
    ).json()
    patched = c.patch(
        f"/api/requests/{request_id}/status-updates/{created['id']}",
        json={"summary": "Aktualisiert", "overallRag": "red"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["summary"] == "Aktualisiert"
    assert patched.json()["overallRag"] == "red"


def test_status_summary_needs_status_text(client):
    c, request_id = client
    res = c.post(f"/api/requests/{request_id}/status-summary")
    assert res.status_code == 400
    assert "Status" in res.json()["detail"]


def test_status_update_writes_live_status(client):
    c, request_id = client
    created = c.post(
        f"/api/requests/{request_id}/status-updates",
        json={
            "reportedOn": "2026-04-01",
            "summary": "QG1 ist durch. Go-Live im Juni. Fachbereich bremst.",
            "overallRag": "green",
        },
    )
    assert created.status_code == 200, created.text

    detail = c.get(f"/api/requests/{request_id}").json()
    by_key = {row["key"]: row["value"] for row in detail["fields"]}
    assert "QG1" in by_key["current_status"]
    blurb = detail["statusSummary"]
    assert "QG1" in blurb
    assert len(blurb) <= 90

    listing = c.get("/api/requests").json()["items"]
    hit = next(item for item in listing if item["id"] == request_id)
    assert hit["statusSummary"] == blurb


def test_status_summary_reads_the_whole_tab(client):
    c, request_id = client
    for text in (
        "test",
        "kjgihb",
        "up to date",
        "es ist alles gut gerade ich warte auf justin",
    ):
        posted = c.post(
            f"/api/requests/{request_id}/status-updates",
            json={"reportedOn": "2026-08-14", "summary": text, "overallRag": "green"},
        )
        assert posted.status_code == 200, posted.text

    res = c.post(f"/api/requests/{request_id}/status-summary")
    assert res.status_code == 200, res.text
    body = res.json()
    text = (body.get("ablauf") or body["current_status"]).lower()
    assert "justin" in text
    assert text.index("test") < text.index("justin")

    detail = c.get(f"/api/requests/{request_id}").json()
    by_key = {row["key"]: row["value"] for row in detail["fields"]}
    assert "status_digest" not in by_key
    assert "justin" in by_key["status_ablauf"].lower()
    assert by_key["status_ablauf"].lower().index("test") < by_key["status_ablauf"].lower().index("justin")
