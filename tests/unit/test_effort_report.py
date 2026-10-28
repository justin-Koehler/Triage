from app.services.effort_report import build_effort_report, merge_lines


class _Request:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "1")
        self.title = kwargs.get("title", "Change")
        self.status = kwargs.get("status", "freigegeben")
        self.change_lead = kwargs.get("change_lead", "")
        self.reference = ""
        self.status_updates = []
        self._values = kwargs.get("values", {})

    def field_values(self):
        return self._values


def test_report_splits_it_days_by_owner_and_status():
    rows = [
        _Request(
            id="a",
            title="Alpha",
            status="freigegeben",
            values={"responsible_sit": "Lena Wetter", "concept_cit_pt": "10", "operate_cit_pt": "2,5"},
        ),
        _Request(
            id="b",
            title="Beta",
            status="abgeschlossen",
            values={"it_owner": "Lena Wetter", "concept_cit_pt": "4"},
        ),
        _Request(
            id="c",
            title="Gamma",
            status="steckbrief",
            values={"concept_cit_pt": "0", "operate_cit_pt": "0"},
        ),
    ]
    report = build_effort_report(rows)
    assert report["totals"]["projects"] == 2
    assert report["totals"]["itPt"] == 16.5
    assert report["totals"]["avgPerOwner"] == 16.5
    owner = report["owners"][0]
    assert owner["name"] == "Lena Wetter"
    assert owner["projects"] == 2
    assert owner["conceptPt"] == 14.0
    assert owner["approvedPt"] == 12.5
    assert owner["donePt"] == 4.0
    assert [item["title"] for item in report["changes"]] == ["Alpha", "Beta"]


def test_jira_pt_fills_gaps_and_sheet_keeps_operate():
    local = _Request(
        id="a",
        title="Alpha",
        status="freigegeben",
        values={"responsible_sit": "Lena Wetter", "operate_cit_pt": "3"},
    )
    local.external_refs = [type("Ref", (), {"external_key": "CMS-1"})()]
    issues = [
        {
            "key": "CMS-1",
            "title": "Alpha",
            "status": "Freigegeben",
            "assignee": "Jemand",
            "values": {"concept_cit_pt": "8"},
        },
        {
            "key": "CMS-2",
            "title": "Nur Jira",
            "status": "Abgeschlossen",
            "assignee": "Tobias Huber",
            "values": {"effort_it": "5"},
        },
    ]
    lines = merge_lines([local], issues)
    by_title = {line["title"]: line for line in lines}
    assert by_title["Alpha"]["concept"] == 8
    assert by_title["Alpha"]["operate"] == 3
    assert by_title["Alpha"]["owner"] == "Lena Wetter"
    assert by_title["Nur Jira"]["concept"] == 5
    assert by_title["Nur Jira"]["bucket"] == "done"
    assert by_title["Nur Jira"]["owner"] == "Tobias Huber"
