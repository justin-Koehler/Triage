from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.domain.types import Priority, RequestKind, RequestStatus
from app.models import StatusUpdate, User
from app.schemas import AiFillIn, CommentIn, MessageIn, RequestPatch, StatusUpdateIn
from app.security import current_actor, optional_user, required_user
from app.services import requests_service as svc
from app.services.settings_service import get_runtime_config
from app.services.status_summary import StatusEmpty
from app.services.status_summary import summarize as summarize_status
from app.services.ticket_chat import TicketChatService
from app.triage.providers import build_provider_from_runtime

router = APIRouter(prefix="/api/requests", tags=["requests"])


def get_ticket_chat(db: Session = Depends(get_db)) -> TicketChatService:
    provider = build_provider_from_runtime(get_runtime_config(db))
    return TicketChatService(db=db, provider=provider)


SortField = Literal["created", "updated", "priority", "status", "reference", "title", "attention"]
SortDir = Literal["asc", "desc"]


@router.get("/meta/filters")
def filters(db: Session = Depends(get_db)) -> dict:
    return svc.filter_options(db)


@router.get("/meta/stats")
def stats(db: Session = Depends(get_db)) -> dict:
    return svc.status_counts(db)


@router.get("")
def list_requests(
    kind: RequestKind | None = None,
    status_filter: RequestStatus | None = Query(default=None, alias="status"),
    priority: Priority | None = None,
    company: str | None = None,
    change_lead: str | None = Query(default=None, alias="responsible"),
    q: str | None = None,
    sort: SortField = "created",
    dir: SortDir = "desc",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(current_actor),
) -> dict:
    return svc.list_requests(
        db,
        svc.RequestFilter(
            kind=kind,
            status=status_filter,
            priority=priority,
            company=company,
            change_lead=change_lead,
            query=q,
            sort=sort,
            direction=dir,
            limit=limit,
            offset=offset,
        ),
        actor=user,
    )


@router.get("/export.csv")
def export_csv(
    kind: RequestKind | None = None,
    status_filter: RequestStatus | None = Query(default=None, alias="status"),
    priority: Priority | None = None,
    company: str | None = None,
    change_lead: str | None = Query(default=None, alias="responsible"),
    q: str | None = None,
    sort: SortField = "created",
    dir: SortDir = "desc",
    db: Session = Depends(get_db),
    _user: User = Depends(required_user),
) -> Response:
    """Semikolon und BOM, damit Excel die Datei ohne Importdialog richtig oeffnet."""
    rows = svc.export_rows(
        db,
        svc.RequestFilter(
            kind=kind,
            status=status_filter,
            priority=priority,
            company=company,
            change_lead=change_lead,
            query=q,
            sort=sort,
            direction=dir,
        ),
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerows(rows)
    filename = f"anliegen-{datetime.now(UTC).strftime('%Y%m%d-%H%M')}.csv"
    return Response(
        content="\ufeff" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{request_id}")
def get_request(
    request_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_actor),
) -> dict:
    request = svc.get_request(db, request_id)
    if not request:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anliegen unbekannt")
    return svc.to_detail(request, actor=user)


@router.get("/{request_id}/chat")
def get_ticket_chat_history(
    request_id: str,
    db: Session = Depends(get_db),
    chat: TicketChatService = Depends(get_ticket_chat),
    user: User | None = Depends(optional_user),
) -> dict:
    request = svc.get_request(db, request_id)
    if not request:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anliegen unbekannt")
    session = chat.ensure_session(request, user)
    return {"sessionId": session.id, "messages": chat.history(session)}


@router.post("/{request_id}/chat")
def post_ticket_chat(
    request_id: str,
    payload: MessageIn,
    db: Session = Depends(get_db),
    chat: TicketChatService = Depends(get_ticket_chat),
    user: User = Depends(current_actor),
) -> dict:
    request = svc.get_request(db, request_id)
    if not request:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anliegen unbekannt")
    session = chat.ensure_session(request, user)
    return chat.handle(session, request, payload.text, actor=user)


@router.patch("/{request_id}")
def patch_request(
    request_id: str,
    payload: RequestPatch,
    db: Session = Depends(get_db),
    _user: User = Depends(required_user),
) -> dict:
    request = svc.get_request(db, request_id)
    if not request:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anliegen unbekannt")
    changes = payload.changes()
    if not changes:
        return svc.to_detail(request)
    updated = svc.update_request(db, request, changes)
    return svc.to_detail(updated)


@router.post("/{request_id}/ai-fill")
def post_ai_fill(
    request_id: str,
    payload: AiFillIn,
    db: Session = Depends(get_db),
    _user: User = Depends(required_user),
) -> dict:
    request = svc.get_request(db, request_id)
    if not request:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anliegen unbekannt")
    updated = svc.ai_fill_request(
        db, request, field_key=payload.fieldKey, overwrite=payload.overwrite
    )
    return svc.to_detail(updated)


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_request(
    request_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(required_user),
) -> Response:
    request = svc.get_request(db, request_id)
    if not request:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anliegen unbekannt")
    svc.delete_request(db, request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{request_id}/comments")
def post_comment(
    request_id: str,
    payload: CommentIn,
    db: Session = Depends(get_db),
    user: User = Depends(required_user),
) -> dict:
    request = svc.get_request(db, request_id)
    if not request:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anliegen unbekannt")
    comment = svc.add_comment(db, request, payload.body, user)
    return {
        "id": comment.id,
        "author": comment.author_name,
        "body": comment.body,
        "createdAt": comment.created_at.isoformat(),
    }


@router.post("/{request_id}/status-summary")
def post_status_summary(
    request_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(required_user),
) -> dict:
    request = svc.get_request(db, request_id)
    if not request:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anliegen unbekannt")
    try:
        return summarize_status(db, request)
    except StatusEmpty as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err


@router.post("/{request_id}/status-updates")
def post_status_update(
    request_id: str,
    payload: StatusUpdateIn,
    db: Session = Depends(get_db),
    _user: User = Depends(required_user),
) -> dict:
    request = svc.get_request(db, request_id)
    if not request:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anliegen unbekannt")
    item = svc.create_status_update(
        db, request, payload.model_dump(exclude_none=True)
    )
    return svc._status_update_view(item)


@router.patch("/{request_id}/status-updates/{update_id}")
def patch_status_update(
    request_id: str,
    update_id: str,
    payload: StatusUpdateIn,
    db: Session = Depends(get_db),
    _user: User = Depends(required_user),
) -> dict:
    request = svc.get_request(db, request_id)
    if not request:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anliegen unbekannt")
    item = db.get(StatusUpdate, update_id)
    if not item or item.request_id != request.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Status-Update unbekannt")
    updated = svc.update_status_update(db, item, payload.model_dump(exclude_none=True))
    return svc._status_update_view(updated)
