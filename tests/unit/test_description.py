from __future__ import annotations

from app.domain.description import (
    CHANGE_FOCUS,
    IT_FOCUS,
    description_job,
    description_user_prompt,
    draft_is_prose,
    draft_is_thin,
    kind_focus,
    normalize_description,
    polish_mode,
    score_description,
)


def test_kind_focus_splits_change_and_it():
    assert "Prozess" in kind_focus("change_request")
    assert kind_focus("change_request") == CHANGE_FOCUS
    assert "Systeme" in kind_focus("it_request")
    assert kind_focus("it_request") == IT_FOCUS
    assert "offen" in kind_focus("").lower() or "Art" in kind_focus("")


def test_polish_mode_thin_vs_prose():
    assert draft_is_thin("urlaub digital")
    assert polish_mode("urlaub digital") == "expand"
    prose = (
        "Urlaubsanträge laufen auf Papier über das Sekretariat. "
        "Anträge gehen verloren, der Stand ist unklar."
    )
    assert draft_is_prose(prose)
    assert polish_mode(prose) == "revise"


def test_description_prompts_carry_mode_and_kind():
    user = description_user_prompt("avatar empfang", "it_request")
    assert "Ausformulieren" in user
    assert "IT Request" in user or "Systeme" in user
    job = description_job("change_request")
    assert "Ist → Problem → Soll" in job
    assert "Change Request" in job or "Prozess" in job


def test_score_ok_for_ist_problem_soll():
    text = (
        "Urlaubsanträge laufen heute auf Papier. "
        "Anträge gehen verloren, niemand sieht den Stand. "
        "Die Erfassung soll digital mit Freigabe laufen."
    )
    scored = score_description(text)
    assert scored.ok
    assert scored.sentences == 3
    assert scored.has_soll


def test_score_flags_meta_and_marketing():
    text = (
        "Die Bauabteilung trägt den Auftrag. "
        "Wir schließen die Lücke mit einer signifikanten Lösung. "
        "Danach wird alles effizienter."
    )
    scored = score_description(text)
    assert not scored.ok
    assert "meta_echo" in scored.issues or "marketing" in scored.issues


def test_normalize_drops_meta_and_caps_sentences():
    raw = (
        "Am Empfang bleiben Fragen hängen. "
        "Die Bauabteilung trägt den Auftrag für diese Maßnahme. "
        "Ein Avatar soll die Fragen beantworten. "
        "Zusätzlich kommt noch ein fünfter Satz dazu. "
        "Und ein sechster Satz auch."
    )
    out = normalize_description(raw, "avatar empfang")
    assert "trägt den Auftrag" not in out
    assert out.count(".") <= 4
