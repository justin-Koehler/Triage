"""Personenauswahl, Duplikat und Phasen-Verknüpfung."""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.types import Priority, RequestKind, RequestStatus
from app.models import Request, User
from app.ports.jira_v3 import user_picker_label, user_picker_sort_key, user_staff_rank
from app.services.requests_service import duplicate_request, link_requests


def test_user_label_uses_email_not_username():
    row = {
        "name": "cschmidt",
        "displayName": "Christian Schmidt (CIT)",
        "emailAddress": "christian.schmidt@campus.example",
    }
    assert user_picker_label(row) == "Christian Schmidt (CIT) · christian.schmidt@campus.example"
    assert "cschmidt" not in user_picker_label(row)


def test_staff_sort_puts_scs_and_cit_first():
    scs = {"displayName": "Ada (SCS)", "emailAddress": "ada@scs.example", "name": "ada"}
    cit = {"displayName": "Bea (CIT)", "emailAddress": "bea@cit.example", "name": "bea"}
    other = {"displayName": "Cem Extern", "emailAddress": "cem@example.com", "name": "cem"}
    assert user_staff_rank(scs) < user_staff_rank(cit) < user_staff_rank(other)
    ordered = sorted([other, cit, scs], key=lambda row: user_picker_sort_key(row, ""))
    assert [row["name"] for row in ordered] == ["ada", "bea", "cem"]


def test_duplicate_and_link(tmp_path: Path):
    from app.db import Base

    engine = create_engine(
        f"sqlite:///{tmp_path / 'copy.db'}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    Base.metadata.create_all(bind=engine)
    with Session() as db:
        user = User(email="ada@campus.example", display_name="Ada")
        db.add(user)
        db.flush()
        origin = Request(
            reference="AN-1001",
            kind=RequestKind.CHANGE_REQUEST,
            status=RequestStatus.IN_PROGRESS,
            priority=Priority.HIGH,
            title="Portal",
            steckbrief_name="Portal",
            description="Text",
            created_by=user.id,
            phase_label="Phase 1",
        )
        other = Request(
            reference="AN-1002",
            kind=RequestKind.CHANGE_REQUEST,
            status=RequestStatus.STECKBRIEF,
            priority=Priority.MEDIUM,
            title="Portal Folge",
            steckbrief_name="Portal Folge",
            description="Mehr",
            created_by=user.id,
        )
        db.add_all([origin, other])
        db.flush()
        copy = duplicate_request(db, origin, user)
        assert copy.id != origin.id
        assert copy.title.startswith("Kopie:")
        assert copy.reference.startswith("AN-")
        assert copy.phase_label == "Phase 1"
        link_requests(db, origin, other, "Phase 2")
        assert other.id in {row["id"] for row in origin.phase_links}
        assert origin.id in {row["id"] for row in other.phase_links}
