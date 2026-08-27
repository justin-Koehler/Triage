"""Fliesstext-Renderer. Zahlen und Referenzen muessen stimmen."""

from __future__ import annotations

from app.chat.answers import (
    count_answer,
    detail_answer,
    empty_answer,
    list_answer,
    stats_answer,
)


def item(reference: str, title: str, priority: str = "Hoch") -> dict:
    return {
        "id": f"id-{reference}",
        "reference": reference,
        "title": title,
        "priorityLabel": priority,
        "createdAt": None,
    }


def test_list_names_the_first_three_and_links_them():
    result = {
        "total": 7,
        "items": [
            item("AN-1007", "Freigabegrenze anheben"),
            item("AN-1004", "SSO klemmt"),
            item("AN-1002", "Report fehlt"),
            item("AN-1001", "Rest"),
        ],
    }
    answer = list_answer(result, "offene Anliegen")

    assert answer.text.startswith("Es gibt sieben offene Anliegen.")
    assert "AN-1007 Freigabegrenze anheben" in answer.text
    assert "Danach AN-1004, AN-1002." in answer.text
    assert [link["label"] for link in answer.links] == ["AN-1007", "AN-1004", "AN-1002"]
    assert answer.url == "/workspace"
    assert "zeig mehr" in answer.text


def test_narrow_kicks_in_above_ten():
    items = [item(f"AN-{1000+i}", f"T{i}") for i in range(11)]
    answer = list_answer({"total": 11, "items": items}, "offene Anliegen")
    assert "zu viel" in answer.text
    assert answer.url == "/workspace"


def test_capabilities_lists_examples():
    from app.chat.answers import capabilities_answer

    text = capabilities_answer().text
    assert "suche Urlaub" in text
    assert "AN-2001 Status: QG1 durch" in text
    assert "einstellungen" in text


def test_clarify_answers():
    from app.chat.answers import clarify_filter_answer, clarify_target_answer

    assert "AN-1002" in clarify_target_answer().text
    assert "offen" in clarify_filter_answer().text.lower()


def test_single_hit_avoids_the_plural():
    answer = list_answer({"total": 1, "items": [item("AN-1002", "Report fehlt")]}, "offene Bugs")

    assert answer.text.startswith("Es gibt genau einen Treffer.")
    assert answer.url is None


def test_empty_stays_a_sentence():
    assert empty_answer("offene Störungen").text == "Offene Störungen gibt es gerade keine."


def test_count_answer_without_hits():
    assert count_answer({"total": 0, "items": []}, "offene Changes").text.endswith("keine.")


def test_stats_lists_every_status():
    stats = {
        "total": 3,
        "byStatus": [
            {"label": "Eingereicht", "count": 2},
            {"label": "Erledigt", "count": 1},
            {"label": "Abgelehnt", "count": 0},
        ],
    }
    text = stats_answer(stats).text

    assert text == "Insgesamt drei Anliegen: zwei eingereicht, ein erledigt."


def test_detail_mentions_gaps_and_jira():
    detail = {
        "id": "abc",
        "reference": "AN-1002",
        "title": "Report fehlt",
        "statusLabel": "In Arbeit",
        "priorityLabel": "Hoch",
        "kindLabel": "Störung / Bug",
        "missingFields": ["Repro-Schritte"],
        "sync": {"externalKey": "OPS-42"},
        "comments": [{"author": "Fachbereich", "body": "Rückfrage"}],
    }
    answer = detail_answer(detail)

    assert "AN-1002 Report fehlt steht auf In Arbeit" in answer.text
    assert "Offen ist noch Repro-Schritte." in answer.text
    assert "OPS-42" in answer.text
    assert "Status setzen" in answer.text
    assert answer.url == "/workspace/abc"
