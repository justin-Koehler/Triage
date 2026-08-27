"""Chat am Ticket: nur dieses Anliegen lesen und aendern."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.domain.types import Priority, RequestKind, RequestStatus
from app.models import IntakeSession, Request, RequestField, StatusUpdate, User

BASE = datetime(2026, 4, 1, 8, 0, tzinfo=UTC)


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "ticket-chat.db"
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

    with Session() as db:
        user = User(email="fach@example.com", display_name="Fachbereich")
        db.add(user)
        db.flush()
        primary = Request(
            reference="AN-3001",
            kind=RequestKind.CHANGE_REQUEST,
            status=RequestStatus.STECKBRIEF,
            priority=Priority.MEDIUM,
            title="Urlaubsanträge digitalisieren",
            steckbrief_name="Urlaubsanträge digitalisieren",
            description="Papier raus",
            created_by=user.id,
            created_at=BASE,
            updated_at=BASE,
        )
        other = Request(
            reference="AN-3002",
            kind=RequestKind.CHANGE_REQUEST,
            status=RequestStatus.IN_PROGRESS,
            priority=Priority.LOW,
            title="SAP-Schnittstelle",
            steckbrief_name="SAP-Schnittstelle",
            description="Anbindung",
            created_by=user.id,
            created_at=BASE,
            updated_at=BASE,
        )
        db.add_all([primary, other])
        db.flush()
        db.add(
            RequestField(
                request_id=primary.id,
                key="problem",
                label="Problem / Ist-Zustand",
                value="Anträge laufen auf Papier",
                position=0,
            )
        )
        db.commit()
        primary_id = primary.id

    with TestClient(app) as c:
        yield c, Session, primary_id

    get_settings.cache_clear()
    get_ticket_port.cache_clear()


def _count(Session) -> int:
    with Session() as db:
        return db.scalar(select(func.count()).select_from(Request)) or 0


def _talk(client: TestClient, request_id: str, text: str) -> dict:
    response = client.post(f"/api/requests/{request_id}/chat", json={"text": text})
    assert response.status_code == 200, response.text
    return response.json()


def test_get_legt_ticket_session_an(client):
    c, Session, request_id = client
    first = c.get(f"/api/requests/{request_id}/chat")
    assert first.status_code == 200
    body = first.json()
    assert body["sessionId"]
    assert body["messages"] == []
    second = c.get(f"/api/requests/{request_id}/chat")
    assert second.json()["sessionId"] == body["sessionId"]
    with Session() as db:
        session = db.get(IntakeSession, body["sessionId"])
        assert session is not None
        assert session.phase == "ticket"
        assert session.request_id == request_id


def test_setzt_prioritaet_nur_dieses_tickets(client):
    c, Session, request_id = client
    body = _talk(c, request_id, "setz das auf hoch")
    assert body["changed"] is True
    assert "Hoch" in body["text"]
    assert body["detail"]["priority"] == "high"
    assert body["detail"]["id"] == request_id
    with Session() as db:
        this = db.get(Request, request_id)
        other = db.scalar(select(Request).where(Request.reference == "AN-3002"))
        assert this.priority == Priority.HIGH
        assert other.priority == Priority.LOW


def test_fremde_referenz_abgelehnt(client):
    c, Session, request_id = client
    body = _talk(c, request_id, "setz AN-3002 auf hoch")
    assert body["changed"] is False
    assert "Nur dieser Change" in body["text"]
    with Session() as db:
        other = db.scalar(select(Request).where(Request.reference == "AN-3002"))
        assert other.priority == Priority.LOW


def test_liste_abgelehnt(client):
    c, _, request_id = client
    body = _talk(c, request_id, "welche tickets sind offen")
    assert body["changed"] is False
    assert "Nur dieser Change" in body["text"]


def test_legt_kein_zweites_anliegen_an(client):
    c, Session, request_id = client
    before = _count(Session)
    body = _talk(
        c,
        request_id,
        "Wir brauchen eine Inventur-App für alle Lager.",
    )
    assert "nichts Neues" in body["text"]
    assert body["changed"] is False
    assert _count(Session) == before


def test_fragt_problem_dieses_tickets(client):
    c, _, request_id = client
    body = _talk(c, request_id, "was ist das Problem")
    assert "Anträge laufen auf Papier" in body["text"]
    assert body["changed"] is False
    assert "detail" not in body


def test_recherchiert_wissen_und_web(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.ticket_chat.web_search",
        lambda query, limit=3: [
            {
                "title": "Digitale Urlaubsanträge im Mittelstand",
                "url": "https://example.com/urlaub",
                "snippet": "Portal statt Papier.",
            }
        ],
    )
    c, Session, request_id = client
    before = _count(Session)
    body = _talk(c, request_id, "recherchiere ähnliche Lösungen")
    assert body["changed"] is False
    assert "KB-0007" in body["text"]
    assert "Digitale Urlaubsanträge im Mittelstand" in body["text"]
    assert "zweistufiger Freigabe" not in body["text"]
    assert "nichts Neues" not in body["text"]
    assert _count(Session) == before


def test_uebernimmt_recherche_in_risiken(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.ticket_chat.web_search",
        lambda query, limit=3: [
            {
                "title": "DSGVO bei digitalen Urlaubsanträgen",
                "url": "https://example.com/dsgvo",
                "snippet": "Personenbezogene Antragsdaten.",
            }
        ],
    )
    c, Session, request_id = client
    first = _talk(
        c,
        request_id,
        "recherchiere bitte ob es online risiken zu diesem thema gibt",
    )
    assert first["changed"] is False
    assert "DSGVO" in first["text"] or "Wissen:" in first["text"] or "Web:" in first["text"]
    assert "übernehmen" in first["text"].lower()

    body = _talk(c, request_id, "trag das bitte ein")
    assert body["changed"] is True, body["text"]
    assert "übernommen" in body["text"].lower()
    assert "test" not in body["text"].lower()
    with Session() as db:
        request = db.get(Request, request_id)
        stored = request.field_values()["risks_obstacles"]
        assert stored
        assert "übernehmen" not in stored.lower()
        assert "test" not in stored.lower()
        assert "DSGVO" in stored or "Wissen:" in stored or "Web:" in stored

    again = _talk(c, request_id, "trag das bitte in das Feld Risiken und Hindernisse ein")
    assert again["changed"] is True
    with Session() as db:
        request = db.get(Request, request_id)
        assert request.field_values()["risks_obstacles"]


def test_schreibt_letzte_antwort_in_status(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.ticket_chat.web_search",
        lambda query, limit=3: [
            {"title": "Schulung schrittweise einführen", "url": "https://example.com/s", "snippet": "Trainer."}
        ],
    )
    c, Session, request_id = client
    first = _talk(c, request_id, "recherchiere nächste Schritte")
    body = _talk(c, request_id, "schreib das in status")
    assert body["changed"] is True, body["text"]
    assert "status" in body["text"].lower()
    assert "steckbrief" not in body["text"].lower()
    with Session() as db:
        request = db.get(Request, request_id)
        notes = db.scalars(
            select(StatusUpdate).where(StatusUpdate.request_id == request_id)
        ).all()
        assert notes
        offer = first["text"].split("Übernehmen")[0].strip()
        assert offer
        assert offer[:40] in notes[-1].summary
        ablauf = request.field_values().get("status_ablauf") or request.field_values().get(
            "current_status"
        )
        assert offer[:40] in (ablauf or notes[-1].summary)


def test_status_eintrag_trifft_nicht_digest(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.ticket_chat.web_search",
        lambda query, limit=3: [
            {
                "title": "Eingang festlegen",
                "url": "https://example.com/ort",
                "snippet": "Ort, Skript, Hardware, Wartung.",
            }
        ],
    )
    c, Session, request_id = client
    with Session() as db:
        db.add(
            RequestField(
                request_id=request_id,
                key="status_digest",
                label="Status-Digest",
                value="oldhash",
                position=90,
            )
        )
        db.add(
            RequestField(
                request_id=request_id,
                key="status_summary",
                label="KI-Zusammenfassung",
                value="Warten auf Justin zur Klärung der Finanzierung.",
                position=91,
            )
        )
        db.commit()

    first = _talk(c, request_id, "recherchiere nächste Schritte")
    body = _talk(c, request_id, "ok Justin soll das machen trag das in den status ein")
    assert body["changed"] is True, body["text"]
    assert "digest" not in body["text"].lower()
    assert "statusfeld" in body["text"].lower()
    offer = first["text"].split("Übernehmen")[0].strip()
    assert offer
    with Session() as db:
        request = db.get(Request, request_id)
        notes = db.scalars(
            select(StatusUpdate).where(StatusUpdate.request_id == request_id)
        ).all()
        assert notes
        blob = " ".join(
            [
                notes[-1].summary or "",
                notes[-1].next_steps or "",
                request.field_values().get("status_ablauf") or "",
                request.field_values().get("status_summary") or "",
            ]
        )
        assert offer[:40] in blob
        assert "Finanzierung" not in (request.field_values().get("status_summary") or "")


def test_schreibt_letzte_antwort_in_einsparungen(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.ticket_chat.web_search",
        lambda query, limit=3: [
            {"title": "Portal statt Papier", "url": "https://example.com/p", "snippet": "Weniger Aufwand."}
        ],
    )
    c, Session, request_id = client
    first = _talk(c, request_id, "recherchiere best practice")
    body = _talk(c, request_id, "Trage das im feld einsparungen ein")
    assert body["changed"] is True, body["text"]
    assert "einspar" in body["text"].lower()
    assert "statusfeld" not in body["text"].lower()
    with Session() as db:
        request = db.get(Request, request_id)
        assert request.field_values()["benefit_savings"]
        assert "übernehmen" not in request.field_values()["benefit_savings"].lower()
        notes = db.scalars(
            select(StatusUpdate).where(StatusUpdate.request_id == request_id)
        ).all()
        assert not notes

    _talk(c, request_id, "schreib das in status")
    redirect = _talk(c, request_id, "nicht in status sondern im feld ergänzung")
    assert redirect["changed"] is True, redirect["text"]
    assert "statusfeld" not in redirect["text"].lower()
    with Session() as db:
        request = db.get(Request, request_id)
        assert request.field_values()["benefit_savings"]


def test_statusfeld_nach_wohin(client, monkeypatch):
    monkeypatch.setattr("app.services.ticket_chat.web_search", lambda query, limit=3: [])
    c, Session, request_id = client
    first = _talk(c, request_id, "recherchiere best practice")
    missing = _talk(c, request_id, "schreib das")
    assert missing["changed"] is False
    assert "Wohin" in missing["text"]
    body = _talk(c, request_id, "in das statusfeld")
    assert body["changed"] is True, body["text"]
    assert "steckbrief" not in body["text"].lower()
    with Session() as db:
        notes = db.scalars(
            select(StatusUpdate).where(StatusUpdate.request_id == request_id)
        ).all()
        assert notes
        offer = first["text"].split("Übernehmen")[0].strip()
        assert offer in notes[-1].summary


def test_statusfrage_bleibt_workflow(client):
    c, _, request_id = client
    body = _talk(c, request_id, "was ist der status")
    assert body["changed"] is False
    assert "Steckbrief" in body["text"]


def test_hilfe_nennt_recherche(client):
    c, _, request_id = client
    body = _talk(c, request_id, "was kannst du")
    assert "recherch" in body["text"].lower()


def test_sucht_online_nach_einsparungen(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.ticket_chat.web_search",
        lambda query, limit=3: [
            {
                "title": "Papierlose Anträge sparen Aufwand",
                "url": "https://example.com/spar",
                "snippet": "Weniger Durchlaufzeit, weniger Druckkosten.",
            }
        ],
    )
    c, Session, request_id = client
    body = _talk(c, request_id, "such bitte online nach einsparungen zu diesem thema")
    assert body["changed"] is False
    assert "Nur dieser Change" not in body["text"]
    assert "Papierlose" in body["text"] or "Web:" in body["text"]
    assert "übernehmen" in body["text"].lower()
    assert "einspar" in body["text"].lower()
    yes = _talk(c, request_id, "ja")
    assert yes["changed"] is True, yes["text"]
    with Session() as db:
        request = db.get(Request, request_id)
        stored = request.field_values()["benefit_savings"]
        assert stored
        assert "übernehmen" not in stored.lower()


def test_sieht_risiko_recherchiert_und_fragt(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.ticket_chat.web_search",
        lambda query, limit=3: [
            {
                "title": "Akzeptanzrisiko bei digitaler Urlaubserfassung",
                "url": "https://example.com/risk",
                "snippet": "Betriebsrat und Schulung.",
            }
        ],
    )
    c, Session, request_id = client
    body = _talk(c, request_id, "was siehst du hier an risiko")
    assert body["changed"] is False
    assert "Nur dieser Change" not in body["text"]
    assert "ist leer" not in body["text"].lower()
    assert "übernehmen" in body["text"].lower()
    assert "risiko" in body["text"].lower()
    yes = _talk(c, request_id, "ja")
    assert yes["changed"] is True, yes["text"]
    with Session() as db:
        request = db.get(Request, request_id)
        stored = request.field_values()["risks_obstacles"]
        assert stored
        assert "übernehmen" not in stored.lower()


STEPS_OFFER = (
    "1. Konkreten Aufstellungsort am Eingang festlegen.\n"
    "2. Inhaltliche Skripte für die Begrüßung definieren.\n"
    "3. Technische Machbarkeit und Hardwarebedarf prüfen.\n"
    "4. Verantwortlichen für Betrieb und Wartung benennen."
)


def test_status_nimmt_schritte_nicht_die_kurzzeile(client, monkeypatch):
    replies = iter(
        [
            {
                "reply": STEPS_OFFER,
                "fields": {},
                "status": None,
                "priority": None,
                "comment": None,
            },
            {
                "reply": "Verantwortung für die nächsten Schritte liegt bei Justin.",
                "fields": {},
                "status": None,
                "priority": None,
                "comment": None,
            },
        ]
    )

    class Fake:
        name = "openai"

        def complete_json(self, system, user):
            return next(replies)

    fake = Fake()
    monkeypatch.setattr("app.api.requests.build_provider_from_runtime", lambda runtime: fake)
    c, Session, request_id = client
    first = _talk(c, request_id, "was sind die nächsten schritte")
    assert "Aufstellungsort" in first["text"]
    _talk(c, request_id, "ok darum soll sich justin kümmern")
    body = _talk(c, request_id, "trag das in den status ein")
    assert body["changed"] is True, body["text"]
    with Session() as db:
        notes = db.scalars(
            select(StatusUpdate).where(StatusUpdate.request_id == request_id)
        ).all()
        assert notes
        assert notes[-1].next_steps
        assert "Aufstellungsort" in notes[-1].next_steps
        assert "Skripte" in notes[-1].next_steps
        assert "Justin" in (notes[-1].summary or "")
