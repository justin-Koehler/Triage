from __future__ import annotations

import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import AppSetting, User
from app.schemas import LoginIn
from app.security import (
    get_or_create_jira_user,
    optional_user,
    required_user,
    sign_session,
)
from app.services.settings_service import decrypt_secret, encrypt_secret, get_runtime_config

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_out(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "displayName": user.display_name,
        "jiraName": user.external_subject or "",
        "role": user.role,
    }


def _jira_login_port(db: Session):
    """Service-Account-Port für Login-Liste. Keine User-Credentials nötig."""
    from app.ports.jira_v3 import JiraRestV3
    from app.ports.ticket_port import TicketPortError

    runtime = get_runtime_config(db)
    if not runtime.jira_enabled:
        return None
    try:
        return JiraRestV3(runtime=runtime)
    except TicketPortError:
        return None


def _jira_accounts(db: Session, *, query: str = "", limit: int = 50) -> list[dict]:
    from app.ports.ticket_port import TicketPortError

    port = _jira_login_port(db)
    if not port:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Jira ist nicht aktiv")
    try:
        rows = port.search_assignable_users(query, limit=limit)
    except TicketPortError as err:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(err)) from err
    out: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        name = str(row.get("name") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append(
            {
                "id": name,
                "displayName": str(row.get("displayName") or name).strip() or name,
                "email": str(row.get("emailAddress") or "").strip(),
            }
        )
    out.sort(key=lambda item: item["displayName"].lower())
    return out


def _resolve_jira_account(db: Session, account_id: str) -> dict | None:
    needle = str(account_id or "").strip()
    if not needle:
        return None
    port = _jira_login_port(db)
    if not port:
        return None
    from app.ports.ticket_port import TicketPortError

    try:
        rows = port.search_assignable_users(needle, limit=30)
    except TicketPortError:
        return None
    low = needle.lower()
    exact = next((row for row in rows if str(row.get("name") or "").lower() == low), None)
    if not exact:
        return None
    name = str(exact.get("name") or "").strip()
    if not name:
        return None
    return {
        "id": name,
        "displayName": str(exact.get("displayName") or name).strip() or name,
        "email": str(exact.get("emailAddress") or "").strip(),
    }


@router.get("/accounts")
def accounts(
    q: str = Query(default="", max_length=80),
    db: Session = Depends(get_db),
) -> dict:
    needle = (q or "").strip()
    items = _jira_accounts(db, query=needle, limit=50)
    return {"accounts": items, "source": "jira"}


@router.get("/me")
def me(user: User | None = Depends(optional_user)) -> dict:
    if not user:
        return {"authenticated": False, "user": None}
    return {"authenticated": True, "user": _user_out(user)}


@router.post("/login")
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    if not settings.dev_login_enabled and settings.app_env != "dev":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Dev-Login deaktiviert")
    account = _resolve_jira_account(db, payload.account)
    if not account:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unbekannter Jira-Account")
    user = get_or_create_jira_user(
        db,
        jira_name=account["id"],
        display_name=account["displayName"],
        email=account.get("email") or None,
    )
    token = sign_session(user.id, settings)
    response.set_cookie(
        key=settings.session_cookie,
        value=token,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=60 * 60 * 12,
    )
    return {"authenticated": True, "user": _user_out(user)}


@router.post("/logout")
def logout(response: Response) -> dict:
    settings = get_settings()
    response.delete_cookie(settings.session_cookie, path="/")
    return {"authenticated": False}


@router.get("/require")
def require(user: User = Depends(required_user)) -> dict:
    return {"id": user.id, "email": user.email}


class JiraTokenIn(BaseModel):
    token: str = Field(max_length=500)


class ProfileIn(BaseModel):
    jiraEmail: str = Field(default="", max_length=255)


def _user_jira_token_key(user_id: str) -> str:
    return f"user.{user_id}.jira_token"


def _user_jira_email_key(user_id: str) -> str:
    return f"user.{user_id}.jira_email"


def _user_jira_oauth_state_key(user_id: str) -> str:
    return f"user.{user_id}.jira_oauth_state"


def _user_jira_refresh_token_key(user_id: str) -> str:
    return f"user.{user_id}.jira_refresh_token"


def _authorize_url(runtime, settings) -> str:
    direct = (settings.jira_oauth_authorize_url or "").strip()
    if direct:
        return direct
    token = (runtime.jira_oauth_token_url or "").strip()
    if token.endswith("/token"):
        return token[: -len("/token")] + "/authorize"
    return ""


def _redirect_url(request: Request, settings) -> str:
    manual = (settings.jira_oauth_redirect_url or "").strip()
    if manual:
        return manual
    base = str(request.base_url).rstrip("/")
    return f"{base}/api/auth/jira/oauth/callback"


@router.get("/me/profile")
def get_profile(
    user: User = Depends(required_user),
    db: Session = Depends(get_db),
) -> dict:
    email_row = db.get(AppSetting, _user_jira_email_key(user.id))
    return {
        "jiraEmail": (email_row.value if email_row else "") or "",
    }


@router.put("/me/profile")
def put_profile(
    payload: ProfileIn,
    user: User = Depends(required_user),
    db: Session = Depends(get_db),
) -> dict:
    key = _user_jira_email_key(user.id)
    email = payload.jiraEmail.strip()
    row = db.get(AppSetting, key)
    if row:
        row.value = email
        row.secret = False
    else:
        db.add(AppSetting(key=key, value=email, secret=False))
    db.flush()
    return {"jiraEmail": email}


@router.get("/me/jira-token")
def get_jira_token(
    user: User = Depends(required_user),
    db: Session = Depends(get_db),
) -> dict:
    key = _user_jira_token_key(user.id)
    row = db.get(AppSetting, key)
    configured = bool(row and row.value)
    return {"configured": configured}


@router.put("/me/jira-token")
def put_jira_token(
    payload: JiraTokenIn,
    user: User = Depends(required_user),
    db: Session = Depends(get_db),
) -> dict:
    key = _user_jira_token_key(user.id)
    token = payload.token.strip()
    if not token:
        # Löschen
        row = db.get(AppSetting, key)
        if row:
            db.delete(row)
        db.flush()
        return {"configured": False}
    stored = encrypt_secret(token)
    row = db.get(AppSetting, key)
    if row:
        row.value = stored
        row.secret = True
    else:
        db.add(AppSetting(key=key, value=stored, secret=True))
    db.flush()
    return {"configured": True}


@router.get("/jira/oauth/start")
def jira_oauth_start(
    request: Request,
    user: User = Depends(required_user),
    db: Session = Depends(get_db),
):
    """Startet OAuth Authorization-Code-Flow für Jira."""
    runtime = get_runtime_config(db)
    settings = get_settings()
    authorize_url = _authorize_url(runtime, settings)
    if not authorize_url:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "OAuth Authorize-URL fehlt. JIRA_OAUTH_AUTHORIZE_URL oder Token-URL konfigurieren.",
        )
    if not runtime.jira_client_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Jira OAuth Client-ID fehlt")

    state = secrets.token_urlsafe(24)
    state_row = db.get(AppSetting, _user_jira_oauth_state_key(user.id))
    stored_state = encrypt_secret(state)
    if state_row:
        state_row.value = stored_state
        state_row.secret = True
    else:
        db.add(
            AppSetting(
                key=_user_jira_oauth_state_key(user.id),
                value=stored_state,
                secret=True,
            )
        )
    db.flush()

    params = {
        "response_type": "code",
        "client_id": runtime.jira_client_id,
        "redirect_uri": _redirect_url(request, settings),
        "state": state,
    }
    if settings.jira_oauth_scope.strip():
        params["scope"] = settings.jira_oauth_scope.strip()
    if settings.jira_oauth_audience.strip():
        params["audience"] = settings.jira_oauth_audience.strip()
    url = f"{authorize_url}?{urlencode(params)}"
    return RedirectResponse(url=url, status_code=302)


@router.get("/jira/oauth/callback")
def jira_oauth_callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    user: User = Depends(required_user),
    db: Session = Depends(get_db),
):
    """OAuth Callback: tauscht Code gegen Token und speichert Bearer im User-Profil."""
    if error:
        text = error_description or error
        return RedirectResponse(url=f"/workspace?jira_oauth=error&reason={text}", status_code=302)
    if not code or not state:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Code oder State fehlt")

    state_row = db.get(AppSetting, _user_jira_oauth_state_key(user.id))
    expected = decrypt_secret(state_row.value) if (state_row and state_row.value) else ""
    if not expected or expected != state:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ungültiger OAuth-State")

    runtime = get_runtime_config(db)
    settings = get_settings()
    token_url = (runtime.jira_oauth_token_url or "").strip()
    if not token_url:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Jira OAuth Token-URL fehlt")
    if not runtime.jira_client_id or not runtime.jira_client_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Jira OAuth Client-Credentials fehlen")

    headers = {"Content-Type": "application/x-www-form-urlencoded", "accept": "*/*"}
    if runtime.jira_api_key:
        headers["x-apikey"] = runtime.jira_api_key
    data = {
        "grant_type": "authorization_code",
        "client_id": runtime.jira_client_id,
        "client_secret": runtime.jira_client_secret,
        "code": code,
        "redirect_uri": _redirect_url(request, settings),
    }
    if settings.jira_oauth_scope.strip():
        data["scope"] = settings.jira_oauth_scope.strip()
    if settings.jira_oauth_audience.strip():
        data["audience"] = settings.jira_oauth_audience.strip()
    try:
        response = httpx.post(token_url, data=data, headers=headers, timeout=20, follow_redirects=False)
    except httpx.HTTPError as err:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(err)[:300]) from err
    if response.status_code in {301, 302, 303, 307, 308}:
        loc = response.headers.get("location") or ""
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"OAuth Redirect statt Token-Antwort: {loc or response.status_code}",
        )
    if response.status_code >= 400:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"OAuth Token-Fehler {response.status_code}: {response.text[:240]}",
        )
    try:
        payload = response.json()
    except ValueError as err:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "OAuth Token-Antwort ist kein JSON") from err
    access_token = str(payload.get("access_token") or "").strip()
    refresh_token = str(payload.get("refresh_token") or "").strip()
    if not access_token:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "OAuth Antwort ohne access_token")

    token_row = db.get(AppSetting, _user_jira_token_key(user.id))
    stored_access = encrypt_secret(access_token)
    if token_row:
        token_row.value = stored_access
        token_row.secret = True
    else:
        db.add(AppSetting(key=_user_jira_token_key(user.id), value=stored_access, secret=True))

    # Für Bearer-Token muss kein Basic-User gesetzt sein.
    email_row = db.get(AppSetting, _user_jira_email_key(user.id))
    if email_row:
        email_row.value = ""
        email_row.secret = False

    if refresh_token:
        rr = db.get(AppSetting, _user_jira_refresh_token_key(user.id))
        stored_refresh = encrypt_secret(refresh_token)
        if rr:
            rr.value = stored_refresh
            rr.secret = True
        else:
            db.add(
                AppSetting(
                    key=_user_jira_refresh_token_key(user.id),
                    value=stored_refresh,
                    secret=True,
                )
            )
    if state_row:
        db.delete(state_row)

    db.flush()
    return RedirectResponse(url="/workspace?jira_oauth=connected", status_code=302)
