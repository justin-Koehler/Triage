from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Response, UploadFile, status
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


def _sync_request_later(request_id: str) -> None:
    import logging

    from app.db import SessionLocal
    from app.ports import build_ticket_port
    from app.sync.outbox import process_request

    log = logging.getLogger("triage.sync")
    with SessionLocal() as session:
        try:
            stats = process_request(session, build_ticket_port(), request_id)
            session.commit()
            if any(stats.values()):
                log.info("comment sync %s %s", request_id[:8], stats)
        except Exception:
            session.rollback()
            log.exception("comment sync fehlgeschlagen %s", request_id)


def _stand_later(request_id: str, expect_comment_id: str | None = None) -> None:
    """Stand-Briefing nach Commit — nie im Request-Pfad (LLM blockiert sonst)."""
    import logging
    import time

    from app.db import SessionLocal
    from app.services.stand_summary import refresh_stand

    log = logging.getLogger("triage.stand")
    for attempt in range(6):
        with SessionLocal() as session:
            try:
                request = svc.get_request(session, request_id)
                if not request:
                    return
                # Frische Kommentare aus der DB — nicht die ggf. stale Collection
                from sqlalchemy import select

                from app.models import Comment

                rows = list(
                    session.scalars(select(Comment).where(Comment.request_id == request_id)).all()
                )
                request.comments = rows
                if expect_comment_id and not any(c.id == expect_comment_id for c in rows):
                    session.rollback()
                    time.sleep(0.12 * (attempt + 1))
                    continue
                refresh_stand(session, request, llm=True)
                session.commit()
                return
            except Exception:
                session.rollback()
                log.exception("stand refresh fehlgeschlagen %s", request_id[:8])
                return
    log.warning(
        "stand refresh: Kommentar %s noch nicht sichtbar für %s",
        (expect_comment_id or "")[:8],
        request_id[:8],
    )


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
    background_tasks: BackgroundTasks,
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
    if any(k in changes for k in ("change_lead", "status", "priority")):
        background_tasks.add_task(_sync_request_later, request_id)
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
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(required_user),
) -> dict:
    from app.services.stand_summary import refresh_stand

    request = svc.get_request(db, request_id)
    if not request:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anliegen unbekannt")
    comment = svc.add_comment(db, request, payload.body, user)
    # Sofort Fallback inkl. neuem Kommentar; LLM danach im Hintergrund
    stand = refresh_stand(db, request, llm=False)
    # Vor Background committen — sonst sieht _stand_later den Kommentar nicht
    db.commit()
    background_tasks.add_task(_sync_request_later, request_id)
    background_tasks.add_task(_stand_later, request_id, comment.id)
    return {
        "id": comment.id,
        "author": comment.author_name,
        "body": comment.body,
        "createdAt": comment.created_at.isoformat(),
        "commentAblauf": (stand.get("brief") or "").strip(),
        "commentSummary": (stand.get("line") or "").strip(),
        "standPending": True,
    }


@router.delete("/{request_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    request_id: str,
    comment_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(required_user),
) -> Response:
    from app.api.jira_lookup import _inbox_port, _user_jira_credentials
    from app.ports.ticket_port import TicketPortError

    request = svc.get_request(db, request_id)
    if not request:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anliegen unbekannt")
    comment = next((c for c in (request.comments or []) if c.id == comment_id), None)
    external_id = str(comment.external_id or "").strip() if comment else ""
    jira_key = next(
        (
            str(r.external_key or "").strip()
            for r in (request.external_refs or [])
            if str(r.external_key or "").strip()
        ),
        "",
    )
    if not svc.delete_comment(db, request, comment_id, user_id=user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kommentar unbekannt")
    # Sofort in Jira löschen, damit Sync den Kommentar nicht zurückholt
    if external_id and jira_key:
        token, email = _user_jira_credentials(db, user)
        try:
            _inbox_port(db).delete_comment(
                jira_key,
                external_id,
                user_token=token,
                user_email=email,
            )
        except TicketPortError:
            # Outbox retry übernimmt
            pass
        except Exception:
            pass
    db.commit()
    background_tasks.add_task(_sync_request_later, request_id)
    background_tasks.add_task(_stand_later, request_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{request_id}/attachments")
async def post_attachment(
    request_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(required_user),
) -> dict:
    from app.api.jira_lookup import _inbox_port
    from app.ports.ticket_port import TicketPortError
    from app.services.jira_inbox import upload_attachment

    request = svc.get_request(db, request_id)
    if not request:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anliegen unbekannt")
    raw = await file.read()
    try:
        att = upload_attachment(
            db,
            _inbox_port(db),
            request,
            filename=file.filename or "anhang",
            content=raw,
            content_type=file.content_type or "application/octet-stream",
            user=user,
        )
        db.commit()
    except TicketPortError as err:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err
    except Exception as err:
        db.rollback()
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Upload fehlgeschlagen: {err}"
        ) from err
    return {
        "id": att.id,
        "externalId": att.external_id,
        "filename": att.filename,
        "contentType": att.content_type or "",
        "size": int(att.size_bytes or 0),
        "author": att.author_name or "",
        "createdAt": att.created_at.isoformat() if att.created_at else "",
        "source": "jira" if att.external_id else "local",
    }


@router.get("/{request_id}/attachments/{attachment_id}/content")
def get_attachment_content(
    request_id: str,
    attachment_id: str,
    thumb: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(required_user),
) -> Response:
    from urllib.parse import quote

    from app.api.jira_lookup import _inbox_port, _user_jira_credentials
    from app.models import RequestAttachment
    from app.ports.ticket_port import TicketPortError

    request = svc.get_request(db, request_id)
    if not request:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anliegen unbekannt")
    att = next((a for a in (request.attachments or []) if a.id == attachment_id), None)
    if not att:
        # Fallback: frisch laden
        att = db.get(RequestAttachment, attachment_id)
        if not att or att.request_id != request_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Anhang unbekannt")
    external_id = str(att.external_id or "").strip()
    if not external_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kein Jira-Anhang")
    token, email = _user_jira_credentials(db, user)
    try:
        content, filename, content_type = _inbox_port(db).download_attachment(
            external_id,
            user_token=token,
            user_email=email,
            thumbnail=bool(thumb),
        )
    except TicketPortError as err:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(err)) from err
    name = filename or att.filename or "anhang"
    safe = quote(name)
    media = (content_type or att.content_type or "").strip() or "application/octet-stream"
    # Bildvorschau im Browser: nie als Download erzwingen
    if media.startswith("image/") or str(att.filename or "").lower().endswith(
        (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
    ):
        if not media.startswith("image/"):
            ext = str(att.filename or name).rsplit(".", 1)[-1].lower()
            media = {
                "png": "image/png",
                "jpg": "image/jpeg",
                "jpeg": "image/jpeg",
                "gif": "image/gif",
                "webp": "image/webp",
                "svg": "image/svg+xml",
            }.get(ext, "image/png")
    return Response(
        content=content,
        media_type=media,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{safe}",
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
    )


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
