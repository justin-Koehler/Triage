from app.domain.calc import compute, parse_number


def test_parse_german_number():
    assert parse_number("1,5 PT") == 1.5
    assert parse_number("") == 0


def test_compute_drops_legacy_total_fields():
    values = {
        "concept_scs_pt": "2",
        "concept_scs_total": "1.600,00 €",
        "operate_cit_total": "0,00 €",
    }
    cleaned = compute(values)
    assert "concept_scs_total" not in cleaned
    assert "operate_cit_total" not in cleaned
    assert cleaned["concept_scs_pt"] == "2"
