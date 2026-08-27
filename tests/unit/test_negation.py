"""Verneinung darf kein Feld fuellen."""

from app.domain.fieldspec import get_rules
from app.domain.routing import keyword_hits
from app.domain.text import mentions, negated
from app.domain.topics import match_topic
from app.domain.types import RequestKind


def test_negation_only_counts_in_the_same_clause():
    assert negated("das ist nicht dringend", len("das ist nicht ")) is True
    assert negated("das ist nicht schoen, aber dringend", len("das ist nicht schoen, aber ")) is False


def test_priority_keywords_ignore_a_negated_hit():
    assert keyword_hits("das ist dringend", ["dringend"]) == 1
    assert keyword_hits("das ist nicht dringend", ["dringend"]) == 0


def test_topic_match_ignores_a_negated_system():
    assert match_topic("der prozess für urlaubsanträge ist papier").name == "prozess"
    assert match_topic("es ist kein prozess, wir brauchen eine schnittstelle").name == "software"


def test_mentions_still_finds_the_plain_hit():
    assert mentions("alle Geräte betroffen", "alle") is True
    assert mentions("keine Geräte betroffen", "geräte") is False


def test_choice_field_respects_negation():
    field = get_rules().spec(RequestKind.CHANGE_REQUEST).field_map()["company"]
    assert field.mentioned_value("nicht CIT") is None
    assert field.mentioned_value("für SIT") == "SIT"
