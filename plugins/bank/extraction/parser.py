"""Bank statement parser.

Architecture: detect bank from text fingerprint → route to bank-specific
parser → emit StandardTransaction records {date, description, amount, type}.

Date is normalized to DD/MM/YYYY in the output. Amount is float.
Type is 'Dr' or 'Cr'.

Banks supported:
  hdfc_cc       — HDFC credit card (positional text, single line)
  idfc          — IDFC First Bank current account (multi-line)
  hdfc_savings  — HDFC Bank savings account (single amount column,
                  Dr/Cr inferred from balance change)
  icici         — ICICI Bank current account (table-based, Withdrawals +
                  Deposits columns explicit) — needs path to PDF, not text
  kotak         — Kotak Mahindra (3-line transactions, explicit DR/CR
                  suffix on amount)
"""
from __future__ import annotations
import re
from datetime import datetime
from typing import Callable, Dict, List, Optional


# ============================================================
# Bank detection
# ============================================================

def detect_bank(text: str) -> str:
    t = text.lower()
    if "hdfc bank credit cards" in t:
        return "hdfc_cc"
    if "idfc first bank" in t:
        return "idfc"
    if "withdrawalamt" in t or "narration chq./ref.no. valuedt" in t:
        return "hdfc_savings"
    if "withdrawals deposits autosweep" in t or ("particulars" in t and "autosweep" in t):
        return "icici"
    if "sl. no. date description chq" in t or "sl. no. date description" in t:
        return "kotak"
    return "unknown"


# ============================================================
# Helpers
# ============================================================

def clean_amount(raw: str) -> float:
    return float(raw.replace(",", "").strip())


def normalize_date(raw: str) -> str:
    """Normalize DD/MM/YYYY, DD/MM/YY, DD-MM-YYYY, DD MMM YY → DD/MM/YYYY."""
    raw = re.sub(r"\s+", " ", raw.strip())
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y", "%d %b %y", "%d %b %Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return raw


# ============================================================
# Parser: HDFC Credit Card
# ============================================================

HDFC_CC_LINE = re.compile(
    r"^(\d{2}/\d{2}/\d{4})(?:\s+\d{2}:\d{2}:\d{2})?\s+(.+?)\s+([\d,]+\.\d{2})\s*(Cr)?\s*$"
)
REWARD_TAIL = re.compile(r"\s+\d+\s*$")


def _parse_hdfc_cc(text: str) -> List[Dict]:
    out = []
    for line in text.split("\n"):
        m = HDFC_CC_LINE.match(line.strip())
        if not m:
            continue
        date, desc, amount, cr = m.groups()
        out.append({
            "date": normalize_date(date),
            "description": REWARD_TAIL.sub("", desc).strip(),
            "amount": clean_amount(amount),
            "type": "Cr" if cr else "Dr",
        })
    return out


# ============================================================
# Parser: IDFC current account (multi-line, two dates)
# ============================================================

IDFC_LINE = re.compile(
    r"^(\d{2}\s+\w{3}\s+\d{2})(?:\s+\d{2}:\d{2})?\s+(\d{2}\s+\w{3}\s+\d{2})\s+"
    r"(.*?)\s*([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s*(CR|DR)?\s*$"
)


def _nearest_text_line(lines, anchor, direction, max_skip=3):
    j = anchor + direction
    steps = 0
    while 0 <= j < len(lines) and steps < max_skip:
        cand = lines[j].strip()
        steps += 1
        if not cand:
            j += direction
            continue
        if re.match(r"^\s*\d{2}[/\s]", cand):
            return ""
        if re.match(r"^[\d,. ]+(CR|DR)?$", cand):
            j += direction
            continue
        return cand
    return ""


def _parse_idfc(text: str) -> List[Dict]:
    lines = text.split("\n")
    out = []
    for i, line in enumerate(lines):
        m = IDFC_LINE.match(line.strip())
        if not m:
            continue
        txn_date, _value_date, desc_inline, amount, _balance, _bal_cr = m.groups()
        prev_desc = _nearest_text_line(lines, i, -1)
        next_desc = _nearest_text_line(lines, i, +1)
        full_desc = " ".join(p for p in (prev_desc, desc_inline.strip(), next_desc) if p)
        if not full_desc:
            continue
        if re.search(r"/DR/", full_desc, re.I):
            dr_cr = "Dr"
        elif re.search(r"/CR/", full_desc, re.I):
            dr_cr = "Cr"
        else:
            continue
        out.append({
            "date": normalize_date(txn_date),
            "description": full_desc,
            "amount": clean_amount(amount),
            "type": dr_cr,
        })
    return out


# ============================================================
# Parser: HDFC Savings (single amount column, Dr/Cr from balance change)
# ============================================================

HDFC_SAV_LINE = re.compile(
    r"^(\d{2}/\d{2}/\d{2})\s+(.+?)\s+(\w{12,20})\s+(\d{2}/\d{2}/\d{2})\s+"
    r"(-?[\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s*$"
)


def _parse_hdfc_savings(text: str) -> List[Dict]:
    lines = text.split("\n")
    out = []
    # Seed prev_balance from the statement summary so the *first* transaction's
    # Dr/Cr can be inferred from a real balance change instead of a heuristic.
    prev_balance: Optional[float] = None
    summary_match = re.search(r"OpeningBalance.*?\n([\d,]+\.\d{2})", text, re.DOTALL)
    if summary_match:
        prev_balance = clean_amount(summary_match.group(1))
    for i, line in enumerate(lines):
        m = HDFC_SAV_LINE.match(line.strip())
        if not m:
            continue
        date, narration, _ref, _value_dt, amount_s, balance_s = m.groups()
        # HDFC prints negative amounts for reversed/rejected entries — these
        # are annotations, not real transactions, and aren't in the statement totals.
        if amount_s.startswith("-"):
            continue
        amount = clean_amount(amount_s)
        balance = clean_amount(balance_s)
        # Continuation of narration on next line(s) (lines that don't match a date line and aren't headers)
        cont_parts = []
        for j in range(i + 1, min(i + 3, len(lines))):
            cand = lines[j].strip()
            if not cand or HDFC_SAV_LINE.match(cand) or re.match(r"^\s*\d{2}/\d{2}/\d{2}", cand):
                break
            if re.search(r"PageNo|STATEMENTSUMMARY|Date Narration", cand):
                break
            cont_parts.append(cand)
        if cont_parts:
            narration = narration + " " + " ".join(cont_parts)
        # Determine Dr/Cr by balance change
        if prev_balance is None:
            # First transaction — guess based on heuristic: most descriptions include UPI-, NEFT-, ATM (debit) or SALSE/INTEREST/CREDIT (credit)
            dr_cr = "Cr" if re.search(r"\b(SALARY|SAL|CREDIT|INTEREST|REFUND|REVERSAL|DEPOSIT)\b", narration, re.I) else "Dr"
        else:
            diff = round(balance - prev_balance, 2)
            if abs(abs(diff) - amount) < 0.01:
                dr_cr = "Cr" if diff > 0 else "Dr"
            else:
                # Balance jump doesn't match the txn amount — likely a missed prior txn or rounding. Fall back to heuristic.
                dr_cr = "Cr" if re.search(r"\b(SALARY|SAL|CREDIT|INTEREST|REFUND|REVERSAL|DEPOSIT)\b", narration, re.I) else "Dr"
        prev_balance = balance
        out.append({
            "date": normalize_date(date),
            "description": narration.strip(),
            "amount": amount,
            "type": dr_cr,
            "balance": balance,
        })
    return out


# ============================================================
# Parser: ICICI (table-based)
# ============================================================

def _parse_icici_from_text(text: str) -> List[Dict]:
    """Fallback when only text is available — parses date-led lines.
    The ICICI text layout puts each transaction on a single line:
      DD-MM-YYYY <particulars> <chq> <withdrawal> <deposit> <bal> Cr
    Withdrawal=0.00 → it's a credit; Deposit=0.00 → debit.
    """
    out = []
    line_re = re.compile(
        r"^(\d{2}-\d{2}-\d{4})\s+(.+?)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+"
        r"([\d,]+\.\d{2})\s+(Cr|Dr)\s*$"
    )
    for line in text.split("\n"):
        m = line_re.match(line.strip())
        if not m:
            continue
        date, particulars, withdrawal, deposit, _bal, _bal_dc = m.groups()
        w = clean_amount(withdrawal)
        d = clean_amount(deposit)
        if w > 0 and d == 0:
            amount, dr_cr = w, "Dr"
        elif d > 0 and w == 0:
            amount, dr_cr = d, "Cr"
        else:
            continue  # B/F or balance-only row
        out.append({
            "date": normalize_date(date),
            "description": particulars.strip(),
            "amount": amount,
            "type": dr_cr,
        })
    return out


# ============================================================
# Parser: Kotak (3-line block)
# ============================================================

KOTAK_AMOUNT_LINE = re.compile(
    r"^(.+?)(?:\s+(\S+))?\s+([\d,]+\.\d{2})\s+(DR|CR)\s+([\d,]+\.\d{2})\s+(DR|CR)\s*$"
)
KOTAK_SL_DATE = re.compile(r"^(\d+)\s+(\d{2}/\d{2}/\d{4})\s*$")


def _parse_kotak(text: str) -> List[Dict]:
    lines = text.split("\n")
    out = []
    for i, line in enumerate(lines):
        m = KOTAK_AMOUNT_LINE.match(line.strip())
        if not m:
            continue
        desc1, _ref, amount_s, dr_cr, _balance, _bal_dc = m.groups()
        # Next line should be `<sl> <date>`
        if i + 1 >= len(lines):
            continue
        sl_match = KOTAK_SL_DATE.match(lines[i + 1].strip())
        if not sl_match:
            continue
        _sl, date = sl_match.groups()
        # Description continuation on lines below sl/date line
        cont = []
        for j in range(i + 2, min(i + 4, len(lines))):
            cand = lines[j].strip()
            if not cand or KOTAK_AMOUNT_LINE.match(cand) or KOTAK_SL_DATE.match(cand):
                break
            cont.append(cand)
        full_desc = (desc1 + " " + " ".join(cont)).strip()
        out.append({
            "date": normalize_date(date),
            "description": full_desc,
            "amount": clean_amount(amount_s),
            "type": dr_cr.title(),
        })
    return out


# ============================================================
# Public entry point
# ============================================================

PARSERS: Dict[str, Callable[[str], List[Dict]]] = {
    "hdfc_cc": _parse_hdfc_cc,
    "idfc": _parse_idfc,
    "hdfc_savings": _parse_hdfc_savings,
    "icici": _parse_icici_from_text,
    "kotak": _parse_kotak,
}


def parse_text(text: str) -> List[Dict]:
    bank = detect_bank(text)
    if bank == "unknown":
        # Try every parser and merge — used when bank detection fails
        seen = set()
        merged = []
        for fn in PARSERS.values():
            for t in fn(text):
                key = (t["date"], t["amount"], t["type"])
                if key not in seen:
                    seen.add(key)
                    merged.append(t)
        return merged
    return PARSERS[bank](text)
