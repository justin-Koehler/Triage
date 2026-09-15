"""Autor-Felder aus Jira-Reporter nachziehen (einmalig / wartbar)."""

from __future__ import annotations

import argparse
import re
import sys

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import SessionLocal
from app.models import ExternalRef, Request
from app.ports import build_ticket_port
from app.services.jira_inbox import FIELD_LABELS, _upsert_field

GENERIC = re.compile(r"^(tu\s+campus\s+it|campus\s+it|jira|system|admin|service\b)", re.I)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _looks_same(a: str, b: str) -> bool:
    left, right = (a or "").strip(), (b or "").strip()
    if not left or not right:
        return False
    if left.lower() == right.lower():
        return True
    nl, nr = _norm(left), _norm(right)
    if nl and nr and (nl in nr or nr in nl):
        return True
    parts = [p for p in re.split(r"[\s.@_-]+", right.lower()) if p]
    if left.lower() in parts or any(p and p in left.lower() for p in parts if len(p) > 3):
        return True
    return False


def _is_accountish(value: str) -> bool:
    v = (value or "").strip()
    if not v:
        return True
    if " " in v or "@" in v:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9._-]{2,40}", v))


def _should_replace(existing: str, reporter: str) -> str | None:
    if not reporter:
        return None
    if GENERIC.search(reporter.strip()):
        return "set" if not existing else None
    if not existing:
        return "set"
    if _looks_same(existing, reporter):
        return "rename" if existing != reporter else None
    if _is_accountish(existing):
        return "fix"
    return "fix"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Änderungen speichern")
    args = parser.parse_args()

    port = build_ticket_port()
    changed = skipped = failed = 0

    with SessionLocal() as db:
        refs = db.scalars(
            select(ExternalRef)
            .options(selectinload(ExternalRef.request).selectinload(Request.fields))
            .where(ExternalRef.external_key.is_not(None))
        ).all()

        print(f"{'KEY':10} {'WAS':32} {'REPORTER':28} ACTION")
        for ref in refs:
            key = (ref.external_key or "").strip()
            req = ref.request
            if not key or not req:
                continue
            existing = next(
                (str(f.value or "").strip() for f in (req.fields or []) if f.key == "author"),
                "",
            )
            try:
                issue = port.inbox_issue(key)
            except Exception as err:  # noqa: BLE001
                failed += 1
                print(f"{key:10} {(existing or '-'):32} ERR:{err}")
                continue
            if not issue:
                failed += 1
                print(f"{key:10} {(existing or '-'):32} MISSING")
                continue

            reporter = str(issue.get("reporter") or "").strip()
            action = _should_replace(existing, reporter)
            if not action:
                skipped += 1
                print(f"{key:10} {(existing or '-'):32} {(reporter or '-'):28} keep")
                continue

            print(f"{key:10} {(existing or '-'):32} {reporter[:28]:28} {action}")
            if args.apply:
                _upsert_field(req, "author", reporter[:500])
                field = next((f for f in req.fields if f.key == "author"), None)
                if field:
                    field.label = FIELD_LABELS.get("author", "Autor")
                changed += 1

        if args.apply:
            db.commit()

    print(
        f"\ndone apply={args.apply} changed={changed} skipped={skipped} failed={failed}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
