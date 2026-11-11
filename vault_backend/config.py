"""Typed, validated configuration. Production refuses unsafe settings at startup (spec v2 §19)."""

from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    pass


def _int(name: str, default: int, lo: int, hi: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if not lo <= value <= hi:
        raise ConfigError(f"{name} must be in [{lo}, {hi}]")
    return value


@dataclass(frozen=True)
class VaultConfig:
    bot_token: str
    allowed_user_id: int
    database_url: str
    session_secret: str
    initdata_max_age_s: int
    session_ttl_s: int
    dev_mock_auth: bool
    is_production: bool

    def __repr__(self) -> str:  # never print secrets
        return (
            f"VaultConfig(allowed_user_id=***, initdata_max_age_s={self.initdata_max_age_s}, "
            f"session_ttl_s={self.session_ttl_s}, dev_mock_auth={self.dev_mock_auth}, "
            f"is_production={self.is_production})"
        )

    __str__ = __repr__


def load_config() -> VaultConfig:
    # Render sets RENDER_EXTERNAL_URL; treat that as production.
    is_production = bool(os.getenv("RENDER_EXTERNAL_URL")) or os.getenv("NODE_ENV") == "production"

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    raw_uid = os.getenv("ALLOWED_USER_ID", "").strip().strip('"').strip("'")
    database_url = os.getenv("VAULT_DATABASE_URL", "").strip()
    session_secret = os.getenv("VAULT_SESSION_SECRET", "").strip()
    dev_mock_auth = os.getenv("VAULT_DEV_MOCK_AUTH", "false").strip().lower() == "true"

    if not bot_token:
        raise ConfigError("BOT_TOKEN is required")
    if not raw_uid.isdigit():
        raise ConfigError("ALLOWED_USER_ID must be a numeric Telegram user id")
    if is_production:
        if dev_mock_auth:
            raise ConfigError("VAULT_DEV_MOCK_AUTH must be false in production")
        if not database_url:
            raise ConfigError("VAULT_DATABASE_URL is required in production")
        if "sslmode=require" not in database_url and "sslmode=verify" not in database_url:
            raise ConfigError("VAULT_DATABASE_URL must enforce TLS (sslmode=require)")
        if len(session_secret) < 32:
            raise ConfigError("VAULT_SESSION_SECRET must be at least 32 characters")

    return VaultConfig(
        bot_token=bot_token,
        allowed_user_id=int(raw_uid),
        database_url=database_url,
        session_secret=session_secret,
        initdata_max_age_s=_int("TELEGRAM_INITDATA_MAX_AGE_SECONDS", 300, 30, 3600),
        session_ttl_s=_int("VAULT_SESSION_TTL_SECONDS", 1800, 300, 7200),
        dev_mock_auth=dev_mock_auth,
        is_production=is_production,
    )

