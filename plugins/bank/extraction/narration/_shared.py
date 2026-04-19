"""Shared primitives used by per-bank narration decoders.

Everything in this module is deliberately bank-agnostic: regexes match
fragments (card mask, VPA, IFSC, account number, bank code), helpers clean
and title-case merchant strings. Per-bank decoders compose these inside
their own envelope patterns.
"""
from __future__ import annotations
import re
from typing import Optional


# ---------------------------------------------------------------
# Regexes for fragments that appear inside many bank envelopes
# ---------------------------------------------------------------

# Masked card in narration: 490246XXXXXX2310 or 490246******2310
CARD_RE = re.compile(r"(?P<bin>\d{6})[X*]{4,8}(?P<last4>\d{4})")

# UPI VPA: user@handle (handle = bank/PSP)
VPA_RE = re.compile(r"(?P<local>[A-Za-z0-9._-]+)@(?P<handle>[A-Za-z]+)")

# IFSC: AAAA0<branch> (4 letter bank code + 0 + 6 alphanumeric)
IFSC_RE = re.compile(r"[A-Z]{4}0[A-Z0-9]{6}")

# Account number (10-18 digits, common for Indian savings/current)
ACCT_RE = re.compile(r"\b\d{10,18}\b")

# A reference number usually preceded by `-` or `/`, 9+ digits
REF_RE = re.compile(r"(?<![\d])\d{9,}(?![\d])")


# ---------------------------------------------------------------
# Bank code → human name
# (short codes banks splash into their narrations; 4-letter prefix
# of IFSC is authoritative, 3-5 letter MMT/IMPS short form covers the rest)
# ---------------------------------------------------------------

BANK_CODES = {
    # 4-letter IFSC prefixes (RBI official)
    "HDFC": "HDFC Bank",
    "ICIC": "ICICI Bank",
    "SBIN": "State Bank of India",
    "UTIB": "Axis Bank",
    "AXIS": "Axis Bank",
    "KKBK": "Kotak Mahindra Bank",
    "YESB": "YES Bank",
    "IDFB": "IDFC First Bank",
    "IDIB": "Indian Bank",
    "IOBA": "Indian Overseas Bank",
    "IBKL": "IDBI Bank",
    "BARB": "Bank of Baroda",
    "PUNB": "Punjab National Bank",
    "CNRB": "Canara Bank",
    "UBIN": "Union Bank of India",
    "CBIN": "Central Bank of India",
    "BKID": "Bank of India",
    "UCBA": "UCO Bank",
    "MAHB": "Bank of Maharashtra",
    "CITI": "Citibank",
    "HSBC": "HSBC",
    "SCBL": "Standard Chartered",
    "DEUT": "Deutsche Bank",
    "RATN": "RBL Bank",
    "FDRL": "Federal Bank",
    "SIBL": "South Indian Bank",
    "KARB": "Karnataka Bank",
    "INDB": "IndusInd Bank",
    # short forms seen in narrations
    "HDFCBANK": "HDFC Bank",
    "HDFCBAN":  "HDFC Bank",
    "SBI":      "State Bank of India",
    "PNB":      "Punjab National Bank",
}


_BANK_NAME_PREFIXES = [
    ("BANK OF BARODA",    "Bank of Baroda"),
    ("BANK OF BAR",       "Bank of Baroda"),
    ("BANK OF INDIA",     "Bank of India"),
    ("BANK OF MAHARASHTRA", "Bank of Maharashtra"),
    ("STATE BANK OF",     "State Bank of India"),
    ("PUNJAB NATIONAL",   "Punjab National Bank"),
    ("ICICI",             "ICICI Bank"),
    ("HDFC",              "HDFC Bank"),
    ("AXIS",              "Axis Bank"),
    ("KOTAK",             "Kotak Mahindra Bank"),
    ("YES BANK",          "YES Bank"),
    ("IDFC",              "IDFC First Bank"),
    ("INDUSIND",          "IndusInd Bank"),
    ("FEDERAL",           "Federal Bank"),
    ("CANARA",            "Canara Bank"),
    ("UNION BANK",        "Union Bank of India"),
    ("CENTRAL BANK",      "Central Bank of India"),
    ("UCO",               "UCO Bank"),
    ("INDIAN BANK",       "Indian Bank"),
    ("PAYTM",             "Paytm Payments Bank"),
    ("AIRTEL",            "Airtel Payments Bank"),
]


def identify_bank(token: str) -> Optional[str]:
    """Resolve a bank short-code / IFSC-prefix / name fragment to full name."""
    if not token:
        return None
    up = token.strip().upper()
    if up in BANK_CODES:
        return BANK_CODES[up]
    # IFSC: take first 4 chars
    m = IFSC_RE.search(up)
    if m:
        return BANK_CODES.get(m.group(0)[:4])
    # Bank-name prefix table (handles "BANK OF BAR…" truncations)
    for prefix, name in _BANK_NAME_PREFIXES:
        if up.startswith(prefix):
            return name
    # Longest short-code prefix match
    for k in sorted(BANK_CODES, key=len, reverse=True):
        if up.startswith(k):
            return BANK_CODES[k]
    return None


# ---------------------------------------------------------------
# Text cleanup
# ---------------------------------------------------------------

_NON_ALNUM = re.compile(r"[^A-Za-z0-9 &'-]")
_MULTI_SPACE = re.compile(r"\s{2,}")


def titlecase(s: Optional[str]) -> Optional[str]:
    """Canonical merchant-name presentation. Preserves short ALLCAPS acronyms."""
    if not s:
        return None
    s = _NON_ALNUM.sub(" ", s).strip()
    s = _MULTI_SPACE.sub(" ", s)
    out = []
    for tok in s.split():
        if len(tok) <= 4 and tok.isupper() and any(c.isalpha() for c in tok):
            out.append(tok)
        else:
            out.append(tok.capitalize())
    return " ".join(out) or None


def strip_tails(s: str, tails: tuple) -> str:
    up = s.upper().strip()
    for tail in tails:
        if up.endswith(tail):
            up = up[: -len(tail)].strip()
            break
    return up


def compact(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def card_last4(masked: str) -> Optional[str]:
    m = re.search(r"(\d{4})$", masked or "")
    return m.group(1) if m else None


# ---------------------------------------------------------------
# Standard result shape
# ---------------------------------------------------------------

def result(channel: str,
           merchant: Optional[str],
           location: Optional[str],
           card_last4: Optional[str],
           ref_number: Optional[str],
           matched_rule: str,
           counterparty_bank: Optional[str] = None) -> dict:
    return {
        "channel": channel,
        "merchant": merchant,
        "location": location,
        "card_last4": card_last4,
        "ref_number": ref_number,
        "counterparty_bank": counterparty_bank,
        "matched_rule": matched_rule,
    }


# ---------------------------------------------------------------
# Static patterns seen across many Indian banks
# ---------------------------------------------------------------

STATIC_EVENTS = {
    "TAXDEDUCTED":               ("tds",             "Income Tax Department"),
    "CREDITINTERESTCAPITALISED": ("interest_credit", "Savings Interest Credit"),
    "INTERESTCAPITALISED":       ("interest_credit", "Savings Interest Credit"),
    "SMSCHARGES":                ("bank_charge",     "SMS Charges"),
    "SMSCHGS":                   ("bank_charge",     "SMS Charges"),
    "AMCINCLGST":                ("bank_charge",     "AMC Fee"),
    "ATMCHG":                    ("bank_charge",     "ATM Charges"),
}


def match_static_event(compact_narr_up: str):
    """Return (channel, merchant) or None for universally-known events."""
    for key, val in STATIC_EVENTS.items():
        if compact_narr_up.startswith(key):
            return val
    return None
