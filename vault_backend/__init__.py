"""Gmail Vault backend — mounted into QuanLyThuChi_Bot's Starlette app (ADR-0001/0002).

The server stores and serves ciphertext only. It never decrypts, never generates OTPs and never
receives seeds, passphrases or DEKs.
"""

from .app import VaultRuntime, build_vault_routes, vault_middleware

__all__ = ["VaultRuntime", "build_vault_routes", "vault_middleware"]
