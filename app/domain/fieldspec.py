"""Pflichtfelder und Signale kommen aus config/triage_rules.yaml, nicht aus dem Code."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from app.config import get_settings
from app.domain.text import mentions
from app.domain.types import Priority, RequestKind, parse_priority

TRUTHY = {"ja", "yes", "true", "1", "wahr", "erforderlich", "notwendig"}
FALSY = {"nein", "no", "false", "0", "keine", "nicht nötig", "nicht notwendig"}

# Wer das Feld fuellt. Nur `dialog` darf eine Chat-Frage kosten.
FILL_DIALOG = "dialog"
FILL_DRAFT = "draft"
FILL_WORKSPACE = "workspace"
FILL_CONTROLLING = "controlling"
FILL_COMPUTED = "computed"
ASKABLE_FILLS = {FILL_DIALOG}
AI_AUTOFILL_EMPTY = "autofill_empty"
AI_SUGGEST_ONLY = "suggest_only"
AI_MANUAL_ONLY = "manual_only"
SYNC_JIRA_FIELD = "jira_field"
SYNC_JIRA_DESCRIPTION = "jira_description"
SYNC_LOCAL_ONLY = "local_only"

GROUP_LABELS: dict[str, str] = {
    "kopf": "Kopf",
    "uebersicht": "Übersicht",
    "team": "Team & Beteiligte",
    "status": "Status",
    "finanzen": "Finanzen, Budget & Gemeinnützigkeit",
    "kalkulation": "Kalkulation",
    "sonstiges": "Sonstiges",
}


def as_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    raw = str(value).strip().lower()
    if raw in TRUTHY:
        return True
    if raw in FALSY:
        return False
    return None


def parse_values(raw: object) -> tuple[tuple[str, ...], dict[str, tuple[str, ...]]]:
    """Werteliste lesen. Ein Eintrag darf `{value: …, match: [Synonyme]}` sein."""
    if isinstance(raw, str):
        items: list = [v.strip() for v in raw.split(",") if v.strip()]
    elif isinstance(raw, list):
        items = raw
    else:
        return (), {}

    values: list[str] = []
    aliases: dict[str, tuple[str, ...]] = {}
    for item in items:
        if isinstance(item, dict):
            value = str(item.get("value") or "").strip()
            match = item.get("match") or []
            if isinstance(match, str):
                match = match.split(",")
            synonyms = tuple(str(m).strip() for m in match if str(m).strip())
            if value and synonyms:
                aliases[value] = synonyms
        else:
            value = str(item).strip()
        if value:
            values.append(value)
    return tuple(values), aliases


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    question: str
    hard: bool = False
    only_if: dict[str, bool] = field(default_factory=dict)
    type: str = "text"
    values: tuple[str, ...] = ()
    aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)
    values_from: str = ""
    auto: bool = False
    group: str = ""
    fill: str = FILL_DIALOG
    formula: str = ""
    required_on_confirm: bool = False
    ai_mode: str = AI_AUTOFILL_EMPTY
    sync_mode: str = SYNC_LOCAL_ONLY

    def applies(self, values: dict[str, str]) -> bool:
        for dep_key, expected in self.only_if.items():
            if as_bool(values.get(dep_key)) is not expected:
                return False
        return True

    @property
    def askable(self) -> bool:
        return self.fill in ASKABLE_FILLS and not self.auto

    @property
    def group_label(self) -> str:
        return GROUP_LABELS.get(self.group, self.group or "Sonstiges")

    def mentioned_value(self, text: str) -> str | None:
        """Erster Wert, der im Text steht — als Wort oder als Synonym."""
        for value in self.values:
            if any(mentions(text, needle) for needle in (value, *self.aliases.get(value, ()))):
                return value
        return None

    def allowed_value(self, text: str) -> str | None:
        """Genau ein Wert aus der Liste oder nichts. Fuer Werte des Modells."""
        raw = str(text).strip()
        if not raw:
            return None
        if not self.values:
            return raw
        lowered = raw.lower()
        for value in self.values:
            if lowered == value.lower():
                return value
        return self.mentioned_value(raw)

    def normalize(self, text: str) -> str:
        """Antwort des Nutzers auf einen erlaubten Wert ziehen, wenn einer gemeint ist."""
        return self.allowed_value(text) or str(text).strip()


@dataclass(frozen=True)
class KindSpec:
    kind: RequestKind
    default_priority: Priority
    signals: tuple[str, ...]
    fields: tuple[FieldSpec, ...]
    max_questions: int | None = None

    def field_map(self) -> dict[str, FieldSpec]:
        return {f.key: f for f in self.fields}

    def hard_fields(self) -> tuple[FieldSpec, ...]:
        return tuple(f for f in self.fields if f.hard)

    def missing_hard_fields(self, values: dict[str, str]) -> tuple[FieldSpec, ...]:
        return tuple(
            f
            for f in self.fields
            if f.hard
            and f.askable
            and f.applies(values)
            and not str(values.get(f.key) or "").strip()
        )

    def missing_soft_fields(self, values: dict[str, str]) -> tuple[FieldSpec, ...]:
        return tuple(
            f
            for f in self.fields
            if not f.hard
            and f.askable
            and f.applies(values)
            and not str(values.get(f.key) or "").strip()
        )


@dataclass(frozen=True)
class TriageRules:
    max_questions: int
    confidence_threshold: float
    kinds: dict[RequestKind, KindSpec]

    def spec(self, kind: RequestKind) -> KindSpec:
        return self.kinds[kind]

    def budget_for(self, kind: RequestKind | None) -> int:
        """Frage-Budget der Art. Solange die Art unklar ist, gilt der globale Wert."""
        spec = self.kinds.get(kind) if kind else None
        return spec.max_questions if spec and spec.max_questions else self.max_questions

    def label_for(self, kind: RequestKind, key: str) -> str:
        spec = self.kinds.get(kind)
        if spec and key in spec.field_map():
            return spec.field_map()[key].label
        return key

    def guess_kind(self, text: str) -> RequestKind | None:
        """Signalbasierte Notfall-Klassifikation, wenn kein LLM antwortet."""
        lowered = text.lower()
        best: tuple[int, RequestKind] | None = None
        for kind, spec in self.kinds.items():
            hits = sum(1 for signal in spec.signals if signal in lowered)
            if hits and (best is None or hits > best[0]):
                best = (hits, kind)
        return best[1] if best else None


def _field(raw: dict) -> FieldSpec:
    values, aliases = parse_values(raw.get("values"))
    fill = str(raw.get("fill") or FILL_DIALOG)
    field_type = str(raw.get("type") or "text")
    default_ai_mode = (
        AI_SUGGEST_ONLY if field_type == "longtext" else AI_AUTOFILL_EMPTY
    )
    if fill == FILL_COMPUTED:
        default_ai_mode = AI_MANUAL_ONLY
    return FieldSpec(
        key=raw["key"],
        label=raw["label"],
        question=raw["question"],
        hard=bool(raw.get("hard")),
        only_if={k: bool(v) for k, v in (raw.get("only_if") or {}).items()},
        type=field_type,
        values=values,
        aliases=aliases,
        values_from=str(raw.get("values_from") or ""),
        auto=bool(raw.get("auto")),
        group=str(raw.get("group") or ""),
        fill=fill,
        formula=str(raw.get("formula") or ""),
        required_on_confirm=bool(raw.get("required_on_confirm", False)),
        ai_mode=str(raw.get("ai_mode") or default_ai_mode),
        sync_mode=str(raw.get("sync_mode") or SYNC_LOCAL_ONLY),
    )


def load_rules(path: Path | None = None) -> TriageRules:
    settings = get_settings()
    raw = yaml.safe_load((path or settings.triage_rules_path).read_text(encoding="utf-8"))

    common = tuple(_field(f) for f in (raw.get("common_fields") or []))

    kinds: dict[RequestKind, KindSpec] = {}
    for key, block in (raw.get("kinds") or {}).items():
        kind = RequestKind(key)
        exclude = {str(name).strip() for name in (block.get("exclude_fields") or []) if str(name).strip()}
        specs = tuple(f for f in common if f.key not in exclude) + tuple(
            _field(f) for f in (block.get("fields") or [])
        )
        kinds[kind] = KindSpec(
            kind=kind,
            default_priority=parse_priority(block.get("default_priority")) or Priority.MEDIUM,
            signals=tuple(str(s).lower() for s in (block.get("signals") or [])),
            fields=specs,
            max_questions=int(block["max_questions"]) if block.get("max_questions") else None,
        )

    return TriageRules(
        max_questions=int(raw.get("max_questions", 8)),
        confidence_threshold=float(raw.get("confidence_threshold", 0.45)),
        kinds=kinds,
    )


@lru_cache
def get_rules() -> TriageRules:
    return load_rules()
