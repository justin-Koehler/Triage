"""Projektleitung darf nicht die anlegende Person sein."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.types import Priority, RequestKind, RequestStatus
from app.models import Request, RequestField, User
from app.services.requests_service import SELF_AS_LEAD, update_request


def test_update_rejects_creator_as_lead(tmp_path: Path):
    from app.db import Base

    engine = create_engine(
        f"sqlite:///{tmp_path / 'lead.db'}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    Base.metadata.create_all(bind=engine)

    with Session() as db:
        user = User(
            email="alex@localhost",
            display_name="Alex Berger",
            external_subject="bergera",
        )
        db.add(user)
        db.flush()
        req = Request(
            reference="SCSCM-1",
            kind=RequestKind.CHANGE_REQUEST,
            status=RequestStatus.STECKBRIEF,
            priority=Priority.MEDIUM,
            title="SCSCM-1",
            steckbrief_name="SCSCM-1",
            description="Text",
            created_by=user.id,
        )
        req.fields = [
            RequestField(
                request_id=req.id,
                key="author",
                label="Autor",
                value="bergera",
                position=0,
            )
        ]
        db.add(req)
        db.flush()

        with pytest.raises(ValueError, match="Vier-Augen-Prinzip"):
            update_request(db, req, {"change_lead": "bergera"})
        assert str(req.change_lead or "") != "bergera"

        update_request(db, req, {"change_lead": "Sam Other"})
        assert req.change_lead == "Sam Other"
        assert SELF_AS_LEAD.startswith("Man darf sich nicht selbst auswählen")
