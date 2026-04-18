"""Persistence for every `/api/extract` call.

Two jobs:
  1. Write the uploaded PDF to a content-addressed file store (shared across
     submissions — identical bytes only land on disk once).
  2. Record a row in `extraction_log` with everything we know about the
     request + what we returned.

Works with any `DATABASE_URL` (SQLite locally, Postgres on Railway) and any
`LEDGERFLOW_PDF_STORE_DIR` (falls back to `backend/data/pdf_store` for dev).
On Railway, point that env var at the mount path of a Railway volume so the
PDFs survive redeploys.
"""
from __future__ import annotations
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.db import BACKEND, ExtractionLogRow, get_session


def _pdf_store_dir() -> Path:
    raw = os.environ.get("LEDGERFLOW_PDF_STORE_DIR", "").strip()
    path = Path(raw) if raw else (BACKEND / "data" / "pdf_store")
    path.mkdir(parents=True, exist_ok=True)
    return path


def store_pdf_bytes(content: bytes) -> tuple[str, str]:
    """Write `content` to the PDF store, keyed by sha256. Returns
    `(hash_hex, relative_path)`. Path is relative to the store directory so
    the DB row stays portable across moves of the volume."""
    h = hashlib.sha256(content).hexdigest()
    # Sharded layout: ab/cd/<full-hash>.pdf — avoids one dir with 100k files.
    sub = Path(h[0:2]) / h[2:4]
    rel = sub / f"{h}.pdf"
    target = _pdf_store_dir() / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    # Content-addressed: only write if missing.
    if not target.exists():
        target.write_bytes(content)
    return h, str(rel).replace("\\", "/")


def resolve_pdf_path(rel_path: str) -> Path:
    """Reverse of `store_pdf_bytes`: rel_path → absolute Path on disk."""
    return _pdf_store_dir() / rel_path


def record(
    *,
    filename: str,
    file_size: int,
    file_hash: str | None,
    pdf_stored_path: str | None,
    was_password_protected: bool,
    http_status: int,
    success: bool,
    response: dict[str, Any] | None,
    error_code: str | None,
    submitter_label: str | None,
    client_ip: str | None,
    user_agent: str | None,
) -> str:
    """Insert an extraction_log row. Returns the new row id.

    All failures are swallowed and logged — logging must never block the
    user-facing response.
    """
    row_id = str(uuid.uuid4())
    meta = (response or {}).get("meta") or {}
    summary = (response or {}).get("summary") or {}
    bank = (response or {}).get("bank") or {}
    try:
        with get_session() as s:
            row = ExtractionLogRow(
                id=row_id,
                received_at=datetime.now(timezone.utc).isoformat(),
                filename=filename,
                file_size=file_size,
                file_hash=file_hash,
                pdf_stored_path=pdf_stored_path,
                was_password_protected=was_password_protected,
                bank_key_detected=bank.get("key") if bank else None,
                page_count=meta.get("page_count"),
                transaction_count=summary.get("transaction_count"),
                issues_json=json.dumps(meta.get("issues") or []),
                success=success,
                http_status=http_status,
                error_code=error_code,
                response_json=json.dumps(response) if response is not None else None,
                submitter_label=submitter_label,
                client_ip=client_ip,
                user_agent=(user_agent or "")[:500],
            )
            s.add(row)
            s.commit()
    except Exception as exc:  # pragma: no cover — non-blocking
        # Don't let logging failures break the request. Print is picked up by
        # the Railway log aggregator and surfaced in the service logs.
        print(f"[extraction_log] failed to record extraction: {exc!r}")
    return row_id
