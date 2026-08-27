from pathlib import Path

import pytest

from app.services.effort_sheet import (
    TEMPLATE_PATH,
    EffortSheetError,
    copy_url,
    export_csv_url,
    parse_effort_csv,
)


def test_template_csv_exists():
    text = Path(TEMPLATE_PATH).read_text(encoding="utf-8")
    parsed = parse_effort_csv(text)
    assert parsed["effort_fb"] == "5 PT"
    assert parsed["effort_it"] == "5 PT"
    assert parsed["concept_scs_pt"] == "5"
    assert parsed["operate_scs_pt"] == "1"
    assert parsed["costs"] == "2500"


def test_export_url_rejects_foreign_host():
    with pytest.raises(EffortSheetError, match="docs.google.com"):
        export_csv_url("https://evil.example/spreadsheets/d/abc123/edit")


def test_copy_and_export_urls():
    src = "https://docs.google.com/spreadsheets/d/AbC_12-3/edit#gid=7"
    assert copy_url(src).endswith("/AbC_12-3/copy")
    assert export_csv_url(src).endswith("/AbC_12-3/export?format=csv&gid=7")


def test_dummy_template_skips_google():
    from app.services.effort_sheet import DUMMY_TEMPLATE_URL, fetch_effort_sheet

    parsed = fetch_effort_sheet(DUMMY_TEMPLATE_URL)
    assert parsed["effort_fb"] == "5 PT"
    assert parsed["effort_sheet_url"] == DUMMY_TEMPLATE_URL
