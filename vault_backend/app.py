"""Route assembly for Gmail Vault API v1 (spec v2 §06, §10, §16, §18)."""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import ValidationError
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

from .auth import (
    MAX_AUTH_BODY_BYTES,
    SESSION_COOKIE_NAME,
    InMemorySessionStore,
    SessionRecord,
    SessionStore,
    SlidingWindowRateLimiter,
    check_same_origin,
    extract_bearer_or_cookie,
)
from .config import VaultConfig, load_config
from .initdata import InitDataError, ReplayProtector, verify_telegram_init_data
from .schemas import (
    BatchCreateEntriesRequest,
    CreateEntryInput,
    CreateVaultRequest,
    DeleteEntryRequest,
    RotateVaultRequest,
    UpdateEnvelopesRequest,
    UpdateEntryRequest,
    canonical_uuid,
)
from .security import VaultSecurityHeaders
from .store import (
    EntryConflictError,
    FullResyncRequiredError,
    InMemoryVaultStore,
    StoreError,
    VaultStore,
)

logger = logging.getLogger("vault.api")

MAX_VAULT_BODY_BYTES = 1_048_576  # 1 MiB max for batch encrypted import


def error(code: str, message: str, status: int, extra: dict[str, Any] | None = None) -> JSONResponse:
    """Typed error body {code,message,requestId,...} (spec 06). Never echoes request bodies."""
    body: dict[str, Any] = {
        "code": code,
        "message": message,
        "requestId": uuid.uuid4().hex,
    }
    if extra:
        body.update(extra)
    return JSONResponse(body, status_code=status)


def _store_error_response(exc: StoreError) -> JSONResponse:
    if isinstance(exc, EntryConflictError):
        extra: dict[str, Any] = {"headRevision": exc.head_revision}
        if exc.current_entry is not None:
            extra["currentEntry"] = exc.current_entry.to_dict()
        return error(exc.code, exc.message, exc.status, extra)
    if isinstance(exc, FullResyncRequiredError):
        return error(exc.code, exc.message, exc.status, {"headRevision": exc.head_revision})
    return error(exc.code, exc.message, exc.status)


async def _parse_json_body(
    request: Request, max_bytes: int = MAX_VAULT_BODY_BYTES
) -> dict[str, Any] | JSONResponse:
    raw_body = await request.body()
    if len(raw_body) > max_bytes:
        return error("PAYLOAD_TOO_LARGE", "Payload vượt quá giới hạn cho phép.", 413)
    try:
        parsed = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return error("VALIDATION_ERROR", "JSON không hợp lệ.", 400)
    if not isinstance(parsed, dict):
        return error("VALIDATION_ERROR", "Body phải là JSON object.", 400)
    return parsed


@dataclass
class VaultRuntime:
    config: VaultConfig = field(default_factory=load_config)
    sessions: SessionStore = field(default_factory=InMemorySessionStore)
    store: VaultStore = field(default_factory=InMemoryVaultStore)
    replay: ReplayProtector = field(default_factory=ReplayProtector)
    auth_limiter: SlidingWindowRateLimiter = field(
        default_factory=lambda: SlidingWindowRateLimiter(max_requests=15, window_seconds=60)
    )
    now_fn: Callable[[], int] = field(default=lambda: int(time.time()))


def _require_session(request: Request, rt: VaultRuntime) -> SessionRecord | JSONResponse:
    if not check_same_origin(request):
        return error("FORBIDDEN", "Origin không hợp lệ.", 403)
    raw_token = extract_bearer_or_cookie(request)
    if not raw_token:
        return error("UNAUTHENTICATED", "Chưa đăng nhập phiên làm việc.", 401)
    now = rt.now_fn()
    rec = rt.sessions.verify(raw_token, now)
    if rec is None:
        return error("UNAUTHENTICATED", "Phiên làm việc đã hết hạn hoặc bị thu hồi.", 401)
    if rec.owner_tg_id != rt.config.allowed_user_id:
        return error("FORBIDDEN", "Không có quyền truy cập.", 403)
    return rec


def build_vault_routes(runtime: VaultRuntime | None = None) -> list[BaseRoute]:
    rt = runtime or VaultRuntime()

    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def auth_telegram(request: Request) -> JSONResponse:
        if not check_same_origin(request):
            return error("FORBIDDEN", "Origin không hợp lệ.", 403)

        now = rt.now_fn()
        client_ip = request.client.host if request.client else "unknown"
        if not rt.auth_limiter.allow(client_ip, now):
            return error("RATE_LIMITED", "Quá nhiều yêu cầu xác thực. Vui lòng thử lại sau.", 429)

        payload = await _parse_json_body(request, max_bytes=MAX_AUTH_BODY_BYTES)
        if isinstance(payload, JSONResponse):
            return payload

        raw_init_data = payload.get("initData")
        platform = str(payload.get("platform", "unknown"))[:32]
        if not isinstance(raw_init_data, str) or not raw_init_data.strip():
            return error("UNAUTHENTICATED", "Thiếu initData từ Telegram.", 401)

        if (
            rt.config.dev_mock_auth
            and not rt.config.is_production
            and raw_init_data == "dev-mock"
        ):
            verified_user_id = rt.config.allowed_user_id
        else:
            try:
                verified = verify_telegram_init_data(
                    raw_init_data,
                    bot_token=rt.config.bot_token,
                    max_age_seconds=rt.config.initdata_max_age_s,
                    now=now,
                    replay_protector=rt.replay,
                )
            except InitDataError as exc:
                logger.warning("auth_failed code=%s", exc.code)
                return error("UNAUTHENTICATED", exc.message, 401)
            verified_user_id = verified.user_id

        if verified_user_id != rt.config.allowed_user_id:
            logger.warning("auth_forbidden non_owner")
            return error("FORBIDDEN", "Tài khoản Telegram này không có quyền truy cập kho.", 403)

        raw_token, rec = rt.sessions.create(
            owner_tg_id=verified_user_id,
            ttl_s=rt.config.session_ttl_s,
            platform=platform,
            now=now,
        )
        vault_exists = await rt.store.vault_exists(verified_user_id)
        logger.info("auth_ok session_id=%s platform=%s", rec.session_id, rec.platform)

        resp = JSONResponse(
            {
                "authenticated": True,
                "vaultExists": vault_exists,
                "sessionToken": raw_token,
                "sessionId": rec.session_id,
                "expiresAt": rec.expires_at,
            }
        )
        resp.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=raw_token,
            max_age=rt.config.session_ttl_s,
            httponly=True,
            secure=rt.config.is_production,
            samesite="lax",
            path="/api/v1",
        )
        return resp

    async def auth_session(request: Request) -> JSONResponse:
        rec = _require_session(request, rt)
        if isinstance(rec, JSONResponse):
            return rec
        vault_exists = await rt.store.vault_exists(rec.owner_tg_id)
        return JSONResponse(
            {
                "authenticated": True,
                "telegramUserId": str(rec.owner_tg_id),
                "vaultExists": vault_exists,
                "sessionId": rec.session_id,
                "expiresAt": rec.expires_at,
            }
        )

    async def auth_logout(request: Request) -> JSONResponse:
        if not check_same_origin(request):
            return error("FORBIDDEN", "Origin không hợp lệ.", 403)
        raw_token = extract_bearer_or_cookie(request)
        if raw_token:
            rt.sessions.revoke_by_token(raw_token, rt.now_fn())
        resp = JSONResponse({"loggedOut": True})
        resp.delete_cookie(key=SESSION_COOKIE_NAME, path="/api/v1")
        return resp

    async def auth_revoke_all(request: Request) -> JSONResponse:
        rec = _require_session(request, rt)
        if isinstance(rec, JSONResponse):
            return rec
        revoked = rt.sessions.revoke_all(rec.owner_tg_id, rt.now_fn())
        logger.info("sessions_revoked_all count=%d", revoked)
        resp = JSONResponse(
            {
                "revokedCount": revoked,
                "notice": (
                    "Đã thu hồi toàn bộ phiên ứng dụng. Lưu ý: thao tác này không thu hồi phiên "
                    "đăng nhập Telegram và không thể xóa dữ liệu đã tải về trên thiết bị."
                ),
            }
        )
        resp.delete_cookie(key=SESSION_COOKIE_NAME, path="/api/v1")
        return resp

    async def list_devices(request: Request) -> JSONResponse:
        rec = _require_session(request, rt)
        if isinstance(rec, JSONResponse):
            return rec
        sessions = rt.sessions.list_for_owner(rec.owner_tg_id, rt.now_fn())
        return JSONResponse(
            {
                "devices": [
                    {
                        "id": s.session_id,
                        "platform": s.platform,
                        "createdAt": s.created_at,
                        "lastSeenAt": s.last_seen_at,
                        "expiresAt": s.expires_at,
                        "current": s.session_id == rec.session_id,
                    }
                    for s in sessions
                ]
            }
        )

    async def revoke_device(request: Request) -> JSONResponse:
        rec = _require_session(request, rt)
        if isinstance(rec, JSONResponse):
            return rec
        target_id = request.path_params.get("id", "")
        ok = rt.sessions.revoke_by_id(rec.owner_tg_id, target_id, rt.now_fn())
        if not ok:
            return error("VALIDATION_ERROR", "Không tìm thấy phiên ứng dụng.", 404)
        return JSONResponse(
            {
                "revoked": True,
                "id": target_id,
                "notice": "Không thể xóa từ xa dữ liệu đã giải mã/sao chép trước đó trên thiết bị.",
            }
        )

    async def handle_vault(request: Request) -> JSONResponse:
        rec = _require_session(request, rt)
        if isinstance(rec, JSONResponse):
            return rec

        if request.method == "GET":
            try:
                vault = await rt.store.get_vault(rec.owner_tg_id)
                return JSONResponse(vault.to_dict())
            except StoreError as exc:
                return _store_error_response(exc)

        payload = await _parse_json_body(request, max_bytes=65_536)
        if isinstance(payload, JSONResponse):
            return payload
        if payload.get("formatVersion") not in (None, 1):
            return error("UNSUPPORTED_VERSION", "Phiên bản định dạng kho không được hỗ trợ.", 400)
        try:
            req = CreateVaultRequest.model_validate(payload)
            created = await rt.store.create_vault(rec.owner_tg_id, req)
            logger.info("vault_created vault_id=%s", created.vaultId)
            return JSONResponse(created.to_dict(), status_code=201)
        except ValidationError:
            return error(
                "VALIDATION_ERROR",
                "Cấu trúc khởi tạo kho không hợp lệ (chỉ chấp nhận envelope mã hóa).",
                400,
            )
        except StoreError as exc:
            return _store_error_response(exc)

    async def patch_vault_envelopes(request: Request) -> JSONResponse:
        rec = _require_session(request, rt)
        if isinstance(rec, JSONResponse):
            return rec
        payload = await _parse_json_body(request, max_bytes=65_536)
        if isinstance(payload, JSONResponse):
            return payload
        try:
            req = UpdateEnvelopesRequest.model_validate(payload)
            updated = await rt.store.update_envelopes(rec.owner_tg_id, req)
            logger.info("vault_envelopes_updated rev=%d", updated.headRevision)
            return JSONResponse(updated.to_dict())
        except ValidationError:
            return error("VALIDATION_ERROR", "Cấu trúc cập nhật envelope không hợp lệ.", 400)
        except StoreError as exc:
            return _store_error_response(exc)

    async def put_vault_rotate(request: Request) -> JSONResponse:
        rec = _require_session(request, rt)
        if isinstance(rec, JSONResponse):
            return rec
        payload = await _parse_json_body(request, max_bytes=MAX_VAULT_BODY_BYTES)
        if isinstance(payload, JSONResponse):
            return payload
        try:
            req = RotateVaultRequest.model_validate(payload)
            rotated = await rt.store.rotate_vault(rec.owner_tg_id, req)
            logger.info("vault_dek_rotated rev=%d", rotated.headRevision)
            return JSONResponse(rotated.to_dict())
        except ValidationError:
            return error("VALIDATION_ERROR", "Dữ liệu xoay khóa DEK không hợp lệ.", 400)
        except StoreError as exc:
            return _store_error_response(exc)

    async def handle_entries(request: Request) -> JSONResponse:
        rec = _require_session(request, rt)
        if isinstance(rec, JSONResponse):
            return rec

        if request.method == "GET":
            raw_since = request.query_params.get("sinceRevision", "0")
            raw_limit = request.query_params.get("limit", "500")
            cursor = request.query_params.get("cursor")
            try:
                since_rev = int(raw_since)
                limit = int(raw_limit)
            except ValueError:
                return error("VALIDATION_ERROR", "Tham số truy vấn không hợp lệ.", 400)
            try:
                page = await rt.store.list_entries(
                    rec.owner_tg_id,
                    since_revision=since_rev,
                    cursor=cursor,
                    limit=limit,
                )
                return JSONResponse(page.to_dict())
            except StoreError as exc:
                return _store_error_response(exc)

        payload = await _parse_json_body(request, max_bytes=MAX_VAULT_BODY_BYTES)
        if isinstance(payload, JSONResponse):
            return payload

        try:
            if "entries" in payload:
                batch_req = BatchCreateEntriesRequest.model_validate(payload)
                inputs = batch_req.entries
            else:
                if payload.get("payloadVersion") not in (None, 1):
                    return error("UNSUPPORTED_VERSION", "Phiên bản bản ghi không được hỗ trợ.", 400)
                single_req = CreateEntryInput.model_validate(payload)
                inputs = [single_req]

            created, head_rev = await rt.store.create_entries(rec.owner_tg_id, inputs)
            logger.info("entries_created count=%d head_rev=%d", len(created), head_rev)
            if "entries" in payload:
                return JSONResponse(
                    {
                        "entries": [e.to_dict() for e in created],
                        "headRevision": head_rev,
                    },
                    status_code=201,
                )
            return JSONResponse(
                {
                    "entry": created[0].to_dict(),
                    "headRevision": head_rev,
                },
                status_code=201,
            )
        except ValidationError:
            return error(
                "VALIDATION_ERROR",
                "Bản ghi không hợp lệ (server chỉ chấp nhận dữ liệu đã mã hóa).",
                400,
            )
        except StoreError as exc:
            return _store_error_response(exc)

    async def handle_entry_by_id(request: Request) -> JSONResponse:
        rec = _require_session(request, rt)
        if isinstance(rec, JSONResponse):
            return rec

        raw_id = request.path_params.get("id", "")
        try:
            entry_id = canonical_uuid(raw_id, "id")
        except ValueError:
            return error("VALIDATION_ERROR", "ID bản ghi phải là UUID hợp lệ.", 400)

        if request.method == "PUT":
            payload = await _parse_json_body(request, max_bytes=65_536)
            if isinstance(payload, JSONResponse):
                return payload
            if payload.get("payloadVersion") not in (None, 1):
                return error("UNSUPPORTED_VERSION", "Phiên bản bản ghi không được hỗ trợ.", 400)
            try:
                req = UpdateEntryRequest.model_validate(payload)
                updated, head_rev = await rt.store.update_entry(rec.owner_tg_id, entry_id, req)
                return JSONResponse({"entry": updated.to_dict(), "headRevision": head_rev})
            except ValidationError:
                return error("VALIDATION_ERROR", "Dữ liệu cập nhật bản ghi không hợp lệ.", 400)
            except StoreError as exc:
                return _store_error_response(exc)

        # DELETE
        expected_rev: int | None = None
        q_rev = request.query_params.get("expectedEntryRevision")
        if q_rev is not None:
            if not q_rev.isdigit() or int(q_rev) < 1:
                return error("VALIDATION_ERROR", "expectedEntryRevision không hợp lệ.", 400)
            expected_rev = int(q_rev)
        else:
            payload = await _parse_json_body(request, max_bytes=4096)
            if isinstance(payload, JSONResponse):
                return payload
            try:
                del_req = DeleteEntryRequest.model_validate(payload)
                expected_rev = del_req.expectedEntryRevision
            except ValidationError:
                return error("VALIDATION_ERROR", "Thiếu expectedEntryRevision khi xóa.", 400)

        try:
            tombstone, head_rev = await rt.store.delete_entry(
                rec.owner_tg_id, entry_id, expected_rev
            )
            return JSONResponse({"entry": tombstone.to_dict(), "headRevision": head_rev})
        except StoreError as exc:
            return _store_error_response(exc)

    return [
        Route("/api/v1/health", health, methods=["GET"]),
        Route("/api/v1/auth/telegram", auth_telegram, methods=["POST"]),
        Route("/api/v1/auth/session", auth_session, methods=["GET"]),
        Route("/api/v1/auth/logout", auth_logout, methods=["POST"]),
        Route("/api/v1/auth/revoke-all", auth_revoke_all, methods=["POST"]),
        Route("/api/v1/devices", list_devices, methods=["GET"]),
        Route("/api/v1/devices/{id}/revoke", revoke_device, methods=["POST"]),
        Route("/api/v1/vault", handle_vault, methods=["GET", "POST"]),
        Route("/api/v1/vault/envelopes", patch_vault_envelopes, methods=["PATCH"]),
        Route("/api/v1/vault/rotate", put_vault_rotate, methods=["PUT"]),
        Route("/api/v1/entries", handle_entries, methods=["GET", "POST"]),
        Route("/api/v1/entries/{id}", handle_entry_by_id, methods=["PUT", "DELETE"]),
    ]


def vault_middleware() -> list[Middleware]:
    return [Middleware(VaultSecurityHeaders)]
