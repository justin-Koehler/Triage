"""Themen-Playbooks: diagnostische Fragen pro Problem, nicht pro Anliegen-Art.

Neue Diagnose = neue Markdown-Datei in config/topics/. Match ueber Stichwoerter
oder den erkannten Service-Slug. Cache haengt an der mtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from app.config import get_settings
from app.domain import text as markdown
from app.domain.fieldspec import FieldSpec, parse_values
from app.domain.text import mentions
from app.domain.types import RequestKind, parse_kind

DEFAULT_MAX_QUESTIONS = 2


@dataclass(frozen=True)
class Topic:
    name: str
    display: str
    match: tuple[str, ...]
    fields: tuple[FieldSpec, ...]
    # Ein Playbook kennt die Art. Steht sie hier, wird sie nicht erfragt.
    kind: RequestKind | None = None
    # Art-Felder, die dieses Thema sinnlos macht: Produktion/Staging trifft kein
    # WLAN. Sie werden nicht gefragt, nicht gefuellt, nicht angezeigt.
    skip: tuple[str, ...] = ()
    max_questions: int = DEFAULT_MAX_QUESTIONS

    def field_map(self) -> dict[str, FieldSpec]:
        return {f.key: f for f in self.fields}

    def hard_fields(self) -> tuple[FieldSpec, ...]:
        return tuple(f for f in self.fields if f.hard)


def parse_question_fields(section: str) -> tuple[FieldSpec, ...]:
    """`## Fragen`-Abschnitt als YAML-Liste lesen. Kaputter Block = leere Liste."""
    if not section.strip():
        return ()
    try:
        raw = yaml.safe_load(section)
    except yaml.YAMLError:
        return ()
    if not isinstance(raw, list):
        return ()
    out: list[FieldSpec] = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("key") or not item.get("question"):
            continue
        key = str(item["key"]).strip()
        label = str(item.get("label") or key).strip()
        values, aliases = parse_values(item.get("values"))
        out.append(
            FieldSpec(
                key=key,
                label=label,
                question=str(item["question"]).strip(),
                hard=bool(item.get("hard", True)),
                type=str(item.get("type") or "text"),
                values=values,
                aliases=aliases,
                auto=bool(item.get("auto", False)),
                group=str(item.get("group") or ""),
                fill=str(item.get("fill") or "dialog"),
            )
        )
    return tuple(out)


def _parse_topic(path: Path) -> Topic | None:
    meta, body = markdown.read(path)
    name = str(meta.get("name") or path.stem).strip().lower()
    if not name or name == "readme":
        return None
    match = tuple(
        str(m).strip().lower() for m in (meta.get("match") or []) if str(m).strip()
    )
    blocks = markdown.sections(body)
    fields = parse_question_fields(blocks.get("fragen", ""))
    max_q = meta.get("max_questions")
    return Topic(
        name=name,
        display=str(meta.get("display") or name).strip(),
        match=match,
        fields=fields,
        kind=parse_kind(meta.get("kind")),
        skip=tuple(str(s).strip() for s in (meta.get("skip") or []) if str(s).strip()),
        max_questions=int(max_q) if max_q else DEFAULT_MAX_QUESTIONS,
    )


_cache: tuple[tuple, tuple[Topic, ...]] | None = None


def load_topics() -> tuple[Topic, ...]:
    global _cache
    directory = get_settings().topics_dir
    paths = sorted(directory.glob("*.md")) if directory.is_dir() else []
    stamp = markdown.signature(paths)
    if _cache and _cache[0] == stamp:
        return _cache[1]
    loaded = tuple(topic for path in paths if (topic := _parse_topic(path)))
    _cache = (stamp, loaded)
    return loaded


def find_topic(name: str) -> Topic | None:
    wanted = name.strip().lower()
    return next((t for t in load_topics() if t.name == wanted), None)


def match_topic(text: str, service: str | None = None) -> Topic | None:
    """Service-Slug zuerst, sonst Stichwort-Treffer. Mehr Treffer = besser."""
    topics = load_topics()
    if not topics:
        return None
    if service:
        by_name = find_topic(service)
        if by_name:
            return by_name
    scored: list[tuple[int, Topic]] = []
    for topic in topics:
        hits = sum(
            1
            for needle in topic.match
            if needle and mentions(text, needle, substring=" " in needle)
        )
        if hits:
            scored.append((hits, topic))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def merge_fields(
    case_fields: tuple[FieldSpec, ...],
    topic_fields: tuple[FieldSpec, ...],
) -> tuple[FieldSpec, ...]:
    """Fall-Fragen zuerst, dann Playbook. Doppelte Keys nur einmal (Fall gewinnt)."""
    seen: set[str] = set()
    out: list[FieldSpec] = []
    for spec in (*case_fields, *topic_fields):
        if spec.key in seen:
            continue
        seen.add(spec.key)
        out.append(spec)
    return tuple(out)
