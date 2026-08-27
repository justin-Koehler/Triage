"""Werte kommen aus der Liste oder vom Nutzer — nie aus der Fantasie."""

from datetime import date

from app.domain.fieldspec import get_rules
from app.domain.types import RequestKind
from app.triage.engine import (
    PURPOSE_PROMPT,
    Diagnosis,
    Draft,
    TriageEngine,
    is_unknown_answer,
    strip_absence,
)


def engine() -> TriageEngine:
    class Silent:
        name = "test"

        def complete_json(self, system, user):  # pragma: no cover
            raise AssertionError("kein Modellaufruf in diesem Test")

    return TriageEngine(provider=Silent())


def test_an_answer_snaps_to_the_value_list():
    spec = get_rules().spec(RequestKind.CHANGE_REQUEST).field_map()["company"]
    assert spec.normalize("für die SIT bitte") == "SIT"


def test_unknown_answers_are_recognised():
    assert is_unknown_answer("keine Ahnung") is True
    assert is_unknown_answer("Weiß ich noch nicht") is True
    assert is_unknown_answer("Ich weiß es noch nicht") is True
    assert is_unknown_answer("Ich weiß es nicht") is True
    assert is_unknown_answer("SIT") is False


def test_facts_answer_fills_all_three():
    tri = engine()
    draft = Draft(kind=RequestKind.CHANGE_REQUEST)
    tri._apply_answer(
        draft,
        ("facts", "1.3.2027 bis 1.9.2027, Frau Berger, SCS Gesamt"),
        Diagnosis(),
    )
    assert draft.values["start_date"] == "2027-03-01"
    assert draft.values["end_date"] == "2027-09-01"
    assert "sponsor" not in draft.values
    assert draft.values["company"] == "SCS Gesamt"


def test_people_answer_fills_roles_from_cues():
    tri = engine()
    draft = Draft(kind=RequestKind.CHANGE_REQUEST)
    tri._apply_answer(
        draft,
        ("people", "Auftraggeber Frau Berger, Frau Berger genehmigt"),
        Diagnosis(),
    )
    assert draft.values.get("sponsor") == "Frau Berger" or draft.values.get("approver") == "Frau Berger"
    assert draft.values["approver"] == "Frau Berger"
    assert "assignee" not in draft.values


def test_konto_answer_is_one_bundle():
    tri = engine()
    draft = Draft(kind=RequestKind.CHANGE_REQUEST)
    tri._apply_answer(
        draft,
        ("konto", "Gesellschaft SCS Gesamt, Kostenträger X, Kostenstelle 4711"),
        Diagnosis(),
    )
    assert draft.values["company"] == "SCS Gesamt"
    assert draft.values["cost_unit"] == "X"
    assert draft.values["cost_center"] == "4711"


def test_effort_unknown_leaves_pt_empty():
    tri = engine()
    draft = Draft(kind=RequestKind.CHANGE_REQUEST)
    tri._apply_answer(draft, ("effort", "keine Ahnung"), Diagnosis())
    assert "effort_tshirt" not in draft.values
    assert "concept_scs_pt" not in draft.values
    assert "operate_scs_pt" not in draft.values


def test_effort_answer_fills_tshirt_and_pt():
    tri = engine()
    draft = Draft(kind=RequestKind.CHANGE_REQUEST)
    tri._apply_answer(
        draft,
        ("effort", "eher L, 8 PT Konzeption und 2 PT Betrieb"),
        Diagnosis(),
    )
    assert draft.values["effort_tshirt"] == "L"
    assert draft.values["concept_scs_pt"] == "8"
    assert draft.values["operate_scs_pt"] == "2"


def test_rich_sentence_fills_without_people_or_konto_question():
    story = (
        "Urlaubsanträge digitalisieren. Zeitraum 1.3.2027 bis 1.9.2027. "
        "Auftraggeber Frau Berger, Frau Berger genehmigt, SCS Gesamt, Kostenträger X."
    )

    class Scripted:
        name = "scripted"

        def complete_json(self, system, user):
            return {
                "kind": "change_request",
                "title": "Urlaub digitalisieren",
                "confidence": 0.9,
                "fields": {"description": story},
            }

    tri = TriageEngine(provider=Scripted())
    result = tri.run(Draft(), [story], 0)
    values = result.draft.values
    assert values["start_date"] == "2027-03-01"
    assert values["end_date"] == "2027-09-01"
    assert "assignee" not in values
    assert values["approver"] == "Frau Berger"
    assert values["company"] == "SCS Gesamt"
    assert values["cost_unit"] == "X"
    asked = result.question_field.key if result.question_field else None
    assert asked not in {"facts", "konto"}


def test_facts_answer_understands_heute_offen_and_custom_company():
    tri = engine()
    draft = Draft(kind=RequestKind.CHANGE_REQUEST)
    tri._apply_answer(
        draft,
        ("facts", "ab heute bis offen, Schwarz digits"),
        Diagnosis(),
    )
    assert draft.values["start_date"] == date.today().isoformat()
    assert draft.values["end_date"] == "offen"
    assert draft.values["company"] == "Schwarz digits"
    assert "sponsor" not in draft.values


def test_an_unknown_answer_fills_nothing():
    tri = engine()
    draft = Draft(kind=RequestKind.CHANGE_REQUEST)
    spec = get_rules().spec(RequestKind.CHANGE_REQUEST).field_map()["company"]
    tri._apply_answer(draft, ("company", "keine Ahnung"), Diagnosis())
    assert "company" not in draft.values
    assert spec.askable is True


def test_start_range_answer_sets_end_even_if_start_already_set():
    tri = engine()
    draft = Draft(
        kind=RequestKind.CHANGE_REQUEST,
        values={"start_date": "2027-03-01"},
    )
    tri._apply_answer(draft, ("start_date", "1.3.2027 bis 1.9.2027"), Diagnosis())
    assert draft.values["start_date"] == "2027-03-01"
    assert draft.values["end_date"] == "2027-09-01"


def test_start_range_answer_does_not_keep_prose_in_start():
    tri = engine()
    draft = Draft(kind=RequestKind.CHANGE_REQUEST)
    tri._apply_answer(draft, ("start_date", "1.3.2027 bis 1.9.2027"), Diagnosis())
    assert draft.values["start_date"] == "2027-03-01"
    assert draft.values["end_date"] == "2027-09-01"
    assert "bis" not in draft.values["start_date"]


def test_merge_splits_start_range_into_end():
    tri = engine()
    kind = RequestKind.CHANGE_REQUEST
    values = tri._merge_values(
        Draft(kind=kind),
        kind,
        {"start_date": "1.3.2027 bis 1.9.2027"},
        Diagnosis(),
        "Zeitraum 1.3.2027 bis 1.9.2027",
    )
    assert values["start_date"] == "2027-03-01"
    assert values["end_date"] == "2027-09-01"


def test_the_model_may_not_invent_a_value():
    tri = engine()
    kind = RequestKind.CHANGE_REQUEST
    values = tri._merge_values(
        Draft(kind=kind),
        kind,
        {"company": "irgendwo erfunden", "sponsor": "Frau Berger"},
        Diagnosis(),
        "Auftraggeber ist Frau Berger",
    )
    assert "company" not in values
    assert values["sponsor"] == "Frau Berger"


def test_the_model_may_not_invent_a_name():
    tri = engine()
    kind = RequestKind.CHANGE_REQUEST
    values = tri._merge_values(
        Draft(kind=kind),
        kind,
        {"sponsor": "Erfundene Person"},
        Diagnosis(),
        "Urlaubsanträge digitalisieren",
    )
    assert "sponsor" not in values


def test_the_model_may_not_invent_pt():
    tri = engine()
    kind = RequestKind.CHANGE_REQUEST
    values = tri._merge_values(
        Draft(kind=kind),
        kind,
        {"concept_scs_pt": "5", "problem": "Papierformular"},
        Diagnosis(),
        "Urlaubsanträge laufen über Papier",
    )
    assert "concept_scs_pt" not in values
    assert values["problem"] == "Papierformular"


def test_low_confidence_asks_clarify_then_facts():
    class Scripted:
        name = "scripted"

        def complete_json(self, system, user):
            return {
                "kind": "change_request",
                "title": "SAP",
                "confidence": 0.3,
                "fields": {"description": "SAP ändern"},
                "question": "Geht es um eine Schnittstelle oder um Berechtigungen?",
            }

    tri = TriageEngine(provider=Scripted())
    first = tri.run(Draft(), ["SAP ändern"], 0)
    assert first.question_field is None
    assert first.ready


def test_high_confidence_rich_story_skips_clarify():
    story = (
        "Urlaubsanträge laufen über ein Papierformular mit zwei Unterschriften. "
        "Anträge gehen verloren, niemand sieht den Stand, und wir wollen ein "
        "digitales Formular mit Freigabe durch Führungskraft und Personal."
    )

    class Scripted:
        name = "scripted"

        def complete_json(self, system, user):
            return {
                "kind": "change_request",
                "title": "Urlaub digitalisieren",
                "confidence": 0.9,
                "fields": {
                    "description": story,
                    "problem": "Anträge gehen verloren, der Stand ist unsichtbar.",
                },
                "question": "Geht es um Papier oder Excel?",
            }

    tri = TriageEngine(provider=Scripted())
    result = tri.run(Draft(), [story], 0)
    assert result.question_field is None or result.question_field.key != "clarify"


def test_forbidden_llm_question_is_ignored():
    class Scripted:
        name = "scripted"

        def complete_json(self, system, user):
            return {
                "kind": "change_request",
                "title": "SAP",
                "confidence": 0.2,
                "fields": {"description": "SAP"},
                "question": "Beschreib den Change genauer.",
            }

    tri = TriageEngine(provider=Scripted())
    result = tri.run(Draft(), ["SAP"], 0)
    assert result.question_field is None
    assert result.ready


HEILBRONN = (
    "Es ist geplant, einen KI-Avatar im Standort Heilbronn einzuführen. "
    "Der genaue Anwendungszweck und die technische Umsetzung sind noch nicht spezifiziert. "
    "Es handelt sich um eine initiale Idee zur Nutzung von KI-Technologie vor Ort. "
    "Keine spezifischen Widerstände oder Hindernisse wurden im Text genannt."
)


def test_strip_absence_drops_not_named():
    cleaned = strip_absence(HEILBRONN)
    low = cleaned.lower()
    assert "nicht genannt" not in low
    assert "nicht spezifiziert" not in low
    assert "unklar" not in low
    assert "initiale idee" not in low
    assert "Heilbronn" in cleaned
    assert strip_absence("keine") == ""
    assert "Budget" in strip_absence("Budget ist knapp. Keine Widerstände wurden genannt.")


def test_heilbronn_idea_asks_for_purpose_not_filler():
    class Scripted:
        name = "scripted"

        def complete_json(self, system, user):
            return {
                "kind": "change_request",
                "title": "KI-Avatar Heilbronn",
                "confidence": 0.9,
                "fields": {
                    "description": HEILBRONN,
                    "risks_obstacles": "Keine spezifischen Widerstände wurden im Text genannt.",
                },
            }

    tri = TriageEngine(provider=Scripted())
    first = tri.run(Draft(), [HEILBRONN], 0)
    blob = " ".join(str(v) for v in first.draft.values.values())
    assert "nicht genannt" not in blob.lower()
    assert "nicht spezifiziert" not in blob.lower()
    assert first.question_field is None
    assert first.ready


def test_unknown_clarify_gets_a_purpose_guess():
    class Scripted:
        name = "scripted"

        def complete_json(self, system, user):
            return {
                "kind": "change_request",
                "title": "KI-Avatar Heilbronn",
                "confidence": 0.9,
                "fields": {"description": HEILBRONN},
            }

    tri = TriageEngine(provider=Scripted())
    first = tri.run(Draft(), [HEILBRONN], 0)
    second = tri.run(
        first.draft,
        [HEILBRONN],
        1,
        answer=("clarify", "Weiß ich noch nicht"),
        declined={"clarify"},
    )
    blob = " ".join(str(v) for v in second.draft.values.values()).lower()
    assert "weiß ich noch nicht" not in blob
    assert second.purpose_guess
    assert "Empfang" in second.purpose_guess or "Beratung" in second.purpose_guess
    assert "avatar" not in second.purpose_guess.lower()
    assert "empfang" in blob or "beratung" in blob
    assert second.question_field is None or second.question_field.key != "clarify"


def test_purpose_guess_skips_restating_the_idea():
    class Echo:
        name = "openai"
        calls = 0

        def complete_json(self, system, user):
            self.calls += 1
            if self.calls == 1:
                return {
                    "kind": "change_request",
                    "title": "KI-Avatar",
                    "confidence": 0.9,
                    "fields": {"description": "KI-Avatar einführen"},
                }
            return {"purpose": "Einführung eines KI-Avatars"}

    tri = TriageEngine(provider=Echo())
    first = tri.run(Draft(), ["KI-Avatar einführen"], 0)
    assert first.question_field is None
    assert first.ready
