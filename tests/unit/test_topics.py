"""Change-Themen laden und matchen. Keine Extra-Fragen."""

from app.domain.topics import find_topic, load_topics, match_topic
from app.domain.types import RequestKind


def test_all_example_topics_load():
    names = {t.name for t in load_topics()}
    assert names == {"prozess", "software", "organisation", "kommunikation"}
    for topic in load_topics():
        assert topic.fields == ()


def test_kinds_are_change():
    assert find_topic("prozess").kind is RequestKind.CHANGE_REQUEST
    assert find_topic("software").kind is RequestKind.CHANGE_REQUEST


def test_match_picks_prozess():
    assert match_topic("Urlaubsanträge sollen digital laufen, der Prozess ist Papier").name == "prozess"


def test_match_picks_software():
    assert match_topic("Wir brauchen eine Schnittstelle nach SAP").name == "software"


def test_match_picks_organisation_on_merge():
    assert match_topic("Zusammenlegung von zwei Abteilungen").name == "organisation"
