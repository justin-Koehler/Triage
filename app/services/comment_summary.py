"""Kommentar-Rohdaten für den Stand."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Comment, Request

MAX_BLURB = 120


def _sorted_comments(request: Request) -> list[Comment]:
    return sorted(request.comments or [], key=lambda c: c.created_at or 0)


def comments_payload(request: Request) -> list[dict]:
    rows = []
    for c in _sorted_comments(request):
        body = " ".join(str(c.body or "").split()).strip()
        if not body:
            continue
        rows.append(
            {
                "author": c.author_name or "unbekannt",
                "body": body,
                "at": c.created_at.isoformat() if c.created_at else "",
            }
        )
    return rows


def comments_payload_for(db: Session, request: Request) -> list[dict]:
    from sqlalchemy import select

    rows = db.scalars(select(Comment).where(Comment.request_id == request.id)).all()
    request.comments = list(rows)
    return comments_payload(request)


def list_comment_blurb(values: dict[str, str]) -> str:
    text = " ".join(str(values.get("comment_summary") or "").split()).strip()
    if len(text) <= MAX_BLURB:
        return text
    return text[: MAX_BLURB - 1].rsplit(" ", 1)[0] + "…"


def summarize_comments(db: Session, request: Request) -> dict:
    from app.services.stand_summary import refresh_stand

    result = refresh_stand(db, request, llm=True)
    return {
        "ablauf": result.get("ablauf") or result.get("brief") or "",
        "summary": result.get("summary") or result.get("line") or "",
        "unchanged": bool(result.get("unchanged")),
    }
