"""Der Chat als Assistent: fragen, navigieren, aendern, ohne Buttons."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.domain.types import OutboxOperation, RequestStatus
from app.models import Comment, OutboxJob, Request, StatusUpdate
from tests.support import say


class ScriptedProvider:
    name = "scripted"

    def __init__(self, script: list[dict[str, Any]]) -> None:
        self.script = script
        self.calls = 0

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        index = min(self.calls, len(self.script) - 1)
        self.calls += 1
        return dict(self.script[index])


@pytest.fixture()
def make_client(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "assistant.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("LLM_PROVIDER", "none")
    monkeypatch.setenv("TICKET_PORT", "fake")
    monkeypatch.setenv("APP_ENV", "dev")

    from app.config import get_settings

    get_settings.cache_clear()

    import app.db as dbmod
    import app.models  # noqa: F401
    from app.db import Base

    engine = create_engine(
        f"sqlite:///{db_path}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    Base.metadata.create_all(bind=engine)
    dbmod.engine = engine
    dbmod.SessionLocal = Session

    from app.main import app
    from app.ports import get_ticket_port

    get_ticket_port.cache_clear()

    def factory(script: list[dict[str, Any]] | None = None):
        provider = ScriptedProvider(script or [{"unclear": True}])
        monkeypatch.setattr(
            "app.api.sessions.build_provider_from_runtime",
            lambda _runtime: provider,
        )
        return TestClient(app), Session

    yield factory

    get_settings.cache_clear()
    get_ticket_port.cache_clear()


def change_script() -> list[dict]:
    base = {
        "intent": "anliegen",
        "kind": "change_request",
        "title": "Urlaubsanträge digitalisieren",
        "confidence": 0.9,
        "fields": {
            "sponsor": "Frau Berger",
            "start_date": "1.3.2027",
            "end_date": "1.9.2027",
            "company": "SCS Gesamt",
            "problem": (
                "Urlaubsanträge laufen über ein Papierformular mit zwei Unterschriften. "
                "Anträge gehen verloren, und niemand sieht den aktuellen Stand."
            ),
            "solution_goals": (
                "Ein digitales Formular mit zweistufiger Freigabe durch Führungskraft und Personal. "
                "Der Resturlaub kommt aus dem Personalsystem, die Excel-Datei entfällt. "
                "Der Betriebsrat wird vor der Einführung eingebunden."
            ),
            "benefit_savings": "Weniger Papier",
            "benefit_risk": "Kein Verlust",            "current_status": "Idee",
            "risks_obstacles": "keine",
            "similar_solution": "Kein vergleichbares Formular",
        },
    }
    return [base]


STORY = (
    "Urlaubsanträge laufen über ein Papierformular mit zwei Unterschriften. "
    "Anträge gehen verloren, niemand sieht den Stand. Wir wollen ein digitales "
    "Formular mit Freigabe. Auftraggeber ist Frau Berger. "
    "Zeitraum 1.3.2027 bis 1.9.2027, Gesellschaft SCS Gesamt."
)
GAPS = {
    "sponsor": "Frau Berger",
    "start_date": "1.3.2027 bis 1.9.2027",
    "end_date": "1.9.2027",
    "company": "SCS Gesamt",
    "description": (
        "Urlaubsanträge laufen über ein Papierformular mit zwei Unterschriften. "
        "Anträge gehen verloren, niemand sieht den Stand. Wir wollen ein digitales "
        "Formular mit Freigabe durch Führungskraft und Personal."
    ),
    "current_status": "Idee, noch kein Steckbrief",
    "benefit_savings": "Weniger Papier",
    "benefit_risk": "Kein Verlust",    "problem": (
        "Urlaubsanträge laufen über ein Papierformular mit zwei Unterschriften. "
        "Anträge gehen verloren, und niemand sieht den aktuellen Stand."
    ),
    "solution_goals": (
        "Ein digitales Formular mit zweistufiger Freigabe durch Führungskraft und Personal. "
        "Der Resturlaub kommt aus dem Personalsystem, die Excel-Datei entfällt. "
        "Der Betriebsrat wird vor der Einführung eingebunden."
    ),
    "risks_obstacles": "keine",
    "similar_solution": "Kein vergleichbares Formular",
}


def new_session(client) -> str:
    return client.post("/api/sessions").json()["sessionId"]


def talk(client, sid: str, text: str, client_info: dict | None = None) -> dict:
    body: dict[str, Any] = {"text": text}
    if client_info:
        body["client"] = client_info
    response = client.post(f"/api/sessions/{sid}/message", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def create_change(client, sid: str, client_info: dict | None = None) -> dict:
    body = talk(client, sid, STORY, client_info)
    while body["type"] in ("question", "unclear"):
        body = talk(client, sid, say(GAPS, body.get("fieldKey")), client_info)
    created = client.post(f"/api/sessions/{sid}/confirm")
    assert created.status_code == 200, created.text
    return created.json()


# --- Navigation ---


def test_single_word_opens_the_settings_page(make_client):
    client, _ = make_client()
    sid = new_session(client)

    body = talk(client, sid, "einstellungen")
    assert body["type"] == "navigate"
    assert body["url"] == "/settings"


def test_verb_plus_target_opens_the_workspace(make_client):
    client, _ = make_client()
    sid = new_session(client)

    assert talk(client, sid, "zeig mir den workspace")["url"] == "/workspace"


def test_sentence_about_a_setting_is_not_navigation(make_client):
    client, _ = make_client(change_script())
    sid = new_session(client)

    body = talk(client, sid, "Ich brauche eine Einstellung im SAP-Modul geändert")
    assert body["type"] != "navigate"


# --- Fragen ---


def test_open_requests_are_answered_in_prose(make_client):
    client, Session = make_client(change_script())
    sid = new_session(client)
    created = create_change(client, sid)

    body = talk(client, sid, "welche tickets sind offen?")
    assert body["type"] == "answer"
    assert created["reference"] in body["text"]
    assert body["links"][0]["url"].startswith("/workspace/")

    # Erledigte zaehlen nicht mehr als offen.
    with Session() as db:
        request = db.get(Request, created["requestId"])
        request.status = RequestStatus.DONE.value
        db.commit()

    assert "gibt es gerade keine" in talk(client, sid, "welche tickets sind offen?")["text"]


def test_counting_question_returns_a_number(make_client):
    client, _ = make_client(change_script())
    sid = new_session(client)
    create_change(client, sid)

    body = talk(client, sid, "wie viele changes sind offen?")
    assert body["type"] == "answer"
    assert body["text"] == "Es gibt genau einen Treffer."


def test_question_without_matches_stays_friendly(make_client):
    client, _ = make_client()
    sid = new_session(client)

    body = talk(client, sid, "welche changes sind offen?")
    assert body["text"] == "Offene Change Requests gibt es gerade keine."


def test_reference_alone_opens_the_ticket(make_client):
    client, _ = make_client(change_script())
    sid = new_session(client)
    created = create_change(client, sid)

    body = talk(client, sid, created["reference"])
    assert body["type"] == "navigate"
    assert created["requestId"] in body["url"]


def test_unknown_reference_says_so(make_client):
    client, _ = make_client()
    sid = new_session(client)

    assert "kenne ich nicht" in talk(client, sid, "AN-9999")["text"]


# --- Aktionen ---


def test_closing_a_request_needs_a_yes(make_client):
    client, Session = make_client(change_script())
    sid = new_session(client)
    created = create_change(client, sid)
    reference = created["reference"]

    ask = talk(client, sid, f"setz {reference} auf erledigt")
    assert ask["type"] == "confirm_action"

    with Session() as db:
        assert db.get(Request, created["requestId"]).status == RequestStatus.STECKBRIEF.value

    done = talk(client, sid, "ja")
    assert done["type"] == "action"
    with Session() as db:
        assert db.get(Request, created["requestId"]).status == RequestStatus.DONE.value
        jobs = db.scalars(
            select(OutboxJob).where(OutboxJob.request_id == created["requestId"])
        ).all()
        assert any(job.operation == OutboxOperation.UPDATE_FIELDS.value for job in jobs)


def test_no_keeps_everything_as_it_is(make_client):
    client, Session = make_client(change_script())
    sid = new_session(client)
    created = create_change(client, sid)

    talk(client, sid, f"setz {created['reference']} auf erledigt")
    body = talk(client, sid, "nein")
    assert "lasse alles" in body["text"]
    with Session() as db:
        assert db.get(Request, created["requestId"]).status == RequestStatus.STECKBRIEF.value


def test_priority_applies_without_asking(make_client):
    client, Session = make_client(change_script())
    sid = new_session(client)
    created = create_change(client, sid)

    body = talk(client, sid, f"{created['reference']} auf hoch")
    assert body["type"] == "action"
    with Session() as db:
        assert db.get(Request, created["requestId"]).priority == "high"


def test_comment_lands_on_the_request(make_client):
    client, Session = make_client(change_script())
    sid = new_session(client)
    created = create_change(client, sid)

    body = talk(client, sid, f"kommentiere bei {created['reference']}: Rückfrage an den Einkauf")
    assert body["type"] == "action"
    with Session() as db:
        comments = db.scalars(
            select(Comment).where(Comment.request_id == created["requestId"])
        ).all()
        assert [c.body for c in comments] == ["Rückfrage an den Einkauf"]


def test_status_note_creates_an_update(make_client):
    client, Session = make_client(change_script())
    sid = new_session(client)
    created = create_change(client, sid)

    body = talk(client, sid, f"{created['reference']} Status: QG1 durch, warte auf Justin")
    assert body["type"] == "action"
    assert "Status" in body["text"]
    with Session() as db:
        updates = db.scalars(
            select(StatusUpdate).where(StatusUpdate.request_id == created["requestId"])
        ).all()
        assert [u.summary for u in updates] == ["QG1 durch, warte auf Justin"]
        assert updates[0].overall_rag == "green"
        request = db.get(Request, created["requestId"])
        assert "QG1" in request.field_values().get("status_summary", "")


def test_status_note_without_target_asks(make_client):
    client, _ = make_client()
    sid = new_session(client)
    body = talk(client, sid, "Status: QG1 durch")
    assert body["type"] == "answer"
    assert "AN-1002" in body["text"]


def test_pronoun_uses_the_last_mentioned_request(make_client):
    client, Session = make_client(change_script())
    sid = new_session(client)
    created = create_change(client, sid)

    # Ohne Referenz, direkt nach der Anlage.
    body = talk(client, sid, "setz das auf hoch")
    assert body["type"] == "action"
    with Session() as db:
        assert db.get(Request, created["requestId"]).priority == "high"


# --- Kontext und Weiterarbeiten ---


def test_draft_patch_corrects_a_field(make_client):
    client, _ = make_client(change_script())
    sid = new_session(client)
    body = talk(client, sid, STORY)
    while body["type"] in ("question", "unclear"):
        body = talk(client, sid, say(GAPS, body.get("fieldKey")))
    assert body["type"] == "summary"

    patched = client.patch(
        f"/api/sessions/{sid}/draft",
        json={"fields": {"problem": "Korrigierter Problemtext"}},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["fields"]["Problem / Reason"] == "Korrigierter Problemtext"


def test_dialog_never_asks_draft_fields(make_client):
    client, _ = make_client(change_script())
    sid = new_session(client)
    body = talk(client, sid, STORY)
    labels = []
    while body["type"] in ("question", "unclear"):
        labels.append(body.get("fieldLabel"))
        body = talk(client, sid, say(GAPS, body.get("fieldKey")))
    assert "Problem / Reason" not in labels
    assert "Kostenträger" not in labels
    assert "Konzeption PT Plan SCS" not in labels


def test_session_stays_usable_after_the_ticket(make_client):
    client, Session = make_client(change_script())
    sid = new_session(client)
    first = create_change(client, sid)

    body = talk(client, sid, "Kommunikation soll zentral laufen")
    assert body["type"] in ("question", "summary")

    with Session() as db:
        session = db.scalar(select(Request).where(Request.id == first["requestId"]))
        assert session is not None


def test_tickets_belong_to_justin(make_client):
    client, Session = make_client(change_script())
    sid = new_session(client)
    created = create_change(client, sid)

    with Session() as db:
        request = db.get(Request, created["requestId"])
        assert request.author is not None
        assert request.author.email == "dev@localhost"
        assert request.author.display_name == "Justin"


def test_comment_author_is_justin(make_client):
    client, Session = make_client(change_script())
    sid = new_session(client)
    created = create_change(client, sid)
    talk(client, sid, f"kommentiere bei {created['reference']}: Ping")

    with Session() as db:
        comments = db.scalars(
            select(Comment).where(Comment.request_id == created["requestId"])
        ).all()
        assert comments[-1].author_name == "Justin"


def test_search_opens_the_matching_ticket(make_client):
    client, _ = make_client(change_script())
    sid = new_session(client)
    created = create_change(client, sid)

    body = talk(client, sid, "suche Urlaub")
    assert body["type"] == "navigate"
    assert created["requestId"] in body["url"]


def test_title_fragment_opens_existing_ticket(make_client):
    client, _ = make_client(change_script())
    sid = new_session(client)
    created = create_change(client, sid)

    other = new_session(client)
    body = talk(client, other, "Urlaubsanträge")
    assert body["type"] == "navigate"
    assert created["requestId"] in body["url"]


def test_ambiguous_search_stays_a_list(make_client):
    client, _ = make_client(change_script())
    create_change(client, new_session(client))
    create_change(client, new_session(client))

    body = talk(client, new_session(client), "suche Urlaub")
    assert body["type"] == "answer"
    assert "zwei" in body["text"]


def test_follow_up_narrows_to_changes(make_client):
    client, _ = make_client(change_script())
    sid = new_session(client)
    created = create_change(client, sid)

    talk(client, sid, "welche tickets sind offen?")
    body = talk(client, sid, "und die changes?")
    assert body["type"] == "answer"
    assert created["reference"] in body["text"] or "Treffer" in body["text"]


def test_ambiguous_question_gets_clarify_not_ticket(make_client):
    client, _ = make_client()
    sid = new_session(client)

    body = talk(client, sid, "welche?")
    assert body["type"] == "answer"
    assert "Wonach" in body["text"] or "genau" in body["text"]


def test_a_sentence_with_habe_starts_intake(make_client):
    """Anlegen ist der Default. "habe" plus Domänenwort ist keine Abfrage."""
    client, _ = make_client(change_script())
    sid = new_session(client)

    body = talk(client, sid, "Ich habe keinen Prozess für Urlaubsanträge")
    assert body["type"] in ("question", "summary")


def test_help_does_not_start_intake(make_client):
    client, _ = make_client(change_script())
    sid = new_session(client)

    body = talk(client, sid, "was kannst du")
    assert body["type"] == "answer"
    assert "Beispiele" in body["text"] or "Anliegen" in body["text"]


def test_confirm_carries_hint(make_client):
    client, _ = make_client(change_script())
    sid = new_session(client)
    created = create_change(client, sid)
    assert "liegt" in (created.get("hint") or "")
    assert created["reference"] in created["hint"]
