"""Websuche aus: leer, kein Netz."""

from app.services.websearch import first_snippet, hits_block, search, search_effort, search_risks


def test_disabled_search_returns_nothing():
    assert search("digitale Urlaubsanträge") == []
    assert search_risks("Urlaub digital", "Anträge auf Papier") == []
    assert search_effort("Urlaub digital", "Anträge auf Papier") == []


def test_hits_block_formats_and_skips_empty():
    text = hits_block(
        [
            {
                "title": "Change-Risiken",
                "url": "https://example.com/a",
                "snippet": "Parallelbetrieb bleibt.",
            },
            {"title": "", "url": "https://example.com/b", "snippet": ""},
        ],
        "Webrecherche",
    )
    assert text.startswith("Webrecherche:")
    assert "Parallelbetrieb" in text
    assert hits_block([]) == ""
    assert first_snippet([{"title": "X", "snippet": "Adoption bleibt freiwillig."}]).startswith(
        "Adoption"
    )
