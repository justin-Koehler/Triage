"""Signierte Session-Cookies ohne Zusatzabhaengigkeit.

Dev-Login ist ein Platzhalter. Phase 5 ersetzt ihn durch OIDC, das Interface
(`current_user`) bleibt dabei gleich.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from fastapi import Depends, HTTPException, status
from fastapi import Request as HttpRequest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import User

MAX_AGE_SECONDS = 60 * 60 * 12


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(raw: str) -> bytes:
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


def sign_session(user_id: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    body = _b64(json.dumps({"sub": user_id, "iat": int(time.time())}).encode())
    mac = hmac.new(settings.session_secret.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64(mac)}"


def read_session(token: str, settings: Settings | None = None) -> str | None:
    settings = settings or get_settings()
    try:
        body, signature = token.split(".", 1)
    except ValueError:
        return None
    expected = hmac.new(settings.session_secret.encode(), body.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(_unb64(signature), expected):
        return None
    try:
        payload = json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(time.time()) - int(payload.get("iat", 0)) > MAX_AGE_SECONDS:
        return None
    return payload.get("sub")


DUMMY_ACCOUNTS = (
    {"id": "dev", "email": "dev@localhost", "displayName": "Dev"},
    {"id": "alex", "email": "alex@localhost", "displayName": "Alex"},
    {"id": "sam", "email": "sam@localhost", "displayName": "Sam"},
)


def account_by_id(account_id: str) -> dict | None:
    needle = str(account_id or "").strip().lower()
    return next((row for row in DUMMY_ACCOUNTS if row["id"] == needle), None)


def ensure_dummy_accounts(db: Session) -> None:
    for row in DUMMY_ACCOUNTS:
        get_or_create_user(db, row["email"], row["displayName"])


def get_or_create_user(db: Session, email: str, display_name: str | None = None) -> User:
    email = email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user:
        return user
    user = User(email=email, display_name=display_name or email.split("@")[0])
    db.add(user)
    db.flush()
    return user


def get_or_create_jira_user(
    db: Session,
    *,
    jira_name: str,
    display_name: str,
    email: str | None = None,
) -> User:
    """Lokalen User aus Jira-Assignable anlegen oder aktualisieren."""
    name = (jira_name or "").strip()
    if not name:
        raise ValueError("jira_name fehlt")
    label = (display_name or name).strip() or name
    email_norm = (email or "").strip().lower() or f"{name.lower()}@jira.local"

    user = db.scalar(select(User).where(User.external_subject == name))
    if not user:
        user = db.scalar(select(User).where(User.email == email_norm))
    if user:
        user.display_name = label
        user.external_subject = name
        if user.email != email_norm:
            taken = db.scalar(select(User).where(User.email == email_norm, User.id != user.id))
            if not taken:
                user.email = email_norm
        db.flush()
        return user

    user = User(email=email_norm, display_name=label, external_subject=name)
    db.add(user)
    db.flush()
    return user


def default_actor(db: Session, settings: Settings | None = None) -> User:
    """Fester Stub-User, bis SSO den Cookie ersetzt."""
    settings = settings or get_settings()
    return get_or_create_user(db, settings.default_actor_email, settings.default_actor_name)


def optional_user(
    request: HttpRequest,
    db: Session = Depends(get_db),
) -> User | None:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie)
    if not token:
        return None
    user_id = read_session(token, settings)
    return db.get(User, user_id) if user_id else None


def current_actor(
    request: HttpRequest,
    db: Session = Depends(get_db),
) -> User:
    """Cookie-User wenn angemeldet, sonst Justin. Schreibende Pfade nutzen das."""
    return optional_user(request, db) or default_actor(db)


def required_user(user: User | None = Depends(optional_user)) -> User:
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Anmeldung erforderlich")
    return user
