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
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import store as store_mod
from app.schemas import (
    Case, CaseDetail, Person, Transaction, TransactionPage, TransactionPatch,
    Statement, CaseSummary, Entity, EntityDetail, EntityCreate, EntityLinkRequest,
    CaseGraph,
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


@app.get("/api/cases/{case_id}/graph", response_model=CaseGraph)
def get_case_graph(case_id: str) -> CaseGraph:
    graph = store_mod.case_graph(case_id)
    if graph is None:
        raise HTTPException(404, f"Case {case_id} not found")
    return graph


@app.get("/api/cases/{case_id}/summary", response_model=CaseSummary)
def get_case_summary(case_id: str) -> CaseSummary:
    summary = store_mod.case_summary(case_id)
    if summary is None:
        raise HTTPException(404, f"Case {case_id} not found")
    return summary


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


def _guess_period(text: str) -> tuple[str | None, str | None]:
    """Return the period printed on the statement header, if detectable.
    Returns (None, None) when no pattern matches — callers should fall back
    to deriving the period from the extracted transaction dates rather than
    inserting today's date, which would be meaningless.
    """
    for rx in _PERIOD_RX:
        m = rx.search(text)
        if m:
            s, e = m.group(1), m.group(2)
            return _to_iso_date(s), _to_iso_date(e)
    return None, None


def _period_from_txns(txns: list[dict]) -> tuple[str | None, str | None]:
    """Derive the period from parsed transactions. Assumes dates are already
    ISO-8601 or can be coerced via _to_iso_date."""
    iso_dates: list[str] = []
    for t in txns:
        raw = t.get("date") or ""
        iso = _to_iso_date(raw)
        # `_to_iso_date` returns the raw string unchanged if it can't parse;
        # accept only values that look ISO-ish (YYYY-MM-DD).
        if re.match(r"^\d{4}-\d{2}-\d{2}$", iso):
            iso_dates.append(iso)
    if not iso_dates:
        return None, None
    return min(iso_dates), max(iso_dates)


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


_HOLDER_LABEL_RX = [
    re.compile(r"(?:Customer|Account Holder|Holder|Primary Holder)\s*Name\s*[:\-]\s*([A-Z][A-Za-z\s\.\-]{2,80})", re.I),
    re.compile(r"Statement\s+(?:for|of)\s+([A-Z][A-Za-z\s\.\-]{2,80})", re.I),
    re.compile(r"\bDear\s+(?:Mr\.?|Mrs\.?|Ms\.?|Miss)?\s*([A-Z][A-Za-z\s\.\-]{2,80})", re.I),
]

# Words that disqualify an all-caps line from being a person's name.
_HOLDER_BLOCKLIST = re.compile(
    r"\b(BANK|LTD|LIMITED|PVT|PRIVATE|STATEMENT|ACCOUNT|BRANCH|ADDRESS|CUSTOMER"
    r"|NOMIN|IFSC|MICR|CITY|STATE|INDIA|EMAIL|PHONE|MOBILE|DATE|PERIOD|PAGE"
    r"|FROM|TO|CURRENCY|INR|OPENING|CLOSING|BALANCE|DEBIT|CREDIT|WITHDRAWAL"
    r"|DEPOSIT|TRANSACTION|REGISTERED|ENTERPRISES|COMPANY|ROAD|STREET|FLOOR"
    r"|NAGAR|MUMBAI|DELHI|BANGALORE|BENGALURU|CHENNAI|KOLKATA|HYDERABAD|PUNE"
    r"|THANE|GURGAON|NOIDA|MAHARASHTRA|KARNATAKA|GUJARAT|RAJASTHAN|PUNJAB"
    r"|HARYANA|ORISSA|ODISHA|BIHAR|GMAIL|YAHOO|HOTMAIL|OUTLOOK|COM|WWW|HTTP"
    r"|JOINT|HOLDERS?|NOMINEE|CHEQUE|REF|SUMMARY|OPERATIVE|TYPE|NUMBER|CENTER"
    r"|ANDHERI|VIKHROLI|POWAI|SAKI|VIHAR|BHILWARA|AJMER|GANDHI)\b",
    re.I,
)

_PREFIX_RX = re.compile(r"^(MR|MRS|MS|MISS|DR|SHRI|SMT|M/S)\.?\s*", re.I)

# Substrings that indicate an address line even when concatenated without
# whitespace (e.g., "MAHAKALICAVESROAD", "ANDHERIWEST"). Checked without
# word boundaries so concatenated tokens still match.
_ADDRESS_SUBSTRING = re.compile(
    r"(ROAD|STREET|NAGAR|PURAM|MANZIL|CENTER|CENTRE|BUILDING|HOUSE|APARTMENT"
    r"|COMPLEX|ESTATES?|MARKET|CHOWK|GALI|PARK|GARDEN|PLAZA|TOWER|MALL|SOCIETY"
    r"|COLONY|LAYOUT|PHASE|SECTOR|BLOCK|FLAT|FLOOR|WING|GROUND|LANE|CROSS|MAIN"
    r"|EAST|WEST|NORTH|SOUTH|DWAR|BAZAAR|BAZAR|COURT|VILLA|HEIGHTS|HILLS)",
    re.I,
)


def _clean_holder_candidate(line: str) -> str:
    name = _PREFIX_RX.sub("", line).strip(" .-,:")
    return name


def _is_holder_candidate(line: str) -> bool:
    """True if `line` looks like a plausible account-holder name."""
    line = line.strip()
    if not (5 <= len(line) <= 80):
        return False
    if any(c.isdigit() for c in line):
        return False
    alpha = [c for c in line if c.isalpha()]
    if len(alpha) < 4:
        return False
    if sum(1 for c in alpha if c.isupper()) / len(alpha) < 0.85:
        return False
    if _HOLDER_BLOCKLIST.search(line):
        return False
    parts = line.split()
    # A single token is only OK if it's long (e.g. "BILALABDULKUDDUSKHANMOHAMMED")
    if len(parts) == 1 and len(line.replace(".", "")) < 14:
        return False
    return True


def _guess_holder_name(text: str) -> str | None:
    """Best-effort holder-name extraction. First tries labeled patterns, then
    falls back to scanning all-caps lines in the top of the statement."""
    # Pass 1 — explicit labels
    for rx in _HOLDER_LABEL_RX:
        m = rx.search(text)
        if m:
            raw = re.split(r"\s{2,}|\n|,", m.group(1).strip(), maxsplit=1)[0].strip(" .-")
            if 3 <= len(raw) < 80 and not _HOLDER_BLOCKLIST.search(raw):
                return _clean_holder_candidate(raw)

    # Pass 2 — lines with an honorific prefix. Strongest bare-name signal.
    lines = [l.rstrip() for l in text.splitlines() if l.strip()][:40]
    for line in lines:
        if not _PREFIX_RX.match(line):
            continue
        probe = _PREFIX_RX.sub("", line).strip()
        if _is_holder_candidate(probe):
            return _clean_holder_candidate(line)

    # Pass 3 — first plausible all-caps line in the header, skipping
    # anything that looks like an address.
    for line in lines:
        if _ADDRESS_SUBSTRING.search(line):
            continue
        probe = _PREFIX_RX.sub("", line).strip()
        if _is_holder_candidate(probe):
            return _clean_holder_candidate(line)

    return None


def _normalise_name(name: str) -> str:
    import re as _re
    return _re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


def _suggest_person_match(holder: str | None, persons: list[dict]) -> str | None:
    """Given a detected holder name and the list of persons in a case, return
    the best-matching person's id if any. Matches by normalised substring
    containment in either direction.
    """
    if not holder:
        return None
    h = _normalise_name(holder)
    if not h or len(h) < 3:
        return None
    best_id = None
    best_score = 0
    for p in persons:
        n = _normalise_name(p.get("name", ""))
        if not n:
            continue
        if n == h:
            return p["id"]
        if n in h or h in n:
            # score = length of shorter, so longer matches win ties
            score = min(len(n), len(h))
            if score > best_score:
                best_score = score
                best_id = p["id"]
    return best_id


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

    # Period: header text first, then the envelope of the parsed transactions
    # (which is what the investigator actually sees). If both fail, leave it
    # unknown rather than writing today's date — that was the bug where
    # April-2021 CC statements showed "2026-04-16 → 2026-04-16".
    period_start, period_end = _guess_period(text)
    if not period_start or not period_end:
        txn_start, txn_end = _period_from_txns(parser_txns)
        period_start = period_start or txn_start
        period_end = period_end or txn_end

    # Ingest
    result = store_mod.ingest_statement(
        case_id=case_id, person_id=person_id,
        source_file_name=file.filename,
        source_file_path=str(dest),
        bank=bank_label, account_type=acc_type,
        account_number=acc_num,
        holder_name=holder_name or "Unknown",
        period_start=period_start or "", period_end=period_end or "",
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


@app.post("/api/statements/preview")
async def preview_statement(
    file: UploadFile = File(...),
    case_id: str | None = Form(default=None),
) -> dict:
    """Detect bank / account number / period / holder name from a PDF without
    persisting it. If `case_id` is provided, also suggest a matching existing
    person whose name is close to the detected holder.
    """
    if not file.filename:
        raise HTTPException(400, "Missing file")
    content = await file.read()
    tmp = UPLOAD_DIR / f"_preview_{int(datetime.utcnow().timestamp())}_{re.sub(r'[^A-Za-z0-9._-]', '_', file.filename)}"
    tmp.write_bytes(content)
    try:
        with pdfplumber.open(tmp) as pdf:
            text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        bank_key = detect_bank(text)
        txns = parse_text(text)
        defaults = BANK_DEFAULTS.get(bank_key, BANK_DEFAULTS["unknown"])

        period_start, period_end = _guess_period(text)
        if not period_start or not period_end:
            txn_start, txn_end = _period_from_txns(
                [{"date": t["date"]} for t in txns]
            )
            period_start = period_start or txn_start
            period_end = period_end or txn_end

        holder = _guess_holder_name(text)

        suggested_person_id = None
        if case_id:
            detail = store_mod.get_case(case_id)
            if detail is not None:
                persons_for_match = [p.model_dump() for p in detail.persons]
                suggested_person_id = _suggest_person_match(holder, persons_for_match)

        return {
            "bank_detected": bank_key,
            "bank_label": defaults["display"],
            "account_type": defaults["account_type"],
            "account_number_guess": _guess_account_number(text),
            "holder_name_guess": holder,
            "suggested_person_id": suggested_person_id,
            "period_start": period_start,
            "period_end": period_end,
            "transaction_count": len(txns),
            "filename": file.filename,
        }
    except Exception as exc:
        raise HTTPException(400, f"Could not read PDF: {exc}") from exc
    finally:
        try:
            tmp.unlink()
        except Exception:
            pass


@app.get("/api/statements/{statement_id}", response_model=Statement)
def get_statement(statement_id: str) -> Statement:
    stmt = store_mod.get_statement(statement_id)
    if not stmt:
        raise HTTPException(404, f"Statement {statement_id} not found")
    return stmt


@app.delete("/api/statements/{statement_id}")
def delete_statement(statement_id: str) -> dict:
    """Remove a statement, its transactions, audit entries, and any entity
    links. If this was the owning account's last statement the account is
    removed too — empty accounts are nearly always mistaken uploads.
    """
    result = store_mod.delete_statement(statement_id)
    if result is None:
        raise HTTPException(404, f"Statement {statement_id} not found")
    return {"status": "deleted", **result}


@app.get("/api/statements/{statement_id}/pdf")
def get_statement_pdf(statement_id: str):
    """Stream the original source PDF for a statement (inline in browser)."""
    result = store_mod.get_statement_pdf_path(statement_id)
    if not result:
        raise HTTPException(404, f"Source PDF for statement {statement_id} not found")
    path, filename = result
    pdf_path = Path(path)
    if not pdf_path.exists():
        raise HTTPException(404, f"PDF file missing on disk: {path}")
    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


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

# ───── entities ─────

@app.get("/api/cases/{case_id}/entities", response_model=list[Entity])
def list_case_entities(case_id: str) -> list[Entity]:
    entities = store_mod.list_entities(case_id)
    if entities is None:
        raise HTTPException(404, f"Case {case_id} not found")
    return entities


@app.post("/api/cases/{case_id}/entities", response_model=Entity, status_code=201)
def create_case_entity(case_id: str, body: EntityCreate) -> Entity:
    entity = store_mod.create_entity(case_id, body)
    if entity is None:
        raise HTTPException(404, f"Case {case_id} not found")
    return entity


@app.post("/api/cases/{case_id}/resolve-entities")
def resolve_case_entities(case_id: str) -> dict:
    result = store_mod.resolve_entities_for_case(case_id)
    if result is None:
        raise HTTPException(404, f"Case {case_id} not found")
    return {"status": "ok", **result}


@app.get("/api/entities/{entity_id}", response_model=EntityDetail)
def get_entity(entity_id: str) -> EntityDetail:
    detail = store_mod.get_entity(entity_id)
    if not detail:
        raise HTTPException(404, f"Entity {entity_id} not found")
    return detail


@app.post("/api/transactions/{txn_id}/entity-links")
def link_transaction_entity(txn_id: str, body: EntityLinkRequest) -> dict:
    result = store_mod.link_transaction_to_entity(txn_id, body.entity_id, body.role)
    if result is None:
        raise HTTPException(404, f"Transaction {txn_id} or entity {body.entity_id} not found")
    return {"status": "linked", "transaction_id": txn_id, "entity_id": body.entity_id}


@app.delete("/api/transactions/{txn_id}/entity-links/{entity_id}")
def unlink_transaction_entity(txn_id: str, entity_id: str) -> dict:
    result = store_mod.unlink_transaction_from_entity(txn_id, entity_id)
    if result is None or result is False:
        raise HTTPException(404, f"Link (transaction={txn_id}, entity={entity_id}) not found")
    return {"status": "unlinked"}


@app.get("/api/transactions/{txn_id}/entities", response_model=list[Entity])
def list_transaction_entities(txn_id: str) -> list[Entity]:
    ents = store_mod.list_entities_for_transaction(txn_id)
    if ents is None:
        raise HTTPException(404, f"Transaction {txn_id} not found")
    return ents


@app.post("/api/cases/{case_id}/run-patterns")
def run_patterns(case_id: str) -> dict:
    """Run all forensic detectors over the case and persist flags."""
    result = store_mod.run_patterns_for_case(case_id)
    if result is None:
        raise HTTPException(404, f"Case {case_id} not found")
    return {"status": "ok", "flags_added": result}


@app.post("/api/dev/reset")
def dev_reset() -> dict:
    """Drop all tables and re-seed from benchmark output. Dev only."""
    store_mod.init_and_seed(reset=True)
    return {"status": "reset+seeded", **store_mod.counts()}
