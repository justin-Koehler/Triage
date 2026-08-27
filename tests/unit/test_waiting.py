from types import SimpleNamespace

from app.domain.text import todo_from_status
from app.services.requests_service import (
    actor_name_needles,
    actor_named_in_status,
    waiting_todo,
)


def _req(summary="", updates=()):
    return SimpleNamespace(
        field_values=lambda: {"status_summary": summary},
        status_updates=list(updates),
    )


def test_kurzstatus_nennt_justin():
    req = _req("Warte auf Justin")
    assert actor_named_in_status(req, "Justin")
    assert not actor_named_in_status(req, "Manuel")
    assert not actor_named_in_status(req, "Tobias")


def test_wartet_auf_jira_username():
    actor = SimpleNamespace(
        display_name="Justin Koehler",
        external_subject="koehlerj",
        email="justin.koehler@example.com",
    )
    assert "koehlerj" in actor_name_needles(actor)
    req = _req("Warte auf koehlerj wegen Freigabe")
    assert actor_named_in_status(req, actor=actor)
    assert waiting_todo(req, actor)


def test_letzter_eintrag_next_steps():
    req = _req(
        "QG1 durch",
        [SimpleNamespace(summary="QG1 durch", next_steps="Manuel anrufen")],
    )
    assert actor_named_in_status(req, "Manuel")
    assert not actor_named_in_status(req, "Justin")


def test_alter_ablauf_zaehlt_nicht():
    req = _req("Alles klar")
    assert not actor_named_in_status(req, "Justin")


def test_todo_nimmt_den_sinn_nicht_den_status():
    assert (
        todo_from_status("Warten auf Justin zur Klärung der Finanzierung.", "Justin")
        == "Klärung der Finanzierung steht aus."
    )
    assert "Warten" not in todo_from_status(
        "Warten auf Justin zur Klärung der Finanzierung.", "Justin"
    )
    assert todo_from_status("Warte auf Justin", "Justin") == "Abstimmung steht aus."
    assert (
        todo_from_status(
            "Verantwortung für die nächsten Schritte liegt bei Justin.", "Justin"
        )
        == "Nächste Schritte stehen aus."
    )
    assert "liegt bei" not in todo_from_status(
        "Verantwortung für die nächsten Schritte liegt bei Justin.", "Justin"
    )


def test_waiting_todo_am_request():
    req = _req("Warten auf Justin zur Klärung der Finanzierung.")
    actor = SimpleNamespace(display_name="Justin")
    assert waiting_todo(req, actor) == "Klärung der Finanzierung steht aus."
    assert waiting_todo(req, SimpleNamespace(display_name="Manuel")) == ""
