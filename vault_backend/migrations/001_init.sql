-- Gmail Vault Postgres Schema (spec v2 §05, ADR-0005).
-- Ciphertext ONLY: no email, TOTP seed, displayName, category, recoveryEmail, phone, or notes columns exist.

CREATE TABLE IF NOT EXISTS vault_schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS vault_vaults (
    id UUID PRIMARY KEY,
    owner_tg_id BIGINT NOT NULL UNIQUE,
    format_version INTEGER NOT NULL CHECK (format_version = 1),
    envelope JSONB NOT NULL,
    recovery_envelope JSONB NOT NULL,
    head_revision BIGINT NOT NULL DEFAULT 0 CHECK (head_revision >= 0),
    min_retained_revision BIGINT NOT NULL DEFAULT 0 CHECK (min_retained_revision >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS vault_entries (
    vault_id UUID NOT NULL REFERENCES vault_vaults(id) ON DELETE CASCADE,
    id UUID NOT NULL,
    payload_version SMALLINT NOT NULL CHECK (payload_version = 1),
    nonce BYTEA NOT NULL,
    ciphertext BYTEA NOT NULL,
    revision BIGINT NOT NULL CHECK (revision >= 1),
    deleted_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (vault_id, id),
    CONSTRAINT vault_entries_ciphertext_bounds CHECK (
        (deleted_at IS NOT NULL AND octet_length(nonce) = 0 AND octet_length(ciphertext) = 0)
        OR (deleted_at IS NULL AND octet_length(nonce) = 12 AND octet_length(ciphertext) BETWEEN 16 AND 16384)
    )
);

CREATE INDEX IF NOT EXISTS vault_entries_vault_revision_idx
    ON vault_entries (vault_id, revision);

CREATE TABLE IF NOT EXISTS vault_sessions (
    session_id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    owner_tg_id BIGINT NOT NULL,
    platform TEXT NOT NULL,
    created_at BIGINT NOT NULL,
    last_seen_at BIGINT NOT NULL,
    expires_at BIGINT NOT NULL,
    revoked_at BIGINT NULL
);

CREATE INDEX IF NOT EXISTS vault_sessions_owner_idx
    ON vault_sessions (owner_tg_id);

CREATE TABLE IF NOT EXISTS vault_sync_log (
    id BIGSERIAL PRIMARY KEY,
    vault_id UUID NOT NULL REFERENCES vault_vaults(id) ON DELETE CASCADE,
    head_revision BIGINT NOT NULL,
    entry_id UUID NULL,
    action TEXT NOT NULL CHECK (action IN ('upsert', 'delete', 'envelope_update')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS vault_sync_log_vault_rev_idx
    ON vault_sync_log (vault_id, head_revision);

