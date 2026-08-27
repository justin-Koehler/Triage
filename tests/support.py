"""Gemeinsame Testhilfen."""

COLLAB_KEYS = frozenset({"collab_risks", "collab_similar"})
FACTS_KEY = "facts"
DIALOG_KEYS = frozenset(
    {
        "clarify",
        "facts",
        "people",
        "components",
        "roles",
        "value",
        "effort",
        "konto",
        "solution",
        "start_date",
        "sponsor",
        "approver",
        "change_lead",
        "fb_owner",
        "process_owner",
        "solution_owner",
        "change_team",
        "stakeholder",
        "company",
        "ordering_company",
        "project_id",
        "cost_unit",
        "cost_center",
        "extra_account",
        "effort_container",
        "benefit_risk",
        "benefit_savings",        "risks_obstacles",
        "similar_solution",
        "solution_exists",
        "solution_type",
    }
)
PACK = {
    "facts": ("start_date", "company"),
    "people": ("sponsor", "approver"),
    "roles": (
        "change_lead",
        "fb_owner",
        "process_owner",
        "solution_owner",
        "change_team",
        "stakeholder",
    ),
    "value": ("benefit_savings", "risks_obstacles"),
    "effort": ("concept_scs_pt", "operate_scs_pt"),
    "konto": ("company", "cost_unit", "cost_center", "effort_container", "extra_account"),
    "solution": ("solution_exists", "solution_type"),
}
LABELS = {
    "sponsor": "Auftraggeber",
    "approver": "Genehmigende Person",
    "change_lead": "Change-Leitung",
    "fb_owner": "FB-Verantwortung",
    "process_owner": "Process Owner",
    "solution_owner": "Solution Owner",
    "change_team": "Change-Team",
    "stakeholder": "Stakeholder",
    "company": "Gesellschaft",
    "cost_unit": "Kostenträger",
    "cost_center": "Kostenstelle",
    "effort_container": "Arbeitspaket",
    "extra_account": "Account",
    "effort_tshirt": "Effort Project",
    "concept_scs_pt": "Konzeption",
    "operate_scs_pt": "Betrieb",
    "solution_exists": "",
    "solution_type": "",
    "benefit_savings": "",
    "risks_obstacles": "Risiko",
    "similar_solution": "Ähnlich",
}


def say(gaps: dict, field_key: str | None, default: str = "Weiß ich noch nicht") -> str:
    if field_key in COLLAB_KEYS:
        return "ja"
    if field_key == "facts":
        packed = ", ".join(
            part for part in (gaps.get("start_date"), gaps.get("company")) if part
        )
        return packed or default
    keys = PACK.get(field_key or "")
    if keys:
        parts = []
        for key in keys:
            value = gaps.get(key)
            if not value:
                continue
            label = LABELS.get(key, "")
            parts.append(f"{label} {value}".strip() if label else str(value))
        return ", ".join(parts) or default
    return gaps.get(field_key, default)


def fact_keys(keys: list[str]) -> list[str]:
    return [key for key in keys if key not in COLLAB_KEYS]
