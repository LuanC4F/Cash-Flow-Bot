"""Security headers for vault routes (spec v1/v2 §12 hardening checklist)."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Telegram bridge script is the only third-party origin allowed (ADR-0004, spec v2 §12).
# 'wasm-unsafe-eval' is required to instantiate the Argon2id WASM module; no 'unsafe-eval'.
CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self' https://telegram.org 'wasm-unsafe-eval'",
        "style-src 'self'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'none'",
        # Telegram Web/Desktop embed the Mini App in an iframe; allow only Telegram origins.
        "frame-ancestors https://web.telegram.org https://*.telegram.org",
    ]
)

BASE_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}

VAULT_PREFIXES = ("/vault", "/api/v1")


class VaultSecurityHeaders(BaseHTTPMiddleware):
    """Adds headers only to vault paths so the existing bot routes are untouched."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        path = request.url.path
        if path.startswith(VAULT_PREFIXES):
            for k, v in BASE_HEADERS.items():
                response.headers.setdefault(k, v)
            if path.startswith("/vault"):
                response.headers.setdefault("Content-Security-Policy", CSP)
            if path.startswith("/api/v1"):
                response.headers["Cache-Control"] = "no-store"
        return response

