"""Leere Aufwand-/Zahlenfelder müssen in Jira auf null gehen — nicht still bleiben."""

from __future__ import annotations

from app.ports.jira_v3 import _format_jira_field_value, mapped_custom_fields_for_update


def _fmt(meta, value):
    return _format_jira_field_value(meta, value, as_description=lambda t: t)


def test_empty_number_maps_to_null_clear():
    field_map = {
        "fields": {
            "concept_cit_pt": {
                "jira": "customfield_17200",
                "jira_type": "number",
            },
            "concept_scs_pt": {
                "jira": "customfield_17201",
                "jira_type": "number",
            },
            "it_costs": {
                "jira": "customfield_10709",
                "jira_type": "number",
            },
        }
    }
    out = mapped_custom_fields_for_update(
        field_map,
        {
            "concept_cit_pt": "",
            "concept_scs_pt": "560",
            "it_costs": "",
        },
        format_value=_fmt,
    )
    assert out["customfield_17200"] is None
    assert out["customfield_10709"] is None
    assert out["customfield_17201"] == 560


def test_omitted_key_is_not_cleared():
    field_map = {
        "fields": {
            "concept_cit_pt": {
                "jira": "customfield_17200",
                "jira_type": "number",
            },
        }
    }
    out = mapped_custom_fields_for_update(
        field_map,
        {"concept_scs_pt": "1"},
        format_value=_fmt,
    )
    assert "customfield_17200" not in out
