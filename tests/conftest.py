"""Testdefaults. Websuche bleibt aus, damit CI nicht ins Netz geht.

Wissensbasis: Produktivordner ist leer — Tests nutzen `tests/fixtures/knowledge`.
"""

from __future__ import annotations
from pathlib import Path

import pytest

FIXTURE_KNOWLEDGE = Path(__file__).resolve().parent / "fixtures" / "knowledge"


@pytest.fixture(autouse=True)
def disable_web_search(monkeypatch):
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "false")
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def use_fixture_knowledge(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_DIR", str(FIXTURE_KNOWLEDGE))
    from app.config import get_settings
    from app.knowledge import cases

    get_settings.cache_clear()
    cases._cache = None
    yield
    get_settings.cache_clear()
    cases._cache = None
