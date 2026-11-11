"""Strict Pydantic v2 wire schemas for encrypted vault & entries (spec v2 §05, §06).

Invariants:
- `extra="forbid"` on all request models so plaintext fields (`email`, `totp`, `password`, etc.) are rejected.
- All binary fields (`nonceB64`, `ciphertextB64`, `saltB64`, `wrapNonceB64`, `wrappedDekB64`) use
  unpadded base64url and have strict decoded byte length checks.
"""

from __future__ import annotations

import base64
import re
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

B64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")
MAX_CIPHERTEXT_BYTES = 16_384
MAX_VAULT_ENTRIES = 1000


def decode_b64url(value: str, *, min_bytes: int, max_bytes: int, field_name: str) -> bytes:
    if not isinstance(value, str) or not value or not B64URL_RE.match(value) or len(value) % 4 == 1:
        raise ValueError(f"{field_name} không đúng định dạng base64url (không padding).")
    pad = "=" * ((4 - (len(value) % 4)) % 4)
    try:
        raw = base64.urlsafe_b64decode(value + pad)
    except Exception as exc:
        raise ValueError(f"{field_name} không thể giải mã base64url.") from exc
    if not (min_bytes <= len(raw) <= max_bytes):
        raise ValueError(f"{field_name} có độ dài byte ngoài ngưỡng [{min_bytes}, {max_bytes}].")
    return raw


def encode_b64url(raw: bytes) -> str:
    if not raw:
        return ""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def canonical_uuid(value: str, field_name: str) -> str:
    try:
        parsed = uuid.UUID(str(value))
    except ValueError as exc:
        raise ValueError(f"{field_name} phải là UUID hợp lệ.") from exc
    if str(parsed) != value.lower():
        raise ValueError(f"{field_name} phải ở dạng chuẩn UUID chữ thường.")
    return str(parsed)


class Argon2ParamsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memorySizeKiB: int = Field(ge=16_384, le=262_144)
    iterations: int = Field(ge=2, le=10)
    parallelism: int = Field(ge=1, le=4)


class KdfSpecModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["argon2id"]
    version: Literal[1]
    params: Argon2ParamsModel


class PassphraseEnvelopeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kdf: KdfSpecModel
    saltB64: str
    wrapNonceB64: str
    wrappedDekB64: str
    aadVersion: Literal[1]

    @field_validator("saltB64")
    @classmethod
    def _check_salt(cls, v: str) -> str:
        decode_b64url(v, min_bytes=16, max_bytes=64, field_name="saltB64")
        return v

    @field_validator("wrapNonceB64")
    @classmethod
    def _check_nonce(cls, v: str) -> str:
        decode_b64url(v, min_bytes=12, max_bytes=12, field_name="wrapNonceB64")
        return v

    @field_validator("wrappedDekB64")
    @classmethod
    def _check_wrapped_dek(cls, v: str) -> str:
        # 32-byte DEK + 16-byte GCM tag = 48 bytes
        decode_b64url(v, min_bytes=48, max_bytes=48, field_name="wrappedDekB64")
        return v


class RecoveryEnvelopeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Literal["hkdf-sha256-aes-256-gcm"]
    version: Literal[1]
    recoverySaltB64: str
    wrapNonceB64: str
    wrappedDekB64: str
    aadVersion: Literal[1]

    @field_validator("recoverySaltB64")
    @classmethod
    def _check_salt(cls, v: str) -> str:
        decode_b64url(v, min_bytes=16, max_bytes=64, field_name="recoverySaltB64")
        return v

    @field_validator("wrapNonceB64")
    @classmethod
    def _check_nonce(cls, v: str) -> str:
        decode_b64url(v, min_bytes=12, max_bytes=12, field_name="wrapNonceB64")
        return v

    @field_validator("wrappedDekB64")
    @classmethod
    def _check_wrapped_dek(cls, v: str) -> str:
        decode_b64url(v, min_bytes=48, max_bytes=48, field_name="wrappedDekB64")
        return v


class CreateVaultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vaultId: str
    formatVersion: int
    envelope: PassphraseEnvelopeModel
    recoveryEnvelope: RecoveryEnvelopeModel

    @field_validator("vaultId")
    @classmethod
    def _check_vault_id(cls, v: str) -> str:
        return canonical_uuid(v, "vaultId")


class UpdateEnvelopesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expectedHeadRevision: int = Field(ge=0)
    envelope: PassphraseEnvelopeModel
    recoveryEnvelope: RecoveryEnvelopeModel | None = None


class CreateEntryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    payloadVersion: int
    nonceB64: str
    ciphertextB64: str

    @field_validator("id")
    @classmethod
    def _check_id(cls, v: str) -> str:
        return canonical_uuid(v, "id")

    @field_validator("nonceB64")
    @classmethod
    def _check_nonce(cls, v: str) -> str:
        decode_b64url(v, min_bytes=12, max_bytes=12, field_name="nonceB64")
        return v

    @field_validator("ciphertextB64")
    @classmethod
    def _check_cipher(cls, v: str) -> str:
        decode_b64url(v, min_bytes=16, max_bytes=MAX_CIPHERTEXT_BYTES, field_name="ciphertextB64")
        return v


class BatchCreateEntriesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[CreateEntryInput] = Field(min_length=1, max_length=MAX_VAULT_ENTRIES)


class UpdateEntryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expectedEntryRevision: int = Field(ge=1)
    payloadVersion: int
    nonceB64: str
    ciphertextB64: str

    @field_validator("nonceB64")
    @classmethod
    def _check_nonce(cls, v: str) -> str:
        decode_b64url(v, min_bytes=12, max_bytes=12, field_name="nonceB64")
        return v

    @field_validator("ciphertextB64")
    @classmethod
    def _check_cipher(cls, v: str) -> str:
        decode_b64url(v, min_bytes=16, max_bytes=MAX_CIPHERTEXT_BYTES, field_name="ciphertextB64")
        return v


class DeleteEntryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expectedEntryRevision: int = Field(ge=1)


class RotateVaultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expectedHeadRevision: int = Field(ge=1)
    envelope: PassphraseEnvelopeModel
    recoveryEnvelope: RecoveryEnvelopeModel
    entries: list[CreateEntryInput] = Field(default_factory=list, max_length=MAX_VAULT_ENTRIES)

