"""Antworten in deutschen Saetzen.

Bewusst ohne LLM: Zahlen und Referenzen muessen stimmen. Ein Modell, das
"AN-1012" erfindet, richtet mehr Schaden an als eine nuechterne Aufzaehlung.
Die Funktionen sind rein, sie bekommen fertige Dicts aus dem requests_service.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

MAX_NAMED = 3
NARROW_AFTER = 10


@dataclass
class Answer:
    text: str
    links: list[dict[str, str]] = field(default_factory=list)
    url: str | None = None


NUMBERS = {
    0: "kein",
    1: "ein",
    2: "zwei",
    3: "drei",
    4: "vier",
    5: "fünf",
    6: "sechs",
    7: "sieben",
    8: "acht",
    9: "neun",
    10: "zehn",
    11: "elf",
    12: "zwölf",
}


def spell(count: int) -> str:
    """Kleine Zahlen ausschreiben, grosse als Ziffer. Liest sich natuerlicher."""
    return NUMBERS.get(count, str(count))


def _age(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        created = datetime.fromisoformat(iso)
    except ValueError:
        return ""
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    days = (datetime.now(UTC) - created).days
    if days <= 0:
        return "von heute"
    if days == 1:
        return "seit gestern"
    return f"seit {spell(days)} Tagen"


def _link(item: dict) -> dict[str, str]:
    return {"label": item["reference"], "url": f"/workspace/{item['id']}"}


def _named(item: dict) -> str:
    age = _age(item.get("createdAt"))
    tail = f", {item['priorityLabel']}" if item.get("priorityLabel") else ""
    if age:
        tail = f"{tail} {age}"
    return f"{item['reference']} {item['title']}{tail}".strip()


def _headline(total: int, label: str) -> str:
    """Bei genau einem Treffer den Sammelbegriff meiden, sonst stimmt der Numerus nicht."""
    if total == 1:
        return "Es gibt genau einen Treffer."
    return f"Es gibt {spell(total)} {label.strip()}."


def empty_answer(label: str) -> Answer:
    clean = label.strip()
    return Answer(text=f"{clean[:1].upper()}{clean[1:]} gibt es gerade keine.")


def list_answer(result: dict, label: str) -> Answer:
    """Treffer als Fliesstext, die ersten drei mit Namen."""
    items = result.get("items") or []
    total = int(result.get("total") or 0)
    if not items:
        return empty_answer(label)

    if total > NARROW_AFTER:
        return narrow_answer(result, label)

    named = items[:MAX_NAMED]
    sentences = [_headline(total, label)]
    if len(named) == 1:
        sentences.append(f"Es geht um {_named(named[0])}.")
    else:
        first = _named(named[0])
        rest = ", ".join(item["reference"] for item in named[1:])
        sentences.append(f"Am dringendsten ist {first}. Danach {rest}.")

    url = None
    if total > len(named):
        sentences.append("Sag „zeig mehr“ für die nächsten, oder öffne den Workspace.")
        url = "/workspace"

    return Answer(
        text=" ".join(sentences),
        links=[_link(item) for item in named],
        url=url,
    )


def narrow_answer(result: dict, label: str) -> Answer:
    """Viele Treffer: Zahl nennen und eingrenzen lassen, keine Fake-Vollstaendigkeit."""
    total = int(result.get("total") or 0)
    items = result.get("items") or []
    named = items[:MAX_NAMED]
    sentences = [
        f"Es gibt {spell(total)} {label.strip()} — das ist zu viel für den Chat.",
        "Grenz ein: Art, Priorität, oder „suche …“ mit Stichwort.",
    ]
    if named:
        sentences.append(
            "Die dringendsten: " + ", ".join(item["reference"] for item in named) + "."
        )
    return Answer(
        text=" ".join(sentences),
        links=[_link(item) for item in named],
        url="/workspace",
    )


def count_answer(result: dict, label: str) -> Answer:
    total = int(result.get("total") or 0)
    if total == 0:
        return empty_answer(label)
    return Answer(text=_headline(total, label))


def stats_answer(stats: dict) -> Answer:
    """Verteilung ueber alle Status, ohne Filter."""
    rows = [row for row in (stats.get("byStatus") or []) if row.get("count")]
    if not rows:
        return Answer(text="Es ist noch kein Anliegen erfasst.")
    parts = [f"{spell(int(row['count']))} {row['label'].lower()}" for row in rows]
    total = int(stats.get("total") or 0)
    return Answer(
        text=f"Insgesamt {spell(total)} Anliegen: " + ", ".join(parts) + "."
    )


def detail_answer(detail: dict) -> Answer:
    parts = [
        f"{detail['reference']} {detail['title']} steht auf {detail['statusLabel']},"
        f" Priorität {detail['priorityLabel']}, Art {detail['kindLabel']}."
    ]
    missing = detail.get("missingFields") or []
    if missing:
        parts.append(f"Offen ist noch {', '.join(missing)}.")
    sync = detail.get("sync") or {}
    if sync.get("externalKey"):
        parts.append(f"In Jira liegt es als {sync['externalKey']}.")
    comments = detail.get("comments") or []
    if comments:
        parts.append(
            f"Es gibt {spell(len(comments))} "
            f"{'Kommentar' if len(comments) == 1 else 'Kommentare'}, "
            f"zuletzt von {comments[-1]['author']}."
        )
    parts.append("Du kannst den Status setzen oder einen Kommentar hinterlassen.")
    return Answer(
        text=" ".join(parts),
        links=[{"label": detail["reference"], "url": f"/workspace/{detail['id']}"}],
        url=f"/workspace/{detail['id']}",
    )


def unknown_reference_answer(reference: str) -> Answer:
    return Answer(text=f"{reference} kenne ich nicht. Prüf die Referenz.")


def clarify_target_answer() -> Answer:
    return Answer(
        text="Welches Anliegen? Nenn die Referenz wie AN-1002 oder frag zuerst die offenen."
    )


def clarify_filter_answer() -> Answer:
    return Answer(
        text=(
            "Wonach genau? Zum Beispiel „welche Changes sind offen“, "
            "„wie viele Changes“, oder „suche Urlaub“."
        )
    )


def duplicate_prompt_answer(duplicates: list[dict]) -> Answer:
    if not duplicates:
        return Answer(text="")
    named = duplicates[:3]
    refs = ", ".join(item.get("reference") or "?" for item in named)
    return Answer(
        text=(
            f"Ähnlich wirken {refs}. "
            "Sag „trotzdem anlegen“ oder „öffne das bestehende“."
        ),
        links=[
            {
                "label": item["reference"],
                "url": f"/workspace/{item['id']}",
            }
            for item in named
            if item.get("reference") and item.get("id")
        ],
    )


def capabilities_answer() -> Answer:
    return Answer(
        text=(
            "Ich lege Changes an, beantworte Fragen und ändere bestehende. "
            "Beispiele: „Urlaubsanträge sollen digital laufen“, "
            "„welche Changes sind offen“, „suche Urlaub“, "
            "„AN-1002 auf hoch“, „kommentier bei AN-1002: Rückfrage“, "
            "„AN-2001 Status: QG1 durch“, "
            "„einstellungen“."
        )
    )
