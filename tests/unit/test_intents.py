"""Absichtserkennung ohne LLM. Falsch-Navigation ist der teuerste Fehler."""

from __future__ import annotations

import pytest

from app.chat.intents import Action, Navigate, OpenRequest, Query, detect
from app.domain.types import Priority, RequestKind, RequestStatus
from app.services.requests_service import OPEN_STATUSES


@pytest.mark.parametrize(
    "text,url",
    [
        ("einstellungen", "/settings"),
        ("Settings", "/settings"),
        ("öffne die einstellungen", "/settings"),
        ("workspace", "/workspace"),
        ("zeig mir die tabelle", "/workspace"),
    ],
)
def test_navigation(text, url):
    intent = detect(text)
    assert isinstance(intent, Navigate)
    assert intent.url == url


@pytest.mark.parametrize(
    "text",
    [
        "Ich brauche eine Einstellung im SAP-Modul geändert",
        "Die Konfiguration der Kasse verliert nach jedem Neustart die Werte",
    ],
)
def test_langer_satz_ist_keine_navigation(text):
    assert not isinstance(detect(text), Navigate)


def test_referenz_mit_verb_oeffnet_das_anliegen():
    intent = detect("öffne AN-1007")
    assert isinstance(intent, OpenRequest)
    assert intent.reference == "AN-1007"


def test_jira_key_oeffnet_das_anliegen():
    intent = detect("öffne TRI-1001")
    assert isinstance(intent, OpenRequest)
    assert intent.reference == "TRI-1001"


def test_jira_key_allein_fragt_nach_dem_detail():
    intent = detect("CHANGE-42")
    assert isinstance(intent, Query)
    assert intent.reference == "CHANGE-42"


def test_offene_frage_setzt_den_sammelstatus():
    intent = detect("welche tickets sind offen?")
    assert isinstance(intent, Query)
    assert intent.statuses == OPEN_STATUSES
    assert intent.counting is False


def test_zaehlfrage_mit_art():
    intent = detect("wie viele changes hängen noch?")
    assert isinstance(intent, Query)
    assert intent.counting is True
    assert intent.kind is RequestKind.CHANGE_REQUEST
    assert intent.label == "Change Requests"


def test_referenz_allein_fragt_nach_dem_detail():
    intent = detect("AN-1002")
    assert isinstance(intent, Query)
    assert intent.reference == "AN-1002"


def test_status_kommando():
    intent = detect("setz AN-1002 auf erledigt")
    assert isinstance(intent, Action)
    assert intent.status is RequestStatus.DONE
    assert intent.reference == "AN-1002"


def test_prioritaet_ohne_referenz_nutzt_den_kontext():
    intent = detect("setz das auf hoch")
    assert isinstance(intent, Action)
    assert intent.priority is Priority.HIGH
    assert intent.reference is None


def test_kommentar_mit_doppelpunkt():
    intent = detect("kommentier bei AN-1002: Rückfrage an den Einkauf")
    assert isinstance(intent, Action)
    assert intent.comment == "Rückfrage an den Einkauf"


def test_status_note_mit_referenz():
    intent = detect("AN-2001 Status: QG1 durch, warte auf Justin")
    assert isinstance(intent, Action)
    assert intent.status_note == "QG1 durch, warte auf Justin"
    assert intent.status is None
    assert intent.reference == "AN-2001"


def test_status_note_erkennt_ampel():
    intent = detect("AN-2001 Status: gelb, Budget unklar")
    assert isinstance(intent, Action)
    assert intent.status_note == "gelb, Budget unklar"
    assert intent.overall_rag == "yellow"


def test_setz_erledigt_bleibt_workflow():
    intent = detect("setz AN-2001 auf erledigt")
    assert isinstance(intent, Action)
    assert intent.status is RequestStatus.DONE
    assert intent.status_note is None


def test_status_note_ohne_ziel_klarifiziert():
    from app.chat.intents import Clarify

    intent = detect("Status: QG1 durch", {})
    assert isinstance(intent, Clarify)
    assert intent.reason == "target"


def test_frage_nach_dem_vorgehen_ist_kein_befehl():
    assert not isinstance(detect("wie setze ich das auf hoch?"), Action)


def test_anliegen_bleibt_ohne_absicht():
    assert detect("Der Login auf Staging bricht seit heute ab") is None


def test_hilfe_liefert_help():
    from app.chat.intents import Help

    assert isinstance(detect("was kannst du"), Help)
    assert isinstance(detect("hilfe"), Help)


def test_freitextsuche_setzt_query_text():
    intent = detect("suche Urlaub")
    assert isinstance(intent, Query)
    assert intent.text == "urlaub"


def test_follow_up_merged_kind_from_last_filter():
    intent = detect(
        "und die changes?",
        {"last_filter": {
            "statuses": [s.value for s in OPEN_STATUSES],
            "label": "offene Anliegen",
        }},
    )
    assert isinstance(intent, Query)
    assert intent.kind is RequestKind.CHANGE_REQUEST
    assert intent.statuses == OPEN_STATUSES


def test_mehrdeutige_frage_klarifiziert():
    from app.chat.intents import Clarify

    intent = detect("welche?")
    assert isinstance(intent, Clarify)
    assert intent.reason == "filter"


def test_aktion_ohne_ziel_klarifiziert():
    from app.chat.intents import Clarify

    intent = detect("setz auf erledigt", {})
    assert isinstance(intent, Clarify)
    assert intent.reason == "target"


def test_looks_like_issue():
    from app.chat.intents import looks_like_issue

    assert looks_like_issue("Wir wollen die Urlaubsanträge digitalisieren")
    assert not looks_like_issue("was?")
    assert not looks_like_issue("hilfe")


def test_looks_like_create():
    from app.chat.intents import looks_like_create

    assert looks_like_create("Wir wollen die Urlaubsanträge digitalisieren")
    assert looks_like_create("Ich habe keinen Prozess für Urlaubsanträge")
    assert not looks_like_create("Urlaubsanträge")
    assert not looks_like_create("SAP-Schnittstelle")


@pytest.mark.parametrize(
    "text",
    [
        "Ich habe keinen Zugang zu Jira",
        "Ich habe ein Problem mit dem VPN",
        "Outlook stürzt beim Senden ab",
        "Wir brauchen dringend Zugang zum neuen Lagerbereich",
        "Was soll ich machen, wenn der Drucker nichts ausgibt?",
    ],
)
def test_saetze_ueber_probleme_landen_im_intake(text):
    # Kein Lesesignal, also Anliegen. Das ist der Default.
    assert detect(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "welche tickets sind offen",
        "zeige meine tickets",
        "wie viele changes hängen noch",
        "gibt es offene changes",
    ],
)
def test_echte_lesefragen_bleiben_query(text):
    assert isinstance(detect(text), Query)


def test_filter_nach_verantwortlichem():
    intent = detect("welche tickets hat A?")
    assert isinstance(intent, Query)
    assert intent.responsible == "A"
    assert intent.label.endswith("von A")


def test_anliegen_von_b_ist_eine_abfrage():
    intent = detect("anliegen von B")
    assert isinstance(intent, Query)
    assert intent.responsible == "B"


def test_einzelner_buchstabe_ohne_bezug_filtert_nicht():
    intent = detect("welche tickets sind offen a")
    assert isinstance(intent, Query)
    assert intent.responsible is None
