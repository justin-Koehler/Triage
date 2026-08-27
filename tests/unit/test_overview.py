"""Problem, Loesung und Risiko sind eigene Saetze, keine Meldungs-Kopie."""

from app.domain.overview import formulate_problem, formulate_risk, formulate_solution, needs_rewrite


STORY = (
    "Urlaubsanträge laufen über ein Papierformular. Anträge gehen verloren, "
    "niemand sieht den Stand. Wir wollen ein digitales Formular."
)


def test_problem_is_ist_not_the_whole_story():
    problem = formulate_problem("Urlaub digitalisieren", STORY)
    assert "Papier" in problem or "Anträge" in problem
    assert "wollen" not in problem.lower()
    assert problem != STORY


def test_solution_is_soll_not_the_problem():
    problem = formulate_problem("Urlaub digitalisieren", STORY)
    solution = formulate_solution("Urlaub digitalisieren", STORY)
    assert "digital" in solution.lower()
    assert solution != problem
    assert solution != STORY
    assert "verloren" not in solution.lower()


def test_avatar_names_a_use_not_the_idea():
    story = "Es ist geplant, einen KI-Avatar im Standort Heilbronn einzuführen."
    problem = formulate_problem("KI-Avatar Heilbronn", story)
    solution = formulate_solution("KI-Avatar Heilbronn", story)
    assert "Empfang" in problem or "Beratung" in problem or "Erstkontakt" in problem
    assert "Empfang" in solution or "Beratung" in solution
    assert problem != solution


def test_needs_rewrite_catches_dumped_story():
    assert needs_rewrite(STORY, STORY) is True
    assert needs_rewrite("", STORY) is True
    assert needs_rewrite("keine", STORY) is True
    assert needs_rewrite("Anträge laufen auf Papier.", STORY, "Anträge laufen auf Papier.") is True
    assert needs_rewrite("Anträge laufen auf Papier.", STORY, "Anträge laufen digital.") is False


def test_risk_is_one_process_sentence():
    risk = formulate_risk("Urlaub digitalisieren", STORY)
    assert "Papier" in risk or "Excel" in risk
    assert "Betriebsrat" not in risk
    assert "Maßnahmen" not in risk
