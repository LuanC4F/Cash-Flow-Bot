"""Session management, rate limiting, and Telegram auth endpoints (spec v2 §06, §16, §18)."""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

from starlette.requests import Request
from starlette.responses import JSONResponse

from .config import VaultConfig
from .initdata import InitDataError, ReplayProtector, verify_telegram_init_data

logger = logging.getLogger("vault.auth")

SESSION_COOKIE_NAME = "vault_session"
MAX_AUTH_BODY_BYTES = 8192


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("ascii")).hexdigest()


@dataclass
class SessionRecord:
    session_id: str
    token_hash: str
    owner_tg_id: int
    platform: str
    created_at: int
    last_seen_at: int
    expires_at: int
    revoked_at: int | None = None


class SessionStore(Protocol):
    def create(self, owner_tg_id: int, ttl_s: int, platform: str, now: int) -> tuple[str, SessionRecord]: ...
    def verify(self, raw_token: str, now: int) -> SessionRecord | None: ...
    def revoke_by_token(self, raw_token: str, now: int) -> bool: ...
    def revoke_by_id(self, owner_tg_id: int, session_id: str, now: int) -> bool: ...
    def revoke_all(self, owner_tg_id: int, now: int) -> int: ...
    def list_for_owner(self, owner_tg_id: int, now: int) -> list[SessionRecord]: ...


class InMemorySessionStore:
    """In-memory session store storing only SHA-256 token hashes. Postgres store plugs in at P3."""

    def __init__(self, max_sessions: int = 128) -> None:
        self._by_hash: dict[str, SessionRecord] = {}
        self._max_sessions = max_sessions

    def _prune(self, now: int) -> None:
        stale = [
            h
            for h, rec in self._by_hash.items()
            if rec.expires_at <= now or (rec.revoked_at is not None and now - rec.revoked_at > 3600)
        ]
        for h in stale:
            self._by_hash.pop(h, None)

    def create(
        self, owner_tg_id: int, ttl_s: int, platform: str, now: int
    ) -> tuple[str, SessionRecord]:
        self._prune(now)
        if len(self._by_hash) >= self._max_sessions:
            oldest_hash = min(self._by_hash, key=lambda h: self._by_hash[h].created_at)
            self._by_hash.pop(oldest_hash, None)
        raw_token = secrets.token_urlsafe(32)
        token_hash = _hash_token(raw_token)
        rec = SessionRecord(
            session_id=uuid.uuid4().hex,
            token_hash=token_hash,
            owner_tg_id=owner_tg_id,
            platform=(platform or "unknown")[:32],
            created_at=now,
            last_seen_at=now,
            expires_at=now + ttl_s,
        )
        self._by_hash[token_hash] = rec
        return raw_token, rec

    def verify(self, raw_token: str, now: int) -> SessionRecord | None:
        if not raw_token or len(raw_token) > 128:
            return None
        rec = self._by_hash.get(_hash_token(raw_token))
        if rec is None or rec.revoked_at is not None or rec.expires_at <= now:
            return None
        rec.last_seen_at = now
        return rec

    def revoke_by_token(self, raw_token: str, now: int) -> bool:
        if not raw_token:
            return False
        rec = self._by_hash.get(_hash_token(raw_token))
        if rec is None or rec.revoked_at is not None:
            return False
        rec.revoked_at = now
        return True

    def revoke_by_id(self, owner_tg_id: int, session_id: str, now: int) -> bool:
        for rec in self._by_hash.values():
            if rec.owner_tg_id == owner_tg_id and rec.session_id == session_id:
                if rec.revoked_at is None:
                    rec.revoked_at = now
                    return True
                return False
        return False

    def revoke_all(self, owner_tg_id: int, now: int) -> int:
        count = 0
        for rec in self._by_hash.values():
            if rec.owner_tg_id == owner_tg_id and rec.revoked_at is None and rec.expires_at > now:
                rec.revoked_at = now
                count += 1
        return count

    def list_for_owner(self, owner_tg_id: int, now: int) -> list[SessionRecord]:
        self._prune(now)
        return sorted(
            [
                rec
                for rec in self._by_hash.values()
                if rec.owner_tg_id == owner_tg_id and rec.revoked_at is None and rec.expires_at > now
            ],
            key=lambda r: r.last_seen_at,
            reverse=True,
        )


class SlidingWindowRateLimiter:
    """Per-key sliding window rate limiter."""

    def __init__(self, max_requests: int = 15, window_seconds: int = 60) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._hits: dict[str, list[int]] = {}

    def allow(self, key: str, now: int) -> bool:
        cutoff = now - self._window
        bucket = [t for t in self._hits.get(key, []) if t > cutoff]
        if len(bucket) >= self._max:
            self._hits[key] = bucket
            return False
        bucket.append(now)
        self._hits[key] = bucket
        return True


def check_same_origin(request: Request) -> bool:
    """Reject cross-origin mutating requests when Origin header is present (TA22)."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return True
    origin = request.headers.get("origin")
    if not origin:
        return True
    parsed = urlparse(origin)
    if not parsed.scheme or not parsed.netloc:
        return False
    req_host = request.headers.get("host") or request.url.netloc
    return parsed.netloc.lower() == req_host.lower()


def extract_bearer_or_cookie(request: Request) -> str | None:
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token:
            return token
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    return cookie_token.strip() if cookie_token else None

