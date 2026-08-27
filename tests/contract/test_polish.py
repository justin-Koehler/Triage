from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "polish.db"
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


def test_polish_uses_model_text(client, monkeypatch):
    class Fake:
        name = "test"

        def complete_text(self, system, user):
            assert "urlaub digital" in user
            assert "Ausformulieren" in user or "Klarziehen" in user
            return "Urlaubsanträge sollen digital erfasst werden."

    monkeypatch.setattr("app.services.polish.build_provider_from_runtime", lambda runtime: Fake())
    body = client.post(
        "/api/sessions/polish",
        json={"text": "urlaub digital machen", "title": "Urlaub"},
    ).json()
    assert body["text"] == "Urlaubsanträge sollen digital erfasst werden."


def test_polish_description_ignores_other_fields(client, monkeypatch):
    class Fake:
        name = "test"

        def complete_text(self, system, user):
            assert "Campus Service" not in user
            assert "Weniger Handarbeit" not in user
            assert "avatar für empfang" in user
            assert "Auftraggeber" in user or "Gemeinnützigkeit" in user
            assert "Beschreibung" in system
            return (
                "Am Empfang bleiben Orientierungsfragen am Personal hängen. "
                "Ein Avatar soll die Standardfragen vor Ort beantworten."
            )

    monkeypatch.setattr("app.services.polish.build_provider_from_runtime", lambda runtime: Fake())
    body = client.post(
        "/api/sessions/polish",
        json={
            "text": "avatar für empfang",
            "title": "KI-Avatar",
            "field": "description",
            "kind": "it_request",
            "fields": {
                "sponsor": "Campus Service",
                "title": "KI-Avatar",
                "benefit": "Weniger Handarbeit am Empfang.",
            },
        },
    ).json()
    assert "Empfang" in body["text"]


def test_polish_description_drops_meta_echo(client, monkeypatch):
    class Fake:
        name = "test"

        def complete_text(self, system, user):
            return (
                "Am Empfang bleiben Standardfragen am Personal hängen. "
                "Die Bauabteilung trägt den Auftrag für diese Maßnahme. "
                "Die Komponente sad bildet die technische Basis für den Avatar. "
                "Das Projekt verfolgt dabei einen gemeinnützigen Charakter. "
                "Ein Avatar soll die Fragen vor Ort beantworten."
            )

    monkeypatch.setattr("app.services.polish.build_provider_from_runtime", lambda runtime: Fake())
    body = client.post(
        "/api/sessions/polish",
        json={
            "text": "avatar für empfang, standardfragen",
            "field": "description",
            "fields": {"sponsor": "Bau", "components": "sad", "nonprofit": "Ja"},
        },
    ).json()
    text = body["text"]
    assert "Empfang" in text or "Avatar" in text
    assert "Bauabteilung" not in text
    assert "trägt den Auftrag" not in text
    assert "Komponente sad" not in text
    assert "gemeinnützig" not in text.lower()


def test_polish_risks_uses_web_hits(client, monkeypatch):
    class Fake:
        name = "test"

        def complete_text(self, system, user):
            assert "Webrecherche" in user
            assert "Parallelbetrieb" in user
            assert "Bekannte Risiken" in system or "Risiken" in system
            return "Papier bleibt parallel, wenn der alte Weg offen ist."

    monkeypatch.setattr("app.services.polish.build_provider_from_runtime", lambda runtime: Fake())
    monkeypatch.setattr(
        "app.services.polish.search_risks",
        lambda title, description, limit=4: [
            {
                "title": "Einführungsrisiken",
                "url": "https://example.com/r",
                "snippet": "Parallelbetrieb und geringe Adoption.",
            }
        ],
    )
    body = client.post(
        "/api/sessions/polish",
        json={
            "text": "Alte Wege bleiben.",
            "title": "Urlaub digital",
            "field": "risks",
            "fields": {"description": "Urlaubsanträge auf Papier ersetzen."},
        },
    ).json()
    assert "Papier" in body["text"] or "parallel" in body["text"].lower()


def test_polish_description_asks_for_ist_problem_soll(client, monkeypatch):
    class Fake:
        name = "test"

        def complete_text(self, system, user):
            assert "Kein Papier mehr im Sekretariat." in user
            assert "Ist → Problem → Soll" in system or "Ist → Problem → Soll" in user
            assert "Klarziehen" in user or "Ausformulieren" in user
            return (
                "Urlaubsanträge laufen auf Papier über das Sekretariat. "
                "Anträge gehen verloren, der Stand ist unklar. "
                "Die Erfassung soll digital mit nachvollziehbarer Freigabe laufen."
            )

    monkeypatch.setattr("app.services.polish.build_provider_from_runtime", lambda runtime: Fake())
    body = client.post(
        "/api/sessions/polish",
        json={
            "text": "Kein Papier mehr im Sekretariat. Anträge laufen digital.",
            "field": "description",
        },
    ).json()
    assert "Papier" in body["text"] or "digital" in body["text"]


def test_polish_description_expand_for_thin_draft(client, monkeypatch):
    class Fake:
        name = "test"

        def complete_text(self, system, user):
            assert "Ausformulieren" in user
            assert "Systeme" in system or "IT Request" in system
            return (
                "Am Empfang bleiben Standardfragen am Personal hängen. "
                "Ein Avatar soll die Fragen vor Ort beantworten."
            )

    monkeypatch.setattr("app.services.polish.build_provider_from_runtime", lambda runtime: Fake())
    body = client.post(
        "/api/sessions/polish",
        json={
            "text": "avatar empfang",
            "field": "description",
            "kind": "it_request",
        },
    ).json()
    assert "Empfang" in body["text"] or "Avatar" in body["text"]


def test_polish_description_revise_for_prose(client, monkeypatch):
    class Fake:
        name = "test"

        def complete_text(self, system, user):
            assert "Klarziehen" in user
            assert "Prozess" in system or "Change" in system
            return (
                "Urlaubsanträge laufen auf Papier über das Sekretariat. "
                "Anträge gehen verloren. "
                "Die Erfassung soll digital laufen."
            )

    monkeypatch.setattr("app.services.polish.build_provider_from_runtime", lambda runtime: Fake())
    body = client.post(
        "/api/sessions/polish",
        json={
            "text": (
                "Urlaubsanträge laufen auf Papier über das Sekretariat. "
                "Anträge gehen verloren, der Stand ist unklar und niemand weiß Bescheid."
            ),
            "field": "description",
            "kind": "change_request",
        },
    ).json()
    assert "Papier" in body["text"] or "digital" in body["text"]


def test_polish_benefit_uses_draft_not_sibling_overview(client, monkeypatch):
    class Fake:
        name = "test"

        def complete_text(self, system, user):
            assert "Weniger Nachfragen am Empfang." in user
            assert "KI-Nutzen-Original" not in user
            assert "verbindlich" in user
            return "Weniger Nachfragen am Empfang."

    monkeypatch.setattr("app.services.polish.build_provider_from_runtime", lambda runtime: Fake())
    body = client.post(
        "/api/sessions/polish",
        json={
            "text": "Weniger Nachfragen am Empfang.",
            "field": "benefit",
            "title": "Avatar",
            "fields": {
                "description": "Avatar am Empfang.",
                "benefit": "KI-Nutzen-Original aus der Übersicht.",
                "reason": "KI-Begründung-Original.",
            },
        },
    ).json()
    assert "Nachfragen" in body["text"]
    assert "KI-Nutzen-Original" not in body["text"]


def test_polish_without_llm_returns_error(client):
    r = client.post(
        "/api/sessions/polish",
        json={"text": "urlaub digital machen", "title": "Urlaub"},
    )
    assert r.status_code == 503
