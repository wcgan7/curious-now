from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CN_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    redis_url: str | None = None

    admin_token: str | None = None
    public_app_base_url: str = "http://localhost:8000"

    # HTTP/security
    cookie_secure: bool = False
    log_magic_link_tokens: bool = False
    trust_proxy_headers: bool = False

    # Stage 6 defaults (used when user_prefs.notification_settings missing)
    default_timezone: str = "UTC"
    default_quiet_hours_start: str = "22:00"
    default_quiet_hours_end: str = "08:00"

    # Email configuration (Stage 6 - Notifications)
    # SendGrid (preferred)
    sendgrid_api_key: str | None = None

    # SMTP (alternative)
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True

    # Email sender defaults
    email_from_address: str = "hello@curious.now"
    email_from_name: str = "Curious Now"
    unpaywall_email: str | None = None

    # Structured logging
    log_format: str = "json"  # "json" or "text"
    log_level: str = "INFO"

    # LLM configuration (for AI features)
    llm_adapter: str = "ollama"  # "ollama", "claude-cli", "codex-cli", "mock"
    llm_model: str | None = None  # Model name (adapter-specific, uses default if None)

    # Paper text hydration debug (ops-only)
    paper_text_debug_dump_dir: str | None = None
    paper_text_debug_dump_pdf_rejected: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def clear_settings_cache() -> None:
    get_settings.cache_clear()
