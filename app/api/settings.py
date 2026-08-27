from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.ports.jira_v3 import jira_auth
from app.ports.ticket_port import TicketPortError
from app.schemas import SettingsIn
from app.security import required_user
from app.services import settings_service as svc
from app.triage.providers import LlmUnavailable, build_provider_from_runtime

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings_api(db: Session = Depends(get_db)) -> dict:
    return svc.public_settings(db)


@router.put("")
def put_settings(
    payload: SettingsIn,
    db: Session = Depends(get_db),
    _: User = Depends(required_user),
) -> dict:
    try:
        return svc.update_settings(
            db,
            payload.model_dump(exclude_none=False),
        )
    except ValueError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err


@router.post("/test-llm")
def test_llm(db: Session = Depends(get_db), _: User = Depends(required_user)) -> dict:
    runtime = svc.get_runtime_config(db)
    provider = build_provider_from_runtime(runtime)
    try:
        # OpenAI-kompatibel: Modell einmal aufloesen und speichern, dann reicht URL+Key.
        if runtime.llm_provider == "openai" and hasattr(provider, "ensure_model"):
            resolved = provider.ensure_model()
            if resolved and resolved != runtime.llm_model:
                svc.update_settings(db, {"llm": {"model": resolved}})
                runtime = svc.get_runtime_config(db)
                provider = build_provider_from_runtime(runtime)
        result = provider.complete_json(
            'Antworte nur als JSON: {"ok": true}',
            'Ping. Antworte mit {"ok": true}.',
        )
        return {
            "ok": True,
            "provider": provider.name,
            "model": getattr(provider, "_model", runtime.llm_model),
            "sample": result,
        }
    except LlmUnavailable as err:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(err)) from err


@router.post("/test-jira")
def test_jira(db: Session = Depends(get_db), user: User = Depends(required_user)) -> dict:
    runtime = svc.get_runtime_config(db)
    if not runtime.jira_base_url:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Jira Base-URL fehlt")
    # User-Token hat Vorrang vor globalem Token
    user_token: str | None = None
    user_email: str | None = None
    if user:
        from app.models import AppSetting
        from app.services.settings_service import decrypt_secret
        token_row = db.get(AppSetting, f"user.{user.id}.jira_token")
        if token_row and token_row.value:
            user_token = decrypt_secret(token_row.value) or None
        email_row = db.get(AppSetting, f"user.{user.id}.jira_email")
        if email_row and email_row.value:
            user_email = email_row.value.strip() or None
    has_oauth = bool(
        runtime.jira_oauth_token_url and runtime.jira_client_id and runtime.jira_client_secret
    )
    if not runtime.jira_api_token and not runtime.jira_api_key and not user_token and not has_oauth:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Jira Token oder API-Key fehlt")
    url = (
        runtime.jira_search_url
        if runtime.jira_search_url
        else f"{runtime.jira_base_url}/rest/api/3/myself"
    )
    try:
        extra, auth = jira_auth(runtime, user_token=user_token, user_email=user_email)
        headers = {"accept": "*/*", **extra}
        kwargs = {"timeout": 20, "headers": headers, "trust_env": False}
        if auth:
            kwargs["auth"] = auth
        if runtime.jira_search_url:
            kwargs["params"] = {
                "jql": "order by updated DESC",
                "maxResults": 1,
                "fields": "key,summary,status",
            }
        response = httpx.get(url, **kwargs)
        if response.status_code >= 400:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                f"Jira {response.status_code}: {response.text[:200]}",
            )
        data = response.json()
        if runtime.jira_search_url:
            return {
                "ok": True,
                "displayName": "Search endpoint reachable",
                "sampleCount": len(data.get("issues") or []),
                "projectKey": runtime.jira_project_key,
            }
        return {
            "ok": True,
            "accountId": data.get("accountId"),
            "displayName": data.get("displayName"),
            "projectKey": runtime.jira_project_key,
        }
    except HTTPException:
        raise
    except TicketPortError as err:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(err)) from err
    except httpx.HTTPError as err:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(err)[:300]) from err
