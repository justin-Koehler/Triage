from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.types import Priority, RequestKind, RequestStatus
from app.models import Request, RequestField
from app.services.requests_service import update_request


def test_update_request_description_is_prose_only_plus_links(tmp_path: Path):
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
        req.fields = [
            RequestField(
                request_id=req.id,
                key="description",
                label="Beschreibung",
                value="Freitext zum Change.",
                position=0,
            ),
            RequestField(
                request_id=req.id,
                key="status_ablauf",
                label="Ablauf",
                value="Wartet auf Freigabe",
                position=1,
            ),
            RequestField(
                request_id=req.id,
                key="current_status",
                label="Was gerade los ist",
                value="Idee, noch kein Steckbrief",
                position=2,
            ),
        ]
        db.add(req)
        db.commit()

        updated = update_request(db, req, {"benefit_risk": "Weniger Ausfälle"})
        assert "Freitext zum Change." in updated.description
        assert "Risikoreduktion" not in updated.description
        assert "Weniger Ausfälle" not in updated.description
        assert "Steckbrief-Name:" not in updated.description
        assert "Wartet auf Freigabe" not in updated.description
        assert f"/workspace/{req.id}" in updated.description
        assert f"/status-update/{req.id}" in updated.description
        assert "CRITR Aufwand Sheet:" in updated.description
        assert "/aufwand/" in updated.description


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
        assert "Weniger Ausfälle" not in updated.description


def test_update_request_always_puts_effort_sheet_in_description(tmp_path: Path):
    from app.db import Base

    db_path = tmp_path / "test3.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    Base.metadata.create_all(bind=engine)

    with Session() as db:
        req = Request(
            reference="AN-2002",
            kind=RequestKind.CHANGE_REQUEST,
            status=RequestStatus.STECKBRIEF,
            priority=Priority.MEDIUM,
            title="AN-2002",
            steckbrief_name="AN-2002",
            description="Freitext",
        )
        req.fields = [
            RequestField(
                request_id=req.id,
                key="description",
                label="Beschreibung",
                value="Freitext",
                position=0,
            ),
            RequestField(
                request_id=req.id,
                key="effort_sheet_url",
                label="Aufwand Sheet",
                value="https://scscm.stackit.gg/aufwand/11111111-2222-3333-4444-555555555555",
                position=1,
            ),
        ]
        db.add(req)
        db.commit()

        updated = update_request(db, req, {"benefit_risk": "Weniger Ausfälle"})
        assert "CRITR Aufwand Sheet:" in updated.description
        assert "/aufwand/11111111-2222-3333-4444-555555555555" in updated.description
        assert "Weniger Ausfälle" not in updated.description
        assert updated.description.count("Aufwand Sheet") == 1
