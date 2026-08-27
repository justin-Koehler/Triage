"""Wissensbasis: Markdown rein, aehnlicher Fall raus."""

from __future__ import annotations

import pytest

from app.knowledge import cases


@pytest.fixture()
def swap_knowledge(tmp_path, monkeypatch):
    from app.config import get_settings
    from app.knowledge import cases as cases_mod

    def use(directory) -> None:
        monkeypatch.setenv("KNOWLEDGE_DIR", str(directory))
        get_settings.cache_clear()
        cases_mod._cache = None

    yield use
    get_settings.cache_clear()
    cases_mod._cache = None


def test_frontmatter_and_sections_are_parsed():
    case = next(item for item in cases.load_cases() if item.id == "KB-0007")
    assert case.kind.value == "change_request"
    assert case.service == "prozess"
    assert "Urlaubsanträge" in case.title
    assert case.effort_fb == 8
    assert "Wochen" in case.duration
    assert "8 PT" in case.effort_line()


def test_search_finds_the_matching_case():
    hits = cases.search("Urlaubsanträge digitalisieren statt Papierformular")
    assert hits
    assert hits[0].case.id == "KB-0007"


def test_short_mentions_still_find_the_case():
    hits = cases.search("urlaubsanträge digitalisieren")
    assert hits and hits[0].case.id == "KB-0007"


def test_filler_words_alone_find_nothing():
    assert cases.search("ich habe da mal ein problem") == []


def test_one_side_keyword_is_no_case():
    assert cases.search("Excel rechnet falsch") == []


def test_empty_folder_is_fine(swap_knowledge, tmp_path):
    swap_knowledge(tmp_path / "leer")
    from app.knowledge import cases as cases_mod

    cases_mod._cache = None
    assert cases.load_cases() == ()
    assert cases.search("Change") == []


def test_real_tickets_can_replace_the_examples(swap_knowledge, tmp_path):
    folder = tmp_path / "echte"
    folder.mkdir()
    (folder / "CHG-482.md").write_text(
        "---\nid: CHG-482\ntitle: Onboarding digitalisieren\n"
        "kind: change_request\nservice: prozess\nstatus: solved\ntags: [onboarding]\n---\n\n"
        "## Problem\nPapier.\n\n## Lösung\nFormular.\n",
        encoding="utf-8",
    )
    swap_knowledge(folder)
    from app.knowledge import cases as cases_mod

    cases_mod._cache = None
    hits = cases.search("Onboarding digitalisieren")
    assert [hit.case.id for hit in hits] == ["CHG-482"]
