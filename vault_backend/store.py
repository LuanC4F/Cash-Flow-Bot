"""Encrypted Vault & Entry storage (InMemory + Postgres asyncpg) (spec v2 §05, §06, §10).

SECURITY INVARIANTS:
- Every operation is scoped by `owner_tg_id` (verified numeric Telegram ID from auth middleware).
- Only opaque UUIDs, versioned envelopes, nonces, ciphertexts, revisions, and timestamps are stored.
- Tombstones clear `nonce` and `ciphertext` bytes and cannot be resurrected by stale revisions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .schemas import (
    MAX_VAULT_ENTRIES,
    CreateEntryInput,
    CreateVaultRequest,
    RotateVaultRequest,
    UpdateEnvelopesRequest,
    UpdateEntryRequest,
    decode_b64url,
    encode_b64url,
)

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


class StoreError(Exception):
    def __init__(self, code: str, message: str, status: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class VaultAlreadyExistsError(StoreError):
    def __init__(self) -> None:
        super().__init__("VAULT_ALREADY_EXISTS", "Kho mã hóa đã tồn tại cho chủ sở hữu này.", 409)


class VaultNotFoundError(StoreError):
    def __init__(self) -> None:
        super().__init__("VAULT_NOT_FOUND", "Kho chưa được khởi tạo.", 404)


class UnsupportedVersionError(StoreError):
    def __init__(self, message: str = "Phiên bản định dạng không được hỗ trợ.") -> None:
        super().__init__("UNSUPPORTED_VERSION", message, 400)


class FullResyncRequiredError(StoreError):
    def __init__(self, head_revision: int) -> None:
        super().__init__(
            "FULL_RESYNC_REQUIRED",
            "Lịch sử đồng bộ đã cũ hoặc không khớp. Cần tải lại toàn bộ bản mã.",
            410,
        )
        self.head_revision = head_revision


class EntryConflictError(StoreError):
    def __init__(
        self,
        message: str,
        *,
        head_revision: int,
        current_entry: EncryptedEntryWire | None = None,
    ) -> None:
        super().__init__("ENTRY_CONFLICT", message, 409)
        self.head_revision = head_revision
        self.current_entry = current_entry


@dataclass(frozen=True)
class VaultWire:
    vaultId: str
    formatVersion: int
    envelope: dict[str, Any]
    recoveryEnvelope: dict[str, Any]
    headRevision: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "vaultId": self.vaultId,
            "formatVersion": self.formatVersion,
            "envelope": self.envelope,
            "recoveryEnvelope": self.recoveryEnvelope,
            "headRevision": self.headRevision,
        }


@dataclass(frozen=True)
class EncryptedEntryWire:
    id: str
    payloadVersion: int
    nonceB64: str
    ciphertextB64: str
    revision: int
    deletedAt: str | None
    updatedAt: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "payloadVersion": self.payloadVersion,
            "nonceB64": self.nonceB64,
            "ciphertextB64": self.ciphertextB64,
            "revision": self.revision,
            "deletedAt": self.deletedAt,
            "updatedAt": self.updatedAt,
        }


@dataclass(frozen=True)
class PaginatedEntriesWire:
    entries: list[EncryptedEntryWire]
    headRevision: int
    nextCursor: str | None
    hasMore: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "entries": [e.to_dict() for e in self.entries],
            "headRevision": self.headRevision,
            "nextCursor": self.nextCursor,
            "hasMore": self.hasMore,
        }


class VaultStore(Protocol):
    async def vault_exists(self, owner_tg_id: int) -> bool: ...
    async def get_vault(self, owner_tg_id: int) -> VaultWire: ...
    async def create_vault(self, owner_tg_id: int, req: CreateVaultRequest) -> VaultWire: ...
    async def update_envelopes(
        self, owner_tg_id: int, req: UpdateEnvelopesRequest
    ) -> VaultWire: ...
    async def list_entries(
        self,
        owner_tg_id: int,
        *,
        since_revision: int = 0,
        cursor: str | None = None,
        limit: int = 500,
    ) -> PaginatedEntriesWire: ...
    async def create_entries(
        self, owner_tg_id: int, inputs: list[CreateEntryInput]
    ) -> tuple[list[EncryptedEntryWire], int]: ...
    async def update_entry(
        self, owner_tg_id: int, entry_id: str, req: UpdateEntryRequest
    ) -> tuple[EncryptedEntryWire, int]: ...
    async def delete_entry(
        self, owner_tg_id: int, entry_id: str, expected_entry_revision: int
    ) -> tuple[EncryptedEntryWire, int]: ...
    async def rotate_vault(
        self, owner_tg_id: int, req: RotateVaultRequest
    ) -> VaultWire: ...



def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _MemVault:
    vault_id: str
    owner_tg_id: int
    format_version: int
    envelope: dict[str, Any]
    recovery_envelope: dict[str, Any]
    head_revision: int = 0
    min_retained_revision: int = 0
    entries: dict[str, EncryptedEntryWire] = field(default_factory=dict)


class InMemoryVaultStore:
    """In-memory implementation enforcing the exact concurrency, tombstone, and ownership rules."""

    def __init__(self) -> None:
        self._by_owner: dict[int, _MemVault] = {}
        self._vault_ids: set[str] = set()

    def dump_raw_state_for_tests(self) -> str:
        """Used by security test T06/TA15 to verify no plaintext exists anywhere in storage."""
        out = []
        for v in self._by_owner.values():
            out.append(
                {
                    "vaultId": v.vault_id,
                    "ownerTgId": v.owner_tg_id,
                    "envelope": v.envelope,
                    "recoveryEnvelope": v.recovery_envelope,
                    "entries": [e.to_dict() for e in v.entries.values()],
                }
            )
        return json.dumps(out)

    def set_min_retained_revision_for_tests(self, owner_tg_id: int, min_rev: int) -> None:
        if owner_tg_id in self._by_owner:
            self._by_owner[owner_tg_id].min_retained_revision = min_rev

    async def vault_exists(self, owner_tg_id: int) -> bool:
        return owner_tg_id in self._by_owner

    async def get_vault(self, owner_tg_id: int) -> VaultWire:
        v = self._by_owner.get(owner_tg_id)
        if v is None:
            raise VaultNotFoundError()
        return VaultWire(
            vaultId=v.vault_id,
            formatVersion=v.format_version,
            envelope=v.envelope,
            recoveryEnvelope=v.recovery_envelope,
            headRevision=v.head_revision,
        )

    async def create_vault(self, owner_tg_id: int, req: CreateVaultRequest) -> VaultWire:
        if req.formatVersion != 1:
            raise UnsupportedVersionError()
        if owner_tg_id in self._by_owner or req.vaultId in self._vault_ids:
            raise VaultAlreadyExistsError()
        v = _MemVault(
            vault_id=req.vaultId,
            owner_tg_id=owner_tg_id,
            format_version=req.formatVersion,
            envelope=req.envelope.model_dump(),
            recovery_envelope=req.recoveryEnvelope.model_dump(),
            head_revision=1,
            min_retained_revision=0,
        )
        self._by_owner[owner_tg_id] = v
        self._vault_ids.add(req.vaultId)
        return await self.get_vault(owner_tg_id)

    async def update_envelopes(
        self, owner_tg_id: int, req: UpdateEnvelopesRequest
    ) -> VaultWire:
        v = self._by_owner.get(owner_tg_id)
        if v is None:
            raise VaultNotFoundError()
        if req.expectedHeadRevision != v.head_revision:
            raise EntryConflictError(
                "Phiên bản kho đã thay đổi trên thiết bị khác.",
                head_revision=v.head_revision,
            )
        v.head_revision += 1
        v.envelope = req.envelope.model_dump()
        if req.recoveryEnvelope is not None:
            v.recovery_envelope = req.recoveryEnvelope.model_dump()
        return await self.get_vault(owner_tg_id)

    async def list_entries(
        self,
        owner_tg_id: int,
        *,
        since_revision: int = 0,
        cursor: str | None = None,
        limit: int = 500,
    ) -> PaginatedEntriesWire:
        v = self._by_owner.get(owner_tg_id)
        if v is None:
            raise VaultNotFoundError()
        if since_revision < 0 or since_revision > v.head_revision:
            raise FullResyncRequiredError(v.head_revision)
        if since_revision > 0 and since_revision < v.min_retained_revision:
            raise FullResyncRequiredError(v.head_revision)

        after_rev = since_revision
        if cursor is not None:
            if not cursor.isdigit():
                raise StoreError("VALIDATION_ERROR", "Cursor phân trang không hợp lệ.", 400)
            after_rev = max(after_rev, int(cursor))

        capped_limit = max(1, min(limit, 500))
        matching = sorted(
            (e for e in v.entries.values() if e.revision > after_rev),
            key=lambda e: e.revision,
        )
        page = matching[:capped_limit]
        has_more = len(matching) > capped_limit
        next_cursor = str(page[-1].revision) if has_more and page else None

        return PaginatedEntriesWire(
            entries=page,
            headRevision=v.head_revision,
            nextCursor=next_cursor,
            hasMore=has_more,
        )

    async def create_entries(
        self, owner_tg_id: int, inputs: list[CreateEntryInput]
    ) -> tuple[list[EncryptedEntryWire], int]:
        v = self._by_owner.get(owner_tg_id)
        if v is None:
            raise VaultNotFoundError()

        for item in inputs:
            if item.payloadVersion != 1:
                raise UnsupportedVersionError()

        seen_ids: set[str] = set()
        for item in inputs:
            if item.id in seen_ids:
                raise StoreError("VALIDATION_ERROR", "Danh sách có ID bản ghi trùng lặp.", 400)
            seen_ids.add(item.id)
            if item.id in v.entries:
                raise EntryConflictError(
                    "Bản ghi với ID này đã tồn tại.",
                    head_revision=v.head_revision,
                    current_entry=v.entries[item.id],
                )

        active_count = sum(1 for e in v.entries.values() if e.deletedAt is None)
        if active_count + len(inputs) > MAX_VAULT_ENTRIES:
            raise StoreError(
                "VALIDATION_ERROR",
                f"Vượt quá giới hạn tối đa {MAX_VAULT_ENTRIES} tài khoản trong kho.",
                400,
            )

        now = _now_iso()
        created: list[EncryptedEntryWire] = []
        for item in inputs:
            v.head_revision += 1
            wire = EncryptedEntryWire(
                id=item.id,
                payloadVersion=item.payloadVersion,
                nonceB64=item.nonceB64,
                ciphertextB64=item.ciphertextB64,
                revision=v.head_revision,
                deletedAt=None,
                updatedAt=now,
            )
            v.entries[item.id] = wire
            created.append(wire)
        return created, v.head_revision

    async def update_entry(
        self, owner_tg_id: int, entry_id: str, req: UpdateEntryRequest
    ) -> tuple[EncryptedEntryWire, int]:
        v = self._by_owner.get(owner_tg_id)
        if v is None:
            raise VaultNotFoundError()
        if req.payloadVersion != 1:
            raise UnsupportedVersionError()

        current = v.entries.get(entry_id)
        if current is None:
            raise StoreError("VALIDATION_ERROR", "Không tìm thấy bản ghi.", 404)
        if current.deletedAt is not None:
            # Never resurrect tombstones via stale edits (spec 05 §77, spec 10 §24)
            raise EntryConflictError(
                "Bản ghi này đã bị xóa trên thiết bị khác.",
                head_revision=v.head_revision,
                current_entry=current,
            )
        if current.revision != req.expectedEntryRevision:
            raise EntryConflictError(
                "Bản ghi đã được cập nhật bởi thiết bị khác.",
                head_revision=v.head_revision,
                current_entry=current,
            )

        v.head_revision += 1
        updated = EncryptedEntryWire(
            id=entry_id,
            payloadVersion=req.payloadVersion,
            nonceB64=req.nonceB64,
            ciphertextB64=req.ciphertextB64,
            revision=v.head_revision,
            deletedAt=None,
            updatedAt=_now_iso(),
        )
        v.entries[entry_id] = updated
        return updated, v.head_revision

    async def delete_entry(
        self, owner_tg_id: int, entry_id: str, expected_entry_revision: int
    ) -> tuple[EncryptedEntryWire, int]:
        v = self._by_owner.get(owner_tg_id)
        if v is None:
            raise VaultNotFoundError()
        current = v.entries.get(entry_id)
        if current is None:
            raise StoreError("VALIDATION_ERROR", "Không tìm thấy bản ghi.", 404)
        if current.deletedAt is not None:
            return current, v.head_revision
        if current.revision != expected_entry_revision:
            raise EntryConflictError(
                "Bản ghi đã thay đổi trước khi xóa.",
                head_revision=v.head_revision,
                current_entry=current,
            )

        v.head_revision += 1
        now = _now_iso()
        tombstone = EncryptedEntryWire(
            id=entry_id,
            payloadVersion=current.payloadVersion,
            nonceB64="",
            ciphertextB64="",
            revision=v.head_revision,
            deletedAt=now,
            updatedAt=now,
        )
        v.entries[entry_id] = tombstone
        return tombstone, v.head_revision

    async def rotate_vault(
        self, owner_tg_id: int, req: RotateVaultRequest
    ) -> VaultWire:
        v = self._by_owner.get(owner_tg_id)
        if v is None:
            raise VaultNotFoundError()
        if req.expectedHeadRevision != v.head_revision:
            raise EntryConflictError(
                "Phiên bản kho đã thay đổi trước khi xoay khóa DEK.",
                head_revision=v.head_revision,
            )
        active_ids = {eid for eid, e in v.entries.items() if e.deletedAt is None}
        submitted_ids = {item.id for item in req.entries}
        if submitted_ids != active_ids or len(submitted_ids) != len(req.entries):
            raise StoreError(
                "VALIDATION_ERROR",
                "Danh sách bản ghi mã hóa lại không khớp với các bản ghi đang hoạt động.",
                400,
            )
        now = _now_iso()
        for item in req.entries:
            if item.payloadVersion != 1:
                raise UnsupportedVersionError()
            v.head_revision += 1
            v.entries[item.id] = EncryptedEntryWire(
                id=item.id,
                payloadVersion=item.payloadVersion,
                nonceB64=item.nonceB64,
                ciphertextB64=item.ciphertextB64,
                revision=v.head_revision,
                deletedAt=None,
                updatedAt=now,
            )
        v.head_revision += 1
        v.envelope = req.envelope.model_dump()
        v.recovery_envelope = req.recoveryEnvelope.model_dump()
        return await self.get_vault(owner_tg_id)



class PostgresVaultStore:
    """Asyncpg-backed PostgreSQL store for production on Neon/Supabase (spec v2 §05)."""

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    @staticmethod
    def _sanitize_asyncpg_dsn(database_url: str) -> str:
        """Strip libpq-only query params like `channel_binding` so asyncpg does not pass them as GUC server_settings."""
        from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

        parsed = urlparse(database_url)
        if not parsed.query:
            return database_url
        filtered = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != "channel_binding"]
        return urlunparse(parsed._replace(query=urlencode(filtered)))

    @classmethod
    async def connect_and_migrate(cls, database_url: str) -> PostgresVaultStore:
        import asyncpg

        clean_dsn = cls._sanitize_asyncpg_dsn(database_url)
        pool = await asyncpg.create_pool(
            dsn=clean_dsn, min_size=1, max_size=5, statement_cache_size=0
        )
        sql_001 = (MIGRATIONS_DIR / "001_init.sql").read_text(encoding="utf-8")
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(sql_001)
                await conn.execute(
                    "INSERT INTO vault_schema_migrations (version) VALUES (1) ON CONFLICT DO NOTHING"
                )
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def vault_exists(self, owner_tg_id: int) -> bool:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM vault_vaults WHERE owner_tg_id = $1", owner_tg_id
            )
            return row is not None

    async def get_vault(self, owner_tg_id: int) -> VaultWire:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, format_version, envelope, recovery_envelope, head_revision
                FROM vault_vaults WHERE owner_tg_id = $1
                """,
                owner_tg_id,
            )
            if row is None:
                raise VaultNotFoundError()
            return VaultWire(
                vaultId=str(row["id"]),
                formatVersion=int(row["format_version"]),
                envelope=json.loads(row["envelope"])
                if isinstance(row["envelope"], str)
                else dict(row["envelope"]),
                recoveryEnvelope=json.loads(row["recovery_envelope"])
                if isinstance(row["recovery_envelope"], str)
                else dict(row["recovery_envelope"]),
                headRevision=int(row["head_revision"]),
            )

    async def create_vault(self, owner_tg_id: int, req: CreateVaultRequest) -> VaultWire:
        if req.formatVersion != 1:
            raise UnsupportedVersionError()
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                existing = await conn.fetchrow(
                    "SELECT 1 FROM vault_vaults WHERE owner_tg_id = $1 OR id = $2::uuid",
                    owner_tg_id,
                    req.vaultId,
                )
                if existing is not None:
                    raise VaultAlreadyExistsError()
                await conn.execute(
                    """
                    INSERT INTO vault_vaults
                        (id, owner_tg_id, format_version, envelope, recovery_envelope, head_revision)
                    VALUES ($1::uuid, $2, $3, $4::jsonb, $5::jsonb, 1)
                    """,
                    req.vaultId,
                    owner_tg_id,
                    req.formatVersion,
                    json.dumps(req.envelope.model_dump()),
                    json.dumps(req.recoveryEnvelope.model_dump()),
                )
                await conn.execute(
                    """
                    INSERT INTO vault_sync_log (vault_id, head_revision, entry_id, action)
                    VALUES ($1::uuid, 1, NULL, 'envelope_update')
                    """,
                    req.vaultId,
                )
        return await self.get_vault(owner_tg_id)

    async def update_envelopes(
        self, owner_tg_id: int, req: UpdateEnvelopesRequest
    ) -> VaultWire:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                v = await conn.fetchrow(
                    "SELECT id, head_revision, recovery_envelope FROM vault_vaults WHERE owner_tg_id = $1 FOR UPDATE",
                    owner_tg_id,
                )
                if v is None:
                    raise VaultNotFoundError()
                head = int(v["head_revision"])
                if req.expectedHeadRevision != head:
                    raise EntryConflictError(
                        "Phiên bản kho đã thay đổi trên thiết bị khác.", head_revision=head
                    )
                new_head = head + 1
                rec_env = (
                    json.dumps(req.recoveryEnvelope.model_dump())
                    if req.recoveryEnvelope is not None
                    else (
                        v["recovery_envelope"]
                        if isinstance(v["recovery_envelope"], str)
                        else json.dumps(dict(v["recovery_envelope"]))
                    )
                )
                await conn.execute(
                    """
                    UPDATE vault_vaults
                    SET envelope = $1::jsonb, recovery_envelope = $2::jsonb,
                        head_revision = $3, updated_at = NOW()
                    WHERE id = $4
                    """,
                    json.dumps(req.envelope.model_dump()),
                    rec_env,
                    new_head,
                    v["id"],
                )
                await conn.execute(
                    """
                    INSERT INTO vault_sync_log (vault_id, head_revision, entry_id, action)
                    VALUES ($1, $2, NULL, 'envelope_update')
                    """,
                    v["id"],
                    new_head,
                )
        return await self.get_vault(owner_tg_id)

    @staticmethod
    def _row_to_entry(row: Any) -> EncryptedEntryWire:
        deleted_at = row["deleted_at"].isoformat() if row["deleted_at"] is not None else None
        return EncryptedEntryWire(
            id=str(row["id"]),
            payloadVersion=int(row["payload_version"]),
            nonceB64="" if deleted_at else encode_b64url(bytes(row["nonce"])),
            ciphertextB64="" if deleted_at else encode_b64url(bytes(row["ciphertext"])),
            revision=int(row["revision"]),
            deletedAt=deleted_at,
            updatedAt=row["updated_at"].isoformat(),
        )

    async def list_entries(
        self,
        owner_tg_id: int,
        *,
        since_revision: int = 0,
        cursor: str | None = None,
        limit: int = 500,
    ) -> PaginatedEntriesWire:
        async with self._pool.acquire() as conn:
            v = await conn.fetchrow(
                "SELECT id, head_revision, min_retained_revision FROM vault_vaults WHERE owner_tg_id = $1",
                owner_tg_id,
            )
            if v is None:
                raise VaultNotFoundError()
            head = int(v["head_revision"])
            min_ret = int(v["min_retained_revision"])
            if since_revision < 0 or since_revision > head:
                raise FullResyncRequiredError(head)
            if since_revision > 0 and since_revision < min_ret:
                raise FullResyncRequiredError(head)

            after_rev = since_revision
            if cursor is not None:
                if not cursor.isdigit():
                    raise StoreError("VALIDATION_ERROR", "Cursor phân trang không hợp lệ.", 400)
                after_rev = max(after_rev, int(cursor))

            capped_limit = max(1, min(limit, 500))
            rows = await conn.fetch(
                """
                SELECT id, payload_version, nonce, ciphertext, revision, deleted_at, updated_at
                FROM vault_entries
                WHERE vault_id = $1 AND revision > $2
                ORDER BY revision ASC
                LIMIT $3
                """,
                v["id"],
                after_rev,
                capped_limit + 1,
            )
            has_more = len(rows) > capped_limit
            page_rows = rows[:capped_limit]
            entries = [self._row_to_entry(r) for r in page_rows]
            next_cursor = str(entries[-1].revision) if has_more and entries else None
            return PaginatedEntriesWire(
                entries=entries,
                headRevision=head,
                nextCursor=next_cursor,
                hasMore=has_more,
            )

    async def create_entries(
        self, owner_tg_id: int, inputs: list[CreateEntryInput]
    ) -> tuple[list[EncryptedEntryWire], int]:
        for item in inputs:
            if item.payloadVersion != 1:
                raise UnsupportedVersionError()
        seen: set[str] = set()
        for item in inputs:
            if item.id in seen:
                raise StoreError("VALIDATION_ERROR", "Danh sách có ID bản ghi trùng lặp.", 400)
            seen.add(item.id)

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                v = await conn.fetchrow(
                    "SELECT id, head_revision FROM vault_vaults WHERE owner_tg_id = $1 FOR UPDATE",
                    owner_tg_id,
                )
                if v is None:
                    raise VaultNotFoundError()
                head = int(v["head_revision"])
                active_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM vault_entries WHERE vault_id = $1 AND deleted_at IS NULL",
                    v["id"],
                )
                if int(active_count) + len(inputs) > MAX_VAULT_ENTRIES:
                    raise StoreError(
                        "VALIDATION_ERROR",
                        f"Vượt quá giới hạn tối đa {MAX_VAULT_ENTRIES} tài khoản trong kho.",
                        400,
                    )
                created: list[EncryptedEntryWire] = []
                for item in inputs:
                    dup = await conn.fetchrow(
                        """
                        SELECT id, payload_version, nonce, ciphertext, revision, deleted_at, updated_at
                        FROM vault_entries WHERE vault_id = $1 AND id = $2::uuid
                        """,
                        v["id"],
                        item.id,
                    )
                    if dup is not None:
                        raise EntryConflictError(
                            "Bản ghi với ID này đã tồn tại.",
                            head_revision=head,
                            current_entry=self._row_to_entry(dup),
                        )
                    head += 1
                    nonce_bytes = decode_b64url(
                        item.nonceB64, min_bytes=12, max_bytes=12, field_name="nonceB64"
                    )
                    cipher_bytes = decode_b64url(
                        item.ciphertextB64, min_bytes=16, max_bytes=16384, field_name="ciphertextB64"
                    )
                    row = await conn.fetchrow(
                        """
                        INSERT INTO vault_entries (vault_id, id, payload_version, nonce, ciphertext, revision)
                        VALUES ($1, $2::uuid, $3, $4, $5, $6)
                        RETURNING id, payload_version, nonce, ciphertext, revision, deleted_at, updated_at
                        """,
                        v["id"],
                        item.id,
                        item.payloadVersion,
                        nonce_bytes,
                        cipher_bytes,
                        head,
                    )
                    await conn.execute(
                        """
                        INSERT INTO vault_sync_log (vault_id, head_revision, entry_id, action)
                        VALUES ($1, $2, $3::uuid, 'upsert')
                        """,
                        v["id"],
                        head,
                        item.id,
                    )
                    created.append(self._row_to_entry(row))
                await conn.execute(
                    "UPDATE vault_vaults SET head_revision = $1, updated_at = NOW() WHERE id = $2",
                    head,
                    v["id"],
                )
                return created, head

    async def update_entry(
        self, owner_tg_id: int, entry_id: str, req: UpdateEntryRequest
    ) -> tuple[EncryptedEntryWire, int]:
        if req.payloadVersion != 1:
            raise UnsupportedVersionError()
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                v = await conn.fetchrow(
                    "SELECT id, head_revision FROM vault_vaults WHERE owner_tg_id = $1 FOR UPDATE",
                    owner_tg_id,
                )
                if v is None:
                    raise VaultNotFoundError()
                head = int(v["head_revision"])
                cur = await conn.fetchrow(
                    """
                    SELECT id, payload_version, nonce, ciphertext, revision, deleted_at, updated_at
                    FROM vault_entries WHERE vault_id = $1 AND id = $2::uuid FOR UPDATE
                    """,
                    v["id"],
                    entry_id,
                )
                if cur is None:
                    raise StoreError("VALIDATION_ERROR", "Không tìm thấy bản ghi.", 404)
                if cur["deleted_at"] is not None:
                    raise EntryConflictError(
                        "Bản ghi này đã bị xóa trên thiết bị khác.",
                        head_revision=head,
                        current_entry=self._row_to_entry(cur),
                    )
                if int(cur["revision"]) != req.expectedEntryRevision:
                    raise EntryConflictError(
                        "Bản ghi đã được cập nhật bởi thiết bị khác.",
                        head_revision=head,
                        current_entry=self._row_to_entry(cur),
                    )
                new_head = head + 1
                nonce_bytes = decode_b64url(
                    req.nonceB64, min_bytes=12, max_bytes=12, field_name="nonceB64"
                )
                cipher_bytes = decode_b64url(
                    req.ciphertextB64, min_bytes=16, max_bytes=16384, field_name="ciphertextB64"
                )
                row = await conn.fetchrow(
                    """
                    UPDATE vault_entries
                    SET payload_version = $1, nonce = $2, ciphertext = $3, revision = $4, updated_at = NOW()
                    WHERE vault_id = $5 AND id = $6::uuid
                    RETURNING id, payload_version, nonce, ciphertext, revision, deleted_at, updated_at
                    """,
                    req.payloadVersion,
                    nonce_bytes,
                    cipher_bytes,
                    new_head,
                    v["id"],
                    entry_id,
                )
                await conn.execute(
                    "UPDATE vault_vaults SET head_revision = $1, updated_at = NOW() WHERE id = $2",
                    new_head,
                    v["id"],
                )
                await conn.execute(
                    """
                    INSERT INTO vault_sync_log (vault_id, head_revision, entry_id, action)
                    VALUES ($1, $2, $3::uuid, 'upsert')
                    """,
                    v["id"],
                    new_head,
                    entry_id,
                )
                return self._row_to_entry(row), new_head

    async def delete_entry(
        self, owner_tg_id: int, entry_id: str, expected_entry_revision: int
    ) -> tuple[EncryptedEntryWire, int]:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                v = await conn.fetchrow(
                    "SELECT id, head_revision FROM vault_vaults WHERE owner_tg_id = $1 FOR UPDATE",
                    owner_tg_id,
                )
                if v is None:
                    raise VaultNotFoundError()
                head = int(v["head_revision"])
                cur = await conn.fetchrow(
                    """
                    SELECT id, payload_version, nonce, ciphertext, revision, deleted_at, updated_at
                    FROM vault_entries WHERE vault_id = $1 AND id = $2::uuid FOR UPDATE
                    """,
                    v["id"],
                    entry_id,
                )
                if cur is None:
                    raise StoreError("VALIDATION_ERROR", "Không tìm thấy bản ghi.", 404)
                if cur["deleted_at"] is not None:
                    return self._row_to_entry(cur), head
                if int(cur["revision"]) != expected_entry_revision:
                    raise EntryConflictError(
                        "Bản ghi đã thay đổi trước khi xóa.",
                        head_revision=head,
                        current_entry=self._row_to_entry(cur),
                    )
                new_head = head + 1
                row = await conn.fetchrow(
                    """
                    UPDATE vault_entries
                    SET nonce = ''::bytea, ciphertext = ''::bytea,
                        deleted_at = NOW(), revision = $1, updated_at = NOW()
                    WHERE vault_id = $2 AND id = $3::uuid
                    RETURNING id, payload_version, nonce, ciphertext, revision, deleted_at, updated_at
                    """,
                    new_head,
                    v["id"],
                    entry_id,
                )
                await conn.execute(
                    "UPDATE vault_vaults SET head_revision = $1, updated_at = NOW() WHERE id = $2",
                    new_head,
                    v["id"],
                )
                await conn.execute(
                    """
                    INSERT INTO vault_sync_log (vault_id, head_revision, entry_id, action)
                    VALUES ($1, $2, $3::uuid, 'delete')
                    """,
                    v["id"],
                    new_head,
                    entry_id,
                )
                return self._row_to_entry(row), new_head

    async def rotate_vault(
        self, owner_tg_id: int, req: RotateVaultRequest
    ) -> VaultWire:
        for item in req.entries:
            if item.payloadVersion != 1:
                raise UnsupportedVersionError()
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                v = await conn.fetchrow(
                    "SELECT id, head_revision FROM vault_vaults WHERE owner_tg_id = $1 FOR UPDATE",
                    owner_tg_id,
                )
                if v is None:
                    raise VaultNotFoundError()
                head = int(v["head_revision"])
                if req.expectedHeadRevision != head:
                    raise EntryConflictError(
                        "Phiên bản kho đã thay đổi trước khi xoay khóa DEK.",
                        head_revision=head,
                    )
                rows = await conn.fetch(
                    "SELECT id FROM vault_entries WHERE vault_id = $1 AND deleted_at IS NULL FOR UPDATE",
                    v["id"],
                )
                active_ids = {str(r["id"]) for r in rows}
                submitted_ids = {item.id for item in req.entries}
                if submitted_ids != active_ids or len(submitted_ids) != len(req.entries):
                    raise StoreError(
                        "VALIDATION_ERROR",
                        "Danh sách bản ghi mã hóa lại không khớp với các bản ghi đang hoạt động.",
                        400,
                    )
                for item in req.entries:
                    head += 1
                    nonce_bytes = decode_b64url(
                        item.nonceB64, min_bytes=12, max_bytes=12, field_name="nonceB64"
                    )
                    cipher_bytes = decode_b64url(
                        item.ciphertextB64, min_bytes=16, max_bytes=16384, field_name="ciphertextB64"
                    )
                    await conn.execute(
                        """
                        UPDATE vault_entries
                        SET payload_version = $1, nonce = $2, ciphertext = $3, revision = $4, updated_at = NOW()
                        WHERE vault_id = $5 AND id = $6::uuid
                        """,
                        item.payloadVersion,
                        nonce_bytes,
                        cipher_bytes,
                        head,
                        v["id"],
                        item.id,
                    )
                    await conn.execute(
                        """
                        INSERT INTO vault_sync_log (vault_id, head_revision, entry_id, action)
                        VALUES ($1, $2, $3::uuid, 'upsert')
                        """,
                        v["id"],
                        head,
                        item.id,
                    )
                head += 1
                await conn.execute(
                    """
                    UPDATE vault_vaults
                    SET envelope = $1::jsonb, recovery_envelope = $2::jsonb,
                        head_revision = $3, updated_at = NOW()
                    WHERE id = $4
                    """,
                    json.dumps(req.envelope.model_dump()),
                    json.dumps(req.recoveryEnvelope.model_dump()),
                    head,
                    v["id"],
                )
                await conn.execute(
                    """
                    INSERT INTO vault_sync_log (vault_id, head_revision, entry_id, action)
                    VALUES ($1, $2, NULL, 'envelope_update')
                    """,
                    v["id"],
                    head,
                )
        return await self.get_vault(owner_tg_id)

