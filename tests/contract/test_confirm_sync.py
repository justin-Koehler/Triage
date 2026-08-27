"""Confirm legt in der eigenen DB an; Outbox spiegelt nach Fake."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.domain.types import Priority, RequestKind, RequestStatus, SyncState
from app.models import ExternalRef, OutboxJob, Request
from app.services.intake import IntakeService
from app.triage.engine import TriageEngine
from app.ports.fake import FakeTicketSystem
from app.sync.outbox import process_pending
from app.triage.providers import NoLlmProvider
from tests.support import say


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

    # Provider-Zwang: Heuristik (kein LLM)
    monkeypatch.setattr(
        "app.triage.providers.build_provider_from_runtime",
        lambda _runtime: NoLlmProvider(),
    )
    get_ticket_port.cache_clear()

    with TestClient(app) as c:
        yield c, Session

    get_settings.cache_clear()
    get_ticket_port.cache_clear()


def test_confirm_writes_own_db_then_fake_sync(client):
    c, Session = client
    sid = c.post("/api/sessions").json()["sessionId"]
    body = c.post(
        f"/api/sessions/{sid}/message",
        json={"text": "Urlaubsanträge sollen digital laufen, der Prozess ist Papier"},
    ).json()
    while body["type"] == "question":
        reply = say(
            {
                "sponsor": "Frau Berger",
                "start_date": "1.3.2027 bis 1.9.2027",
                "end_date": "1.9.2027",
                "company": "SCS Gesamt",
                "description": (
                    "Urlaubsanträge laufen über ein Papierformular mit zwei Unterschriften. "
                    "Anträge gehen verloren, niemand sieht den Stand. Wir wollen ein digitales "
                    "Formular mit Freigabe durch Führungskraft und Personal."
                ),
                "current_status": "Idee, noch kein Steckbrief",
                "benefit_savings": "Weniger Papier",
                "benefit_risk": "Keine verlorenen Anträge",                "problem": (
                    "Urlaubsanträge laufen über ein Papierformular mit zwei Unterschriften. "
                    "Anträge gehen verloren, und niemand sieht den aktuellen Stand."
                ),
                "solution_goals": (
                    "Ein digitales Formular mit zweistufiger Freigabe durch Führungskraft "
                    "und Personal. Der Resturlaub kommt aus dem Personalsystem. "
                    "Der Betriebsrat wird vor der Einführung eingebunden."
                ),
                "risks_obstacles": "keine",
                "similar_solution": "Kein vergleichbares Formular im Einsatz",
            },
            body["fieldKey"],
        )
        body = c.post(f"/api/sessions/{sid}/message", json={"text": reply}).json()
    assert body["type"] == "summary", body

    created = c.post(
        f"/api/sessions/{sid}/confirm",
        headers={"Idempotency-Key": "test-confirm-1"},
    )
    assert created.status_code == 200, created.text
    payload = created.json()
    assert payload["type"] == "created"
    assert payload["jiraKey"]
    assert payload["reference"] == payload["jiraKey"]
    assert payload["ticketKey"] == payload["jiraKey"]
    request_id = payload["requestId"]

    again = c.post(
        f"/api/sessions/{sid}/confirm",
        headers={"Idempotency-Key": "test-confirm-1"},
    ).json()
    assert again["requestId"] == request_id

    with Session() as db:
        request = db.get(Request, request_id)
        assert request is not None
        assert request.title
        jobs = db.scalars(select(OutboxJob).where(OutboxJob.request_id == request_id)).all()
        assert len(jobs) >= 1
        port = FakeTicketSystem(Session, project="TRI")
        process_pending(db, port)
        db.refresh(request)
        ref = db.scalar(select(ExternalRef).where(ExternalRef.request_id == request_id))
        assert ref is not None
        assert ref.external_key
        assert ref.sync_state == SyncState.SYNCED
        assert request.reference == ref.external_key


def test_next_reference_follows_highest_not_count(client):
    """Drei Tickets mit Luecken: Count waere AN-1004, die Nummer ist aber vergeben."""
    _c, Session = client
    with Session() as db:
        for ref in ("AN-1002", "AN-1004", "AN-1018"):
            db.add(
                Request(
                    reference=ref,
                    kind=RequestKind.CHANGE_REQUEST,
                    status=RequestStatus.STECKBRIEF,
                    priority=Priority.MEDIUM,
                    title=ref,
                    steckbrief_name=ref,
                    description="x",
                )
            )
        db.commit()
        service = IntakeService(db=db, engine=TriageEngine(provider=NoLlmProvider()))
        assert service._next_reference() == "AN-1019"


def test_publish_from_ticket_mask(client):
    c, Session = client
    body = c.post(
        "/api/sessions/publish",
        json={
            "title": "Urlaubsanträge digitalisieren",
            "kind": "change_request",
            "priority": "medium",
            "fields": {
                "start": "01.03.2027",
                "sponsor": "Personalleitung",
                "nonprofit": "Ja",
                "description": "Urlaubsanträge laufen auf Papier und gehen verloren.",
                "lead": "A",
            },
        },
    )
    assert body.status_code == 200, body.text
    payload = body.json()
    assert payload["title"] == "Urlaubsanträge digitalisieren"
    assert payload["jiraKey"]
    assert payload["jiraKey"].count("-") == 1 and payload["jiraKey"].split("-")[1].isdigit()
    assert payload["ticketKey"] == payload["jiraKey"]
    assert payload["reference"] == payload["jiraKey"]
    with Session() as db:
        req = db.get(Request, payload["requestId"])
        assert req is not None
        assert req.reference == payload["jiraKey"]
        assert req.change_lead == "A"
        assert req.field_values().get("nonprofit_dss") == "Ja"
