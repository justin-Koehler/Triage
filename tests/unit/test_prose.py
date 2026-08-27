from app.services.prose import clean_prose


def test_clean_prose_strips_label_and_quotes():
    assert clean_prose('Nutzen: "Weniger Aufwand."') == "Weniger Aufwand."


def test_clean_prose_strips_fences():
    assert clean_prose("```\nDigital erfassen.\n```") == "Digital erfassen."
