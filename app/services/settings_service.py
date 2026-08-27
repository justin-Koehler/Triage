"""App-Einstellungen in der DB. Secrets nur verschluesselt, nie im Klartext raus."""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import AppSetting
from app.services.effort_sheet import DUMMY_TEMPLATE_URL, copy_url, dummy_open_url

SECRET_KEYS = frozenset(
    {"llm.api_key", "jira.api_token", "jira.api_key", "jira.client_secret"}
)
LLM_PROVIDERS = ("ollama", "openai", "anthropic", "gemini")


def _fernet(settings: Settings | None = None) -> Fernet:
    settings = settings or get_settings()
    raw = settings.settings_encryption_key or settings.session_secret
    digest = hashlib.sha256(raw.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str, settings: Settings | None = None) -> str:
    return _fernet(settings).encrypt(value.encode()).decode()


def decrypt_secret(value: str, settings: Settings | None = None) -> str:
    if not value:
        return ""
    try:
        return _fernet(settings).decrypt(value.encode()).decode()
    except InvalidToken:
        # Fail closed: Ciphertext nie als Klartext weiterreichen
        return ""


@dataclass
class RuntimeConfig:
    llm_provider: str
    llm_model: str
    llm_base_url: str
    llm_api_key: str
    llm_timeout: int
    jira_enabled: bool
    jira_base_url: str
    jira_search_url: str
    jira_email: str
    jira_api_token: str
    jira_api_key: str
    jira_oauth_token_url: str
    jira_client_id: str
    jira_client_secret: str
    jira_project_key: str
    jira_effort_sheet_field: str = ""
    effort_sheet_template_url: str = ""

    @property
    def ticket_port(self) -> str:
        if self.jira_enabled and self.jira_base_url and (
            self.jira_api_token or self.jira_api_key
        ):
            return "jira"
        return "fake"

    @property
    def llm_label(self) -> str:
        if self.llm_provider == "ollama":
            return f"ollama:{self.llm_model}"
        if self.llm_provider in ("openai", "anthropic", "gemini") and self.llm_api_key:
            return f"{self.llm_provider}:{self.llm_model or 'auto'}"
        return "heuristik"


def _defaults(settings: Settings) -> dict[str, str]:
    provider = settings.llm_provider
    model = settings.ollama_model if provider == "ollama" else settings.openai_model
    base_url = settings.ollama_base_url if provider == "ollama" else settings.openai_base_url
    api_key = settings.openai_api_key
    if provider == "anthropic":
        model = settings.anthropic_model
        base_url = settings.anthropic_base_url
        api_key = settings.anthropic_api_key
    elif provider == "gemini":
        model = settings.gemini_model
        base_url = settings.gemini_base_url
        api_key = settings.gemini_api_key

    return {
        "llm.provider": provider,
        "llm.model": model,
        "llm.base_url": base_url,
        "llm.api_key": api_key,
        "llm.timeout": str(settings.llm_timeout),
        "jira.enabled": "true" if settings.ticket_port == "jira" else "false",
        "jira.base_url": settings.jira_base_url,
        "jira.search_url": settings.jira_search_url,
        "jira.email": settings.jira_email,
        "jira.api_token": settings.jira_api_token,
        "jira.api_key": settings.jira_api_key,
        "jira.oauth_token_url": settings.jira_oauth_token_url,
        "jira.client_id": settings.jira_client_id,
        "jira.client_secret": settings.jira_client_secret,
        "jira.project_key": settings.jira_project_key or "TRI",
        "jira.effort_sheet_field": settings.jira_effort_sheet_field,
        "effort.sheet_template_url": settings.effort_sheet_template_url,
    }


# Leere DB-Werte sollen Env-Defaults nicht überschreiben (typisch nach UI-Reset).
_EMPTY_KEEPS_ENV = frozenset(
    {
        "jira.search_url",
        "jira.api_key",
        "jira.email",
        "jira.oauth_token_url",
        "jira.client_id",
        "jira.client_secret",
    }
)


def _load_raw(db: Session) -> dict[str, str]:
    settings = get_settings()
    values = _defaults(settings)
    for row in db.scalars(select(AppSetting)).all():
        val = decrypt_secret(row.value, settings) if row.secret else row.value
        if val == "" and row.key in _EMPTY_KEEPS_ENV:
            continue
        values[row.key] = val
    return values


def get_runtime_config(db: Session | None = None) -> RuntimeConfig:
    settings = get_settings()
    if db is None:
        from app.db import SessionLocal

        with SessionLocal() as session:
            return get_runtime_config(session)

    raw = _load_raw(db)
    provider = (raw.get("llm.provider") or "ollama").lower()
    model = (raw.get("llm.model") or "").strip()
    # Leeres Modell darf NICHT auf den Ollama-Default fallen — sonst 404 bei STACKIT.
    if not model and provider == "ollama":
        model = settings.ollama_model
    return RuntimeConfig(
        llm_provider=provider,
        llm_model=model,
        llm_base_url=raw.get("llm.base_url") or "",
        llm_api_key=raw.get("llm.api_key") or "",
        llm_timeout=int(raw.get("llm.timeout") or settings.llm_timeout),
        jira_enabled=str(raw.get("jira.enabled", "false")).lower() in ("1", "true", "yes"),
        jira_base_url=(raw.get("jira.base_url") or "").rstrip("/"),
        jira_search_url=raw.get("jira.search_url") or "",
        jira_email=raw.get("jira.email") or "",
        jira_api_token=raw.get("jira.api_token") or "",
        jira_api_key=raw.get("jira.api_key") or "",
        jira_oauth_token_url=raw.get("jira.oauth_token_url") or "",
        jira_client_id=raw.get("jira.client_id") or "",
        jira_client_secret=raw.get("jira.client_secret") or "",
        jira_project_key=raw.get("jira.project_key") or "TRI",
        jira_effort_sheet_field=(raw.get("jira.effort_sheet_field") or "").strip(),
        effort_sheet_template_url=(raw.get("effort.sheet_template_url") or "").strip(),
    )


def public_settings(db: Session) -> dict:
    raw = _load_raw(db)
    runtime = get_runtime_config(db)
    template = (raw.get("effort.sheet_template_url") or "").strip() or DUMMY_TEMPLATE_URL
    return {
        "llm": {
            "provider": raw.get("llm.provider"),
            "model": raw.get("llm.model"),
            "baseUrl": raw.get("llm.base_url"),
            "timeout": int(raw.get("llm.timeout") or 180),
            "apiKeyConfigured": bool(raw.get("llm.api_key")),
            "providers": list(LLM_PROVIDERS),
        },
        "jira": {
            "enabled": runtime.jira_enabled,
            "baseUrl": raw.get("jira.base_url"),
            "searchUrl": raw.get("jira.search_url"),
            "email": raw.get("jira.email"),
            "projectKey": raw.get("jira.project_key"),
            "apiTokenConfigured": bool(raw.get("jira.api_token")),
            "apiKeyConfigured": bool(raw.get("jira.api_key")),
            "oauthConfigured": bool(
                raw.get("jira.oauth_token_url")
                and raw.get("jira.client_id")
                and raw.get("jira.client_secret")
            ),
            "effortSheetField": raw.get("jira.effort_sheet_field") or "",
            "effortSheetTemplateUrl": template,
            "effortSheetCopyUrl": copy_url(template),
            "effortSheetOpenUrl": dummy_open_url(template),
        },
        "runtime": {
            "llmProvider": runtime.llm_provider,
            "llmModel": runtime.llm_model,
            "llmLabel": runtime.llm_label,
            "ticketPort": runtime.ticket_port,
            "jiraEnabled": runtime.jira_enabled,
        },
    }


def update_settings(db: Session, payload: dict) -> dict:
    settings = get_settings()
    mapping: dict[str, str] = {}

    llm = payload.get("llm") or {}
    if llm.get("provider") is not None:
        provider = str(llm["provider"]).lower()
        if provider not in LLM_PROVIDERS:
            raise ValueError(f"Unbekannter Provider: {provider}")
        mapping["llm.provider"] = provider
    if llm.get("model") is not None:
        mapping["llm.model"] = str(llm["model"]).strip()
    if "baseUrl" in llm and llm["baseUrl"] is not None:
        from app.triage.providers import normalize_openai_base_url

        base = str(llm["baseUrl"]).strip()
        # OpenAI-kompatible Gateways (STACKIT): Pfad auf /v1 normalisieren.
        provider = (mapping.get("llm.provider") or _load_raw(db).get("llm.provider") or "").lower()
        if provider == "openai" or base.rstrip("/").endswith("/v1"):
            base = normalize_openai_base_url(base)
        mapping["llm.base_url"] = base
    if llm.get("timeout") is not None:
        mapping["llm.timeout"] = str(int(llm["timeout"]))
    if "apiKey" in llm:
        key = llm["apiKey"]
        if key and not str(key).startswith("•"):
            mapping["llm.api_key"] = str(key).strip()

    jira = payload.get("jira") or {}
    if jira.get("enabled") is not None:
        mapping["jira.enabled"] = "true" if jira["enabled"] else "false"
    if "baseUrl" in jira and jira["baseUrl"] is not None:
        mapping["jira.base_url"] = str(jira["baseUrl"]).strip().rstrip("/")
    if "searchUrl" in jira and jira["searchUrl"] is not None:
        mapping["jira.search_url"] = str(jira["searchUrl"]).strip()
    if "email" in jira and jira["email"] is not None:
        mapping["jira.email"] = str(jira["email"]).strip()
    if jira.get("projectKey") is not None:
        mapping["jira.project_key"] = str(jira["projectKey"]).strip().upper()
    if "apiToken" in jira:
        token = jira["apiToken"]
        if token and not str(token).startswith("•"):
            mapping["jira.api_token"] = str(token).strip()
    if "apiKey" in jira:
        key = jira["apiKey"]
        if key and not str(key).startswith("•"):
            mapping["jira.api_key"] = str(key).strip()
    if "oauthTokenUrl" in jira and jira["oauthTokenUrl"] is not None:
        mapping["jira.oauth_token_url"] = str(jira["oauthTokenUrl"]).strip()
    if "clientId" in jira and jira["clientId"] is not None:
        mapping["jira.client_id"] = str(jira["clientId"]).strip()
    if "clientSecret" in jira:
        secret = jira["clientSecret"]
        if secret and not str(secret).startswith("•"):
            mapping["jira.client_secret"] = str(secret).strip()
    if "effortSheetField" in jira and jira["effortSheetField"] is not None:
        mapping["jira.effort_sheet_field"] = str(jira["effortSheetField"]).strip()
    if "effortSheetTemplateUrl" in jira and jira["effortSheetTemplateUrl"] is not None:
        mapping["effort.sheet_template_url"] = str(jira["effortSheetTemplateUrl"]).strip()

    for key, value in mapping.items():
        is_secret = key in SECRET_KEYS
        stored = encrypt_secret(value, settings) if is_secret else value
        row = db.get(AppSetting, key)
        if row:
            row.value = stored
            row.secret = is_secret
        else:
            db.add(AppSetting(key=key, value=stored, secret=is_secret))
    db.flush()

    # OpenAI-kompatibel: fehlendes/falsches Modell vom Endpunkt nachziehen.
    runtime = get_runtime_config(db)
    if runtime.llm_provider == "openai" and runtime.llm_base_url and runtime.llm_api_key:
        from app.triage.providers import LlmUnavailable, resolve_openai_model

        try:
            resolved = resolve_openai_model(
                runtime.llm_base_url,
                runtime.llm_api_key,
                runtime.llm_model,
                timeout=min(20, runtime.llm_timeout),
            )
        except LlmUnavailable:
            resolved = ""
        if resolved and resolved != runtime.llm_model:
            row = db.get(AppSetting, "llm.model")
            if row:
                row.value = resolved
            else:
                db.add(AppSetting(key="llm.model", value=resolved, secret=False))
            db.flush()

    invalidate_runtime_cache()
    return public_settings(db)


def invalidate_runtime_cache() -> None:
    from app.ports import get_ticket_port

    get_ticket_port.cache_clear()
