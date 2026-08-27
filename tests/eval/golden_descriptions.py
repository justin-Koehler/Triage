"""Golden Set: kurze Entwürfe → erwartete Qualitätsmerkmale der Beschreibung."""

from __future__ import annotations

# Offline prüfbar: fertige Beschreibungen + erwartete Score-Signale.
# Eval mit LLM: draft + kind → Polish muss dieselben Regeln treffen.

GOLDEN_GOOD = [
    {
        "id": "urlaub-papier",
        "kind": "change_request",
        "draft": "urlaub digital statt papier",
        "text": (
            "Urlaubsanträge laufen heute auf Papier über das Sekretariat. "
            "Anträge gehen verloren, der Stand bleibt unklar. "
            "Die Erfassung soll digital mit nachvollziehbarer Freigabe laufen."
        ),
        "min_sentences": 2,
        "max_sentences": 4,
        "must_have_soll": True,
    },
    {
        "id": "avatar-empfang",
        "kind": "it_request",
        "draft": "avatar für empfang standardfragen",
        "text": (
            "Am Empfang bleiben Orientierungsfragen am Personal hängen. "
            "Das Personal hat wenig Zeit für Wiederholungsfragen. "
            "Ein Avatar soll die Standardfragen vor Ort beantworten."
        ),
        "min_sentences": 2,
        "max_sentences": 4,
        "must_have_soll": True,
    },
    {
        "id": "sap-auswertung",
        "kind": "it_request",
        "draft": "sap kostenträger auswertung fehlt",
        "text": (
            "Kostenträger-Auswertungen laufen derzeit manuell aus SAP-Exports. "
            "Fehler und Nacharbeit verzögern die Monatsabschlüsse. "
            "Eine Auswertung im System soll die Zahlen direkt liefern."
        ),
        "min_sentences": 2,
        "max_sentences": 4,
        "must_have_soll": True,
    },
    {
        "id": "abteilungen-merge",
        "kind": "change_request",
        "draft": "zwei abteilungen zusammenlegen",
        "text": (
            "Zwei Abteilungen arbeiten heute mit getrennten Abläufen. "
            "Abstimmungen dauern, Verantwortlichkeiten bleiben unklar. "
            "Die Bereiche sollen zusammengeführt und Rollen neu geklärt werden."
        ),
        "min_sentences": 2,
        "max_sentences": 4,
        "must_have_soll": True,
    },
    {
        "id": "rechnungsfreigabe",
        "kind": "change_request",
        "draft": "rechnungsfreigabe dauert zu lang",
        "text": (
            "Rechnungen werden aktuell per E-Mail freigegeben. "
            "Freigaben stocken, Lieferanten mahnen. "
            "Der Freigabeprozess soll digital und nachvollziehbar laufen."
        ),
        "min_sentences": 2,
        "max_sentences": 4,
        "must_have_soll": True,
    },
    {
        "id": "inventur-app",
        "kind": "it_request",
        "draft": "inventur per app statt excel",
        "text": (
            "Inventur läuft heute über Excel-Listen. "
            "Zählstände gehen verloren und weichen ab. "
            "Eine App soll Zählung und Abgleich digital erfassen."
        ),
        "min_sentences": 2,
        "max_sentences": 4,
        "must_have_soll": True,
    },
    {
        "id": "thin-two-sentences",
        "kind": "change_request",
        "draft": "papier weg",
        "text": (
            "Anträge laufen heute auf Papier. "
            "Sie sollen digital erfasst werden."
        ),
        "min_sentences": 2,
        "max_sentences": 3,
        "must_have_soll": True,
    },
    {
        "id": "login-zugang",
        "kind": "it_request",
        "draft": "login für externes portal fehlt",
        "text": (
            "Externe Partner haben derzeit keinen Login zum Portal. "
            "Anfragen laufen umständlich per E-Mail. "
            "Zugänge sollen bereitgestellt und freigeschaltet werden."
        ),
        "min_sentences": 2,
        "max_sentences": 4,
        "must_have_soll": True,
    },
]

GOLDEN_BAD = [
    {
        "id": "meta-sponsor",
        "text": (
            "Die Bauabteilung trägt den Auftrag für diese Maßnahme. "
            "Ein Avatar soll Fragen beantworten."
        ),
        "expect_issues": ("meta_echo",),
    },
    {
        "id": "marketing",
        "text": (
            "Wir schließen die Lücke mit einer signifikanten, skalierbaren Lösung. "
            "Danach steigt die Effizienz nachhaltig."
        ),
        "expect_issues": ("marketing",),
    },
    {
        "id": "one-sentence",
        "text": "Urlaub soll digital werden.",
        "expect_issues": ("zu_wenige_saetze",),
    },
    {
        "id": "bloated-from-thin",
        "draft": "papier weg",
        "text": (
            "Aktuell existiert ein papierbasierter Prozess im Sekretariat. "
            "Dadurch entstehen signifikante Wartezeiten und Informationsverluste. "
            "Wir streben eine ganzheitliche Digitalisierung an. "
            "Dabei wird die Nutzererfahrung zielgerichtet verbessert. "
            "Zusätzlich entsteht nachhaltiger Mehrwert für alle Stakeholder."
        ),
        "expect_issues": ("marketing", "zu_viele_saetze", "aufgeblasen"),
    },
]

# Inputs für Live-LLM-Eval (pytest -m eval).
GOLDEN_POLISH_INPUTS = [
    {
        "id": case["id"],
        "kind": case["kind"],
        "draft": case["draft"],
        "min_sentences": case["min_sentences"],
        "max_sentences": case["max_sentences"],
        "must_have_soll": case["must_have_soll"],
    }
    for case in GOLDEN_GOOD
    if case.get("draft")
]
