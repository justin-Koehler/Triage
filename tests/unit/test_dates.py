"""Deutsche Datumsangaben aus dem Chat (US-003)."""

from datetime import date

import pytest

from app.domain.dates import (
    leftover_after_period,
    normalize_date_value,
    parse_german_date,
    parse_german_dates,
    parse_german_period,
)

TODAY = date(2026, 6, 15)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2027-03-01", "2027-03-01"),
        ("01.03.2027", "2027-03-01"),
        ("1.3.27", "2027-03-01"),
        ("ab dem 1. März 2027", "2027-03-01"),
        ("Start ist der 01.09.", "2026-09-01"),
        # Liegt im laufenden Jahr schon hinter uns, also naechstes Jahr.
        ("01.03.", "2027-03-01"),
        ("heute", "2026-06-15"),
        ("ab sofort", "2026-06-15"),
        ("morgen", "2026-06-16"),
    ],
)
def test_parse_german_date(text, expected):
    assert parse_german_date(text, today=TODAY) == expected


@pytest.mark.parametrize("text", ["", "irgendwann im Sommer", "sobald das Budget steht", "32.13."])
def test_parse_german_date_returns_none_for_prose(text):
    assert parse_german_date(text, today=TODAY) is None


def test_normalize_keeps_prose_as_is():
    assert normalize_date_value("sobald das Budget steht", today=TODAY) == (
        "sobald das Budget steht"
    )


def test_heute_in_prose_is_not_a_calendar_date():
    assert parse_german_dates("läuft heute analog", today=TODAY) == []


@pytest.mark.parametrize(
    ("text", "start", "end"),
    [
        ("ab heute bis offen", "2026-06-15", "offen"),
        ("ab sofort bis unbefristet", "2026-06-15", "offen"),
        ("1.3.2027 bis 1.9.2027", "2027-03-01", "2027-09-01"),
        ("dieses Quartal", "2026-04-01", "2026-06-30"),
        ("nächstes Jahr", "2027-01-01", "2027-12-31"),
        ("ab heute bis morgen", "2026-06-15", "2026-06-16"),
    ],
)
def test_parse_german_period(text, start, end):
    assert parse_german_period(text, today=TODAY) == (start, end)


def test_leftover_keeps_custom_company():
    assert leftover_after_period("ab heute bis offen, Schwarz digits") == "Schwarz digits"


def test_leftover_drops_person_and_dates():
    assert leftover_after_period(
        "1.3.2027 bis 1.9.2027, Frau Berger, SCS Gesamt"
    ) == "SCS Gesamt"

TODAY = date(2026, 6, 15)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2027-03-01", "2027-03-01"),
        ("01.03.2027", "2027-03-01"),
        ("1.3.27", "2027-03-01"),
        ("ab dem 1. März 2027", "2027-03-01"),
        ("Start ist der 01.09.", "2026-09-01"),
        # Liegt im laufenden Jahr schon hinter uns, also naechstes Jahr.
        ("01.03.", "2027-03-01"),
    ],
)
def test_parse_german_date(text, expected):
    assert parse_german_date(text, today=TODAY) == expected


@pytest.mark.parametrize("text", ["", "irgendwann im Sommer", "sobald das Budget steht", "32.13."])
def test_parse_german_date_returns_none_for_prose(text):
    assert parse_german_date(text, today=TODAY) is None


def test_normalize_keeps_prose_as_is():
    assert normalize_date_value("sobald das Budget steht", today=TODAY) == (
        "sobald das Budget steht"
    )
