from types import SimpleNamespace

from app.services.open_todos import open_todos


def _req(*, summary="", next_steps="", comments=()):
    return SimpleNamespace(
        field_values=lambda: {"status_summary": summary},
        status_updates=[SimpleNamespace(summary=summary, next_steps=next_steps)]
        if (summary or next_steps)
        else [],
        comments=[
            SimpleNamespace(body=body, created_at=i)
            for i, body in enumerate(comments)
        ],
    )


def test_next_steps_werden_todos():
    req = _req(next_steps="Steckbrief nachziehen; Freigabe einholen")
    texts = [t["text"] for t in open_todos(req)]
    assert any("Steckbrief" in t for t in texts)
    assert any("Freigabe" in t for t in texts)


def test_warte_auf_aus_status():
    req = _req(summary="Warten auf Justin zur Klärung der Finanzierung.")
    todos = open_todos(req)
    assert todos
    assert "Finanzierung" in todos[0]["text"]
    assert todos[0].get("who", "").lower().startswith("justin")


def test_bitte_aus_kommentar():
    req = _req(comments=["Alles gut bisher", "Bitte Kosten prüfen und zurückmelden."])
    todos = open_todos(req)
    assert len([t for t in todos if "Kosten" in t["text"]]) == 1
    assert not any(
        "zurückmelden" in t["text"].lower() and "Kosten" not in t["text"]
        for t in todos
    )


def test_zwei_personen_zwei_todos():
    req = _req(next_steps="Justin klärt Kosten und Manuel holt Freigabe")
    todos = open_todos(req)
    whos = {t.get("who", "").lower() for t in todos}
    assert "justin" in whos
    assert "manuel" in whos
    assert len(todos) >= 2


def test_warten_auf_justin_finanzierung():
    req = _req(summary="Warten auf Justin zur Finanzierung")
    todos = open_todos(req)
    assert len(todos) == 1
    assert todos[0].get("who", "").lower().startswith("justin")


def test_und_zwei_eigenstaendige_aktionen():
    req = _req(next_steps="Steckbrief nachziehen und Freigabe einholen")
    texts = [t["text"] for t in open_todos(req)]
    assert any("Steckbrief" in t for t in texts)
    assert any("Freigabe" in t for t in texts)


def test_keine_leeren_danke():
    req = _req(comments=["Danke", "Ok", "FYI", "Update"])
    assert open_todos(req) == []


def test_mention_todo():
    req = _req(comments=["@Manuel bitte Freigabe prüfen"])
    todos = open_todos(req)
    assert todos
    assert todos[0].get("who", "").lower().startswith("manuel")
    assert "Freigabe" in todos[0]["text"]


def test_liegt_bei():
    req = _req(summary="Verantwortung liegt bei Justin: Kosten klären")
    todos = open_todos(req)
    assert todos
    assert todos[0].get("who", "").lower().startswith("justin")


def test_narrative_ohne_aktion_kein_todo():
    req = _req(comments=["Heute haben wir den Stand besprochen und alles wirkt ruhig."])
    assert open_todos(req) == []


def test_erledigt_kommentar_filtert():
    req = _req(
        next_steps="Kosten prüfen",
        comments=["Erledigt: Kosten prüfen"],
    )
    todos = open_todos(req)
    assert not any("Kosten" in t["text"] for t in todos)


def test_erledigt_suffix_filtert():
    req = _req(
        next_steps="Kosten prüfen",
        comments=["Kosten prüfen ist erledigt."],
    )
    todos = open_todos(req)
    assert not any("Kosten" in t["text"] for t in todos)


def test_notiert_wird_todo():
    req = _req(comments=["Notiert: Freigabe einholen."])
    todos = open_todos(req)
    assert any("Freigabe" in t["text"] for t in todos)


def test_todo_label():
    req = _req(comments=["TODO: Steckbrief finalisieren"])
    todos = open_todos(req)
    assert any("Steckbrief" in t["text"] for t in todos)
