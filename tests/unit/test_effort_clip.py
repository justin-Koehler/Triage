"""Unit tests for effort hint clipping and review."""

from unittest.mock import MagicMock

from app.services.effort import HINT_MAX, _clip_hint, as_pt, review_effort


def test_clip_keeps_short_project_line():
    out = _clip_hint(
        "Ähnlich wie Digital Twin TUM — oft 6–12 Monate. Bei uns kleinerer Einstieg."
    )
    assert "Digital Twin TUM" in out
    assert "Monate" in out
    assert len(out) <= HINT_MAX
    assert not out.endswith("…")


def test_clip_drops_jargon_sentence():
    out = _clip_hint(
        "Analog zum 'Digital Twin TUM' (oft 6–12 Monate). "
        "Hier kompakter Campus-Start: IT-lastig für 3D-Modellierung."
    )
    assert "Digital Twin TUM" in out
    assert "ähnlich wie" in out.lower()
    assert "IT-lastig" not in out
    assert "Analog" not in out
    assert len(out) <= HINT_MAX


def test_clip_drops_all_junk_to_empty():
    assert _clip_hint("Hoher Aufwand für IoT-Integration und Echtzeit-Sync.") == ""


def test_review_keeps_user_pt(monkeypatch):
    class Fake:
        name = "test"

        def complete_json(self, system, user):
            assert "Nutzer-Angabe" in user
            return {"rating": "eher_hoch", "span": "6–12", "why": "Spanne 6–12 PT. Wie SAP-Anbindung — oft 8 PT IT."}

    monkeypatch.setattr("app.services.effort.build_provider_from_runtime", lambda runtime: Fake())
    monkeypatch.setattr("app.services.effort.search_effort", lambda *a, **k: [])
    monkeypatch.setattr("app.services.effort.cases.search", lambda *a, **k: [])

    out = review_effort(
        MagicMock(),
        "SAP Schnittstelle für Campus",
        title="SAP",
        kind="it_request",
        fb=5,
        it=3,
    )
    assert out["fb"] == "5 PT"
    assert out["it"] == "3 PT"
    assert out["rating"] == "eher_hoch"
    assert out["effort"] == "M"


def test_as_pt_parses_strings():
    assert as_pt("8 PT") == 8.0
    assert as_pt("3,5") == 3.5
