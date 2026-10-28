"""Aufwand und Kosten aus dem Sheet gewinnen gegen eine Änderung in Jira."""

from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.domain.types import OutboxOperation, Priority, RequestKind, RequestStatus, SyncState
from app.models import ExternalRef, OutboxJob, Request, RequestField
from app.services.effort_sheet import (
    JIRA_SHEET_KEYS,
    TEMPLATE_PATH,
    commit_effort_csv,
    effort_sync_fields,
    parse_effort_csv,
    sheet_drift,
)
from app.services.jira_inbox import apply_effort_share_to_request


def test_sheet_drift_ignores_same_number_and_missing_fields():
    drift = sheet_drift(
        {"concept_scs_pt": "12.0", "concept_cit_pt": "99", "title": "x"},
        {"concept_scs_pt": "12", "concept_cit_pt": "4"},
    )
    assert drift == {"concept_cit_pt": "4"}
    assert sheet_drift({"it_costs": ""}, {"it_costs": "80"}) == {"it_costs": "80"}
    assert sheet_drift({}, {"concept_scs_pt": "3"}) == {}


def test_apply_writes_sheet_back_over_jira(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CRITR_PAUSE_JIRA_PUSH", raising=False)
    from app.db import Base

    engine = create_engine(
        f"sqlite:///{tmp_path / 'sheet.db'}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    Base.metadata.create_all(bind=engine)
    csv_text = TEMPLATE_PATH.read_text(encoding="utf-8")
    sheet = effort_sync_fields(parse_effort_csv(csv_text))

    with Session() as db:
        saved = commit_effort_csv(db, csv_text, "https://scscm.stackit.gg")
        req = Request(
            reference="SCSCM-9",
            kind=RequestKind.CHANGE_REQUEST,
            status=RequestStatus.STECKBRIEF,
            priority=Priority.MEDIUM,
            title="SCSCM-9",
            steckbrief_name="SCSCM-9",
            description="Text",
        )
        req.fields = [
            RequestField(
                request_id=req.id,
                key="effort_sheet_url",
                label="Aufwand",
                value=saved["effort_sheet_url"],
                position=0,
            ),
            RequestField(
                request_id=req.id,
                key="concept_scs_pt",
                label="PT",
                value="99",
                position=1,
            ),
        ]
        req.external_refs = [
            ExternalRef(
                request_id=req.id,
                system="jira",
                external_key="SCSCM-9",
                sync_state=SyncState.SYNCED,
            )
        ]
        db.add(req)
        db.flush()

        jira_values = {key: "999" for key in JIRA_SHEET_KEYS}
        jira_values["concept_cit_pt"] = f"{sheet['concept_cit_pt']}.0"
        apply_effort_share_to_request(db, req, jira_values=jira_values)
        db.flush()
        assert req.field_values()["concept_scs_pt"] == sheet["concept_scs_pt"]
        assert req.field_values()["concept_scs_pt"] != "99"

        jobs = list(db.scalars(select(OutboxJob)).all())
        assert len(jobs) == 1
        assert jobs[0].operation == OutboxOperation.UPDATE_FIELDS
        fields = jobs[0].payload["fields"]
        assert fields["concept_scs_pt"] == sheet["concept_scs_pt"]
        assert fields["it_costs"] == sheet["it_costs"]
        assert "concept_cit_pt" not in fields

        apply_effort_share_to_request(db, req, jira_values=jira_values)
        assert db.scalar(select(func.count()).select_from(OutboxJob)) == 1

        for job in jobs:
            db.delete(job)
        db.flush()
        apply_effort_share_to_request(db, req, jira_values=dict(sheet))
        assert db.scalar(select(func.count()).select_from(OutboxJob)) == 0
