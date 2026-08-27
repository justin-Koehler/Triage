"""Workspace Hub: Sortierung, Filter, Paginierung, CSV und Outbox beim Status-PATCH."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.domain.types import OutboxOperation, Priority, RequestKind, RequestStatus
from app.models import OutboxJob, Request, RequestField, User

BASE = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)

SEED = [
    ("AN-1001", RequestKind.CHANGE_REQUEST, RequestStatus.STECKBRIEF, Priority.LOW, "Kommunikation zentralisieren"),
    ("AN-1002", RequestKind.CHANGE_REQUEST, RequestStatus.IN_PROGRESS, Priority.CRITICAL, "SAP-Schnittstelle"),
    ("AN-1003", RequestKind.CHANGE_REQUEST, RequestStatus.STECKBRIEF, Priority.HIGH, "Neues Feld im Antrag"),
    ("AN-1004", RequestKind.CHANGE_REQUEST, RequestStatus.DONE, Priority.MEDIUM, "Lizenz für Tool X"),
    ("AN-1005", RequestKind.CHANGE_REQUEST, RequestStatus.STECKBRIEF, Priority.MEDIUM, "Export als CSV"),
]


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "hub.db"
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

    get_ticket_port.cache_clear()

    class FakeLoginPort:
        def search_assignable_users(self, query="", *, limit=10, user_token=None, user_email=None):
            rows = [
                {"name": "justin", "displayName": "Justin", "emailAddress": "justin@example.com"},
                {"name": "manuel", "displayName": "Manuel", "emailAddress": "manuel@example.com"},
            ]
            needle = (query or "").strip().lower()
            if needle:
                rows = [
                    row
                    for row in rows
                    if needle in row["name"] or needle in row["displayName"].lower()
                ]
            return rows[:limit]

    monkeypatch.setattr("app.api.auth._jira_login_port", lambda db: FakeLoginPort())

    with Session() as db:
        user = User(email="fach@example.com", display_name="Fachbereich Eins")
        db.add(user)
        db.flush()
        for index, (reference, kind, status, priority, title) in enumerate(SEED):
            db.add(
                Request(
                    reference=reference,
                    kind=kind,
                    status=status,
                    priority=priority,
                    title=title,
                    steckbrief_name=title,
                    description=f"Beschreibung zu {title}",
                    created_by=user.id,
                    created_at=BASE + timedelta(hours=index),
                    updated_at=BASE + timedelta(hours=index),
                )
            )
        db.commit()

    with TestClient(app) as c:
        login = c.post("/api/auth/login", json={"account": "manuel"})
        assert login.status_code == 200
        yield c, Session

    get_settings.cache_clear()
    get_ticket_port.cache_clear()


def refs(payload: dict) -> list[str]:
    return [item["reference"] for item in payload["items"]]


def test_default_sort_is_newest_first(client):
    c, _ = client
    body = c.get("/api/requests").json()
    assert body["total"] == 5
    assert refs(body) == ["AN-1005", "AN-1004", "AN-1003", "AN-1002", "AN-1001"]


def test_list_names_missing_fields(client):
    c, _ = client
    item = c.get("/api/requests").json()["items"][0]
    assert "Auftraggeber" in item["missingFields"]
    assert "Start" in item["missingFields"]
    assert "unvollständig" not in item["missingFields"]


def test_sort_by_priority_uses_business_rank(client):
    c, _ = client
    body = c.get("/api/requests", params={"sort": "priority", "dir": "asc"}).json()
    assert [item["priority"] for item in body["items"]] == [
        "critical",
        "high",
        "medium",
        "medium",
        "low",
    ]

    reverse = c.get("/api/requests", params={"sort": "priority", "dir": "desc"}).json()
    assert reverse["items"][0]["priority"] == "low"


def test_sort_by_status_uses_workflow_rank(client):
    c, _ = client
    body = c.get("/api/requests", params={"sort": "status", "dir": "asc"}).json()
    assert [item["status"] for item in body["items"]] == [
        "steckbrief",
        "steckbrief",
        "steckbrief",
        "umsetzung",
        "abgeschlossen",
    ]


def test_filter_combination(client):
    c, _ = client
    body = c.get("/api/requests", params={"kind": "change_request", "status": "steckbrief"}).json()
    assert body["total"] == 3
    assert set(refs(body)) == {"AN-1001", "AN-1003", "AN-1005"}

    narrowed = c.get(
        "/api/requests",
        params={"kind": "change_request", "status": "steckbrief", "priority": "high"},
    ).json()
    assert refs(narrowed) == ["AN-1003"]

    searched = c.get("/api/requests", params={"q": "csv"}).json()
    assert refs(searched) == ["AN-1005"]

    nothing = c.get("/api/requests", params={"kind": "change_request", "status": "abgelehnt"}).json()
    assert nothing["total"] == 0
    assert nothing["items"] == []


def test_pagination_keeps_total(client):
    c, _ = client
    first = c.get("/api/requests", params={"limit": 2, "offset": 0}).json()
    second = c.get("/api/requests", params={"limit": 2, "offset": 2}).json()
    third = c.get("/api/requests", params={"limit": 2, "offset": 4}).json()

    assert first["total"] == second["total"] == third["total"] == 5
    assert len(first["items"]) == 2
    assert len(third["items"]) == 1
    assert refs(first) + refs(second) + refs(third) == [
        "AN-1005",
        "AN-1004",
        "AN-1003",
        "AN-1002",
        "AN-1001",
    ]


def test_stats_counts_by_status(client):
    c, _ = client
    body = c.get("/api/requests/meta/stats").json()
    counts = {row["value"]: row["count"] for row in body["byStatus"]}
    assert body["total"] == 5
    assert counts["steckbrief"] == 3
    assert counts["umsetzung"] == 1
    assert counts["abgeschlossen"] == 1
    assert counts["entwurf"] == 0


def test_csv_export_has_bom_semicolon_and_respects_filters(client):
    c, _ = client
    response = c.get("/api/requests/export.csv", params={"status": "steckbrief"})
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]

    text = response.content.decode("utf-8")
    assert text.startswith("\ufeff")
    lines = text.lstrip("\ufeff").strip().splitlines()
    assert lines[0].split(";")[:3] == ["Change-Titel", "Change-Leitung SCS", "Status"]
    assert "QG1" not in lines[0]
    assert "QG2" not in lines[0]
    assert len(lines) == 4


def test_status_patch_writes_own_db_and_enqueues_outbox(client):
    c, Session = client
    target = refs(c.get("/api/requests", params={"q": "schnittstelle"}).json())[0]
    listed = c.get("/api/requests", params={"q": "schnittstelle"}).json()["items"][0]

    patched = c.patch(f"/api/requests/{listed['id']}", json={"status": "qg1"})
    assert patched.status_code == 200
    assert patched.json()["status"] == "qg1"

    with Session() as db:
        request = db.scalar(select(Request).where(Request.reference == target))
        assert request.status == RequestStatus.QG1
        jobs = db.scalars(select(OutboxJob).where(OutboxJob.request_id == request.id)).all()
        assert [job.operation for job in jobs] == [OutboxOperation.UPDATE_FIELDS]
        assert jobs[0].payload["fields"]["status"] == "qg1"


def test_detail_groups_expose_type_and_choice_values(client):
    c, Session = client
    with Session() as db:
        request = db.scalar(select(Request).where(Request.reference == "AN-1001"))
        db.add(
            RequestField(
                request_id=request.id,
                key="company",
                label="Gesellschaft",
                value="SIT",
                position=0,
            )
        )
        db.add(
            RequestField(
                request_id=request.id,
                key="start_date",
                label="Start",
                value="2027-03-01",
                position=1,
            )
        )
        db.commit()
        request_id = request.id

    detail = c.get(f"/api/requests/{request_id}").json()
    by_key = {f["key"]: f for g in detail["groups"] for f in g["fields"]}
    assert by_key["company"]["type"] == "choice"
    assert by_key["company"]["fill"] == "dialog"
    assert "SCS Gesamt" in by_key["company"]["values"]
    assert "SIT" in by_key["company"]["values"]
    assert by_key["start_date"]["type"] == "date"
    assert by_key["start_date"]["values"] == []


def test_detail_shows_empty_template_fields(client):
    c, Session = client
    with Session() as db:
        request = db.scalar(select(Request).where(Request.reference == "AN-1001"))
        request_id = request.id
    detail = c.get(f"/api/requests/{request_id}").json()
    keys = {field["key"] for group in detail["groups"] for field in group["fields"]}
    for key in (
        "approver",
        "fb_owner",
        "process_owner",
        "cost_unit",
    ):
        assert key in keys, key
    by_key = {field["key"]: field for group in detail["groups"] for field in group["fields"]}
    assert "assignee" not in by_key


def test_delete_removes_the_ticket(client):
    c, _ = client
    listed = c.get("/api/requests").json()["items"]
    target = listed[0]
    gone = c.delete(f"/api/requests/{target['id']}")
    assert gone.status_code == 204
    assert c.get(f"/api/requests/{target['id']}").status_code == 404
    refs = [item["reference"] for item in c.get("/api/requests").json()["items"]]
    assert target["reference"] not in refs
    missing = c.delete(f"/api/requests/{target['id']}")
    assert missing.status_code == 404


def test_home_is_workspace_with_intake(client):
    c, _ = client
    page = c.get("/")
    assert page.status_code == 200
    html = page.text
    assert 'id="hub"' in html
    assert 'id="form"' in html
    assert 'id="jira-create"' in html or "In Jira" in html
    assert 'id="search"' not in html
    assert ">Chat<" not in html
    assert c.get("/workspace").text == html


def test_filter_options_laden(client):
    c, _ = client
    body = c.get("/api/requests/meta/filters").json()
    assert body["statuses"]
    assert "responsibles" in body


def test_status_nennt_angemeldeten_oben_und_markiert(client):
    c, Session = client
    with Session() as db:
        justin_ticket = db.scalar(select(Request).where(Request.reference == "AN-1001"))
        manuel_ticket = db.scalar(select(Request).where(Request.reference == "AN-1003"))
        db.add(
            RequestField(
                request_id=justin_ticket.id,
                key="status_summary",
                label="KI-Zusammenfassung",
                value="Warten auf Justin zur Klärung der Finanzierung.",
                position=0,
            )
        )
        db.add(
            RequestField(
                request_id=manuel_ticket.id,
                key="status_summary",
                label="KI-Zusammenfassung",
                value="Warte auf Manuel",
                position=0,
            )
        )
        db.commit()

    assert c.post("/api/auth/login", json={"account": "justin"}).status_code == 200
    body = c.get("/api/requests").json()
    assert refs(body)[0] == "AN-1001"
    mine = [item["reference"] for item in body["items"] if item["waitingOnMe"]]
    assert mine == ["AN-1001"]
    hit = body["items"][0]
    assert hit["waitingTodo"] == "Klärung der Finanzierung steht aus."
    assert hit["waitingTodo"] != hit["statusSummary"]

    login = c.post("/api/auth/login", json={"account": "manuel"})
    assert login.status_code == 200
    body = c.get("/api/requests").json()
    assert refs(body)[0] == "AN-1003"
    mine = [item["reference"] for item in body["items"] if item["waitingOnMe"]]
    assert mine == ["AN-1003"]
    assert "AN-1001" in refs(body)[1:]
