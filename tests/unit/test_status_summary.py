from types import SimpleNamespace

from app.services.status_summary import (
    _fallback_ablauf,
    _fallback_prose,
    _fallback_summary,
    _strip_filler,
    _updates_payload,
    list_blurb,
    status_tab_text,
)


def test_fallback_is_one_short_line():
    text = "QG1 ist durch. Go-Live im Juni. Der Fachbereich bremst."
    summary = _fallback_summary(text)
    assert summary == "QG1 ist durch."
    assert "Juni" not in summary


def test_fallback_prose_newest_then_past():
    text = _fallback_prose(
        [
            "es ist alles gut gerade ich warte auf justin",
            "up to date",
            "kjgihb",
            "test",
        ]
    )
    assert text.index("justin") < text.index("up to date") < text.index("test")
    assert "kjgihb" in text


def test_list_blurb_prefers_summary():
    assert list_blurb({"status_summary": "QG1 durch", "current_status": "lang"}) == "QG1 durch"


def test_list_blurb_ignores_intake_status():
    assert list_blurb({"current_status": "Idee, noch kein Steckbrief."}) == ""


def test_strip_filler_drops_empty_past():
    raw = (
        "Alles gut, warte auf Justin. "
        "Zuvor gab es keine weiteren dokumentierten Aktivitäten. "
        "Anfangs wurde das Projekt gestartet."
    )
    cleaned = _strip_filler(raw)
    assert "Justin" in cleaned
    assert "dokumentierten" not in cleaned
    assert "gestartet" not in cleaned
    assert "Aktivitäten" not in cleaned


def test_status_tab_lists_every_entry_like_the_ticket():
    request = SimpleNamespace(
        status_updates=[
            SimpleNamespace(
                reported_on="2026-08-14",
                overall_rag="green",
                summary="test",
                decisions="",
                risks="",
                next_steps="",
                created_at=SimpleNamespace(isoformat=lambda: "2026-08-14T10:00:00"),
            ),
            SimpleNamespace(
                reported_on="2026-08-14",
                overall_rag="green",
                summary="es ist alles gut gerade ich warte auf justin",
                decisions="",
                risks="",
                next_steps="",
                created_at=SimpleNamespace(isoformat=lambda: "2026-08-14T12:00:00"),
            ),
        ]
    )
    tab = status_tab_text(request)
    assert "2026-08-14 · grün" in tab
    assert "test" in tab
    assert "warte auf justin" in tab
    assert tab.index("warte auf justin") < tab.index("test")

    chrono = status_tab_text(request, newest_first=False)
    assert chrono.index("test") < chrono.index("warte auf justin")
    assert "14.08.2026" in _fallback_ablauf(request)
    assert _fallback_ablauf(request).index("test") < _fallback_ablauf(request).index("justin")


def test_updates_payload_includes_next_step_and_risk():
    request = SimpleNamespace(
        status_updates=[
            SimpleNamespace(
                reported_on="2026-08-17",
                overall_rag="yellow",
                summary="QG1 durch",
                decisions="",
                risks="Budget unklar",
                next_steps="warte auf Justin",
                created_at=SimpleNamespace(isoformat=lambda: "2026-08-17T10:00:00"),
            ),
        ]
    )
    rows = _updates_payload(request)
    assert rows[0]["rag"] == "gelb"
    assert rows[0]["summary"] == "QG1 durch"
    assert rows[0]["next_steps"] == "warte auf Justin"
    assert rows[0]["risks"] == "Budget unklar"
    tab = status_tab_text(request)
    assert "Nächster Schritt: warte auf Justin" in tab
    assert "Risiko: Budget unklar" in tab
    assert _fallback_summary("QG1 durch") == "QG1 durch"
