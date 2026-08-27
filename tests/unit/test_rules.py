"""Regeln des Change-Steckbriefs."""

from app.domain.fieldspec import get_rules
from app.domain.types import RequestKind
from app.triage.engine import Diagnosis, Draft, TriageEngine

JIRA_KEYS = {
    "start_date": "start_date",
    "end_date": "end_date",
    "sponsor": "sponsor",
    "approver": "approver",
    "components": "components",
    "benefit_risk": "benefit_risk",    "benefit_savings": "benefit_savings",
    "problem": "problem",
    "solution_goals": "solution_goals",
    "risks_obstacles": "risks_obstacles",
    "similar_solution": "similar_solution",
    "change_lead": "change_lead",
    "fb_owner": "fb_owner",
    "process_owner": "process_owner",
    "solution_owner": "solution_owner",
    "stakeholder": "stakeholder",
    "company": "company",
    "ordering_company": "ordering_company",
    "cost_unit": "cost_unit",
    "cost_center": "cost_center",
    "effort_container": "effort_container",
    "project_id": "project_id",
    "extra_account": "extra_account",
    "solution_exists": "solution_exists",
    "solution_type": "solution_type",
    "concept_scs_pt": "concept_scs_pt",
    "operate_scs_pt": "operate_scs_pt",
    "effort_tshirt": "effort_tshirt",
}


def test_budget_is_eight_bundles():
    rules = get_rules()
    assert rules.max_questions == 8
    assert rules.budget_for(RequestKind.CHANGE_REQUEST) == 8
    assert rules.budget_for(RequestKind.IT_REQUEST) == 8


def test_two_kinds_exist():
    assert set(get_rules().kinds) == {
        RequestKind.CHANGE_REQUEST,
        RequestKind.IT_REQUEST,
    }


def test_jira_labels_have_keys():
    change = get_rules().spec(RequestKind.CHANGE_REQUEST).field_map()
    it = get_rules().spec(RequestKind.IT_REQUEST).field_map()
    for key in JIRA_KEYS:
        assert key in it, key
    # Non-IT Changes zeigen keine IT-Aufwandsfelder.
    assert "concept_scs_pt" not in change
    assert "operate_scs_pt" not in change
    assert "effort_tshirt" not in change
    assert "effort_sheet_url" in change
    assert "effort_sheet_url" in it


def test_change_request_dialog_fields_skip_it_effort_bundle():
    spec = get_rules().spec(RequestKind.CHANGE_REQUEST)
    asked = [f.key for f in spec.fields if f.hard and f.askable]
    assert "start_date" in asked
    assert "company" in asked
    assert "sponsor" in asked
    assert "assignee" not in asked
    assert "approver" in asked
    assert "components" in asked
    assert "change_lead" in asked
    assert "fb_owner" in asked
    assert "process_owner" in asked
    assert "solution_owner" not in asked
    assert "change_team" in asked
    assert "stakeholder" in asked
    assert "cost_unit" in asked
    assert spec.field_map()["sponsor"].auto is False
    assert spec.field_map()["change_lead"].auto is False


def test_nonprofit_offers_unknown_choice():
    spec = get_rules().spec(RequestKind.CHANGE_REQUEST).field_map()["nonprofit_dss"]
    assert spec.values == ("Ja", "Nein", "Weiß ich noch nicht")
    assert spec.normalize("ja") == "Ja"
    assert spec.normalize("Weiß ich noch nicht") == "Weiß ich noch nicht"


def test_it_request_dialog_fields_include_effort_bundle():
    spec = get_rules().spec(RequestKind.IT_REQUEST)
    asked = [f.key for f in spec.fields if f.hard and f.askable]
    assert "effort_tshirt" not in asked
    assert "concept_scs_pt" not in asked
    assert "operate_scs_pt" not in asked
    assert "solution_owner" in asked


def test_description_and_end_are_draft_not_askable():
    spec = get_rules().spec(RequestKind.CHANGE_REQUEST)
    for key in ("description", "end_date", "problem", "solution_goals"):
        field = spec.field_map()[key]
        assert field.fill == "draft"
        assert field.askable is False
        assert field.hard is True


def test_hub_fields_stay_unasked():
    spec = get_rules().spec(RequestKind.CHANGE_REQUEST)
    assert spec.field_map()["status_summary"].fill == "workspace"
    assert spec.field_map()["status_summary"].askable is False
    assert "approval_date" not in spec.field_map()
    assert "approval_state" not in spec.field_map()
    ablauf = spec.field_map()["status_ablauf"]
    assert ablauf.fill == "computed"
    assert ablauf.askable is False
    assert ablauf.group == "team"
    assert ablauf.label == "Ablauf"

    it_spec = get_rules().spec(RequestKind.IT_REQUEST)
    assert it_spec.field_map()["concept_cit_pt"].askable is False


def test_cit_fields_apply_for_it_requests():
    spec = get_rules().spec(RequestKind.IT_REQUEST)
    cit = spec.field_map()["concept_cit_pt"]
    assert cit.applies({}) is True
    assert cit.fill == "workspace"


def test_short_description_is_not_asked():
    class Silent:
        name = "test"

        def complete_json(self, system, user):  # pragma: no cover
            raise AssertionError("kein Modellaufruf")

    tri = TriageEngine(provider=Silent())
    draft = Draft(kind=RequestKind.CHANGE_REQUEST, values={"description": "Urlaub digital"})
    keys = [f.key for f in tri.missing_hard(draft, Diagnosis())]
    assert "description" not in keys
    assert "end_date" not in keys


def test_heuristic_seeds_problem_from_description():
    from app.triage.providers import LlmUnavailable

    class Dead:
        name = "dead"

        def complete_json(self, system, user):
            raise LlmUnavailable("kein modell")

    story = "Urlaub digitalisieren"
    tri = TriageEngine(provider=Dead())
    result = tri.run(Draft(), [story], 0)
    values = result.draft.values
    assert values["description"] == story
    assert values["problem"]
    assert values["solution_goals"]
    assert values["problem"] != story
    assert values["solution_goals"] != story
    assert values["problem"] != values["solution_goals"]
    rows = {row["key"]: row["value"] for row in tri.labeled_fields(result.draft)}
    assert rows["benefit_savings"] == ""
    assert "Einsparungen / zus. Umsatz" in tri.open_questions(result.draft)


def test_heuristic_seeds_benefits_from_the_story():
    from app.triage.providers import LlmUnavailable

    class Dead:
        name = "dead"

        def complete_json(self, system, user):
            raise LlmUnavailable("kein modell")

    story = (
        "Urlaubsanträge laufen über ein Papierformular. Anträge gehen verloren, "
        "niemand sieht den Stand. Wir wollen ein digitales Formular."
    )
    tri = TriageEngine(provider=Dead())
    result = tri.run(Draft(), [story], 0)
    values = result.draft.values
    assert "Papier" in values["benefit_savings"] or "Aufwand" in values["benefit_savings"]
    assert "verloren" in values["benefit_risk"]
