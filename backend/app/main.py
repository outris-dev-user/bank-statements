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
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pdfplumber
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import store as store_mod
from app import extraction_log
from app import llm as llm_mod
from app.auth import api_key_middleware, require_api_key
from app.schemas import (
    Case, CaseDetail, Person, Transaction, TransactionPage, TransactionPatch,
    Statement, CaseSummary, Entity, EntityDetail, EntityCreate, EntityLinkRequest,
    CaseGraph,
)

# Import the bank parser from plugins/bank (separate tree, no coupling)
REPO = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO))
from plugins.bank.extraction.parser import parse_text, detect_bank  # noqa: E402
from app.entity_inference import (  # noqa: E402
    infer_counterparty, infer_channel, infer_category, iso_date,
)


app = FastAPI(
    title="LedgerFlow",
    version="0.2.0",
    description="Forensic bank-statement analysis backend.",
)

def _allowed_origins() -> list[str]:
    """Read ALLOWED_ORIGINS env var (comma-separated). Each origin is
    normalised: trailing slashes stripped, surrounding whitespace removed,
    empty entries dropped. Falls back to the local dev vite + preview ports.

    Browsers send the `Origin` header *without* a trailing slash, so a
    stored origin like `https://foo.up.railway.app/` would never match —
    we strip the slash to make paste-errors harmless.
    """
    raw = os.environ.get("ALLOWED_ORIGINS")
    if not raw:
        return ["http://localhost:5173", "http://localhost:4173"]
    return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]


# Explicit header list — `*` is ambiguous under `allow_credentials=True` in
# some CORS implementations, and the frontend only needs these two.
_CORS_HEADERS = ["Content-Type", "X-API-Key", "X-Submitter", "Authorization"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    # We authenticate via the X-API-Key header, not cookies. Disabling
    # credentials avoids the extra constraints browsers put on CORS when
    # credentials mode is on (wildcard origins disallowed, stricter header
    # echoing, etc.).
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=_CORS_HEADERS,
    expose_headers=["Content-Disposition"],  # so admin PDF download can expose filename
)

# API-key enforcement. Active only when LEDGERFLOW_API_KEY is set in env.
# Declared AFTER CORS so the CORS middleware runs first on each request and
# can answer preflight even if the key is missing.
app.middleware("http")(api_key_middleware)


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
    # Metro / tier-1 cities
    r"|NAGAR|MUMBAI|DELHI|BANGALORE|BENGALURU|CHENNAI|KOLKATA|HYDERABAD|PUNE"
    r"|THANE|GURGAON|GURUGRAM|NOIDA|GHAZIABAD|FARIDABAD"
    # Other major cities frequently seen on statements
    r"|CHANDIGARH|AHMEDABAD|SURAT|VADODARA|JAIPUR|JODHPUR|UDAIPUR|KOTA"
    r"|LUCKNOW|KANPUR|AGRA|VARANASI|ALLAHABAD|PRAYAGRAJ|MEERUT|BAREILLY"
    r"|NAGPUR|NASIK|NASHIK|AURANGABAD|SOLAPUR|KOLHAPUR"
    r"|INDORE|BHOPAL|JABALPUR|GWALIOR"
    r"|PATNA|GAYA|MUZAFFARPUR"
    r"|RANCHI|JAMSHEDPUR|DHANBAD|BOKARO"
    r"|RAIPUR|BILASPUR"
    r"|BHUBANESWAR|CUTTACK|ROURKELA"
    r"|GUWAHATI|DIBRUGARH|SILCHAR"
    r"|COIMBATORE|MADURAI|TIRUCHIRAPPALLI|TRICHY|SALEM|TIRUNELVELI"
    r"|MYSORE|MYSURU|MANGALORE|MANGALURU|HUBLI|HUBBALLI|BELGAUM|BELAGAVI"
    r"|VISAKHAPATNAM|VIZAG|VIJAYAWADA|GUNTUR|TIRUPATI"
    r"|KOCHI|COCHIN|ERNAKULAM|THIRUVANANTHAPURAM|TRIVANDRUM|KOZHIKODE|CALICUT"
    r"|AMRITSAR|LUDHIANA|JALANDHAR|PATIALA|BATHINDA|MOHALI"
    r"|JAMMU|SRINAGAR|LEH"
    r"|SHIMLA|DHARAMSHALA|MANALI"
    r"|DEHRADUN|HARIDWAR|RISHIKESH|NAINITAL"
    r"|PANAJI|MARGAO|VASCO"
    r"|PUDUCHERRY|PONDICHERRY"
    r"|DARJEELING|SILIGURI|ASANSOL|DURGAPUR|HOWRAH"
    r"|SHILLONG|IMPHAL|AIZAWL|KOHIMA|ITANAGAR|AGARTALA"
    # States and UTs (full words and common abbreviations)
    r"|MAHARASHTRA|KARNATAKA|GUJARAT|RAJASTHAN|PUNJAB|HARYANA|ORISSA|ODISHA"
    r"|BIHAR|JHARKHAND|CHHATTISGARH|TELANGANA|UTTARAKHAND|KERALA|GOA|SIKKIM"
    r"|ASSAM|MEGHALAYA|MANIPUR|MIZORAM|NAGALAND|TRIPURA|MADHYA|PRADESH"
    r"|TAMIL|WEST|BENGAL|ANDHRA|HIMACHAL|UTTAR|JAMMU|KASHMIR|LADAKH"
    # Email/URL fragments and meta-tokens
    r"|GMAIL|YAHOO|HOTMAIL|OUTLOOK|COM|WWW|HTTP"
    r"|JOINT|HOLDERS?|NOMINEE|CHEQUE|REF|SUMMARY|OPERATIVE|TYPE|NUMBER|CENTER"
    # Notice/disclaimer text that appears in statement footers
    r"|IMPORTANT|MESSAGE|NOTICE|DISCLAIMER|SAFETY|TIPS|WARNING|ALERT|INFORMATION"
    # Localities / common suffixes
    r"|ANDHERI|VIKHROLI|POWAI|SAKI|VIHAR|BHILWARA|AJMER|GANDHI)\b",
    re.I,
)

# Parenthesised 2–3 letter uppercase codes like (UT), (PB), (HR), (MH), (KA)
# — always a state/UT code on an address line, never part of a name.
_LOCATION_CODE_RX = re.compile(r"\([A-Z]{2,3}\)")

# Indian postal codes (6 digits, often on the line above or below city).
# A line containing one is almost never a person name.
_POSTAL_CODE_RX = re.compile(r"\b\d{6}\b")

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
    # Parenthesised 2–3 letter codes — state/UT abbreviations like (UT), (PB).
    # Only ever appears on address lines.
    if _LOCATION_CODE_RX.search(line):
        return False
    # 6-digit postal codes: definitely an address line.
    if _POSTAL_CODE_RX.search(line):
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
    request: Request,
    case_id: str,
    file: UploadFile = File(...),
    person_id: str = Form(...),
    bank: str | None = Form(default=None),
    account_type: str | None = Form(default=None),
    account_number: str | None = Form(default=None),
    holder_name: str | None = Form(default=None),
    password: str | None = Form(default=None),
) -> dict:
    """Upload a PDF, run the full extraction pipeline (deterministic +
    dual-LLM when enabled), and ingest the result into the case store.
    Goes through the same `_run_extraction` helper as `/api/extract`, so
    every upload from the frontend is recorded in `extraction_log` and
    both LLMs fire when `LLM_ENABLED=1`."""
    if not file.filename:
        raise HTTPException(400, "Missing file")

    content = await file.read()

    # Keep a per-case copy on the local upload dir so `/api/statements/{id}/pdf`
    # streaming keeps working. The extraction pipeline also writes a
    # content-addressed archive into the PDF store — that's the long-term copy.
    safe_name = re.sub(r"[^A-Za-z0-9._\-]", "_", file.filename)
    dest = UPLOAD_DIR / f"{case_id}_{int(datetime.utcnow().timestamp())}_{safe_name}"
    dest.write_bytes(content)

    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    try:
        _eid, response, _text = await _run_extraction(
            content=content,
            filename=file.filename,
            content_type=file.content_type,
            password=password,
            submitter=f"case:{case_id}",
            client_ip=client_ip,
            user_agent=user_agent,
        )
    except ExtractionError as e:
        raise HTTPException(e.status, _err(e.code, e.message, e.extra))

    shaped_txns = response.get("transactions") or []
    if not shaped_txns:
        bank_key_ui = (response.get("bank") or {}).get("key") or "unknown"
        raise HTTPException(
            400,
            f"No transactions extracted (bank={bank_key_ui}). "
            f"Try a different file or manual account setup.",
        )

    resp_bank = response.get("bank") or {}
    resp_account = response.get("account") or {}
    resp_period = response.get("period") or {}
    resp_balance = response.get("balance") or {}

    bank_key = resp_bank.get("key") or "unknown"
    bank_label = bank or resp_bank.get("label") or BANK_DEFAULTS["unknown"]["display"]
    acc_type = account_type or resp_bank.get("account_type") or BANK_DEFAULTS["unknown"]["account_type"]
    acc_num = account_number or resp_account.get("number_masked") or "****????"
    resolved_holder = holder_name or resp_account.get("holder_name") or "Unknown"

    # ingest_statement expects `{date, description, amount, type}` where
    # `type` ∈ {"Dr", "Cr"}. The shared pipeline returns the public shape
    # with `direction` ∈ {"debit", "credit"} — map back here so the case
    # store keeps its existing contract.
    def _to_dr_cr(v: str | None) -> str:
        if v in ("Dr", "Cr"):
            return v
        return "Dr" if v == "debit" else "Cr"

    parser_txns = [
        {
            "date": t.get("date"),
            "description": t.get("description"),
            "amount": t.get("amount"),
            "type": _to_dr_cr(t.get("direction") or t.get("type")),
        }
        for t in shaped_txns
    ]

    result = store_mod.ingest_statement(
        case_id=case_id, person_id=person_id,
        source_file_name=file.filename,
        source_file_path=str(dest),
        bank=bank_label, account_type=acc_type,
        account_number=acc_num,
        holder_name=resolved_holder,
        period_start=resp_period.get("start") or "",
        period_end=resp_period.get("end") or "",
        opening_balance=resp_balance.get("opening") or 0.0,
        closing_balance=resp_balance.get("closing") or 0.0,
        declared_dr=None, declared_cr=None,
        parser_txns=parser_txns,
        uploaded_by="unknown",
    )
    if result is None:
        raise HTTPException(404, f"Case or person not found (case_id={case_id}, person_id={person_id})")
    statement, txns = result
    return {
        "bank_detected": bank_key,
        "extraction_source": (response.get("meta") or {}).get("source"),
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


_OPENING_BALANCE_RX = [
    re.compile(r"Opening\s*Balance[^\d-]{0,20}(-?[\d,]+\.\d{2})", re.I),
    re.compile(r"OpeningBalance[^\d-]{0,20}(-?[\d,]+\.\d{2})", re.I),
    re.compile(r"B/F\s*Balance[^\d-]{0,20}(-?[\d,]+\.\d{2})", re.I),
]
_CLOSING_BALANCE_RX = [
    re.compile(r"Closing\s*Balance[^\d-]{0,20}(-?[\d,]+\.\d{2})", re.I),
    re.compile(r"ClosingBalance[^\d-]{0,20}(-?[\d,]+\.\d{2})", re.I),
]


def _parse_amount(raw: str) -> float | None:
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def _guess_balances(text: str) -> tuple[float | None, float | None]:
    opening = closing = None
    for rx in _OPENING_BALANCE_RX:
        m = rx.search(text)
        if m:
            opening = _parse_amount(m.group(1))
            break
    for rx in _CLOSING_BALANCE_RX:
        m = rx.search(text)
        if m:
            closing = _parse_amount(m.group(1))
            break
    return opening, closing


# Chunks that the UPI/NEFT/IMPS narrations put before the merchant name —
# safe to strip when they appear as leading tokens, so the first useful token
# is actually the merchant.
_NARRATION_NOISE = re.compile(
    r"^(?:DR|CR|TO|FROM|P2A|P2M|P2P|PAY|PAYMENT|TRF|TRANSFER|INB|REV|IMPS|NEFT|RTGS|UPI|POS|ATM)$",
    re.I,
)


def _counterparty_from_description(desc: str, channel: str) -> str:
    """More forgiving counterparty extractor than `infer_counterparty`.

    Strategy: strip the channel prefix, split on /, drop leading tokens that
    are direction markers, numbers, or common noise words; the first remaining
    token with at least 3 letters is the merchant. Falls back to the shared
    heuristic if nothing survives.
    """
    text = desc.strip()
    # Drop the leading channel prefix (UPI/ NEFT/ IMPS/ etc).
    text = re.sub(r"^(UPI|NEFT|IMPS|RTGS|POS|ATM|ECS|NACH|CHQ|CHEQUE)[\s\-/:]*", "", text, flags=re.I)
    parts = [p.strip() for p in re.split(r"[/|]", text) if p.strip()]
    for part in parts:
        # Skip tokens that are pure digits, direction markers, or noise.
        if _NARRATION_NOISE.match(part):
            continue
        letters = sum(1 for c in part if c.isalpha())
        digits = sum(1 for c in part if c.isdigit())
        if letters < 3:
            continue
        if digits > letters:  # looks like a ref number
            continue
        # Trim trailing ref/serial chunks on this token itself.
        cleaned = re.sub(r"[-\s]+\d{6,}.*$", "", part).strip()
        return cleaned[:80] or part[:80]
    # Fallback: the shared inference.
    fallback = infer_counterparty(desc, channel)
    return fallback if fallback != "(unknown)" else (desc[:60] or "(unknown)")


def _shape_transaction(raw: dict) -> dict:
    desc = raw.get("description", "")
    channel = infer_channel(desc)
    direction = "debit" if raw.get("type") == "Dr" else "credit"
    return {
        "date": iso_date(raw.get("date", "")),
        "amount": raw.get("amount"),
        "direction": direction,
        "description": desc,
        "counterparty": _counterparty_from_description(desc, channel),
        "channel": channel,
        "category": infer_category(desc),
        "balance_after": raw.get("balance"),  # only populated by hdfc_savings today
    }


MAX_EXTRACT_BYTES = 25 * 1024 * 1024  # 25 MB — bank statements are small; guard against mis-uploads.
ALLOWED_PDF_MIMES = {"application/pdf", "application/octet-stream", "binary/octet-stream", ""}


def _err(code: str, message: str, extra: dict | None = None) -> dict:
    """Consistent error envelope. FastAPI wraps this in `{"detail": ...}`."""
    body: dict = {"error_code": code, "message": message}
    if extra:
        body["extra"] = extra
    return body


class ExtractionError(Exception):
    """Raised by `_run_extraction` for any validation / parse failure that
    should surface to the caller as an HTTP error. Carries the fields the
    `/api/extract` error envelope expects so either caller can re-raise it
    as an HTTPException cleanly."""
    def __init__(self, status: int, code: str, message: str, extra: dict | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.extra = extra or {}


async def _run_extraction(
    *,
    content: bytes,
    filename: str,
    content_type: str | None,
    password: str | None,
    submitter: str | None,
    client_ip: str | None,
    user_agent: str | None,
) -> tuple[str, dict, str]:
    """Core PDF→structured-JSON pipeline shared by `/api/extract` and the
    frontend upload endpoint. Archives the PDF, runs pdfplumber + the
    deterministic parser, dual-runs Claude + Gemini (when enabled), and
    records every step to `extraction_log` / `extraction_trace` /
    `llm_attempts`. Returns `(extraction_id, response_dict, pdfplumber_text)`.
    Raises `ExtractionError` on any validation / read failure — the finally
    block still records the row so failed uploads are visible in the log."""
    extraction_id = extraction_log.new_extraction_id()
    log_ctx: dict = {
        "extraction_id": extraction_id,
        "filename": filename or "",
        "file_size": len(content),
        "file_hash": None,
        "pdf_stored_path": None,
        "was_password_protected": bool(password),
        "http_status": 200,
        "success": False,
        "response": None,
        "error_code": None,
        "submitter_label": submitter,
        "client_ip": client_ip,
        "user_agent": user_agent,
    }

    def _raise(status: int, code: str, message: str, extra: dict | None = None):
        log_ctx["http_status"] = status
        log_ctx["error_code"] = code
        raise ExtractionError(status, code, message, extra)

    try:
        # ── validation ────────────────────────────────────────────────────
        if not filename:
            _raise(400, "MISSING_FILE", "No file was uploaded.")

        fname = filename
        if not fname.lower().endswith(".pdf"):
            _raise(415, "INVALID_FILE_TYPE",
                   "Only PDF files are supported.",
                   {"filename": fname, "expected_extension": ".pdf"})

        if content_type and content_type.lower() not in ALLOWED_PDF_MIMES:
            _raise(415, "INVALID_FILE_TYPE",
                   "Expected application/pdf.",
                   {"received_content_type": content_type})

        if len(content) == 0:
            _raise(400, "EMPTY_FILE", "Uploaded file is empty (0 bytes).")

        if len(content) > MAX_EXTRACT_BYTES:
            _raise(413, "FILE_TOO_LARGE",
                   f"File exceeds the {MAX_EXTRACT_BYTES // (1024*1024)} MB limit.",
                   {"size_bytes": len(content), "max_bytes": MAX_EXTRACT_BYTES})

        if not content.startswith(b"%PDF-"):
            _raise(415, "INVALID_PDF_SIGNATURE",
                   "File does not start with %PDF- — it is not a valid PDF.",
                   {"first_bytes_hex": content[:8].hex()})

        # ── archive the PDF bytes (content-addressed) ─────────────────────
        try:
            fh, rel_path = extraction_log.store_pdf_bytes(content)
            log_ctx["file_hash"] = fh
            log_ctx["pdf_stored_path"] = rel_path
        except Exception as exc:
            # Never fail the extraction just because the archive write failed.
            print(f"[extract] PDF archive failed: {exc!r}")

        tmp = UPLOAD_DIR / f"_extract_{int(datetime.utcnow().timestamp())}_{re.sub(r'[^A-Za-z0-9._-]', '_', fname)}"
        tmp.write_bytes(content)
        try:
            # ── open with pdfplumber ─────────────────────────────────────
            try:
                with pdfplumber.open(tmp, password=password or "") as pdf:
                    page_count = len(pdf.pages)
                    text = "\n".join((p.extract_text() or "") for p in pdf.pages)
            except Exception as exc:
                msg = str(exc).lower()
                if "password" in msg or "encrypt" in msg:
                    code = "PDF_PASSWORD_INCORRECT" if password else "PDF_PASSWORD_REQUIRED"
                    hint = (
                        "Incorrect password for the encrypted PDF."
                        if password else
                        "PDF is password-protected. Provide the correct `password` form field."
                    )
                    _raise(401, code, hint)
                _raise(422, "PDF_UNREADABLE",
                       "Could not read the PDF — file may be corrupted or malformed.",
                       {"underlying_error": str(exc)[:200]})

            bank_key = detect_bank(text)
            defaults = BANK_DEFAULTS.get(bank_key, BANK_DEFAULTS["unknown"])

            # ── scanned / image PDF branch ───────────────────────────────
            if not text.strip():
                response = {
                    "bank": {"key": "unknown", "label": "Unknown", "account_type": None},
                    "account": {"number_masked": None, "holder_name": None},
                    "period": {"start": None, "end": None},
                    "balance": {"opening": None, "closing": None, "currency": "INR"},
                    "summary": {
                        "transaction_count": 0, "total_debit": 0.0,
                        "total_credit": 0.0, "net_change": 0.0,
                    },
                    "transactions": [],
                    "meta": {
                        "filename": fname,
                        "page_count": page_count,
                        "parser": None,
                        "text_empty": True,
                        "issues": ["scanned_pdf_no_text_layer"],
                        "source": "pdfplumber",
                        "note": "pdfplumber returned no text — likely a scanned/image PDF. Send a text-layer PDF, or retry once the OCR fallback is enabled.",
                    },
                }
                # Record the empty-text trace so scan samples show up in the corpus.
                extraction_log.record_trace(
                    extraction_log_id=extraction_id,
                    pdfplumber_text=text,
                    deterministic_raw=[],
                    bank_detected=bank_key,
                )
                log_ctx["success"] = True
                log_ctx["response"] = response
                return extraction_id, response, text

            # ── deterministic parse ──────────────────────────────────────
            raw_txns = parse_text(text)
            shaped = [_shape_transaction(t) for t in raw_txns]

            period_start, period_end = _guess_period(text)
            if not period_start or not period_end:
                txn_start, txn_end = _period_from_txns(raw_txns)
                period_start = period_start or txn_start
                period_end = period_end or txn_end

            opening, closing = _guess_balances(text)

            det_total_debit = sum(t["amount"] or 0.0 for t in shaped if t["direction"] == "debit")
            det_total_credit = sum(t["amount"] or 0.0 for t in shaped if t["direction"] == "credit")

            # Snapshot pdfplumber text + deterministic raw parse before LLM work.
            extraction_log.record_trace(
                extraction_log_id=extraction_id,
                pdfplumber_text=text,
                deterministic_raw=raw_txns,
                bank_detected=bank_key,
            )

            det_issues: list[str] = []
            if bank_key == "unknown":
                det_issues.append("unknown_bank_format")
            if not shaped:
                det_issues.append("zero_transactions_extracted")

            deterministic_response = {
                "bank": {
                    "key": bank_key,
                    "label": defaults["display"],
                    "account_type": defaults["account_type"],
                },
                "account": {
                    "number_masked": _guess_account_number(text),
                    "holder_name": _guess_holder_name(text),
                },
                "period": {"start": period_start, "end": period_end},
                "balance": {"opening": opening, "closing": closing, "currency": "INR"},
                "summary": {
                    "transaction_count": len(shaped),
                    "total_debit": round(det_total_debit, 2),
                    "total_credit": round(det_total_credit, 2),
                    "net_change": round(det_total_credit - det_total_debit, 2),
                },
                "transactions": shaped,
                "meta": {
                    "filename": fname,
                    "page_count": page_count,
                    "parser": bank_key if bank_key != "unknown" else None,
                    "text_empty": False,
                    "issues": det_issues,
                    "source": "deterministic",
                },
            }

            # ── dual-provider LLM extraction (test phase: always run) ────
            # Fires for every non-empty-text request, regardless of whether
            # the deterministic parser succeeded. Every attempt is recorded
            # so we can compare Claude vs Gemini vs deterministic later.
            llm_responses: dict[str, dict] = {}
            if llm_mod.llm_enabled():
                try:
                    dual = await llm_mod.run_dual(text, bank_hint=bank_key)
                except Exception as exc:
                    print(f"[extract] run_dual raised: {exc!r}")
                    dual = {}
                for provider, llm_result in dual.items():
                    extraction_log.record_llm_attempt(
                        extraction_log_id=extraction_id,
                        provider=llm_result.provider,
                        model=llm_result.model,
                        prompt_text=llm_result.prompt_text,
                        raw_response=llm_result.raw_response,
                        parsed_json=llm_result.parsed,
                        parse_error=llm_result.parse_error,
                        provider_error=llm_result.error,
                        prompt_tokens=llm_result.prompt_tokens,
                        completion_tokens=llm_result.completion_tokens,
                        latency_ms=llm_result.latency_ms,
                    )
                    if llm_result.parsed:
                        llm_responses[provider] = llm_mod.normalise_llm_response(
                            llm_result.parsed, source_filename=fname,
                        )

            # ── choose what to return the caller ─────────────────────────
            # Priority: deterministic (if it found txns) > Claude > Gemini.
            # Deterministic is preferred because it's auditable and free; LLMs
            # are the fallback for banks we haven't written a parser for.
            if shaped:
                response = deterministic_response
            elif llm_responses.get("claude"):
                response = llm_responses["claude"]
                response["meta"]["source"] = "llm-claude"
                response["meta"]["deterministic_parser"] = bank_key
                response["meta"]["page_count"] = page_count
            elif llm_responses.get("gemini"):
                response = llm_responses["gemini"]
                response["meta"]["source"] = "llm-gemini"
                response["meta"]["deterministic_parser"] = bank_key
                response["meta"]["page_count"] = page_count
            else:
                response = deterministic_response  # zero-txn, but still shaped

            log_ctx["success"] = True
            log_ctx["response"] = response
            return extraction_id, response, text
        finally:
            try:
                tmp.unlink()
            except Exception:
                pass
    finally:
        # Always record — validation reject, password error, unreadable, or
        # success. Gives us the full picture of what users are sending us.
        extraction_log.record(
            extraction_id=log_ctx["extraction_id"],
            filename=log_ctx["filename"],
            file_size=log_ctx["file_size"],
            file_hash=log_ctx["file_hash"],
            pdf_stored_path=log_ctx["pdf_stored_path"],
            was_password_protected=log_ctx["was_password_protected"],
            http_status=log_ctx["http_status"],
            success=log_ctx["success"],
            response=log_ctx["response"],
            error_code=log_ctx["error_code"],
            submitter_label=log_ctx["submitter_label"],
            client_ip=log_ctx["client_ip"],
            user_agent=log_ctx["user_agent"],
        )


@app.post("/api/extract")
async def extract_statement(
    request: Request,
    file: UploadFile = File(...),
    password: str | None = Form(default=None),
    submitted_by: str | None = Form(default=None),
) -> dict:
    """Standalone PDF → structured bank-statement extraction.

    Input  : multipart `file` (required, PDF, ≤25 MB), `password` (optional),
             `submitted_by` (optional free-text tag — e.g. "rahul-cousin" —
             persisted in the extraction log so we can triage later uploads).
             You can also send the tag as the `X-Submitter` header.
    Output : `{bank, account, period, balance, summary, transactions, meta}`.

    Every call is recorded in the `extraction_log` table regardless of
    success, and every valid PDF is archived by content hash in the PDF store.
    See api_reference_bank_statement.md for the full contract.
    """
    submitter = (submitted_by or request.headers.get("x-submitter") or "").strip() or None
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    content = await file.read()
    try:
        _eid, response, _text = await _run_extraction(
            content=content,
            filename=file.filename or "",
            content_type=file.content_type,
            password=password,
            submitter=submitter,
            client_ip=client_ip,
            user_agent=user_agent,
        )
    except ExtractionError as e:
        raise HTTPException(e.status, _err(e.code, e.message, e.extra))
    return response


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


# ───── admin: browse the extraction log ─────

@app.get("/api/admin/extractions")
def list_extractions(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    success: bool | None = Query(default=None),
    bank: str | None = Query(default=None),
    submitter: str | None = Query(default=None),
) -> dict:
    """Browse every /api/extract call we've logged. Filterable by success,
    bank key, and submitter label. Includes pagination. The full response
    JSON is excluded from the list view — fetch a single row for that.
    """
    from app.db import ExtractionLogRow, get_session
    with get_session() as s:
        q = s.query(ExtractionLogRow)
        if success is not None:
            q = q.filter(ExtractionLogRow.success == success)
        if bank:
            q = q.filter(ExtractionLogRow.bank_key_detected == bank)
        if submitter:
            q = q.filter(ExtractionLogRow.submitter_label == submitter)
        total = q.count()
        rows = (
            q.order_by(ExtractionLogRow.received_at.desc())
            .offset(offset).limit(limit).all()
        )
        items = [
            {
                "id": r.id,
                "received_at": r.received_at,
                "filename": r.filename,
                "file_size": r.file_size,
                "file_hash": r.file_hash,
                "was_password_protected": r.was_password_protected,
                "bank_key_detected": r.bank_key_detected,
                "page_count": r.page_count,
                "transaction_count": r.transaction_count,
                "issues": json.loads(r.issues_json or "[]"),
                "success": r.success,
                "http_status": r.http_status,
                "error_code": r.error_code,
                "submitter_label": r.submitter_label,
                "client_ip": r.client_ip,
            }
            for r in rows
        ]
        return {"total": total, "offset": offset, "limit": limit, "items": items}


@app.get("/api/admin/extractions/{extraction_id}")
def get_extraction(extraction_id: str) -> dict:
    """Full detail — includes the response JSON we returned to the caller."""
    from app.db import ExtractionLogRow, get_session
    with get_session() as s:
        r = s.get(ExtractionLogRow, extraction_id)
        if not r:
            raise HTTPException(404, f"Extraction {extraction_id} not found")
        return {
            "id": r.id,
            "received_at": r.received_at,
            "filename": r.filename,
            "file_size": r.file_size,
            "file_hash": r.file_hash,
            "pdf_stored_path": r.pdf_stored_path,
            "was_password_protected": r.was_password_protected,
            "bank_key_detected": r.bank_key_detected,
            "page_count": r.page_count,
            "transaction_count": r.transaction_count,
            "issues": json.loads(r.issues_json or "[]"),
            "success": r.success,
            "http_status": r.http_status,
            "error_code": r.error_code,
            "response": json.loads(r.response_json) if r.response_json else None,
            "submitter_label": r.submitter_label,
            "client_ip": r.client_ip,
            "user_agent": r.user_agent,
        }


@app.get("/api/admin/extractions/{extraction_id}/pdf")
def download_extraction_pdf(extraction_id: str):
    """Stream the archived PDF. 404 if we never stored it (e.g. rejected at
    validation for non-PDF signature)."""
    from app.db import ExtractionLogRow, get_session
    with get_session() as s:
        r = s.get(ExtractionLogRow, extraction_id)
        if not r:
            raise HTTPException(404, f"Extraction {extraction_id} not found")
        if not r.pdf_stored_path:
            raise HTTPException(404, "No PDF was archived for this extraction (validation rejected before archive).")
        path = extraction_log.resolve_pdf_path(r.pdf_stored_path)
        if not path.exists():
            raise HTTPException(410, "PDF was logged but is no longer on disk.")
        return FileResponse(
            str(path),
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{r.filename}"'},
        )


@app.get("/api/admin/extractions/{extraction_id}/trace")
def get_extraction_trace(extraction_id: str) -> dict:
    """Return the heavy diagnostic blobs we stashed during this extraction —
    raw pdfplumber text and the deterministic parser's raw output (before
    it was shaped into the wire format)."""
    from app.db import ExtractionTraceRow, get_session
    with get_session() as s:
        row = (
            s.query(ExtractionTraceRow)
            .filter(ExtractionTraceRow.extraction_log_id == extraction_id)
            .order_by(ExtractionTraceRow.created_at.desc())
            .first()
        )
        if not row:
            raise HTTPException(404, f"No trace recorded for extraction {extraction_id}")
        return {
            "id": row.id,
            "extraction_log_id": row.extraction_log_id,
            "bank_detected": row.bank_detected,
            "text_char_count": row.text_char_count,
            "pdfplumber_text": row.pdfplumber_text,
            "deterministic_raw": json.loads(row.deterministic_raw_json) if row.deterministic_raw_json else None,
            "created_at": row.created_at,
        }


@app.get("/api/admin/extractions/{extraction_id}/llm-attempts")
def get_extraction_llm_attempts(extraction_id: str) -> dict:
    """Return every LLM provider call made for this extraction. One row per
    provider per request — so 2 rows in dual-provider mode (Claude + Gemini).

    `agreement` summarises how the providers compare on txn count, bank key,
    and holder name — useful for spotting divergence at a glance.
    """
    from app.db import LLMAttemptRow, get_session
    with get_session() as s:
        rows = (
            s.query(LLMAttemptRow)
            .filter(LLMAttemptRow.extraction_log_id == extraction_id)
            .order_by(LLMAttemptRow.created_at.asc())
            .all()
        )
        attempts = [
            {
                "id": r.id,
                "provider": r.provider,
                "model": r.model,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "latency_ms": r.latency_ms,
                "provider_error": r.provider_error,
                "parse_error": r.parse_error,
                "extracted_txn_count": r.extracted_txn_count,
                "extracted_bank_key": r.extracted_bank_key,
                "extracted_holder_name": r.extracted_holder_name,
                "confidence": r.confidence,
                "prompt_text": r.prompt_text,
                "raw_response": r.raw_response,
                "parsed_json": json.loads(r.parsed_json) if r.parsed_json else None,
                "created_at": r.created_at,
            }
            for r in rows
        ]
        by_provider = {a["provider"]: a for a in attempts}
        claude = by_provider.get("claude") or {}
        gemini = by_provider.get("gemini") or {}
        agreement = {
            "txn_count_match": (
                claude.get("extracted_txn_count") is not None
                and claude.get("extracted_txn_count") == gemini.get("extracted_txn_count")
            ),
            "bank_key_match": (
                claude.get("extracted_bank_key") is not None
                and claude.get("extracted_bank_key") == gemini.get("extracted_bank_key")
            ),
            "holder_name_match": (
                claude.get("extracted_holder_name") is not None
                and claude.get("extracted_holder_name") == gemini.get("extracted_holder_name")
            ),
        }
        return {
            "extraction_log_id": extraction_id,
            "attempts": attempts,
            "agreement": agreement,
        }


@app.get("/api/admin/llm-attempts")
def list_llm_attempts(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    provider: str | None = Query(default=None),
    bank: str | None = Query(default=None),
    has_error: bool | None = Query(default=None),
) -> dict:
    """Browse every LLM call we've ever made. Use for cross-cutting analysis:
    cost trends, latency distributions, failure rates, per-bank accuracy."""
    from app.db import LLMAttemptRow, get_session
    with get_session() as s:
        q = s.query(LLMAttemptRow)
        if provider:
            q = q.filter(LLMAttemptRow.provider == provider)
        if bank:
            q = q.filter(LLMAttemptRow.extracted_bank_key == bank)
        if has_error is True:
            q = q.filter(
                (LLMAttemptRow.provider_error.isnot(None))
                | (LLMAttemptRow.parse_error.isnot(None))
            )
        elif has_error is False:
            q = q.filter(
                LLMAttemptRow.provider_error.is_(None),
                LLMAttemptRow.parse_error.is_(None),
            )
        total = q.count()
        rows = (
            q.order_by(LLMAttemptRow.created_at.desc())
            .offset(offset).limit(limit).all()
        )
        # Do NOT include `prompt_text` / `raw_response` / `parsed_json` here
        # — keep the list view small. Fetch /api/admin/extractions/{id}/llm-attempts
        # for the full payload.
        items = [
            {
                "id": r.id,
                "extraction_log_id": r.extraction_log_id,
                "provider": r.provider,
                "model": r.model,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "latency_ms": r.latency_ms,
                "provider_error": r.provider_error,
                "parse_error": r.parse_error,
                "extracted_txn_count": r.extracted_txn_count,
                "extracted_bank_key": r.extracted_bank_key,
                "extracted_holder_name": r.extracted_holder_name,
                "confidence": r.confidence,
                "created_at": r.created_at,
            }
            for r in rows
        ]
        return {"total": total, "offset": offset, "limit": limit, "items": items}
