"""Jira-Vorschläge für Workspace-Felder (User, Komponenten)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AppSetting, User
from app.ports.jira_v3 import JiraRestV3
from app.ports.ticket_port import TicketPortError
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
        names = _port(db).search_components(
            q, limit=limit, user_token=token, user_email=email
        )
    except TicketPortError as err:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(err)) from err
    return {"items": [{"name": name, "label": name} for name in names]}


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
