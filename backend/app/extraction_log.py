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

from app.db import (
    BACKEND, ExtractionLogRow, ExtractionTraceRow, LLMAttemptRow, get_session,
)


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


def new_extraction_id() -> str:
    """Pre-generate an extraction id so trace + llm_attempt rows written
    *before* the main log row finalises can still FK to the right parent."""
    return str(uuid.uuid4())


def record(
    *,
    extraction_id: str | None = None,
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
    """Insert an extraction_log row. Returns the row id (either the supplied
    `extraction_id` or a freshly-generated one).

    All failures are swallowed and logged — logging must never block the
    user-facing response.
    """
    row_id = extraction_id or str(uuid.uuid4())
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


def record_trace(
    *,
    extraction_log_id: str,
    pdfplumber_text: str | None,
    deterministic_raw: list[dict] | None,
    bank_detected: str | None,
) -> None:
    """Store the full pdfplumber + deterministic-parser snapshot for one
    extraction. Large blobs live here, off the hot list-view path.
    Non-blocking: a write failure is logged but does not affect the response.
    """
    try:
        with get_session() as s:
            s.add(ExtractionTraceRow(
                id=str(uuid.uuid4()),
                extraction_log_id=extraction_log_id,
                pdfplumber_text=pdfplumber_text,
                deterministic_raw_json=json.dumps(deterministic_raw) if deterministic_raw is not None else None,
                bank_detected=bank_detected,
                text_char_count=len(pdfplumber_text) if pdfplumber_text else 0,
                created_at=datetime.now(timezone.utc).isoformat(),
            ))
            s.commit()
    except Exception as exc:  # pragma: no cover
        print(f"[extraction_log] failed to record trace: {exc!r}")


def record_llm_attempt(
    *,
    extraction_log_id: str,
    provider: str,
    model: str,
    prompt_text: str | None,
    raw_response: str | None,
    parsed_json: dict | None,
    parse_error: str | None,
    provider_error: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    latency_ms: int | None,
) -> str:
    """Store one LLM call. Returns the attempt id. Always best-effort.

    Derived columns (`extracted_txn_count`, `extracted_bank_key`,
    `extracted_holder_name`, `confidence`) are populated from `parsed_json`
    when present, so admin list views can sort/filter without re-parsing.
    """
    row_id = str(uuid.uuid4())
    try:
        txn_count = None
        bank_key = None
        holder_name = None
        confidence = None
        if parsed_json:
            txns = parsed_json.get("transactions")
            if isinstance(txns, list):
                txn_count = len(txns)
            bank = parsed_json.get("bank") or {}
            if isinstance(bank, dict):
                bank_key = bank.get("key")
            account = parsed_json.get("account") or {}
            if isinstance(account, dict):
                holder_name = account.get("holder_name")
            confidence = parsed_json.get("confidence")

        with get_session() as s:
            s.add(LLMAttemptRow(
                id=row_id,
                extraction_log_id=extraction_log_id,
                provider=provider,
                model=model,
                prompt_text=prompt_text,
                raw_response=raw_response,
                parsed_json=json.dumps(parsed_json) if parsed_json is not None else None,
                parse_error=parse_error,
                provider_error=provider_error,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
                extracted_txn_count=txn_count,
                extracted_bank_key=bank_key,
                extracted_holder_name=holder_name,
                confidence=confidence,
                created_at=datetime.now(timezone.utc).isoformat(),
            ))
            s.commit()
    except Exception as exc:  # pragma: no cover
        print(f"[extraction_log] failed to record llm_attempt: {exc!r}")
    return row_id
