from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.types import Priority, RequestKind, RequestStatus
from app.models import Request, RequestField
from app.services.requests_service import update_request


def test_update_request_rebuilds_jira_null_fields_in_description(tmp_path: Path):
    from app.db import Base

    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    Base.metadata.create_all(bind=engine)

    with Session() as db:
        req = Request(
            reference="AN-2000",
            kind=RequestKind.CHANGE_REQUEST,
            status=RequestStatus.STECKBRIEF,
            priority=Priority.MEDIUM,
            title="AN-2000",
            steckbrief_name="AN-2000",
            description="BASE",
        )
        db.add(req)
        db.commit()

        # benefit_risk hat jira: null → landet in der Jira-Description.
        updated = update_request(db, req, {"benefit_risk": "Weniger Ausfälle"})
        assert "Risikoreduktion" in updated.description
        assert "Weniger Ausfälle" in updated.description
        assert "Steckbrief-Name: AN-2000" in updated.description

        updated = update_request(db, req, {"benefit_risk": "Stabilerer Betrieb"})
        assert "Stabilerer Betrieb" in updated.description
        assert "Weniger Ausfälle" not in updated.description


def test_update_request_keeps_free_text_description_as_lead(tmp_path: Path):
    from app.db import Base

    db_path = tmp_path / "test2.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    Base.metadata.create_all(bind=engine)

    with Session() as db:
        req = Request(
            reference="AN-2001",
            kind=RequestKind.CHANGE_REQUEST,
            status=RequestStatus.STECKBRIEF,
            priority=Priority.MEDIUM,
            title="AN-2001",
            steckbrief_name="AN-2001",
            description="Alt",
        )
        req.fields = [
            RequestField(
                request_id=req.id,
                key="description",
                label="Beschreibung",
                value="Freitext-Basis",
                position=0,
            )
        ]
        db.add(req)
        db.commit()

        updated = update_request(db, req, {"benefit_risk": "Weniger Ausfälle"})
        assert updated.description.startswith("Freitext-Basis")
