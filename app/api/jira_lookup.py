"""Jira-Vorschläge für Workspace-Felder (User, Komponenten)."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import SessionLocal, get_db
from app.models import AppSetting, User
from app.ports.fake import FakeTicketSystem
from app.ports.jira_v3 import JiraRestV3
from app.ports.ticket_port import TicketPort, TicketPortError
from app.security import current_actor
from app.services.settings_service import decrypt_secret, get_runtime_config

router = APIRouter(prefix="/api/jira", tags=["jira"])


def _user_jira_credentials(db: Session, user: User) -> tuple[str | None, str | None]:
    token_row = db.get(AppSetting, f"user.{user.id}.jira_token")
    token = decrypt_secret(token_row.value) if (token_row and token_row.value) else None
    email_row = db.get(AppSetting, f"user.{user.id}.jira_email")
    email = (email_row.value or "").strip() if email_row else None
    return token or None, email or None


def _port(db: Session) -> JiraRestV3:
    runtime = get_runtime_config(db)
    if not runtime.jira_enabled or runtime.ticket_port != "jira":
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Jira ist nicht aktiv")
    return JiraRestV3(runtime=runtime)


def _inbox_port(db: Session) -> TicketPort:
    runtime = get_runtime_config(db)
    if runtime.ticket_port == "jira":
        return JiraRestV3(runtime=runtime)
    return FakeTicketSystem(SessionLocal, project=runtime.jira_project_key or "TRI")


@router.get("/users")
def search_users(
    q: str = Query(default="", max_length=80),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(current_actor),
) -> dict:
    token, email = _user_jira_credentials(db, user)
    try:
        items = _port(db).search_assignable_users(
            q, limit=limit, user_token=token, user_email=email
        )
    except TicketPortError as err:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(err)) from err
    return {
        "items": [
            {
                "name": row["name"],
                "displayName": row.get("displayName") or row["name"],
                "label": f'{row.get("displayName") or row["name"]} ({row["name"]})',
                "avatarUrl": row.get("avatarUrl") or "",
            }
            for row in items
        ]
    }


@router.get("/components")
def search_components(
    q: str = Query(default="", max_length=80),
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(current_actor),
) -> dict:
    token, email = _user_jira_credentials(db, user)
    try:
        from app.services.component_tree import build_component_tree, flatten_tree

        records = _port(db).list_component_records(user_token=token, user_email=email)
        tree = build_component_tree(records)
        items = flatten_tree(tree)
        needle = (q or "").strip().casefold()
        if needle:
            items = [
                row
                for row in items
                if needle in row["name"].casefold() or needle in (row.get("description") or "").casefold()
            ]
        items = items[: max(1, min(limit, 200))]
    except TicketPortError as err:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(err)) from err
    return {"items": items, "tree": tree}


@router.get("/options")
def search_options(
    field: str = Query(..., min_length=2, max_length=64),
    q: str = Query(default="", max_length=80),
    limit: int = Query(default=100, ge=1, le=200),
    kind: str = Query(default="it_request", max_length=32),
    db: Session = Depends(get_db),
    user: User = Depends(current_actor),
) -> dict:
    """AllowedValues für Option-Felder (Solution Category, Solution, …)."""
    from app.domain.types import parse_kind

    token, email = _user_jira_credentials(db, user)
    issue_kind = parse_kind(kind)
    try:
        names = _port(db).list_field_options(
            field,
            kind=issue_kind,
            query=q,
            limit=limit,
            user_token=token,
            user_email=email,
        )
    except TicketPortError as err:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(err)) from err
    return {"items": [{"name": name, "label": name} for name in names]}


class JiraResolveIn(BaseModel):
    kind: str = Field(pattern="^(user|components|option)$")
    value: str = Field(default="", max_length=500)
    field: str = Field(default="", max_length=64)


@router.post("/resolve")
def resolve_value(
    payload: JiraResolveIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_actor),
) -> dict:
    token, email = _user_jira_credentials(db, user)
    port = _port(db)
    try:
        if payload.kind == "user":
            hit = port.resolve_user(payload.value, user_token=token, user_email=email)
            if not hit:
                return {"resolved": None, "label": None, "value": payload.value}
            rows = port.search_assignable_users(
                hit["name"], limit=1, user_token=token, user_email=email
            )
            display = rows[0]["displayName"] if rows else hit["name"]
            return {
                "resolved": hit["name"],
                "label": f"{display} ({hit['name']})",
                "value": hit["name"],
            }
        if payload.kind == "option":
            field_key = (payload.field or "").strip()
            if not field_key:
                return {"resolved": None, "label": None, "value": payload.value}
            options = port.list_field_options(
                field_key,
                query=payload.value,
                limit=20,
                user_token=token,
                user_email=email,
            )
            needle = payload.value.strip().lower()
            exact = next((name for name in options if name.lower() == needle), None)
            if not exact and len(options) == 1:
                exact = options[0]
            if not exact:
                return {"resolved": None, "label": None, "value": payload.value}
            return {"resolved": exact, "label": exact, "value": exact}
        parts = port.resolve_components(payload.value, user_token=token, user_email=email)
        if not parts:
            return {"resolved": None, "label": None, "value": payload.value}
        names = [part["name"] for part in parts]
        joined = ", ".join(names)
        return {"resolved": joined, "label": joined, "value": joined}
    except TicketPortError as err:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(err)) from err


@router.get("/issues")
def list_issues(
    q: str = Query(default="", max_length=80),
    limit: int = Query(default=50, ge=1, le=100),
    sync: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(current_actor),
) -> dict:
    from app.services.jira_inbox import list_inbox, sync_comments_batch

    token, email = _user_jira_credentials(db, user)
    try:
        port = _inbox_port(db)
        body = list_inbox(
            db,
            port,
            query=q,
            limit=limit,
            user_token=token,
            user_email=email,
            actor=user,
        )
        sync_info = {"synced": 0, "updated": 0, "failed": 0}
        if sync:
            keys = [str(item.get("key") or "") for item in (body.get("items") or [])]
            sync_info = sync_comments_batch(
                db, port, keys=keys, limit=limit, user_token=token, user_email=email
            )
            # Stand-Zeilen nach Sync neu lesen
            body = list_inbox(
                db,
                port,
                query=q,
                limit=limit,
                user_token=token,
                user_email=email,
                actor=user,
            )
        body["sync"] = sync_info
        return body
    except TicketPortError as err:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(err)) from err


@router.post("/hooks/sync")
def webhook_sync_comments(
    payload: dict = Body(default_factory=dict),
    key: str = Query(default="", max_length=64),
    secret: str = Query(default="", max_length=200),
    db: Session = Depends(get_db),
) -> dict:
    """Jira-Webhook oder manueller Trigger: Kommentare eines Tickets nachziehen."""
    from app.config import get_settings
    from app.services.jira_inbox import sync_comments_batch

    settings = get_settings()
    expected = (settings.jira_webhook_secret or "").strip()
    if not expected or secret.strip() != expected:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Webhook-Secret ungültig")
    issue_key = (key or "").strip()
    if not issue_key and isinstance(payload, dict):
        issue = payload.get("issue") if isinstance(payload.get("issue"), dict) else {}
        issue_key = str(issue.get("key") or payload.get("key") or "").strip()
    if not issue_key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Issue-Key fehlt")
    stats = sync_comments_batch(db, _inbox_port(db), keys=[issue_key], limit=1)
    return {"ok": True, "key": issue_key, **stats}


@router.post("/issues/{key}/import")
def import_issue(
    key: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(current_actor),
) -> dict:
    from app.api.requests import _stand_later
    from app.services.jira_inbox import import_issue_view

    token, email = _user_jira_credentials(db, user)
    try:
        body = import_issue_view(
            db,
            _inbox_port(db),
            key,
            user=user,
            user_token=token,
            user_email=email,
        )
    except LookupError as err:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(err)) from err
    except TicketPortError as err:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(err)) from err
    rid = str(body.get("id") or "").strip()
    if rid:
        background_tasks.add_task(_stand_later, rid)
    return body
