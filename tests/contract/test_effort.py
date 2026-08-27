from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "effort.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("LLM_PROVIDER", "none")
    monkeypatch.setenv("TICKET_PORT", "fake")
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "false")

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


def test_effort_review_uses_user_pt_not_model_numbers(client, monkeypatch):
    class Fake:
        name = "test"

        def complete_json(self, system, user):
            assert "span" in system
            assert "Spanne" in system or "span" in system
            assert "Nutzer-Angabe" in user
            assert "3 PT" in user or "8 PT" in user
            return {
                "rating": "angemessen",
                "span": "8–15",
                "why": "Spanne 8–15 PT: SAP-Anbindung mit begrenztem Scope.",
            }

    monkeypatch.setattr("app.services.effort.build_provider_from_runtime", lambda runtime: Fake())
    monkeypatch.setattr("app.services.effort.search_effort", lambda *a, **k: [])
    body = client.post(
        "/api/sessions/effort",
        json={
            "text": "SAP-Schnittstelle für Urlaubsanträge anbinden.",
            "title": "SAP Urlaub",
            "kind": "it_request",
            "fb": "3 PT",
            "it": "8 PT",
        },
    ).json()
    assert body["fb"] == "3 PT"
    assert body["it"] == "8 PT"
    assert body["effort"] == "M"
    assert body["rating"] == "angemessen"
    assert body["span"] == "8–15"
    assert "Spanne" in body["hint"] or "8–15" in body["hint"]
    assert "Keine Vergleichsdaten" not in body["hint"]
    assert len(body["hint"]) <= 240


def test_effort_change_zeros_it(client, monkeypatch):
    class Fake:
        name = "test"

        def complete_json(self, system, user):
            return {
                "rating": "eher_niedrig",
                "span": "6–12",
                "why": "Spanne 6–12 PT. Vier PT wirken knapp für die Abstimmung.",
            }

    monkeypatch.setattr("app.services.effort.build_provider_from_runtime", lambda runtime: Fake())
    monkeypatch.setattr("app.services.effort.search_effort", lambda *a, **k: [])
    body = client.post(
        "/api/sessions/effort",
        json={
            "text": "Neue Abstimmungsrunde zwischen Bau und Event.",
            "kind": "change_request",
            "fb": "4",
            "it": "12",
        },
    ).json()
    assert body["fb"] == "4 PT"
    assert body["it"] == "0 PT"
    assert body["effort"] == "S"
    assert body["rating"] == "eher_niedrig"


def test_effort_uses_web_hits_in_prompt(client, monkeypatch):
    class Fake:
        name = "test"

        def complete_json(self, system, user):
            assert "Webrecherche" in user or "Vergleichsfälle" in user
            assert "4–8 Wochen" in user or "4-8 Wochen" in user
            return {
                "rating": "angemessen",
                "span": "4–10",
                "why": (
                    "Spanne 4–10 PT. Sechs PT FB wirken realistisch. "
                    "Ähnlich Digitale Rechnungsfreigabe — oft 4–8 Wochen."
                ),
            }

    monkeypatch.setattr("app.services.effort.build_provider_from_runtime", lambda runtime: Fake())
    monkeypatch.setattr(
        "app.services.effort.search_effort",
        lambda title, description, limit=4: [
            {
                "title": "Digitale Rechnungsfreigabe",
                "url": "https://example.com/e",
                "snippet": "Einführung dauert typisch 4–8 Wochen.",
            }
        ],
    )
    body = client.post(
        "/api/sessions/effort",
        json={
            "text": "Rechnungsfreigabe soll digital und schneller laufen.",
            "title": "Rechnungsfreigabe digital",
            "kind": "change_request",
            "fb": "6 PT",
        },
    ).json()
    assert body["fb"] == "6 PT"
    assert "Rechnungsfreigabe" in body["hint"] or "Wochen" in body["hint"]
    assert "Spanne" in body["hint"] or "4–10" in body["hint"] or body.get("span")
    assert len(body["hint"]) <= 240


def test_effort_names_similar_project(client, monkeypatch):
    class Fake:
        name = "test"

        def complete_json(self, system, user):
            assert "Digital Twin TUM" in user
            return {
                "rating": "eher_hoch",
                "span": "18–40",
                "why": (
                    "Spanne 18–40 PT. 32 PT wirken eher hoch. Ähnlich wie Digital Twin TUM — "
                    "dort oft 6–12 Monate, bei uns kleinerer Einstieg."
                ),
            }

    monkeypatch.setattr("app.services.effort.build_provider_from_runtime", lambda runtime: Fake())
    monkeypatch.setattr(
        "app.services.effort.search_effort",
        lambda title, description, limit=4: [
            {
                "title": "Digital Twin TUM — Campus",
                "url": "https://example.com/tum",
                "snippet": "Projektlaufzeit typisch 6–12 Monate.",
            }
        ],
    )
    body = client.post(
        "/api/sessions/effort",
        json={
            "text": "Digital Twin für den Campus mit BIM.",
            "title": "Digital Twin",
            "kind": "it_request",
            "fb": "12",
            "it": "20",
        },
    ).json()
    assert body["rating"] == "eher_hoch"
    assert "Digital Twin TUM" in body["hint"]
    assert "Monate" in body["hint"]
    assert "IT-lastig" not in body["hint"]
    assert len(body["hint"]) <= 240


def test_effort_plain_language_rewrites_jargon(client, monkeypatch):
    class Fake:
        name = "test"

        def complete_json(self, system, user):
            return {
                "rating": "angemessen",
                "span": "15–35",
                "why": (
                    "Spanne 15–35 PT. Analog zum 'Digital Twin TUM' (oft 6–12 Monate). "
                    "Hier kompakter Campus-Start: IT-lastig für 3D-Modellierung "
                    "und Datenintegration, FB für fachliche Validierung."
                ),
            }

    monkeypatch.setattr("app.services.effort.build_provider_from_runtime", lambda runtime: Fake())
    monkeypatch.setattr("app.services.effort.search_effort", lambda *a, **k: [])
    body = client.post(
        "/api/sessions/effort",
        json={
            "text": "Digital Twin für den Campus.",
            "title": "Digital Twin",
            "kind": "it_request",
            "fb": "10",
            "it": "18",
        },
    ).json()
    hint = body["hint"]
    assert "Digital Twin TUM" in hint
    assert "ähnlich wie" in hint.lower() or "Ähnlich wie" in hint
    assert "IT-lastig" not in hint
    assert "Analog zum" not in hint
    assert "fachliche Validierung" not in hint
    assert len(hint) <= 240


def test_effort_clips_tech_list_keeps_named_project(client, monkeypatch):
    class Fake:
        name = "test"

        def complete_json(self, system, user):
            return {
                "rating": "eher_hoch",
                "span": "18–40",
                "why": (
                    "Spanne 18–40 PT. Ähnlich Digital Twin TUM — oft 6–12 Monate. "
                    "Hoher Aufwand für IoT-Integration, Echtzeit-Sync und 3D-Visualisierung."
                ),
            }

    monkeypatch.setattr("app.services.effort.build_provider_from_runtime", lambda runtime: Fake())
    monkeypatch.setattr("app.services.effort.search_effort", lambda *a, **k: [])
    body = client.post(
        "/api/sessions/effort",
        json={
            "text": "Digital Twin für den Campus mit BIM.",
            "title": "Digital Twin",
            "kind": "it_request",
            "fb": "12",
            "it": "20",
        },
    ).json()
    assert "Digital Twin TUM" in body["hint"]
    assert "Echtzeit-Sync" not in body["hint"]
    assert "3D-Visualisierung" not in body["hint"]
    assert len(body["hint"]) <= 240


def test_effort_without_user_pt_fails(client, monkeypatch):
    monkeypatch.setattr("app.services.effort.search_effort", lambda *a, **k: [])
    r = client.post(
        "/api/sessions/effort",
        json={
            "text": "Urlaubsanträge digitalisieren statt Papierformular",
            "title": "Urlaub digital",
            "kind": "change_request",
        },
    )
    assert r.status_code == 503


def test_effort_without_llm_uses_fallback_hint(client, monkeypatch):
    monkeypatch.setattr("app.services.effort.search_effort", lambda *a, **k: [])
    body = client.post(
        "/api/sessions/effort",
        json={
            "text": "Urlaubsanträge digitalisieren statt Papierformular",
            "title": "Urlaub digital",
            "kind": "change_request",
            "fb": "8 PT",
        },
    ).json()
    assert body["fb"] == "8 PT"
    assert body["it"] == "0 PT"
    assert body["effort"] == "M"
    assert body["span"]
    assert "Spanne" in body["hint"]
    assert "Keine Vergleichsdaten" not in body["hint"]
    assert body["hint"]


def test_effort_rejects_empty_comparison_excuse(client, monkeypatch):
    class Fake:
        name = "test"

        def complete_json(self, system, user):
            return {
                "rating": "unsicher",
                "span": "",
                "why": "Unsicher: Keine Vergleichsdaten verfügbar. Ein Digital Twin ist komplex.",
            }

    monkeypatch.setattr("app.services.effort.build_provider_from_runtime", lambda runtime: Fake())
    monkeypatch.setattr("app.services.effort.search_effort", lambda *a, **k: [])
    body = client.post(
        "/api/sessions/effort",
        json={
            "text": (
                "Digital Twin für den Campus mit BIM, 3D-Darstellung und "
                "Anbindung an bestehende Systeme. Pilot für zwei Gebäude."
            ),
            "title": "Digital Twin",
            "kind": "it_request",
            "fb": "10",
            "it": "20",
        },
    ).json()
    assert "Keine Vergleichsdaten" not in body["hint"]
    assert "Spanne" in body["hint"] or "–" in body["hint"]
    assert body["span"]
    assert body["rating"] != "unsicher" or "Spanne" in body["hint"]
