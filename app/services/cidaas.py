"""Cidaas OIDC (OAuth 2.1): Discovery, PKCE S256, Token, Userinfo."""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from functools import lru_cache
from urllib.parse import urlencode

import httpx

from app.config import Settings, get_settings

OIDC_COOKIE = "cidaas_oidc"
OIDC_MAX_AGE = 600
SCOPES = "openid profile email"


class CidaasError(RuntimeError):
    """Provider nicht erreichbar oder Antwort unbrauchbar."""


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


def safe_next(raw: str | None, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    fallback = settings.cidaas_post_login_path or "/"
    path = (raw or "").strip() or fallback
    if not path.startswith("/") or path.startswith("//") or "://" in path:
        return fallback
    return path


@lru_cache(maxsize=1)
def _discovery_cached(url: str, bucket: int) -> dict:
    try:
        response = httpx.get(url, timeout=15, follow_redirects=True)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as err:
        raise CidaasError(f"Discovery fehlgeschlagen: {err}") from err
    needed = ("authorization_endpoint", "token_endpoint", "userinfo_endpoint")
    if not all(data.get(key) for key in needed):
        raise CidaasError("Discovery unvollständig")
    return data


def discovery(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    url = (settings.cidaas_discovery_url or "").strip()
    if not url:
        raise CidaasError("CIDAAS_DISCOVERY_URL fehlt")
    return _discovery_cached(url, int(time.time()) // 300)


def redirect_uri(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return (settings.cidaas_redirect_url or "").strip() or (
        "https://scscm.stackit.gg/api/auth/cidaas/callback"
    )


def authorize_url(
    *, state: str, nonce: str, challenge: str, settings: Settings | None = None
) -> str:
    settings = settings or get_settings()
    meta = discovery(settings)
    params = urlencode(
        {
            "response_type": "code",
            "client_id": settings.cidaas_client_id,
            "redirect_uri": redirect_uri(settings),
            "scope": SCOPES,
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{meta['authorization_endpoint']}?{params}"


def exchange_code(code: str, verifier: str, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    meta = discovery(settings)
    try:
        response = httpx.post(
            meta["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "client_id": settings.cidaas_client_id,
                "client_secret": settings.cidaas_client_secret,
                "code": code,
                "redirect_uri": redirect_uri(settings),
                "code_verifier": verifier,
            },
            headers={"Accept": "application/json"},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as err:
        raise CidaasError(f"Token fehlgeschlagen: {err}") from err
    if not payload.get("access_token"):
        raise CidaasError("Token-Antwort ohne access_token")
    return payload


def userinfo(access_token: str, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    meta = discovery(settings)
    try:
        response = httpx.get(
            meta["userinfo_endpoint"],
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as err:
        raise CidaasError(f"Userinfo fehlgeschlagen: {err}") from err


def display_from_userinfo(info: dict) -> tuple[str, str]:
    sub = str(info.get("sub") or "").strip()
    email = str(info.get("email") or "").strip().lower()
    if not email:
        email = f"{sub or 'cidaas'}@cidaas.local"
    name = (
        str(info.get("name") or "").strip()
        or " ".join(
            part
            for part in (info.get("given_name"), info.get("family_name"))
            if part
        ).strip()
        or email.split("@")[0]
    )
    return email, name
