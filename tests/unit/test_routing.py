"""Zustaendigkeit aus Keyword-Dateien."""

from app.domain.routing import match_priority, match_responsible
from app.domain.types import Priority, RequestKind


def test_process_keywords_go_to_b():
    assert match_responsible("Urlaubsanträge digitalisieren", RequestKind.CHANGE_REQUEST).name == "B"


def test_it_keywords_go_to_a():
    assert match_responsible("Schnittstelle nach SAP einrichten", RequestKind.CHANGE_REQUEST).name == "A"


def test_fallback_uses_kind():
    assert match_responsible("irgendwas ohne stichwort", RequestKind.CHANGE_REQUEST).name == "B"


def test_priority_from_keywords():
    assert match_priority("das ist dringend") is Priority.HIGH
    assert match_priority("das ist nicht dringend") is None
