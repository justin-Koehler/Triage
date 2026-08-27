"""Problem, Loesung und Risiko als Steckbrief-Prosa, nicht als Kopie der Meldung."""

from __future__ import annotations

from app.domain.text import mentions

MAX = 800


def _norm(text: str) -> str:
    return " ".join(str(text or "").split()).strip()


def _clip(text: str) -> str:
    raw = _norm(text)
    if not raw:
        return ""
    if raw[-1] not in ".!?":
        raw = f"{raw}."
    return raw[:MAX]


def _same(left: str, right: str) -> bool:
    a, b = _norm(left).lower().rstrip(".!"), _norm(right).lower().rstrip(".!")
    return bool(a and b and a == b)


def needs_rewrite(current: str, story: str, other: str = "") -> bool:
    """Leer, 1:1 die Meldung, oder identisch zum Nachbarfeld."""
    cur = _norm(current)
    if not cur or cur.lower() in {"keine", "kein", "-", "nein"}:
        return True
    if _same(cur, story):
        return True
    if other and _same(cur, other):
        return True
    return False


def _has(blob: str, *needles: str) -> bool:
    return any(
        mentions(blob, word, substring=len(word) >= 5 and word != "stand")
        for word in needles
    )


def formulate_problem(title: str, story: str) -> str:
    """Ist-Zustand. Nicht den Soll-Satz, nicht die ganze Meldung."""
    blob = " ".join(part for part in (title, story) if part)
    if not _norm(blob):
        return ""

    if _has(blob, "papier", "formular", "excel"):
        parts = ["Anträge laufen über Papier oder Einzellisten."]
        if _has(blob, "verloren", "verlust"):
            parts.append("Anträge gehen verloren.")
        if _has(blob, "sichtbar", "stand", "niemand", "nachvollzieh"):
            parts.append("Niemand sieht den aktuellen Stand.")
        else:
            parts.append("Der Ablauf ist schlecht nachvollziehbar.")
        return _clip(" ".join(parts))

    if _has(blob, "urlaub", "antrag"):
        return _clip(
            "Urlaubsanträge laufen analog. Der Stand ist nicht nachvollziehbar."
        )

    if _has(blob, "sap", "schnittstelle"):
        return _clip(
            "Daten werden zwischen Systemen per Hand übertragen. "
            "Das ist langsam und fehleranfällig."
        )

    if _has(blob, "zusammenleg", "fusion", "reorg"):
        return _clip(
            "Bereiche arbeiten getrennt. Rollen und Abläufe sind nicht harmonisiert."
        )

    if _has(blob, "avatar", "chatbot"):
        return _clip(
            "Vor Ort fehlt ein klarer digitaler Erstkontakt. "
            "Anfragen bleiben am Empfang oder in der Beratung hängen."
        )

    if _has(blob, "schulung"):
        return _clip(
            "Das Wissen zum neuen Ablauf sitzt nicht in den Teams. Der Start bleibt ungleich."
        )

    subject = _norm(title) or "Der Ablauf"
    return _clip(f"{subject} läuft heute analog. Der Stand ist nicht nachvollziehbar.")


def formulate_solution(title: str, story: str) -> str:
    """Soll-Zustand. Nicht das Problem wiederholen."""
    blob = " ".join(part for part in (title, story) if part)
    if not _norm(blob):
        return ""

    if _has(blob, "papier", "formular", "excel"):
        parts = [
            "Anträge laufen digital mit nachvollziehbarer Freigabe. Papier und parallele Listen entfallen."
        ]
        if _has(blob, "sichtbar", "nachvollzieh") or mentions(blob, "stand"):
            parts.append("Der Stand ist für Antrag und Bearbeitung sichtbar.")
        else:
            parts.append("Der Stand bleibt nachvollziehbar.")
        return _clip(" ".join(parts))

    if _has(blob, "urlaub", "antrag"):
        return _clip(
            "Urlaubsanträge laufen digital. Der Stand ist sichtbar, der Weg verbindlich."
        )

    if _has(blob, "sap", "schnittstelle"):
        return _clip(
            "Die Anbindung übernimmt den Datenaustausch im Fachablauf. "
            "Handarbeit zwischen den Systemen entfällt."
        )

    if _has(blob, "zusammenleg", "fusion", "reorg"):
        return _clip(
            "Die Bereiche laufen in einer Linie. Prozesse und Rollen sind vor dem Stichtag geklärt."
        )

    if _has(blob, "avatar", "chatbot"):
        return _clip(
            "Ein KI-Avatar übernimmt Erstkontakt: Empfang und Beratung vor Ort. "
            "Der Ablauf ist klar, Anfragen bleiben nicht liegen."
        )

    if _has(blob, "schulung"):
        return _clip(
            "Die Teams sind vor dem Stichtag eingewiesen. Der neue Ablauf startet einheitlich."
        )

    subject = _norm(title) or "Der Ablauf"
    return _clip(f"{subject} läuft digital. Der Stand ist sichtbar, der Weg verbindlich.")


def formulate_risk(title: str, story: str) -> str:
    """Naheliegendes Prozessrisiko. Leer, wenn nichts greift."""
    blob = " ".join(part for part in (title, story) if part)
    if not _norm(blob):
        return ""
    if _has(blob, "papier", "excel", "formular"):
        return _clip(
            "Papier und Excel laufen parallel weiter, wenn der alte Weg offen bleibt."
        )
    if _has(blob, "sap", "schnittstelle"):
        return _clip("Anbindung und Tests mit den Umsystemen ziehen sich.")
    if _has(blob, "zusammenleg", "fusion", "reorg", "kultur"):
        return ""
    if _has(blob, "avatar", "chatbot"):
        return _clip(
            "Ohne festen Platz im Ablauf bleibt der Avatar ungenutzt, der Empfang arbeitet wie bisher."
        )
    if _has(blob, "digital", "app"):
        return _clip("Die Nutzung bleibt freiwillig, der alte Weg bleibt offen.")
    return ""
