"""Risiken und aehnliche Loesungen: Meinung, Ja/Nein, Extra-Text."""

from __future__ import annotations

from app.domain.types import RequestKind
from app.services.collab import (
    COLLAB_RISKS,
    COLLAB_SIMILAR,
    apply_decision,
    classify,
    next_step,
    propose_risks,
    propose_similar,
    think_risk,
)
from app.triage.engine import Draft


def draft(**values) -> Draft:
    return Draft(
        kind=RequestKind.CHANGE_REQUEST,
        title="Verkauf und Einkauf zusammenlegen",
        values=values,
    )


def test_classify_yes_no_skip_add():
    assert classify("ja") == ("yes", "")
    assert classify("Übernehmen") == ("yes", "")
    assert classify("ja, und der Betriebsrat")[0] == "yes"
    assert classify("ja, und der Betriebsrat")[1] == "und der Betriebsrat"
    assert classify("Nicht übernehmen") == ("no", "")
    assert classify("nein") == ("no", "")
    assert classify("Weiß ich noch nicht") == ("skip", "")
    assert classify("keine Ahnung") == ("skip", "")
    assert classify("Kulturkonflikt in den Teams") == ("add", "Kulturkonflikt in den Teams")


def test_yes_writes_proposal_no_clears_skip_keeps():
    base = draft(risks_obstacles="alte Saat")
    yes = apply_decision(Draft.from_dict(base.to_dict()), COLLAB_RISKS, "ja", "Betriebsrat bremst")
    assert yes.values["risks_obstacles"] == "Betriebsrat bremst"

    no = apply_decision(Draft.from_dict(base.to_dict()), COLLAB_RISKS, "nein", "Betriebsrat bremst")
    assert not no.values.get("risks_obstacles")

    skip = apply_decision(Draft.from_dict(base.to_dict()), COLLAB_RISKS, "Weiß ich noch nicht", "Betriebsrat")
    assert skip.values["risks_obstacles"] == "alte Saat"


def test_extra_text_appends_to_proposal():
    item = apply_decision(
        draft(),
        COLLAB_RISKS,
        "ja, und Schnittstellen fehlen",
        "Betriebsrat bremst",
    )
    assert "Betriebsrat bremst" in item.values["risks_obstacles"]
    assert "Schnittstellen fehlen" in item.values["risks_obstacles"]

    added = apply_decision(draft(), COLLAB_RISKS, "Nur die IT-Kapazität", "Betriebsrat")
    assert "Betriebsrat" in added.values["risks_obstacles"]
    assert "IT-Kapazität" in added.values["risks_obstacles"]


def test_next_step_is_risks_then_similar():
    assert next_step({}) == COLLAB_RISKS
    assert next_step({"collab_done": [COLLAB_RISKS]}) == COLLAB_SIMILAR
    assert next_step({"collab_done": [COLLAB_RISKS, COLLAB_SIMILAR]}) is None


def test_merge_pattern_becomes_risk_proposal():
    proposal, sources = propose_risks(
        draft(
            description="Wir legen Verkauf und Einkauf zusammen. Zwei Abteilungen fusionieren."
        )
    )
    assert "Betriebsrat" in proposal or "Kultur" in proposal
    assert sources == [] or sources[0]["kind"] == "knowledge"


def test_similar_is_a_pointer_not_a_solution_dump(monkeypatch):
    monkeypatch.setattr("app.services.collab.find_similar", lambda *a, **k: [])
    monkeypatch.setattr("app.services.collab.web_search", lambda *a, **k: [])
    item = Draft(
        kind=RequestKind.CHANGE_REQUEST,
        title="Urlaubsanträge digitalisieren",
        values={
            "description": (
                "Urlaubsanträge laufen über ein Papierformular. "
                "Wir wollen ein digitales Formular mit Freigabe."
            )
        },
    )
    proposal, sources = propose_similar(None, item)
    assert sources
    assert proposal.startswith("KB-0007")
    assert "Erwartete Widerstände" not in proposal
    assert "Excel-Datei" not in proposal
    assert "Führungskraft, dann Personal" not in proposal


def test_urlaub_gets_a_process_risk_not_a_culture_risk():
    item = Draft(
        kind=RequestKind.CHANGE_REQUEST,
        title="Urlaubsanträge digitalisieren",
        values={
            "description": (
                "Urlaubsanträge laufen über ein Papierformular. "
                "Wir wollen ein digitales Formular mit Freigabe."
            ),
            "problem": "Papier, Anträge gehen verloren.",
        },
    )
    proposal, _ = propose_risks(item, hits=[])
    assert proposal
    assert "Papier" in proposal or "Excel" in proposal or "Weg" in proposal
    assert "Betriebsrat" not in proposal
    assert "Kultur" not in proposal


def test_think_risk_uses_the_model():
    class Fake:
        name = "ollama:test"

        def complete_json(self, system, user):
            assert "Change-Berater" in system
            return {"risk": "Führungskräfte geben weiter auf Papier frei."}

    item = Draft(
        kind=RequestKind.CHANGE_REQUEST,
        title="Urlaubsanträge digitalisieren",
        values={"description": "Urlaubsanträge digital, bisher Papier."},
    )
    assert think_risk(item, Fake()) == "Führungskräfte geben weiter auf Papier frei."
