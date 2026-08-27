"""Kulturelle Risiken: Stichwort trifft Muster, sonst nichts."""

from app.domain.risks import apply_to_values, load_patterns, match_patterns, warning_text


def test_patterns_load():
    names = {p.name for p in load_patterns()}
    assert "zusammenlegung" in names
    assert "kulturwandel" in names


def test_merge_hits_zusammenlegung():
    hits = match_patterns("Zusammenlegung von zwei Abteilungen")
    assert hits
    assert hits[0].pattern.name == "zusammenlegung"


def test_negation_skips_the_pattern():
    assert match_patterns("keine Zusammenlegung, nur ein Toolwechsel") == []


def test_urlaub_is_not_a_cultural_risk():
    assert match_patterns(
        "Urlaubsanträge sollen digital laufen, der Prozess ist Papier"
    ) == []


def test_apply_replaces_keine_and_warns():
    values = {"risks_obstacles": "keine"}
    warning = apply_to_values(values, "Zwei Abteilungen fusionieren")
    assert warning
    assert "Risiko" in warning
    assert "keine" not in values["risks_obstacles"].lower()
    assert "Betriebsrat" in values["risks_obstacles"]


def test_warning_without_field_change_when_empty_text():
    values = {"risks_obstacles": "keine"}
    assert apply_to_values(values, "SAP-Schnittstelle nach FiBu") is None
    assert values["risks_obstacles"] == "keine"


def test_keeps_stated_risks_and_appends():
    values = {"risks_obstacles": "Budget ist knapp"}
    warning = apply_to_values(values, "kultureller Wandel in der Führung")
    assert warning
    assert values["risks_obstacles"].startswith("Budget ist knapp")
    assert "Unsicherheit" in values["risks_obstacles"] or "Kultur" in values["risks_obstacles"]


def test_warning_text_is_short():
    hits = match_patterns("Reorganisation der zwei Abteilungen")
    text = warning_text(hits)
    assert text
    assert len(text) <= 420
