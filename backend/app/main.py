"""LedgerFlow FastAPI backend.

Phase 1 endpoints (read + PATCH + POST upload) backed by SQLite.

  GET    /api/health
  GET    /api/cases
  POST   /api/cases                                 {fir_number, title, officer_name}
  GET    /api/cases/{id}                            case + persons + accounts
  POST   /api/cases/{id}/persons                    {name, pan?, phone?}
  GET    /api/cases/{id}/transactions               ?account_id, offset, limit
  POST   /api/cases/{id}/statements                 multipart: file, person_id, bank, account_type, account_number, …
  GET    /api/statements/{id}
  PATCH  /api/transactions/{id}                     edits + audit
  GET    /api/transactions/{id}/audit
  POST   /api/dev/reset                             dev: drop all tables, re-seed

Run:
    cd backend
    uvicorn app.main:app --reload --port 8000

Env:
    LEDGERFLOW_RESET_DB=1   # reset + reseed on startup (dev only)
"""
from __future__ import annotations
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pdfplumber
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import store as store_mod
from app.schemas import (
    Case, CaseDetail, Person, Transaction, TransactionPage, TransactionPatch,
    Statement,
)

# Import the bank parser from plugins/bank (separate tree, no coupling)
REPO = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO))
from plugins.bank.extraction.parser import parse_text, detect_bank  # noqa: E402


app = FastAPI(
    title="LedgerFlow",
    version="0.2.0",
    description="Forensic bank-statement analysis backend.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    reset = os.environ.get("LEDGERFLOW_RESET_DB") == "1"
    store_mod.init_and_seed(reset=reset)


# ───── health ─────

@app.get("/api/health")
def health() -> dict:
    c = store_mod.counts()
    return {"status": "ok", **c}


# ───── cases ─────

@app.get("/api/cases", response_model=list[Case])
def list_cases() -> list[Case]:
    return store_mod.list_cases()


class CaseCreate(BaseModel):
    fir_number: str
    title: str
    officer_name: str


@app.post("/api/cases", response_model=Case, status_code=201)
def create_case(body: CaseCreate) -> Case:
    return store_mod.create_case(body.fir_number, body.title, body.officer_name)


@app.get("/api/cases/{case_id}", response_model=CaseDetail)
def get_case(case_id: str) -> CaseDetail:
    detail = store_mod.get_case(case_id)
    if not detail:
        raise HTTPException(404, f"Case {case_id} not found")
    return detail


@app.get("/api/cases/{case_id}/transactions", response_model=TransactionPage)
def list_case_transactions(
    case_id: str,
    account_id: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=2000),
) -> TransactionPage:
    page = store_mod.list_case_transactions(case_id, account_id=account_id, offset=offset, limit=limit)
    if page is None:
        raise HTTPException(404, f"Case {case_id} not found")
    return page


# ───── persons ─────

class PersonCreate(BaseModel):
    name: str
    pan: str | None = None
    phone: str | None = None


@app.post("/api/cases/{case_id}/persons", response_model=Person, status_code=201)
def add_person(case_id: str, body: PersonCreate) -> Person:
    p = store_mod.create_person(case_id, body.name, pan=body.pan, phone=body.phone)
    if not p:
        raise HTTPException(404, f"Case {case_id} not found")
    return p


# ───── statements / upload ─────

UPLOAD_DIR = REPO / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Heuristics for detected-bank → (account_type, period detection, etc)
BANK_DEFAULTS = {
    "hdfc_cc":      {"display": "HDFC Bank",       "account_type": "CC"},
    "hdfc_savings": {"display": "HDFC Bank",       "account_type": "SA"},
    "idfc":         {"display": "IDFC First Bank", "account_type": "CA"},
    "icici":        {"display": "ICICI Bank",      "account_type": "CA"},
    "kotak":        {"display": "Kotak Mahindra",  "account_type": "SA"},
    "unknown":      {"display": "Unknown",         "account_type": "SA"},
}

_PERIOD_RX = [
    re.compile(r"From\s*[:\-]\s*(\d{2}/\d{2}/\d{4}).*?To\s*[:\-]\s*(\d{2}/\d{2}/\d{4})", re.I),
    re.compile(r"Period From\s*(\d{2}/\d{2}/\d{4}).*?To\s*(\d{2}/\d{2}/\d{4})", re.I),
    re.compile(r"(\d{2}-\d{2}-\d{4}).*?To\s*(\d{2}-\d{2}-\d{4})", re.I),
]


def _guess_period(text: str) -> tuple[str, str]:
    for rx in _PERIOD_RX:
        m = rx.search(text)
        if m:
            s, e = m.group(1), m.group(2)
            s_iso = _to_iso_date(s)
            e_iso = _to_iso_date(e)
            return s_iso, e_iso
    today = datetime.utcnow().date().isoformat()
    return today, today


def _to_iso_date(raw: str) -> str:
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return raw


def _guess_account_number(text: str) -> str | None:
    m = re.search(r"(?:A/C|Account|AccountNo|AC NO)[^0-9]*(\d{6,20})", text, re.I)
    if m:
        num = m.group(1)
        return f"****{num[-4:]}" if len(num) >= 4 else num
    return None


@app.post("/api/cases/{case_id}/statements", status_code=201)
async def upload_statement(
    case_id: str,
    file: UploadFile = File(...),
    person_id: str = Form(...),
    bank: str | None = Form(default=None),
    account_type: str | None = Form(default=None),
    account_number: str | None = Form(default=None),
    holder_name: str | None = Form(default=None),
) -> dict:
    if not file.filename:
        raise HTTPException(400, "Missing file")

    # Persist the PDF
    safe_name = re.sub(r"[^A-Za-z0-9._\-]", "_", file.filename)
    dest = UPLOAD_DIR / f"{case_id}_{int(datetime.utcnow().timestamp())}_{safe_name}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    # Parse
    try:
        with pdfplumber.open(dest) as pdf:
            text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception as exc:
        raise HTTPException(400, f"Could not read PDF: {exc}") from exc

    bank_key = detect_bank(text)
    parser_txns = parse_text(text)
    if not parser_txns:
        raise HTTPException(400, f"No transactions extracted (bank={bank_key}). Try a different file or manual account setup.")

    # Bank metadata
    bank_label = bank or BANK_DEFAULTS.get(bank_key, BANK_DEFAULTS["unknown"])["display"]
    acc_type = account_type or BANK_DEFAULTS.get(bank_key, BANK_DEFAULTS["unknown"])["account_type"]
    acc_num = account_number or _guess_account_number(text) or "****????"
    period_start, period_end = _guess_period(text)

    # Ingest
    result = store_mod.ingest_statement(
        case_id=case_id, person_id=person_id,
        source_file_name=file.filename,
        source_file_path=str(dest),
        bank=bank_label, account_type=acc_type,
        account_number=acc_num,
        holder_name=holder_name or "Unknown",
        period_start=period_start, period_end=period_end,
        opening_balance=0.0, closing_balance=0.0,
        declared_dr=None, declared_cr=None,
        parser_txns=[{"date": t["date"], "description": t["description"],
                      "amount": t["amount"], "type": t["type"]} for t in parser_txns],
        uploaded_by="unknown",
    )
    if result is None:
        raise HTTPException(404, f"Case or person not found (case_id={case_id}, person_id={person_id})")
    statement, txns = result
    return {
        "bank_detected": bank_key,
        "statement": statement.model_dump(),
        "transaction_count": len(txns),
    }


@app.get("/api/statements/{statement_id}", response_model=Statement)
def get_statement(statement_id: str) -> Statement:
    stmt = store_mod.get_statement(statement_id)
    if not stmt:
        raise HTTPException(404, f"Statement {statement_id} not found")
    return stmt


# ───── transactions ─────

@app.patch("/api/transactions/{txn_id}", response_model=Transaction)
def patch_transaction(txn_id: str, patch: TransactionPatch) -> Transaction:
    txn = store_mod.patch_transaction(txn_id, patch)
    if not txn:
        raise HTTPException(404, f"Transaction {txn_id} not found")
    return txn


@app.get("/api/transactions/{txn_id}/audit")
def get_transaction_audit(txn_id: str) -> list[dict]:
    audit = store_mod.list_transaction_audit(txn_id)
    if audit is None:
        raise HTTPException(404, f"Transaction {txn_id} not found")
    return audit


# ───── dev / admin ─────

@app.post("/api/dev/reset")
def dev_reset() -> dict:
    """Drop all tables and re-seed from benchmark output. Dev only."""
    store_mod.init_and_seed(reset=True)
    return {"status": "reset+seeded", **store_mod.counts()}
