"""API-key gate for the LedgerFlow backend.

Enforced when the `LEDGERFLOW_API_KEY` env var is set. Callers must send the
key in the `X-API-Key` header. Deliberately permissive when the env var is
unset so local dev keeps working without ceremony.

Health probes and CORS preflights bypass the gate — Railway's healthcheck
and the browser's OPTIONS don't carry custom headers.
"""
from __future__ import annotations
import os
import secrets
from fastapi import Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

# Paths that don't need the key. Health must be open for Railway's probe; the
# OpenAPI JSON and docs are conveniences you can flip off by unsetting them.
_UNAUTHED_PATHS = {
    "/api/health",
    "/openapi.json",
    "/docs",
    "/redoc",
    "/docs/oauth2-redirect",
}


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """FastAPI dependency form — still available for per-route use if needed."""
    expected = os.environ.get("LEDGERFLOW_API_KEY")
    if not expected:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-API-Key header.",
        )


async def api_key_middleware(request: Request, call_next):
    """ASGI middleware that enforces the key on every request except the
    whitelisted paths and CORS preflight (OPTIONS)."""
    expected = os.environ.get("LEDGERFLOW_API_KEY")
    if not expected:
        return await call_next(request)
    if request.method == "OPTIONS" or request.url.path in _UNAUTHED_PATHS:
        return await call_next(request)
    provided = request.headers.get("x-api-key")
    if not provided or not secrets.compare_digest(provided, expected):
        return JSONResponse(
            status_code=401,
            content={"detail": "Missing or invalid X-API-Key header."},
        )
    return await call_next(request)
