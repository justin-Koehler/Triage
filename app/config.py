"""Konfiguration ausschliesslich aus Env/Secrets (cloud-native Regel)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    app_env: str = "dev"
    database_url: str = f"sqlite:///{ROOT / 'data' / 'triage.db'}"

    llm_provider: str = "ollama"
    llm_timeout: int = 180
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:14b"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    ticket_port: str = "fake"
    jira_base_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    jira_api_key: str = ""
    jira_oauth_token_url: str = ""
    jira_oauth_authorize_url: str = ""
    jira_oauth_redirect_url: str = ""
    jira_oauth_scope: str = ""
    jira_oauth_audience: str = ""
    jira_client_id: str = ""
    jira_client_secret: str = ""
    jira_search_url: str = ""
    jira_project_key: str = ""
    jira_effort_sheet_field: str = ""
    effort_sheet_template_url: str = ""

    triage_rules_path: Path = ROOT / "config" / "triage_rules.yaml"
    field_map_path: Path = ROOT / "config" / "field_map.yaml"
    rates_path: Path = ROOT / "config" / "rates.yaml"
    # Zustaendigkeit und Dringlichkeit als Markdown, austauschbar ohne Deploy.
    responsibles_dir: Path = ROOT / "config" / "responsibles"
    priority_keywords_path: Path = ROOT / "config" / "priority_keywords.md"
    # Geloeste Faelle als Triage-Kontext. Echte Exporte ersetzen den Ordner.
    knowledge_dir: Path = ROOT / "knowledge" / "tickets"
    # Diagnostische Fragen pro Thema (prozess, software, …).
    topics_dir: Path = ROOT / "config" / "topics"
    # Kulturelle Risiken: Stichwort → Warnung und Steckbrief-Feld.
    risks_dir: Path = ROOT / "config" / "risks"
    web_search_enabled: bool = True

    session_secret: str = "dev-only-change-me"
    session_cookie: str = "triage_session"
    dev_login_enabled: bool = True
    # Bis SSO da ist: alle Anliegen und Kommentare laufen unter diesem Stub.
    default_actor_email: str = "dev@localhost"
    default_actor_name: str = "Dev"
    settings_encryption_key: str = ""

    outbox_max_attempts: int = 6
    outbox_poll_seconds: int = 15

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"
    anthropic_base_url: str = "https://api.anthropic.com"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"

    web_dist: Path = ROOT / "web" / "dist"
    legacy_static: Path = ROOT / "static"

    @property
    def llm_label(self) -> str:
        if self.llm_provider == "ollama":
            return f"ollama:{self.ollama_model}"
        if self.llm_provider == "openai" and self.openai_api_key:
            return f"openai:{self.openai_model}"
        return "heuristik"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.is_sqlite:
        target = settings.database_url.split("///", 1)[-1]
        Path(target).parent.mkdir(parents=True, exist_ok=True)
    return settings
