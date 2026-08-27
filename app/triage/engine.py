"""Triage-Loop: Steckbrief aus dem Text schreiben, Lueckenfragen stellen."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.domain.calc import compute
from app.domain.dates import leftover_after_period, parse_german_dates, parse_german_period
from app.domain.description import intake_description_block, normalize_description
from app.domain.fieldspec import (
    FILL_COMPUTED,
    FILL_CONTROLLING,
    FILL_DIALOG,
    FILL_DRAFT,
    FILL_WORKSPACE,
    GROUP_LABELS,
    FieldSpec,
    TriageRules,
    get_rules,
)
from app.domain.overview import formulate_problem, formulate_risk, formulate_solution, needs_rewrite
from app.domain.routing import keyword_match, match_priority, match_responsible
from app.domain.text import mentions
from app.domain.topics import Topic, match_topic, merge_fields
from app.domain.types import (
    KIND_LABELS,
    Priority,
    RequestKind,
    TriageSource,
    parse_kind,
    parse_priority,
)
from app.knowledge import cases
from app.triage.providers import LlmProvider, LlmUnavailable, build_provider

PROMPT_PATH = Path(__file__).parent / "prompts" / "de_intake.md"
PURPOSE_PROMPT = (
    "Wofür soll das konkret eingesetzt werden — welcher Ablauf oder welches Problem?"
)
SOLUTION_PROMPT = "Was soll danach anders laufen?"
AFFECTED_PROMPT = "Wer ist betroffen, und wer könnte das ausbremsen?"
# Die Beschreibung ist das Gespraech selbst. Deckel gegen ausufernde Verlaeufe.
MAX_DESCRIPTION = 4000
MAX_VALUE = 500
MAX_LONGTEXT = 4000
CLARIFY_KEY = "clarify"
EMPATHY_KEY = "empathy"
FACTS_KEY = "facts"
FACTS_KEYS = ("start_date",)
PEOPLE_KEY = "people"
PEOPLE_KEYS = ("sponsor", "approver")
ROLES_KEY = "roles"
ROLES_KEYS = (
    "change_lead",
    "fb_owner",
    "process_owner",
    "solution_owner",
    "change_team",
    "stakeholder",
)
VALUE_KEY = "value"
VALUE_KEYS = (
    "benefit_savings",
    "benefit_risk",
    "risks_obstacles",
    "similar_solution",
)
EFFORT_KEY = "effort"
EFFORT_KEYS = ("concept_scs_pt", "operate_scs_pt")
KONTO_KEY = "konto"
KONTO_KEYS = (
    "company",
    "ordering_company",
    "cost_unit",
    "cost_center",
    "effort_container",
    "extra_account",
    "project_id",
)
SOLUTION_KEY = "solution"
SOLUTION_KEYS = ("solution_exists", "solution_type")
COMPONENTS_KEY = "components"
COMPONENTS_KEYS = ("components",)
CONFIDENCE_CLARIFY = 0.55
THIN_STORY = 80
MAX_STORY_ASKS = 3
CASE_ENRICH_MIN = 0.22
FORBIDDEN_QUESTION = re.compile(
    r"beschreib den change|beschreibe den change|beschreibung genauer|"
    r"vorgangstyp|autor\b|projekt\s*scs|change.?management|"
    r"freigabedatum|aufschl[üu]sselung|status.?ablauf|"
    r"dringlich|priorit[äa]t",
    re.I,
)
CLARIFY_SPEC = FieldSpec(
    key=CLARIFY_KEY,
    label="Klarfrage",
    question="",
    hard=False,
    fill=FILL_DIALOG,
)
EMPATHY_SPEC = FieldSpec(
    key=EMPATHY_KEY,
    label="Nutzen und Widerstände",
    question="",
    hard=False,
    fill=FILL_DIALOG,
)
FACTS_SPEC = FieldSpec(
    key=FACTS_KEY,
    label="Zeitraum",
    question="Wann soll der Change starten, und wann soll er fertig sein?",
    hard=True,
    fill=FILL_DIALOG,
)
PEOPLE_SPEC = FieldSpec(
    key=PEOPLE_KEY,
    label="Auftrag und Genehmigung",
    question="Wer ist Auftraggeber, und wer genehmigt den Change (nach Freigabematrix)?",
    hard=True,
    fill=FILL_DIALOG,
)
ROLES_SPEC = FieldSpec(
    key=ROLES_KEY,
    label="Rollen SCS",
    question=(
        "Wer ist Change-Leitung, FB, Process/Solution Owner, Change-Team — "
        "und wer ist Stakeholder?"
    ),
    hard=True,
    fill=FILL_DIALOG,
)
VALUE_SPEC = FieldSpec(
    key=VALUE_KEY,
    label="Nutzen und Risiko",
    question=(
        "Welcher Nutzen entsteht, welche Risiken siehst du, "
        "gibt es schon etwas Vergleichbares?"
    ),
    hard=True,
    fill=FILL_DIALOG,
)
EFFORT_SPEC = FieldSpec(
    key=EFFORT_KEY,
    label="Aufwand",
    question=(
        "Eher S oder L — und ungefähr wie viele Personentage auf SCS-Seite "
        "(Konzeption und Betrieb)?"
    ),
    hard=True,
    fill=FILL_DIALOG,
)
KONTO_SPEC = FieldSpec(
    key=KONTO_KEY,
    label="Kontierung",
    question="Gesellschaft, Kostenträger, Kostenstelle, Arbeitspaket und Account?",
    hard=True,
    fill=FILL_DIALOG,
)
SOLUTION_SPEC = FieldSpec(
    key=SOLUTION_KEY,
    label="Solution",
    question="Läuft das schon in einer Solution oder einem AP?",
    hard=True,
    fill=FILL_DIALOG,
)
COMPONENTS_SPEC = FieldSpec(
    key=COMPONENTS_KEY,
    label="Stichwörter / Tags",
    question=(
        "Welche Stichwörter / Tags passen? z. B. SAP, Schul-App"
    ),
    hard=True,
    fill=FILL_DIALOG,
)
BUNDLES: tuple[tuple[str, tuple[str, ...], FieldSpec], ...] = (
    (FACTS_KEY, FACTS_KEYS, FACTS_SPEC),
    (PEOPLE_KEY, PEOPLE_KEYS, PEOPLE_SPEC),
    (COMPONENTS_KEY, COMPONENTS_KEYS, COMPONENTS_SPEC),
    (ROLES_KEY, ROLES_KEYS, ROLES_SPEC),
    (VALUE_KEY, VALUE_KEYS, VALUE_SPEC),
    (EFFORT_KEY, EFFORT_KEYS, EFFORT_SPEC),
    (KONTO_KEY, KONTO_KEYS, KONTO_SPEC),
    (SOLUTION_KEY, SOLUTION_KEYS, SOLUTION_SPEC),
)
BUNDLE_MEMBERS: dict[str, tuple[str, ...]] = {key: members for key, members, _ in BUNDLES}

_NAME = (
    r"(?:(?:Frau|Herr|Dr\.?|Prof\.?)\s+)?"
    r"[A-ZÄÖÜ][A-Za-zÄÖÜäöüß.-]+(?:\s+[A-ZÄÖÜ][A-Za-zÄÖÜäöüß.-]+)?"
)
_PEOPLE_CUES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "sponsor",
        re.compile(
            rf"(?i)(?:auftraggebende(?:\s+person)?|auftraggeber(?:in)?)"
            rf"\s*(?:ist|:)?\s*({_NAME})"
        ),
    ),
    ("sponsor", re.compile(rf"(?i)({_NAME})\s+gibt den auftrag")),
    ("approver", re.compile(rf"(?i)({_NAME})\s+genehmigt")),
    (
        "approver",
        re.compile(
            rf"(?i)(?:genehmigende(?:\s+person)?|genehmiger(?:in)?)"
            rf"\s*(?:ist|:)?\s*({_NAME})"
        ),
    ),
)
_ROLE_CUES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "change_lead",
        re.compile(
            rf"(?i)(?:change-?leitung|gesamtprojektleitung|"
            rf"gesamtprojektleiter(?:in)?)\s*(?:ist|:)?\s*({_NAME})"
        ),
    ),
    (
        "fb_owner",
        re.compile(
            rf"(?i)(?:fb-?verantwortung|verantwortliche[rn]?\s+fb|fachbereich)"
            rf"\s*(?:ist|:)?\s*({_NAME})"
        ),
    ),
    (
        "process_owner",
        re.compile(
            rf"(?i)(?:process\s*owner|betriebs(?:übernahme|uebernahme))"
            rf"\s*(?:ist|:)?\s*({_NAME})"
        ),
    ),
    (
        "solution_owner",
        re.compile(
            rf"(?i)(?:solution\s*owner)"
            rf"\s*(?:ist|:)?\s*({_NAME})"
        ),
    ),
    ("stakeholder", re.compile(r"(?i)stakeholder\s*(?:sind|:)?\s*(.+)$")),
)
_KONTO_CUES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("cost_unit", re.compile(r"(?i)kostentr[äa]ger(?:nummer)?:?\s*(\S+)")),
    ("cost_center", re.compile(r"(?i)kostenstelle:?\s*(\S+)")),
    ("effort_container", re.compile(r"(?i)(?:arbeitspaket|aufwandscontainer|\bap\b)\s*:?\s*(\S+)")),
    ("extra_account", re.compile(r"(?i)(?:account|zusatzkontierung):?\s*(\S+)")),
    ("project_id", re.compile(r"(?i)(?:projekt(?:-?id|nummer)?|projektnr\.?):?\s*(\S+)")),
    ("ordering_company", re.compile(r"(?i)beauftragende?\s+(?:gesellschaft|firma):?\s*(.+)$")),
)
_VALUE_CUES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "similar_solution",
        re.compile(r"(?i)(?:ähnlich|aehnlich|bezug|vergleich)\s*(?:ist|:)?\s*(.+)$"),
    ),
    ("risks_obstacles", re.compile(r"(?i)(?:risiko|risiken|hindernis)\s*(?:ist|:)?\s*(.+)$")),
    ("benefit_savings", re.compile(r"(?i)(?:einspar|umsatz)\s*(?:ist|:)?\s*(.+)$")),
    ("benefit_risk", re.compile(r"(?i)risikoreduktion\s*(?:ist|:)?\s*(.+)$")),
)
_TSHIRT = re.compile(r"(?<![A-Za-zÄÖÜäöü])(XS|XL|S|M|L)(?![A-Za-zÄÖÜäöü])", re.I)
_PT = re.compile(
    r"(?i)(\d+(?:[.,]\d+)?)\s*(?:pt|personentage|tage)(?:\s*(konzeption|betrieb))?"
)
_NAME_TOKEN = re.compile(rf"(?i)({_NAME})")
_LABEL_PREFIX = re.compile(
    r"(?i)^(auftraggebende(?:\s+person)?|auftraggeber(?:in)?|"
    r"bearbeitende(?:\s+person)?|bearbeiter(?:in)?|"
    r"genehmigende(?:\s+person)?|genehmiger(?:in)?|"
    r"change-?leitung|gesamtprojektleitung|"
    r"fb-?verantwortung|verantwortliche[rn]?\s+fb|"
    r"process owner|stakeholder|gesellschaft|"
    r"kostentr[äa]ger|kostenstelle|arbeitspaket|account|zeitraum|"
    r"effort project|konzeption|betrieb)\s+"
)

# "Keine Ahnung" ist keine Angabe. Der Wortlaut darf nicht als Wert im
# Steckbrief landen, und die Frage darf nicht nochmal kommen.
UNKNOWN_ANSWERS = (
    "keine ahnung",
    "keine idee",
    "kein plan",
    "weiss nicht",
    "weiß nicht",
    "weiss ich nicht",
    "weiß ich nicht",
    "weiss ich noch nicht",
    "weiß ich noch nicht",
    "ich weiss nicht",
    "ich weiß nicht",
    "ich weiss es nicht",
    "ich weiß es nicht",
    "ich weiss es noch nicht",
    "ich weiß es noch nicht",
    "unbekannt",
    "unklar",
    "egal",
)
_NUMBER = re.compile(r"^[\d.,]+$")
_GROUNDED_FILLS = {FILL_WORKSPACE, FILL_CONTROLLING, FILL_COMPUTED}
# Laengen-Schwelle fuer „zu duenn“. Beschreibung darf kurz bleiben.
THIN_MIN: dict[str, int] = {}
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_PLACEHOLDER = {"", "keine", "kein", "-", "nein", "n/a", "none", "null"}
_ABSENCE = re.compile(
    r"(?i)"
    r"("
    r"(keine|kein|nichts|nicht).{0,72}"
    r"(genannt|erwähnt|erwaehnt|spezifiziert|festgelegt|definiert|bekannt|beschrieben)"
    r"|(noch nicht|bisher nicht|nicht näher|nicht naeher).{0,48}"
    r"(spezifiziert|klar|festgelegt|bekannt|beschrieben)"
    r"|(ist|sind|bleibt|bleiben|war|waren).{0,24}\bunklar\b"
    r"|im (nutzer)?text"
    r"|keine spezifischen"
    r"|initiale idee"
    r"|genaue[r]? anwendungszweck"
    r"|technische umsetzung"
    r"|es handelt sich um eine"
    r")"
)
_IDEA_ONLY = re.compile(
    r"(?i)("
    r"es ist geplant|initiale idee|erste idee|nur eine idee|"
    r"idee zur nutzung|anwendungszweck|noch nicht spezifiziert"
    r")"
)
_SUBSTANCE = re.compile(
    r"(?i)\b("
    r"weil|damit|wofür|wofuer|problem|heute|statt|ablauf|"
    r"empfang|besucher|schulung|beratung|antrag|formular|papier|"
    r"schnittstelle|berechtigung|verlieren|freigabe"
    r")\b"
)
_CONCRETE_CHANGE = re.compile(
    r"(?i)digitalis|zusammenleg|harmonis|automatis|ablös|abloes|ersetz|umstell"
)
_STORY_KEYS = (
    "description",
    "problem",
    "solution_goals",
    "risks_obstacles",
    "stakeholder",
    "similar_solution",
    "benefit_savings",
    "benefit_risk",
)


def strip_absence(text: str) -> str:
    """Meta-Saetze ('nicht genannt', 'unklar', 'nicht spezifiziert') streichen."""
    raw = str(text or "").strip()
    if raw.lower() in _PLACEHOLDER:
        return ""
    parts = [p.strip() for p in _SENTENCE.split(raw) if p.strip()]
    kept: list[str] = []
    for part in parts:
        if _ABSENCE.search(part):
            continue
        kept.append(part if part[-1] in ".!?" else part)
    return " ".join(kept).strip()


def _has_substance(text: str) -> bool:
    blob = strip_absence(text)
    if not blob:
        return False
    if _SUBSTANCE.search(blob):
        return True
    return bool(_CONCRETE_CHANGE.search(blob))


def _is_idea_only(text: str) -> bool:
    blob = strip_absence(text)
    if not blob:
        return True
    if _has_substance(blob):
        return False
    return bool(_IDEA_ONLY.search(blob))


_STOP_STEMS = {
    "eines",
    "einer",
    "einem",
    "einen",
    "eine",
    "ein",
    "der",
    "die",
    "das",
    "und",
    "oder",
    "für",
    "fuer",
    "am",
    "im",
    "in",
    "an",
    "von",
    "mit",
    "zur",
    "zum",
    "des",
    "dem",
    "den",
    "ist",
    "soll",
    "wir",
    "einen",
}


def _content_stems(text: str) -> set[str]:
    words = re.findall(r"[a-zäöüß0-9]+", str(text or "").lower())
    return {word[:6] for word in words if len(word) > 3 and word not in _STOP_STEMS}


def _restates_idea(guess: str, draft: Draft) -> bool:
    """True, wenn der Vorschlag nur die Idee nochmal sagt."""
    stems = _content_stems(guess)
    if not stems:
        return True
    idea = " ".join(part for part in (draft.title, draft.values.get("description")) if part)
    idea_stems = _content_stems(idea)
    leftover = {
        stem
        for stem in stems
        if not any(stem[:4] == other[:4] for other in idea_stems)
    }
    return len(leftover) < 2


def _too_thin(key: str, value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    return len(text) < THIN_MIN.get(key, 0)


def _stated(text: str, value: str) -> bool:
    """Steht der Wert wörtlich im Nutzertext — Zahlen auch einstellig."""
    raw = str(value or "").strip()
    if not raw:
        return False
    if mentions(text, raw):
        return True
    if _NUMBER.fullmatch(raw):
        return bool(re.search(rf"(?<!\d){re.escape(raw)}(?!\d)", text))
    return False


def _llm_may_formulate(spec: FieldSpec) -> bool:
    """Übersichtstexte darf die KI formulieren. Zahlen, Daten, Namen nicht erfinden."""
    if spec.values or spec.type in ("choice", "date", "number", "money", "person"):
        return False
    return spec.fill in {FILL_DRAFT, FILL_DIALOG} or spec.type == "longtext"


def _show_empty_in_review(spec: FieldSpec) -> bool:
    """Luecken im Review und Ticket — intern und Summen nicht als leere Maske."""
    if spec.auto or spec.key in {"status_summary", "status_digest"}:
        return False
    if spec.fill == FILL_COMPUTED:
        return False
    return spec.fill in {FILL_DRAFT, FILL_DIALOG, FILL_WORKSPACE, FILL_CONTROLLING}


def is_unknown_answer(text: str) -> bool:
    """Lieber eine Luecke im Steckbrief als ein erfundener Wert."""
    raw = str(text or "").strip().lower().strip(".!? ")
    if not raw:
        return True
    return any(raw == phrase or raw.startswith(phrase) for phrase in UNKNOWN_ANSWERS)


def _clean_extracted(text: str) -> str:
    raw = str(text or "").strip(" ,.;:-")
    raw = _LABEL_PREFIX.sub("", raw).strip(" ,.;:-")
    return raw[:MAX_VALUE]


def _set_if_empty(draft: Draft, key: str, value: str, overwrite: bool = False) -> None:
    cleaned = _clean_extracted(value)
    if not cleaned or is_unknown_answer(cleaned):
        return
    current = str(draft.values.get(key) or "").strip()
    if current and not overwrite:
        return
    draft.values[key] = cleaned


def _split_names(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for match in _NAME_TOKEN.finditer(text or ""):
        name = " ".join(match.group(1).split())
        marker = name.lower()
        if marker in seen or marker in {
            "scs", "sit", "cit", "sap", "ap", "xs", "xl",
        }:
            continue
        seen.add(marker)
        found.append(name)
    return found


def _extract_cued(
    text: str, cues: tuple[tuple[str, re.Pattern[str]], ...]
) -> tuple[dict[str, str], str]:
    leftover = text or ""
    found: dict[str, str] = {}
    for key, pattern in cues:
        match = pattern.search(leftover)
        if not match:
            continue
        value = _clean_extracted(match.group(1))
        if value:
            found.setdefault(key, value)
            leftover = leftover[: match.start()] + " " + leftover[match.end() :]
    return found, leftover


def _extract_tshirt(text: str) -> str | None:
    match = _TSHIRT.search(text or "")
    if not match:
        return None
    size = match.group(1).upper()
    return size if size in {"XS", "S", "M", "L", "XL"} else None


def _extract_pt(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for match in _PT.finditer(text or ""):
        amount = match.group(1).replace(",", ".")
        phase = (match.group(2) or "").lower()
        if phase.startswith("betrieb") and "operate_scs_pt" not in found:
            found["operate_scs_pt"] = amount
        elif "concept_scs_pt" not in found:
            found["concept_scs_pt"] = amount
        elif "operate_scs_pt" not in found:
            found["operate_scs_pt"] = amount
    return found


def _order_by_needs(
    fields: tuple[FieldSpec, ...], needed: tuple[str, ...]
) -> tuple[FieldSpec, ...]:
    """Felder aus dem aehnlichen Fall zuerst, die YAML-Reihenfolge bleibt stabil."""
    if not needed:
        return fields
    rank = {key: index for index, key in enumerate(needed)}
    return tuple(sorted(fields, key=lambda f: rank.get(f.key, len(rank))))


@dataclass
class Draft:
    """Arbeitsstand eines Anliegens, bevor es angelegt wird."""

    kind: RequestKind | None = None
    title: str = ""
    service: str | None = None
    priority: Priority | None = None
    confidence: float | None = None
    values: dict[str, str] = field(default_factory=dict)
    kind_locked: bool = False
    priority_locked: bool = False

    def to_dict(self) -> dict:
        return {
            "kind": self.kind.value if self.kind else None,
            "title": self.title,
            "service": self.service,
            "priority": self.priority.value if self.priority else None,
            "confidence": self.confidence,
            "values": dict(self.values),
            "kind_locked": self.kind_locked,
            "priority_locked": self.priority_locked,
        }

    @classmethod
    def from_dict(cls, raw: dict | None) -> Draft:
        raw = raw or {}
        return cls(
            kind=parse_kind(raw.get("kind")),
            title=str(raw.get("title") or ""),
            service=raw.get("service"),
            priority=parse_priority(raw.get("priority")),
            confidence=raw.get("confidence"),
            values={k: str(v) for k, v in (raw.get("values") or {}).items()},
            kind_locked=bool(raw.get("kind_locked")),
            priority_locked=bool(raw.get("priority_locked")),
        )


@dataclass(frozen=True)
class Diagnosis:
    """Diagnosefragen des Turns und die Art-Felder, die sie ersetzen.

    Ein Playbook doppelt die Art nicht, es tritt an ihre Stelle: gleiche
    Bedeutung heisst gleicher Key (`scope`), und was das Thema sinnlos macht,
    steht in `skip` (`environment` bei WLAN, `client_env` ausserhalb des
    Browsers). Beides muss ueberall dieselbe Antwort geben — Fragen, offene
    Punkte, Steckbrief.
    """

    topic: Topic | None = None
    fields: tuple[FieldSpec, ...] = ()

    @property
    def keys(self) -> frozenset[str]:
        return frozenset(f.key for f in self.fields)

    def field_map(self) -> dict[str, FieldSpec]:
        return {f.key: f for f in self.fields}

    @property
    def skip(self) -> frozenset[str]:
        return frozenset(self.topic.skip) if self.topic else frozenset()

    @property
    def covered(self) -> frozenset[str]:
        """Art-Felder, die nicht mehr selbst fragen oder erscheinen duerfen."""
        return self.keys | self.skip


@dataclass
class TriageResult:
    draft: Draft
    question: str | None = None
    question_field: FieldSpec | None = None
    budget: int = 0
    unclear: bool = False
    ready: bool = False
    intent: str | None = None
    source: TriageSource = TriageSource.LLM
    model: str | None = None
    latency_ms: int | None = None
    error: str | None = None
    previous_kind: RequestKind | None = None
    switched_reason: str | None = None
    # Thema oder geloester Fall kennen die Art. Dann wird sie nicht erfragt.
    kind_certain: bool = False
    # Aehnliche geloeste Faelle des Turns, fuer Prompt und Loesungshinweis.
    hits: list[cases.Hit] = field(default_factory=list)
    # Diagnose: Fall-Fragen zuerst, dann Playbook.
    diagnosis: Diagnosis = field(default_factory=Diagnosis)
    # Felder, zu denen der Nutzer "keine Ahnung" gesagt hat. Nicht nochmal fragen.
    declined: frozenset[str] = frozenset()
    raw: dict = field(default_factory=dict)
    risk_warning: str | None = None
    purpose_guess: str | None = None


class TriageEngine:
    def __init__(self, provider: LlmProvider | None = None, rules: TriageRules | None = None):
        self.rules = rules or get_rules()
        self.provider = provider or build_provider()
        self._prompt_template = PROMPT_PATH.read_text(encoding="utf-8")

    # --- Prompt ---

    def _kind_catalog(self) -> str:
        lines = []
        for kind, spec in self.rules.kinds.items():
            hard = ", ".join(f.key for f in spec.fields if f.hard and f.askable) or "-"
            draft_keys = ", ".join(f.key for f in spec.fields if f.fill == "draft") or "-"
            budget = self.rules.budget_for(kind)
            lines.append(
                f"- {kind.value} ({KIND_LABELS[kind]}): fragen = {hard}; "
                f"entwurf = {draft_keys}; max_fragen = {budget}"
            )
        return "\n".join(lines)

    def _topic_block(self, topic: Topic | None, fields: tuple[FieldSpec, ...]) -> str:
        """Diagnosefelder des Themas, damit das Modell sie aus dem Text fuellt."""
        if not fields:
            return "keines"
        head = f"Thema: {topic.display}" if topic else "Thema: aus einem aehnlichen Fall"
        lines = [head]
        for spec in fields:
            values = f" — erlaubte Werte: {', '.join(spec.values)}" if spec.values else ""
            lines.append(f"- {spec.key} ({spec.label}): {spec.question}{values}")
        return "\n".join(lines)

    def system_prompt(
        self,
        kind: RequestKind | None = None,
        hits: list[cases.Hit] | None = None,
        topic: Topic | None = None,
        fields: tuple[FieldSpec, ...] = (),
    ) -> str:
        fields = fields or (topic.fields if topic else ())
        return (
            self._prompt_template.replace("{kind_catalog}", self._kind_catalog())
            .replace("{max_questions}", str(self._budget(kind, topic)))
            .replace("{solved_cases}", cases.prompt_block(hits or []))
            .replace("{topic_fields}", self._topic_block(topic, fields))
            .replace("{description_spec}", intake_description_block(kind))
        )

    # --- Hauptlauf ---

    def run(
        self,
        draft: Draft,
        transcript: list[str],
        questions_asked: int,
        prefill: dict[str, str] | None = None,
        answer: tuple[str, str] | None = None,
        report: list[str] | None = None,
        declined: set[str] | None = None,
    ) -> TriageResult:
        latest = transcript[-1] if transcript else ""
        started = time.perf_counter()
        text = self._description(transcript)
        hits = cases.search(text)
        # Thema vor dem Modell: nur so kennt der Prompt die Diagnosefelder und
        # das Modell kann sie im ersten Zug aus dem Satz fuellen.
        diagnosis = self.diagnose(text, draft.service, hits)
        try:
            state = {
                "questions_asked": questions_asked,
                "max_questions": self._budget(draft.kind, diagnosis.topic),
                "known": draft.to_dict(),
                "transcript": transcript,
                "latest_user_message": latest,
            }
            raw = self.provider.complete_json(
                self.system_prompt(draft.kind, hits, diagnosis.topic, diagnosis.fields),
                json.dumps(state, ensure_ascii=False),
            )
            latency = int((time.perf_counter() - started) * 1000)
            result = self._from_llm(raw, draft, diagnosis, text)
            result.model = self.provider.name
            result.latency_ms = latency
            result.raw = raw
        except LlmUnavailable as err:
            result = self._from_heuristics(draft, transcript)
            result.error = str(err)
            result.latency_ms = int((time.perf_counter() - started) * 1000)
        result.hits = hits
        result.declined = frozenset(declined or ())
        # Erst die Art klaeren, dann fuellen: beides braucht ein bekanntes kind.
        self._adopt_kind(result, diagnosis.topic, hits)
        self._attach_diagnosis(result, transcript, diagnosis, hits)
        self._apply_prefill(result.draft, prefill, result.diagnosis)
        if answer and answer[0] == CLARIFY_KEY and is_unknown_answer(answer[1]):
            guess = self._propose_purpose(result.draft)
            if guess:
                result.purpose_guess = guess
                answer = (CLARIFY_KEY, guess)
        self._apply_answer(result.draft, answer, result.diagnosis)
        self._apply_routing(result.draft, transcript, hits, report)
        self._prefill_from_text(
            result.draft, transcript, result.diagnosis.fields, result.draft.kind
        )
        self._seed_overview_from_story(result.draft)
        self._apply_risks(result, text, hits)
        self._strip_absence_fields(result.draft)
        self._apply_computed(result.draft)
        self._apply_prefill(result.draft, prefill, result.diagnosis)
        return self._decide(result, questions_asked)

    def diagnose(
        self, text: str, service: str | None, hits: list[cases.Hit] | None = None
    ) -> Diagnosis:
        """Thema und Fall-Fragen zu einem Satz Diagnosefelder zusammenziehen."""
        topic = match_topic(text, service)
        case_fields = hits[0].case.questions if hits else ()
        return Diagnosis(
            topic=topic,
            fields=merge_fields(case_fields, topic.fields if topic else ()),
        )

    def _attach_diagnosis(
        self,
        result: TriageResult,
        transcript: list[str],
        diagnosis: Diagnosis,
        hits: list[cases.Hit],
    ) -> None:
        """Diagnose festschreiben. Thema als interner Slug, wenn noch leer."""
        draft = result.draft
        if diagnosis.topic is None:
            late = self.diagnose(self._description(transcript), draft.service, hits)
            if late.topic:
                diagnosis = late
                self._adopt_kind(result, late.topic, hits)
        result.diagnosis = diagnosis
        topic = diagnosis.topic
        if topic and not draft.service:
            draft.service = topic.name

    def _adopt_kind(
        self, result: TriageResult, topic: Topic | None, hits: list[cases.Hit]
    ) -> None:
        """Art aus Thema/Fall nur sanft nachziehen, nie gegen ein Lock."""
        draft = result.draft
        if draft.kind_locked:
            return
        current = draft.kind
        if current is None:
            cues = " ".join(
                part
                for part in (
                    getattr(topic, "name", "") if topic else "",
                    " ".join(getattr(topic, "match", ()) or ()) if topic else "",
                    " ".join(hit.case.title for hit in hits[:2]),
                )
                if part
            )
            draft.kind = self.rules.guess_kind(cues) or RequestKind.CHANGE_REQUEST
        result.kind_certain = True
        if result.unclear and draft.title:
            result.unclear = False
            result.question = None

    def _description(self, transcript: list[str]) -> str:
        return "\n\n".join(line.strip() for line in transcript if line.strip())[:MAX_DESCRIPTION]

    def _apply_routing(
        self,
        draft: Draft,
        transcript: list[str],
        hits: list[cases.Hit] | None = None,
        report: list[str] | None = None,
    ) -> None:
        """Pflichtfelder ohne Rueckfrage setzen.

        Beschreibung ist die Meldung des Nutzers, nicht das Protokoll: Antworten
        auf Feldfragen stehen schon als eigene Felder. Prioritaet und
        Verantwortliche kommen aus den Keyword-Dateien und lesen alles Gesagte.
        Ein Keyword-Treffer schlaegt dabei einen frueheren Fallback, damit ein
        spaeter genanntes System noch zieht.
        """
        if not draft.kind:
            return
        text = self._description(transcript)
        described = self._description(report) if report is not None else text
        field_map = self.rules.spec(draft.kind).field_map()

        if "description" in field_map and described:
            current = str(draft.values.get("description") or "").strip()
            if not current:
                draft.values["description"] = described

        if not draft.priority_locked:
            by_keyword = match_priority(text)
            if by_keyword:
                draft.priority = by_keyword
            elif hits and hits[0].case.priority and not draft.priority:
                # Kein Schluesselwort: die Einstufung des aehnlichen Falls gilt.
                draft.priority = hits[0].case.priority

        if "change_lead" in field_map and not draft.values.get("change_lead"):
            person = keyword_match(text)
            if not person:
                person = match_responsible(text, draft.kind)
            if person:
                draft.values["change_lead"] = person.name

        if hits and "similar_solution" in field_map and not draft.values.get("similar_solution"):
            case = hits[0].case
            draft.values["similar_solution"] = f"{case.id} — {case.title}"

    def _apply_risks(self, result: TriageResult, text: str, hits: list[cases.Hit]) -> None:
        """Warnung aus Mustern. Feld schreibt der Chat nach Bestaetigung."""
        from app.domain.risks import match_patterns, warning_text

        warning = warning_text(match_patterns(text), hits)
        if warning:
            result.risk_warning = warning

    def _seed_overview_from_story(self, draft: Draft) -> None:
        """Problem, Loesung, Risiko als eigene Saetze — nie die Meldung 1:1 kopieren."""
        if not draft.kind:
            return
        story = str(draft.values.get("description") or "").strip()
        if not story:
            return
        field_map = self.rules.spec(draft.kind).field_map()
        title = draft.title or ""
        if _is_idea_only(story):
            self._seed_benefits_from_story(draft)
            return
        if "problem" in field_map and needs_rewrite(
            str(draft.values.get("problem") or ""),
            story,
            str(draft.values.get("solution_goals") or ""),
        ):
            draft.values["problem"] = formulate_problem(title, story)[:MAX_LONGTEXT]
        if "solution_goals" in field_map and needs_rewrite(
            str(draft.values.get("solution_goals") or ""),
            story,
            str(draft.values.get("problem") or ""),
        ):
            draft.values["solution_goals"] = formulate_solution(title, story)[:MAX_LONGTEXT]
        if "risks_obstacles" in field_map and needs_rewrite(
            str(draft.values.get("risks_obstacles") or ""),
            story,
        ):
            risk = formulate_risk(title, story)
            if risk:
                draft.values["risks_obstacles"] = risk[:MAX_LONGTEXT]
        self._seed_benefits_from_story(draft)

    def _seed_benefits_from_story(self, draft: Draft) -> None:
        """Einsparung, Risikoreduktion, Qualitaet aus dem Gesagten ableiten."""
        if not draft.kind:
            return
        blob = " ".join(
            part
            for part in (
                draft.title,
                draft.values.get("description"),
                draft.values.get("problem"),
                draft.values.get("solution_goals"),
            )
            if part
        )
        if not blob or _is_idea_only(blob):
            return
        field_map = self.rules.spec(draft.kind).field_map()

        def cue(*needles: str, part: bool = True) -> bool:
            return any(mentions(blob, word, substring=part) for word in needles)

        lines = {}
        if cue("papier", "excel", "handarbeit", "manuell", "formular"):
            lines["benefit_savings"] = (
                "Aufwand und Papier sinken, weil Anträge nicht mehr per Hand laufen."
            )
        if cue("verloren", "verlust", "fehler"):
            lines["benefit_risk"] = (
                "Anträge gehen nicht mehr verloren, der Stand bleibt nachvollziehbar."
            )
        for key, text in lines.items():
            if key in field_map and _too_thin(key, draft.values.get(key)):
                draft.values[key] = text

    def _apply_prefill(
        self,
        draft: Draft,
        prefill: dict[str, str] | None,
        diagnosis: Diagnosis | None = None,
    ) -> None:
        """Systemwissen in Auto-Felder schreiben, sobald die Art bekannt ist.

        Die YAML entscheidet, wo ein Auto-Feld existiert. Was dort nicht steht,
        wird verworfen statt an eine unpassende Anliegen-Art geheftet. Was das
        Thema abwaehlt, entsteht gar nicht: Browser und Aufloesung gehoeren nicht
        an einen toten Access Point.
        """
        if not prefill or not draft.kind:
            return
        skip = diagnosis.skip if diagnosis else frozenset()
        field_map = self.rules.spec(draft.kind).field_map()
        for key, value in prefill.items():
            if key in skip:
                continue
            spec = field_map.get(key)
            if not spec or not value:
                continue
            if spec.auto:
                draft.values[key] = value
                continue
            if key == "sponsor" and not str(draft.values.get(key) or "").strip():
                draft.values[key] = value

    def _apply_answer(
        self, draft: Draft, answer: tuple[str, str] | None, diagnosis: Diagnosis
    ) -> None:
        """Die Antwort auf eine Feldfrage in genau dieses Feld schreiben.

        Hat das Feld eine Werteliste, wird die Antwort darauf gezogen: "sofort,
        und zwar zu Hause" ist der Wert "sofort". Passt kein Wert, gilt der
        Wortlaut. "Keine Ahnung" fuellt nichts.

        Pending-Keys koennen Topic-Felder sein und stehen nicht in der Art-YAML.
        Zeitraum-Antworten (Start inkl. Ende) splitten immer Start und Ende.
        """
        if not answer:
            return
        key, value = answer
        text = str(value or "").strip()
        if not key or not text:
            return
        if is_unknown_answer(text):
            return
        apply_bundle = {
            FACTS_KEY: self._apply_facts_answer,
            PEOPLE_KEY: self._apply_people_answer,
            ROLES_KEY: self._apply_roles_answer,
            VALUE_KEY: self._apply_value_answer,
            EMPATHY_KEY: self._apply_empathy_answer,
            EFFORT_KEY: self._apply_effort_answer,
            KONTO_KEY: self._apply_konto_answer,
            SOLUTION_KEY: self._apply_solution_answer,
        }.get(key)
        if apply_bundle:
            apply_bundle(draft, text, diagnosis)
            return
        if key == CLARIFY_KEY:
            desc = str(draft.values.get("description") or "").strip()
            if text not in desc:
                draft.values["description"] = f"{desc}\n{text}".strip()[:MAX_LONGTEXT]
            problem = str(draft.values.get("problem") or "").strip()
            if not problem or problem == desc:
                draft.values["problem"] = text[:MAX_LONGTEXT]
            return
        spec = self._spec_for(draft, key, diagnosis)
        if spec and spec.type == "date":
            self._apply_date_answer(draft, key, text, spec)
            return
        existing = str(draft.values.get(key) or "").strip()
        if existing and not _too_thin(key, existing):
            return
        limit = MAX_LONGTEXT if spec and spec.type == "longtext" else MAX_VALUE
        draft.values[key] = (spec.normalize(text) if spec else text)[:limit]

    def _apply_date_answer(
        self, draft: Draft, key: str, text: str, spec: FieldSpec
    ) -> None:
        """Datum oder Zeitraum schreiben. Nie '1.3. bis 1.9.' nur in Start belassen."""
        start, end = parse_german_period(text)
        if key == "start_date" and (start or end):
            if start:
                draft.values["start_date"] = start[:MAX_VALUE]
            if end:
                draft.values["end_date"] = end[:MAX_VALUE]
            return
        if key == "end_date" and (end or start):
            draft.values["end_date"] = (end or start)[:MAX_VALUE]
            return
        existing = str(draft.values.get(key) or "").strip()
        if existing and not _too_thin(key, existing):
            return
        if start:
            draft.values[key] = start[:MAX_VALUE]
        elif key == "start_date" and re.search(r"\bbis\b|–", text, re.I):
            # Zeitraum ohne parsebare Daten nicht als Klumpen in Start speichern.
            return
        else:
            draft.values[key] = spec.normalize(text)[:MAX_VALUE]

    def _apply_facts_answer(self, draft: Draft, text: str, diagnosis: Diagnosis) -> None:
        """Eine Antwort fuellt den Zeitraum, Rest geht in die anderen Parser."""
        start_spec = self._spec_for(draft, "start_date", diagnosis)
        if start_spec:
            self._apply_date_answer(draft, "start_date", text, start_spec)
        leftover = leftover_after_period(text)
        self._extract_stated_facts(draft, text, diagnosis, overwrite_sponsor=True)
        if leftover:
            self._apply_konto_answer(draft, leftover, diagnosis)

    def _apply_people_answer(self, draft: Draft, text: str, diagnosis: Diagnosis) -> None:
        found, leftover = _extract_cued(text, _PEOPLE_CUES)
        for key, value in found.items():
            _set_if_empty(draft, key, value, overwrite=True)
        names = _split_names(leftover)
        for name in names:
            for key in PEOPLE_KEYS:
                if not str(draft.values.get(key) or "").strip():
                    _set_if_empty(draft, key, name)
                    break

    def _apply_roles_answer(self, draft: Draft, text: str, diagnosis: Diagnosis) -> None:
        found, leftover = _extract_cued(text, _ROLE_CUES)
        for key, value in found.items():
            _set_if_empty(draft, key, value, overwrite=True)
        names = _split_names(leftover)
        for name in names:
            for key in ROLES_KEYS:
                if not str(draft.values.get(key) or "").strip():
                    _set_if_empty(draft, key, name)
                    break

    def _apply_value_answer(self, draft: Draft, text: str, diagnosis: Diagnosis) -> None:
        found, leftover = _extract_cued(text, _VALUE_CUES)
        for key, value in found.items():
            _set_if_empty(draft, key, value, overwrite=True)
        blob = leftover.strip()
        if blob and not is_unknown_answer(blob):
            for key in VALUE_KEYS:
                if _too_thin(key, draft.values.get(key)):
                    limit = MAX_LONGTEXT
                    draft.values[key] = blob[:limit]
                    break

    def _apply_empathy_answer(self, draft: Draft, text: str, diagnosis: Diagnosis) -> None:
        """Antwort auf die Empathie-Frage: Nutzen und Widerstände trennen.

        Einfache Heuristik: Widerstand-Cues → risks_obstacles, Rest → benefit_savings.
        Dann übrige VALUE_KEYS füllen wie _apply_value_answer.
        """
        found, leftover = _extract_cued(text, _VALUE_CUES)
        for key, value in found.items():
            _set_if_empty(draft, key, value, overwrite=True)
        blob = leftover.strip() or text.strip()
        if not blob or is_unknown_answer(blob):
            return
        # Widerstand-Signale → risks_obstacles bevorzugen
        resistance = re.search(
            r"(?i)\b(widerstand|bremse|hürde|huerden?|hindernis|scheitern|"
            r"akzeptanz|ablehnung|kritisch|gegner)\b",
            blob,
        )
        benefit_keys = ("benefit_savings", "benefit_risk")
        if resistance and _too_thin("risks_obstacles", draft.values.get("risks_obstacles")):
            draft.values["risks_obstacles"] = blob[:MAX_LONGTEXT]
        elif any(_too_thin(k, draft.values.get(k)) for k in benefit_keys):
            for k in benefit_keys:
                if _too_thin(k, draft.values.get(k)):
                    draft.values[k] = blob[:MAX_LONGTEXT]
                    break
        elif _too_thin("risks_obstacles", draft.values.get("risks_obstacles")):
            draft.values["risks_obstacles"] = blob[:MAX_LONGTEXT]

    def _apply_effort_answer(self, draft: Draft, text: str, diagnosis: Diagnosis) -> None:
        size = _extract_tshirt(text)
        if size:
            _set_if_empty(draft, "effort_tshirt", size, overwrite=True)
        for key, value in _extract_pt(text).items():
            _set_if_empty(draft, key, value, overwrite=True)

    def _apply_konto_answer(self, draft: Draft, text: str, diagnosis: Diagnosis) -> None:
        found, leftover = _extract_cued(text, _KONTO_CUES)
        for key, value in found.items():
            _set_if_empty(draft, key, value, overwrite=True)
        company_spec = self._spec_for(draft, "company", diagnosis)
        if company_spec:
            company = company_spec.allowed_value(text) or (
                company_spec.allowed_value(leftover) if leftover else None
            )
            if company:
                _set_if_empty(draft, "company", company)
            elif leftover and not found:
                stripped = leftover_after_period(leftover) or leftover
                if (
                    stripped
                    and not is_unknown_answer(stripped)
                    and not _PT.search(stripped)
                    and not _extract_tshirt(stripped)
                ):
                    _set_if_empty(draft, "company", stripped)

    def _apply_solution_answer(self, draft: Draft, text: str, diagnosis: Diagnosis) -> None:
        spec = self._spec_for(draft, "solution_exists", diagnosis)
        snapped = spec.normalize(text) if spec else text
        low = text.lower()
        if spec and snapped in spec.values:
            _set_if_empty(draft, "solution_exists", snapped, overwrite=True)
        elif re.search(r"(?i)\b(ja|läuft|laeuft|schon|vorhanden)\b", low):
            _set_if_empty(draft, "solution_exists", "ja", overwrite=True)
        elif re.search(r"(?i)\b(nein|keine|nicht)\b", low):
            _set_if_empty(draft, "solution_exists", "nein", overwrite=True)
        leftover = re.sub(r"(?i)\b(ja|nein|läuft|laeuft|schon|keine solution)\b", " ", text)
        leftover = " ".join(leftover.split()).strip(" ,.;:-")
        if leftover and str(draft.values.get("solution_exists") or "") == "ja":
            _set_if_empty(draft, "solution_type", leftover)

    def _extract_stated_facts(
        self,
        draft: Draft,
        text: str,
        diagnosis: Diagnosis | None = None,
        overwrite_sponsor: bool = False,
    ) -> None:
        """Namen, T-Shirt, Kontierung und Rollen aus dem Gesagten ziehen."""
        diagnosis = diagnosis or Diagnosis()
        found, _ = _extract_cued(text, _PEOPLE_CUES)
        for key, value in found.items():
            _set_if_empty(
                draft, key, value, overwrite=overwrite_sponsor and key == "sponsor"
            )
        found, _ = _extract_cued(text, _ROLE_CUES)
        for key, value in found.items():
            _set_if_empty(draft, key, value)
        found, _ = _extract_cued(text, _KONTO_CUES)
        for key, value in found.items():
            _set_if_empty(draft, key, value)
        size = _extract_tshirt(text)
        if size:
            _set_if_empty(draft, "effort_tshirt", size)
        for key, value in _extract_pt(text).items():
            _set_if_empty(draft, key, value)
        company_spec = self._spec_for(draft, "company", diagnosis)
        if company_spec and not str(draft.values.get("company") or "").strip():
            company = company_spec.mentioned_value(text) or company_spec.allowed_value(
                leftover_after_period(text)
            )
            if company:
                _set_if_empty(draft, "company", company)

    def _spec_for(self, draft: Draft, key: str, diagnosis: Diagnosis) -> FieldSpec | None:
        """Feld-Definition zu einem Key. Die Diagnose gewinnt vor der Art-YAML."""
        kind_fields = self.rules.spec(draft.kind).fields if draft.kind else ()
        return next(
            (spec for spec in (*diagnosis.fields, *kind_fields) if spec.key == key), None
        )

    def _prefill_from_text(
        self,
        draft: Draft,
        transcript: list[str],
        fields: tuple[FieldSpec, ...],
        kind: RequestKind | None = None,
    ) -> None:
        """Antworten, die schon im Text stehen, nicht nochmal fragen."""
        extra = self.rules.spec(kind).fields if kind else ()
        pool = (*fields, *extra)
        if not pool:
            return
        text = self._description(transcript)
        dates = parse_german_dates(text)
        for spec in pool:
            if spec.auto:
                continue
            if str(draft.values.get(spec.key) or "").strip():
                continue
            if spec.type == "date":
                if spec.key == "start_date" and dates:
                    draft.values["start_date"] = dates[0]
                    if len(dates) > 1 and not draft.values.get("end_date"):
                        draft.values["end_date"] = dates[1]
                elif spec.key == "end_date" and len(dates) > 1:
                    draft.values["end_date"] = dates[1]
                continue
            hit = spec.mentioned_value(text)
            if hit:
                draft.values[spec.key] = hit
        self._extract_stated_facts(draft, text, Diagnosis(fields=fields))

    # --- Auswertung ---

    def _merge_values(
        self,
        draft: Draft,
        kind: RequestKind | None,
        incoming: dict,
        diagnosis: Diagnosis,
        source_text: str = "",
    ) -> dict[str, str]:
        field_map = self.rules.spec(kind).field_map() if kind else {}
        allowed = (set(field_map) | diagnosis.keys) - diagnosis.skip
        specs = {**field_map, **diagnosis.field_map()}
        values = dict(draft.values)
        known_dates = parse_german_dates(source_text)
        for key, value in (incoming or {}).items():
            text = str(value).strip()
            if not text or text.lower() in ("null", "none", "unbekannt"):
                continue
            if allowed and key not in allowed:
                continue
            spec = specs.get(key)
            if spec and spec.auto:
                continue
            if spec and spec.fill == FILL_COMPUTED:
                continue
            if spec and spec.type == "date":
                dates = parse_german_dates(text)
                if key == "start_date" and dates:
                    if dates[0] not in known_dates:
                        continue
                    values["start_date"] = dates[0][:MAX_VALUE]
                    if (
                        len(dates) > 1
                        and dates[1] in known_dates
                        and not str(values.get("end_date") or "").strip()
                    ):
                        values["end_date"] = dates[1][:MAX_VALUE]
                    continue
                parsed = dates[-1] if key == "end_date" and dates else (dates[0] if dates else None)
                if not parsed or parsed not in known_dates:
                    continue
                values[key] = parsed[:MAX_VALUE]
                continue
            elif spec and spec.values:
                snapped = spec.allowed_value(text)
                if not snapped:
                    continue
                if snapped != spec.mentioned_value(source_text) and not _stated(
                    source_text, snapped
                ):
                    continue
                text = snapped
            elif spec and (spec.fill in _GROUNDED_FILLS or spec.type in ("number", "money")):
                if not _stated(source_text, text):
                    continue
            elif spec and not _llm_may_formulate(spec) and not _stated(source_text, text):
                continue
            cleaned = strip_absence(text)
            if not cleaned:
                continue
            existing = str(values.get(key) or "").strip()
            if existing and _has_substance(existing) and not _has_substance(cleaned):
                continue
            if existing and _has_substance(existing) and len(existing) > len(cleaned):
                continue
            limit = MAX_LONGTEXT if spec and spec.type == "longtext" else MAX_VALUE
            values[key] = cleaned[:limit]
        return values

    def _apply_computed(self, draft: Draft) -> None:
        if not draft.kind:
            return
        draft.values.update(compute(draft.values))

    def _grounded_service(
        self, raw_service: object, text: str, diagnosis: Diagnosis
    ) -> str | None:
        """Ein System, das im Text nicht vorkommt, hat das Modell dazuerfunden.

        Erlaubt sind das erkannte Thema samt seiner Stichwoerter — "kommt nicht
        ins Netz" ist WLAN, weil das Playbook das sagt, nicht das Modell.
        """
        if not raw_service:
            return None
        service = str(raw_service).strip().lower().replace(" ", "_")
        if not service:
            return None
        topic = diagnosis.topic
        if topic and service in {topic.name, *topic.match}:
            return service
        words = [w for w in service.replace("_", " ").split() if len(w) > 2]
        if words and all(mentions(text, word, substring=True) for word in words):
            return service
        return None

    def _from_llm(
        self, raw: dict, previous: Draft, diagnosis: Diagnosis, text: str = ""
    ) -> TriageResult:
        kind = parse_kind(raw.get("kind")) or previous.kind
        if previous.kind_locked:
            kind = previous.kind

        values = self._merge_values(previous, kind, raw.get("fields") or {}, diagnosis, text)
        desc = str(values.get("description") or "").strip()
        if desc:
            values["description"] = normalize_description(desc, text)[:MAX_LONGTEXT]
        kind, reason = self._resolve_kind_switch(kind, values, locked=previous.kind_locked)
        if kind:
            allowed = set(self.rules.spec(kind).field_map()) | diagnosis.keys
            kept = {k: v for k, v in values.items() if k in allowed}
            # Diagnostik aus frueheren Turns nicht verlieren.
            for key, value in previous.values.items():
                if key not in allowed:
                    kept.setdefault(key, value)
            values = kept

        service = self._grounded_service(raw.get("service"), text, diagnosis) or previous.service

        priority = previous.priority if previous.priority_locked else parse_priority(
            raw.get("priority")
        )
        if not priority and kind:
            priority = self.rules.spec(kind).default_priority

        confidence = raw.get("confidence")
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = None

        draft = Draft(
            kind=kind,
            title=str(raw.get("title") or previous.title or "").strip()[:200],
            service=service,
            priority=priority,
            confidence=confidence,
            values=values,
            kind_locked=previous.kind_locked,
            priority_locked=previous.priority_locked,
        )
        question = str(raw.get("question") or "").strip() or None
        return TriageResult(
            draft=draft,
            question=question,
            unclear=bool(raw.get("unclear")) or (not kind and not draft.title),
            intent=str(raw.get("intent") or "").strip().lower() or None,
            source=TriageSource.LLM,
            previous_kind=previous.kind,
            switched_reason=reason,
        )

    def _from_heuristics(self, previous: Draft, transcript: list[str]) -> TriageResult:
        text = " ".join(transcript)
        kind = previous.kind if previous.kind_locked else (
            previous.kind or self.rules.guess_kind(text) or RequestKind.CHANGE_REQUEST
        )
        service = previous.service
        values = dict(previous.values)
        title = previous.title or (transcript[-1].strip()[:120] if transcript else "")
        priority = previous.priority or (self.rules.spec(kind).default_priority if kind else None)
        draft = Draft(
            kind=kind,
            title=title,
            service=service,
            priority=priority,
            confidence=None,
            values=values,
            kind_locked=previous.kind_locked,
            priority_locked=previous.priority_locked,
        )
        return TriageResult(
            draft=draft,
            unclear=not title,
            source=TriageSource.HEURISTIC,
            previous_kind=previous.kind,
        )

    def _resolve_kind_switch(
        self, kind: RequestKind | None, values: dict[str, str], locked: bool
    ) -> tuple[RequestKind | None, str | None]:
        if locked:
            return kind, None
        if kind is None:
            return RequestKind.CHANGE_REQUEST, None
        if kind in self.rules.kinds:
            return kind, None
        return RequestKind.CHANGE_REQUEST, None

    # --- Entscheidung ueber Frage, Abschluss oder Abbruch ---

    def _strip_absence_fields(self, draft: Draft) -> None:
        for key in _STORY_KEYS:
            current = str(draft.values.get(key) or "")
            cleaned = strip_absence(current)
            if cleaned != current.strip():
                if cleaned:
                    draft.values[key] = cleaned
                else:
                    draft.values.pop(key, None)

    def _story_gap(self, draft: Draft) -> str | None:
        """Naechste inhaltliche Luecke. Nie 'unklar' oder 'nicht genannt'."""
        story = str(draft.values.get("description") or draft.title or "").strip()
        problem = str(draft.values.get("problem") or "").strip()
        solution = str(draft.values.get("solution_goals") or "").strip()
        blob = " ".join(part for part in (story, problem, solution) if part)
        if _is_idea_only(blob):
            return PURPOSE_PROMPT
        if (
            not _has_substance(blob)
            and self._story_is_thin(draft)
            and not _CONCRETE_CHANGE.search(blob)
        ):
            return PURPOSE_PROMPT
        return None

    def _story_is_thin(self, draft: Draft) -> bool:
        story = str(draft.values.get("description") or draft.title or "").strip()
        if len(story) < THIN_STORY:
            return True
        problem = str(draft.values.get("problem") or "").strip()
        return bool(problem) and problem == story and len(story) < 200

    def _usable_question(self, prompt: str | None) -> str | None:
        text = str(prompt or "").strip()
        if len(text) < 12 or FORBIDDEN_QUESTION.search(text):
            return None
        if re.search(r"(?i)\bunklar\b|nicht genannt|nicht spezifiziert", text):
            return None
        return text

    def _should_clarify(self, result: TriageResult, questions_asked: int) -> bool:
        if CLARIFY_KEY in result.declined:
            return False
        if questions_asked >= MAX_STORY_ASKS:
            return False
        gap = self._story_gap(result.draft)
        if gap:
            return True
        if questions_asked != 0:
            return False
        blob = str(result.draft.values.get("description") or result.draft.title or "")
        if _has_substance(blob) or _CONCRETE_CHANGE.search(blob):
            return False
        confidence = result.draft.confidence
        low = confidence is not None and confidence < CONFIDENCE_CLARIFY
        return bool(result.unclear or low or self._story_is_thin(result.draft))

    def _empathy_question(self, draft: Draft, declined: frozenset[str]) -> str | None:
        """Gezielte Rückfrage, wenn Nutzen oder Widerstände dünn sind.

        Nur einmal pro Session — danach trägt der Nutzer VALUE_KEY in declined.
        Nur wenn die Story schon steht (description vorhanden), nie vorher.
        """
        if EMPATHY_KEY in declined or VALUE_KEY in declined:
            return None
        description = str(draft.values.get("description") or "").strip()
        if not description or len(description) < THIN_STORY:
            return None
        benefit_keys = ("benefit_savings", "benefit_risk")
        has_benefit = any(
            not _too_thin(k, draft.values.get(k)) for k in benefit_keys
        )
        has_resistance = not _too_thin("risks_obstacles", draft.values.get("risks_obstacles"))
        if has_benefit and has_resistance:
            return None
        if not has_benefit and not has_resistance:
            return (
                "Was ist der konkrete Nutzen dieses Changes — "
                "was wird messbar besser? Und: wo siehst du Widerstände oder Hürden bei der Einführung?"
            )
        if not has_benefit:
            return (
                "Was ist der konkrete Nutzen dieses Changes — "
                "was wird messbar besser (Zeit, Kosten, Qualität, Risiko)?"
            )
        return (
            "Wo siehst du Widerstände oder Hürden bei der Einführung — "
            "wer könnte bremsen, was könnte schiefgehen?"
        )

    def _decide(self, result: TriageResult, questions_asked: int) -> TriageResult:
        draft = result.draft
        if draft.kind is None:
            draft.kind = RequestKind.CHANGE_REQUEST
        spec = self.rules.spec(draft.kind)
        if spec and not draft.priority:
            draft.priority = spec.default_priority
        result.unclear = False
        result.question = None
        result.question_field = None
        result.ready = bool(draft.title)
        result.budget = 0
        # Empathie-Frage: einmalig nach der Story, vor dem Summary.
        if result.ready:
            empathy_q = self._empathy_question(draft, result.declined)
            if empathy_q:
                result.question = empathy_q
                result.question_field = EMPATHY_SPEC
                result.ready = False
        return result

    def _ask_clarify(self, result: TriageResult) -> TriageResult:
        result.unclear = False
        result.question = (
            self._usable_question(result.question)
            or self._story_gap(result.draft)
            or PURPOSE_PROMPT
        )
        result.question_field = CLARIFY_SPEC
        result.ready = False
        guess = self._propose_purpose(result.draft)
        if guess:
            result.purpose_guess = guess
        return result

    def _propose_purpose(self, draft: Draft) -> str:
        """Konkreten Ablauf nennen, nie die Idee wiederholen."""
        for guessed in (self._llm_purpose(draft), self._heuristic_purpose(draft)):
            text = " ".join(str(guessed or "").split()).strip()[:MAX_VALUE]
            if text and not _restates_idea(text, draft):
                return text
        return ""

    def _llm_purpose(self, draft: Draft) -> str:
        name = str(getattr(self.provider, "name", "") or "").lower()
        if name in {"heuristik", "scripted", "none", "dead", "test"} or name.startswith("scripted"):
            return ""
        try:
            raw = self.provider.complete_json(
                "Nenne EINEN konkreten Ablauf oder ein Problem, wo das eingesetzt wird. "
                "Nicht die Idee wiederholen, nicht 'Einführung von …', keine Titelworte. "
                "Beispiel: Idee 'KI-Avatar' → 'Empfang und Erstberatung am Standort'. "
                'Kein unklar, keine Floskel. JSON: {"purpose": "..."}',
                f"Titel: {draft.title}\nText: {draft.values.get('description') or ''}",
            )
        except (LlmUnavailable, TypeError, ValueError):
            return ""
        if not isinstance(raw, dict):
            return ""
        text = str(raw.get("purpose") or "").strip()
        if not text or is_unknown_answer(text) or _ABSENCE.search(text):
            return ""
        return text

    def _heuristic_purpose(self, draft: Draft) -> str:
        blob = " ".join(
            part for part in (draft.title, draft.values.get("description")) if part
        )

        def has(*needles: str) -> bool:
            return any(mentions(blob, word, substring=True) for word in needles)

        if has("avatar", "chatbot", "bot"):
            return "Empfang und Erstberatung am Standort."
        if has("urlaub", "antrag") or has("formular", "papier"):
            return "Anträge digital statt Papier, Stand für alle sichtbar."
        if has("schulung"):
            return "Onboarding und Einweisung in den neuen Prozess."
        if has("schnittstelle", "sap"):
            return "Daten nicht mehr per Hand übertragen, sondern automatisch im Fachablauf."
        return "Empfang, Hotline oder ein Antragsweg, der heute hakt."

    def impulse_for(self, draft: Draft, hits: list[cases.Hit] | None) -> dict | None:
        """Ein Ja/Nein-Vorschlag im Review, aus dem aehnlichen Fall."""
        if not draft.kind or not hits:
            return None
        hit = hits[0]
        if hit.score < CASE_ENRICH_MIN:
            return None
        case = hit.case
        fields: dict[str, str] = {}
        stakeholder = str(draft.values.get("stakeholder") or "").strip()
        tags = set(case.tags)
        if not stakeholder and tags & {"personal", "fuehrung", "führung", "betriebsrat", "genehmigung"}:
            fields["stakeholder"] = "Personal, Führung"
        if not fields:
            return None
        return {
            "prompt": f"Aus {case.id}: {case.title} — übernehmen?",
            "fields": fields,
        }

    def _bundle_askable(
        self, askable: tuple[FieldSpec, ...], declined: frozenset[str]
    ) -> tuple[FieldSpec, ...]:
        """Luecken zu einer natuerlichen Frage bündeln. Reihenfolge laut Plan."""
        by_key = {spec.key: spec for spec in askable}
        used: set[str] = set()
        out: list[FieldSpec] = []
        for key, members, spec in BUNDLES:
            if key in declined or all(member in declined for member in members):
                used.update(members)
                continue
            if any(member in by_key for member in members):
                out.append(spec)
                used.update(members)
        for spec_field in askable:
            if spec_field.key not in used:
                out.append(spec_field)
        return tuple(out)

    def _budget(self, kind: RequestKind | None, topic: Topic | None) -> int:
        base = self.rules.budget_for(kind)
        if topic and topic.hard_fields():
            return max(base, topic.max_questions)
        return base

    def _ask(self, result: TriageResult, spec: FieldSpec) -> TriageResult:
        result.question = self._natural_prompt(spec)
        result.question_field = spec
        result.ready = False
        return result

    def _natural_prompt(self, spec: FieldSpec) -> str:
        prompt = str(spec.question or "").strip()
        if prompt and len(prompt) >= 10:
            return prompt
        label = str(spec.label or spec.key).strip()
        if spec.type == "choice" and spec.values:
            values = ", ".join(spec.values[:4])
            return f"Wie ist {label}? Du kannst z. B. {values} wählen."
        return f"Kannst du bitte kurz {label} angeben?"

    def _needed_keys(self, result: TriageResult) -> tuple[str, ...]:
        """Was beim aehnlichsten geloesten Fall zur Loesung noetig war."""
        return result.hits[0].case.needs if result.hits else ()

    # --- Ableitungen fuer die Anlage ---

    def steckbrief_name(self, draft: Draft) -> str:
        return (draft.title or "Ohne Titel")[:200]

    def steckbrief_specs(
        self, draft: Draft, diagnosis: Diagnosis | None = None
    ) -> tuple[FieldSpec, ...]:
        """Feldreihenfolge des Steckbriefs: Art-Felder, dann Diagnose.

        Deckt die Diagnose ein Art-Feld ab (gleicher Key) oder waehlt sie es ab,
        faellt das Art-Feld hier raus. Sonst stuende dieselbe Angabe zweimal da,
        einmal als "Betroffene Nutzer" und einmal als "Umfang".
        """
        diagnosis = diagnosis or Diagnosis()
        kind_fields = self.rules.spec(draft.kind).fields if draft.kind else ()
        return (
            tuple(f for f in kind_fields if f.key not in diagnosis.covered) + diagnosis.fields
        )

    def labeled_fields(
        self,
        draft: Draft,
        diagnosis: Diagnosis | None = None,
    ) -> list[dict[str, str]]:
        """Gefuellte Felder mit Gruppe, Typ und Besitzer. Jeder Key genau einmal."""
        diagnosis = diagnosis or Diagnosis()
        rows: list[dict[str, str]] = []
        seen: set[str] = set()
        for spec_field in self.steckbrief_specs(draft, diagnosis):
            if spec_field.key in seen:
                continue
            seen.add(spec_field.key)
            if not spec_field.applies(draft.values):
                continue
            value = str(draft.values.get(spec_field.key) or "").strip()
            if not value and not _show_empty_in_review(spec_field):
                continue
            row = {
                "group": spec_field.group,
                "groupLabel": spec_field.group_label,
                "key": spec_field.key,
                "label": spec_field.label,
                "value": value,
                "type": spec_field.type,
                "fill": spec_field.fill,
            }
            if spec_field.values:
                row["values"] = list(spec_field.values)
            rows.append(row)
        for key, value in draft.values.items():
            if key not in seen and key not in diagnosis.skip and value:
                rows.append(
                    {
                        "group": "",
                        "groupLabel": "Sonstiges",
                        "key": key,
                        "label": key,
                        "value": value,
                        "type": "text",
                        "fill": "draft",
                    }
                )
        rank = {name: index for index, name in enumerate(GROUP_LABELS)}
        rows.sort(key=lambda row: rank.get(row["group"], len(rank)))
        return rows

    def field_label_map(
        self,
        draft: Draft,
        diagnosis: Diagnosis | None = None,
    ) -> dict[str, str]:
        """Labels fuer Hinweise. Bei gleichem Key gewinnt die Diagnose."""
        labels: dict[str, str] = {}
        if draft.kind:
            labels.update(
                {k: f.label for k, f in self.rules.spec(draft.kind).field_map().items()}
            )
        for spec_field in (diagnosis or Diagnosis()).fields:
            labels[spec_field.key] = spec_field.label
        return labels

    def missing_hard(self, draft: Draft, diagnosis: Diagnosis | None = None) -> tuple[
        FieldSpec, ...
    ]:
        """Harte Art-Felder, die noch fehlen — ohne alles, was die Diagnose traegt."""
        if not draft.kind:
            return ()
        covered = (diagnosis or Diagnosis()).covered
        return tuple(
            f
            for f in self.rules.spec(draft.kind).hard_fields()
            if f.askable
            and f.applies(draft.values)
            and f.key not in covered
            and _too_thin(f.key, draft.values.get(f.key))
        )

    def missing_soft(self, draft: Draft, diagnosis: Diagnosis | None = None) -> tuple[
        FieldSpec, ...
    ]:
        """Weiche Dialog-Felder, die noch fehlen."""
        if not draft.kind:
            return ()
        covered = (diagnosis or Diagnosis()).covered
        return tuple(
            f
            for f in self.rules.spec(draft.kind).missing_soft_fields(draft.values)
            if f.askable
            and f.key not in covered
            and _too_thin(f.key, draft.values.get(f.key))
        )

    def missing_required_on_confirm(
        self, draft: Draft, diagnosis: Diagnosis | None = None
    ) -> tuple[FieldSpec, ...]:
        """Confirm-Pflichtfelder, die noch fehlen."""
        if not draft.kind:
            return ()
        covered = (diagnosis or Diagnosis()).covered
        return tuple(
            f
            for f in self.rules.spec(draft.kind).fields
            if f.required_on_confirm
            and f.askable
            and f.applies(draft.values)
            and f.key not in covered
            and _too_thin(f.key, draft.values.get(f.key))
        )

    def open_questions(self, draft: Draft, diagnosis: Diagnosis | None = None) -> list[str]:
        """Was fehlt, wird benannt — auch wenn nicht mehr danach gefragt wird.

        Eine harte Diagnosefrage, die der Nutzer nicht beantworten konnte, ist
        eine Luecke. Der Steckbrief darf sich deswegen nicht vollstaendig nennen.
        """
        if diagnosis is None:
            text = " ".join(
                part for part in (draft.title, draft.values.get("description")) if part
            )
            diagnosis = self.diagnose(text, draft.service)
        missing = [
            *self.missing_hard(draft, diagnosis),
            *(
                f
                for f in diagnosis.fields
                if f.hard and not f.auto and not str(draft.values.get(f.key) or "").strip()
            ),
        ]
        if draft.kind:
            missing.extend(
                f
                for f in self.rules.spec(draft.kind).fields
                if f.hard
                and _show_empty_in_review(f)
                and _too_thin(f.key, draft.values.get(f.key))
            )
        labels: list[str] = []
        seen: set[str] = set()
        for spec in missing:
            if spec.label in seen:
                continue
            seen.add(spec.label)
            labels.append(spec.label)
        return labels
