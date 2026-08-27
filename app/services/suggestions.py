"""Wertelisten fuer Rueckfragen (US-003).

Zwei Quellen: die feste Liste aus config/triage_rules.yaml und das, was
Kolleginnen bei aehnlichen Anliegen schon eingetragen haben. Vorschlag, keine
Pflicht — Freitext bleibt jederzeit moeglich.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.fieldspec import FieldSpec
from app.domain.routing import responsible_names
from app.models import Request, RequestField

MAX_SUGGESTIONS = 5
MAX_LENGTH = 60


def _from_history(db: Session, key: str, kind: str | None, limit: int) -> list[str]:
    stmt = (
        select(RequestField.value, func.count().label("hits"))
        .where(RequestField.key == key, RequestField.value != "")
        .group_by(RequestField.value)
        .order_by(func.count().desc(), RequestField.value)
        .limit(limit * 3)
    )
    if kind:
        stmt = stmt.join(Request, Request.id == RequestField.request_id).where(
            Request.kind == kind
        )
    return [row[0] for row in db.execute(stmt).all() if len(row[0]) <= MAX_LENGTH]


def _from_source(name: str) -> list[str]:
    """Wertelisten, die nicht in der YAML stehen, sondern in eigenen Dateien."""
    if name == "responsibles":
        return responsible_names()
    return []


def values_for(
    db: Session,
    spec: FieldSpec | None,
    kind: str | None = None,
    limit: int = MAX_SUGGESTIONS,
) -> list[str]:
    if spec is None or spec.type == "date":
        return []

    out: list[str] = []
    seen: set[str] = set()
    dynamic = _from_source(spec.values_from) if spec.values_from else []
    for value in [*spec.values, *dynamic, *_from_history(db, spec.key, kind, limit)]:
        normalized = value.strip()
        marker = normalized.lower()
        if not normalized or marker in seen:
            continue
        seen.add(marker)
        out.append(normalized)
        if len(out) >= limit:
            break
    return out
