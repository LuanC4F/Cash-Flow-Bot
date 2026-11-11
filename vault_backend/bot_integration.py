"""Integration helpers for QuanLyThuChi_Bot (spec v2 §12, §16, §18 TA09, ADR-0001).

- Sets the "🔐 Gmail Vault" menu button ONLY for the owner's private chat (`chat_id=owner_user_id`).
- Connects & migrates `PostgresVaultStore` on startup when `VAULT_DATABASE_URL` is set.
- Never sends OTP codes, TOTP seeds, or account lists in Telegram chat messages.
"""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path
from typing import Any

from starlette.routing import BaseRoute, Mount
from starlette.staticfiles import StaticFiles

from .app import VaultRuntime, build_vault_routes
from .config import VaultConfig, _int
from .store import PostgresVaultStore

logger = logging.getLogger("vault.bot")

NON_SECRET_VAULT_HELP = (
    "🔐 *Gmail Vault*\n\n"
    "Kho mã 2FA chỉ hoạt động trực tiếp bên trong Mini App đã mã hóa.\n"
    "Bot tuyệt đối không nhận khóa 2FA, không nhận email tra cứu và không gửi mã OTP qua tin nhắn chat."
)


async def configure_owner_menu_button(bot: Any, owner_user_id: int, vault_url: str) -> bool:
    """Configure the Mini App menu button exclusively for `owner_user_id`."""
    if not vault_url.startswith("https://"):
        logger.warning("Skipping Vault menu button: URL is not HTTPS")
        return False
    try:
        from telegram import MenuButtonWebApp, WebAppInfo

        await bot.set_chat_menu_button(
            chat_id=owner_user_id,
            menu_button=MenuButtonWebApp(
                text="🔐 Gmail Vault",
                web_app=WebAppInfo(url=vault_url),
            ),
        )
        logger.info("Vault menu button configured for owner chat")
        return True
    except Exception as exc:  # pragma: no cover - depends on live Telegram API
        logger.warning("Could not set owner menu button: %s", type(exc).__name__)
        return False


def build_vault_Reply_for_user(
    *, user_id: int | None, owner_user_id: int, vault_url: str
) -> tuple[bool, str]:
    """Pure helper (testable without python-telegram-bot) for `/vault` or `/otp` commands.

    Returns `(allowed, message_text)`. Never returns OTPs, seeds, or account emails (TA09).
    """
    if user_id is None or user_id != owner_user_id:
        return False, "⛔ Bạn không có quyền sử dụng chức năng này."
    return True, NON_SECRET_VAULT_HELP


def create_bot_vault_runtime() -> VaultRuntime:
    """Create a `VaultRuntime` inside `QuanLyThuChi_Bot` without crashing the bot if
    `VAULT_DATABASE_URL` or `VAULT_SESSION_SECRET` has not been added to Render yet.
    """
    is_production = bool(os.getenv("RENDER_EXTERNAL_URL")) or os.getenv("NODE_ENV") == "production"
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    raw_uid = os.getenv("ALLOWED_USER_ID", "").strip().strip('"').strip("'")
    database_url = os.getenv("VAULT_DATABASE_URL", "").strip()
    session_secret = os.getenv("VAULT_SESSION_SECRET", "").strip() or secrets.token_urlsafe(32)

    if is_production and database_url:
        if "sslmode=require" not in database_url and "sslmode=verify" not in database_url:
            raise RuntimeError("VAULT_DATABASE_URL must enforce TLS (sslmode=require)")
    elif is_production and not database_url:
        logger.warning(
            "VAULT_DATABASE_URL is not set; Gmail Vault is running in ephemeral in-memory mode."
        )

    cfg = VaultConfig(
        bot_token=bot_token,
        allowed_user_id=int(raw_uid) if raw_uid.isdigit() else 0,
        database_url=database_url,
        session_secret=session_secret,
        initdata_max_age_s=_int("TELEGRAM_INITDATA_MAX_AGE_SECONDS", 300, 30, 3600),
        session_ttl_s=_int("VAULT_SESSION_TTL_SECONDS", 1800, 300, 7200),
        dev_mock_auth=False if is_production else (
            os.getenv("VAULT_DEV_MOCK_AUTH", "false").strip().lower() == "true"
        ),
        is_production=is_production,
    )
    return VaultRuntime(config=cfg)


def build_bot_vault_routes(
    runtime: VaultRuntime, static_dir: Path | str
) -> list[BaseRoute]:
    """Return all `/api/v1/*` routes plus the `/vault` static Mini App mount if `static_dir` exists."""
    routes: list[BaseRoute] = list(build_vault_routes(runtime))
    static_path = Path(static_dir)
    if static_path.is_dir():
        routes.append(
            Mount("/vault", app=StaticFiles(directory=static_path, html=True), name="vault")
        )
    return routes


async def startup_vault_on_bot(
    *, runtime: VaultRuntime, bot: Any, webhook_url: str
) -> PostgresVaultStore | None:
    """Connect & migrate Postgres (if configured) and register the owner-only Menu Button."""
    pg_store: PostgresVaultStore | None = None
    if runtime.config.database_url:
        pg_store = await PostgresVaultStore.connect_and_migrate(runtime.config.database_url)
        runtime.store = pg_store
        logger.info("Vault Postgres store connected and migrated")

    if webhook_url:
        vault_url = f"{webhook_url.rstrip('/')}/vault/"
        await configure_owner_menu_button(bot, runtime.config.allowed_user_id, vault_url)

    return pg_store
