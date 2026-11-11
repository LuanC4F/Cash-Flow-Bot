"""Telegram Mini App `initData` cryptographic verification (spec v2 §06, §16, §18 TA01–TA06).

Reference: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

MAX_INITDATA_BYTES = 4096
MAX_FUTURE_SKEW_SECONDS = 60


class InitDataError(ValueError):
    """Raised when `initData` is malformed, tampered with, expired, or replayed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class VerifiedTelegramUser:
    user_id: int
    auth_date: int
    initdata_hash: str


class ReplayProtector:
    """In-memory bounded TTL cache preventing a single signed `initData` from minting multiple sessions."""

    def __init__(self, max_entries: int = 2048) -> None:
        self._seen: dict[str, int] = {}
        self._max_entries = max_entries

    def check_and_mark(self, initdata_hash: str, expires_at: int, now: int) -> bool:
        expired = [k for k, exp in self._seen.items() if exp <= now]
        for k in expired:
            self._seen.pop(k, None)
        digest = hashlib.sha256(initdata_hash.encode("ascii")).hexdigest()
        if digest in self._seen:
            return False
        if len(self._seen) >= self._max_entries:
            oldest = min(self._seen, key=self._seen.get)  # type: ignore[arg-type]
            self._seen.pop(oldest, None)
        self._seen[digest] = expires_at
        return True


def verify_telegram_init_data(
    raw_init_data: str,
    *,
    bot_token: str,
    max_age_seconds: int,
    now: int | None = None,
    replay_protector: ReplayProtector | None = None,
) -> VerifiedTelegramUser:
    """Verify signed `Telegram.WebApp.initData` string and return the verified numeric user ID."""
    if not isinstance(raw_init_data, str) or not raw_init_data.strip():
        raise InitDataError("INVALID_INITDATA", "Thiếu dữ liệu xác thực Telegram.")
    if len(raw_init_data.encode("utf-8")) > MAX_INITDATA_BYTES:
        raise InitDataError("INVALID_INITDATA", "Dữ liệu xác thực vượt quá giới hạn.")

    try:
        pairs = parse_qsl(raw_init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise InitDataError("INVALID_INITDATA", "Định dạng initData không hợp lệ.") from exc

    fields: dict[str, str] = {}
    for key, value in pairs:
        if not key or key in fields:
            raise InitDataError("INVALID_INITDATA", "Trường initData bị trùng hoặc rỗng.")
        fields[key] = value

    received_hash = fields.pop("hash", None)
    if not received_hash or len(received_hash) != 64:
        raise InitDataError("INVALID_INITDATA", "Thiếu chữ ký xác thực.")
    try:
        bytes.fromhex(received_hash)
    except ValueError as exc:
        raise InitDataError("INVALID_INITDATA", "Chữ ký xác thực không hợp lệ.") from exc

    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields.keys()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash.lower()):
        raise InitDataError("INVALID_SIGNATURE", "Chữ ký Telegram không hợp lệ.")

    raw_auth_date = fields.get("auth_date", "")
    if not raw_auth_date.isdigit():
        raise InitDataError("INVALID_INITDATA", "Thiếu thời gian xác thực.")
    auth_date = int(raw_auth_date)

    current_time = int(time.time()) if now is None else int(now)
    if auth_date > current_time + MAX_FUTURE_SKEW_SECONDS:
        raise InitDataError("EXPIRED_INITDATA", "Thời gian xác thực không hợp lệ.")
    if current_time - auth_date > max_age_seconds:
        raise InitDataError(
            "EXPIRED_INITDATA", "Phiên mở ứng dụng đã hết hạn. Hãy đóng và mở lại từ Telegram."
        )

    raw_user = fields.get("user")
    if not raw_user:
        raise InitDataError("INVALID_INITDATA", "Thiếu thông tin người dùng Telegram.")
    try:
        user_obj = json.loads(raw_user)
    except json.JSONDecodeError as exc:
        raise InitDataError("INVALID_INITDATA", "Thông tin người dùng không hợp lệ.") from exc

    if not isinstance(user_obj, dict):
        raise InitDataError("INVALID_INITDATA", "Thông tin người dùng không hợp lệ.")
    user_id = user_obj.get("id")
    if type(user_id) is not int or user_id <= 0:
        raise InitDataError("INVALID_INITDATA", "ID người dùng Telegram không hợp lệ.")

    if replay_protector is not None:
        expires_at = auth_date + max_age_seconds + MAX_FUTURE_SKEW_SECONDS
        if not replay_protector.check_and_mark(received_hash.lower(), expires_at, current_time):
            raise InitDataError(
                "REPLAYED_INITDATA", "Dữ liệu mở ứng dụng đã được sử dụng. Hãy mở lại từ Telegram."
            )

    return VerifiedTelegramUser(
        user_id=user_id,
        auth_date=auth_date,
        initdata_hash=received_hash.lower(),
    )

