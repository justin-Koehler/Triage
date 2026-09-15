from pathlib import Path

import pytest

from app.services.effort_sheet import (
    TEMPLATE_PATH,
    EffortSheetError,
    copy_url,
    export_csv_url,
    kalkulation_xlsx,
    parse_effort_csv,
)


def test_template_csv_exists():
    text = Path(TEMPLATE_PATH).read_text(encoding="utf-8")
    parsed = parse_effort_csv(text)
    assert parsed["effort_fb"] == "5 PT"
    assert parsed["effort_it"] == "5 PT"
    assert parsed["concept_scs_pt"] == "5"
    assert parsed["operate_scs_pt"] == "1"
    assert parsed["costs"] == "7000"


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
    assert parsed["effort_fb"] == "0 PT"
    assert parsed["effort_it"] == "0 PT"
    assert parsed["effort_sheet_url"] == DUMMY_TEMPLATE_URL


def test_vorlage_csv_maps_screenshot_layout():
    parsed = parse_effort_csv(
        "\ufeffKonzeptions & Einführungs-Phase;;;\r\n"
        "Kalkulation SCS;;;\r\n"
        "3;Gesamt-Personentage (Summe aus der PT-Aufschlüsselung);;\r\n"
        "Personentage;Aufschlüsselung / Beschreibung;;\r\n"
        "3;Workshop;;\r\n"
        "Sach-/Lizenzkosten;Aufschlüsselung / Beschreibung;;\r\n"
        "500;Lizenz;;\r\n"
        "Kosten-Kalkulation;Sätze;Teilsummen;Berechnungen\r\n"
        "Tarifsatz (SCS);750,00;;2.250,00 €\r\n"
        "Kalkulation IT;;;\r\n"
        "Personentage;Aufschlüsselung / Beschreibung;;\r\n"
        "2;Umsetzung;;\r\n"
        "Betriebs-Phase;;;\r\n"
        "Kalkulation SCS;;;\r\n"
        "Personentage;Aufschlüsselung / Beschreibung;;\r\n"
        "1;Betreuung;;\r\n"
    )
    assert parsed["concept_scs_pt"] == "3"
    assert parsed["concept_cit_pt"] == "2"
    assert parsed["operate_scs_pt"] == "1"
    assert parsed["concept_scs_material"] == "500"
    assert parsed["effort_fb"] == "4 PT"
    assert parsed["costs"] == "3500"
    assert parsed["it_costs"]


def test_kalkulation_xlsx_styles_phase_rows():
    from io import BytesIO

    from openpyxl import load_workbook

    data = kalkulation_xlsx(
        "Konzeptions & Einführungs-Phase;;;\n"
        "Kalkulation SCS;;;\n"
        "Summe Brutto;;;1.000,00 €\n"
    )
    book = load_workbook(BytesIO(data))
    sheet = book.active
    assert sheet["A1"].fill.fgColor.rgb[-6:] == "0A1A4F"
    assert sheet["A1"].font.color.rgb[-6:] == "FFFFFF"
    assert sheet.merged_cells.ranges


def test_kalkulation_csv_maps_blocks():
    parsed = parse_effort_csv(
        "phase,rolle,art,menge,beschreibung,satz\n"
        "konzeption,scs,pt,3,Workshop,750\n"
        "konzeption,scs,sach,500,Lizenz,\n"
        "konzeption,cit,pt,2,Umsetzung,665\n"
        "betrieb,scs,pt,1,Betreuung,750\n"
    )
    assert parsed["concept_scs_pt"] == "3"
    assert parsed["concept_cit_pt"] == "2"
    assert parsed["operate_scs_pt"] == "1"
    assert parsed["concept_scs_material"] == "500"
    assert parsed["effort_fb"] == "4 PT"
    assert parsed["effort_it"] == "2 PT"
    assert parsed["costs"] == "3500"
    assert parsed["it_costs"]
    assert "Workshop" in parsed["concept_scs_pt_detail"]


def test_aufwand_fb_it_columns():
    parsed = parse_effort_csv("Aufwand FB,Aufwand IT,Summe\n3,5,99\n1,1,0\n")
    assert parsed["effort_fb"] == "4 PT"
    assert parsed["effort_it"] == "6 PT"
    assert parsed["summe"] == "10"


def test_vorlage_uses_summe_brutto():
    parsed = parse_effort_csv(
        "Kalkulation SCS;;;\n"
        "Personentage;Aufschlüsselung / Beschreibung;;\n"
        "10;Programmieren;;\n"
        "Sach-/Lizenzkosten;Aufschlüsselung / Beschreibung;;\n"
        "1000;Laptop;;\n"
        "Summe Brutto;;;8500,00 €\n"
        "Kalkulation IT;;;\n"
        "Personentage;Aufschlüsselung / Beschreibung;;\n"
        "30;Umsetzung;;\n"
        "Summe Brutto;;;24181,79 €\n"
    )
    assert parsed["effort_fb"] == "10 PT"
    assert parsed["effort_it"] == "30 PT"
    assert parsed["costs"] == "8500"
    assert parsed["it_costs"] == "24181,79"
