"""Application settings, read from environment / `.env`.

Accepts both the standard names (GOOGLE_CLIENT_ID, SERP_API_KEY, ...) and the short names
already used in the local `.env` (Client_ID, Client_Secret, SerpApi).
"""

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_SECRET = "dev-insecure-secret-change-me-0123456789"  # noqa: S105 - dev-only, rejected in prod


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        env_ignore_empty=True,
    )

    app_env: Literal["dev", "test", "prod"] = "dev"
    app_base_url: str = "http://localhost:8000"
    web_base_url: str = "http://localhost:5173"
    auth_secret: SecretStr = SecretStr(_DEV_SECRET)
    app_encryption_key: SecretStr | None = None
    session_days: int = 14
    signup_rate_limit_per_min: int = 10  # per client IP
    login_rate_limit_per_min: int = 10  # per client IP + email

    database_url: str = "postgresql+asyncpg://seomaster:seomaster@localhost:5432/seomaster"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    clickhouse_url: str = "http://localhost:8123"
    clickhouse_user: str = "seomaster"
    clickhouse_password: SecretStr = SecretStr("seomaster")
    clickhouse_database: str = "seomaster"

    google_client_id: str = Field(
        default="", validation_alias=AliasChoices("GOOGLE_CLIENT_ID", "Client_ID")
    )
    google_client_secret: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("GOOGLE_CLIENT_SECRET", "Client_Secret"),
    )
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"

    dataforseo_login: str = ""
    dataforseo_password: SecretStr = SecretStr("")
    dataforseo_base_url: str = "https://api.dataforseo.com"
    keyword_provider_fake: bool = False  # force the free fake provider even with credentials
    serp_api_provider: str = "serpapi"
    serp_api_key: SecretStr = Field(
        default=SecretStr(""), validation_alias=AliasChoices("SERP_API_KEY", "SerpApi")
    )

    # Email (dev: Mailpit on localhost:1025; prod: Brevo/Resend SMTP with STARTTLS + login)
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_starttls: bool = False
    email_from: str = "Brandiz <no-reply@brandiz.local>"

    budget_daily_global_usd: float = 5.0
    budget_daily_org_usd: float = 1.0

    admin_emails: str = ""  # comma separated; gates /api/v1/admin (empty = all users, non-prod)

    sentry_dsn: str = ""
    otel_exporter_otlp_endpoint: str = ""

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"

    @property
    def dataforseo_enabled(self) -> bool:
        return not self.keyword_provider_fake and bool(
            self.dataforseo_login and self.dataforseo_password.get_secret_value()
        )

    @property
    def google_oauth_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret.get_secret_value())

    @model_validator(mode="after")
    def _prod_requires_real_secret(self) -> "Settings":
        secret = self.auth_secret.get_secret_value()
        if self.is_prod and (secret == _DEV_SECRET or len(secret) < 32):
            raise ValueError("AUTH_SECRET must be set in production (32+ characters)")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
