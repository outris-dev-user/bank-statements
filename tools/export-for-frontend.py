"""export-for-frontend.py

Reads the benchmark's per-file parser output
(`benchmarks/results/pdfplumber_text/*.json`) and emits a single
`frontend/src/app/data/realData.ts` file that the frontend can consume
in place of `mockData.ts`.

The output is carefully typed so it's a drop-in for `mockData.ts` —
same Case / Person / Account / Statement / Transaction interfaces.

Usage:
    python tools/export-for-frontend.py

This is a one-way export: edits in the frontend don't flow back to the
parser. When Phase 2 wires a real backend (FastAPI), the frontend will
read via HTTP and this script retires.
"""
from __future__ import annotations
import json
import re
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parent
RESULTS = REPO / "benchmarks" / "results" / "pdfplumber_text"
OUT = REPO / "frontend" / "src" / "app" / "data" / "realData.ts"

# ───────────────────────────────────────────────────────────────────
# Bank + account metadata per test PDF (mirrors sum_check.py DECLARED)
# ───────────────────────────────────────────────────────────────────

# Each entry: {pdf_filename: {bank, account_type, account_number, holder,
#                             case_label, period_start, period_end,
#                             declared_dr, declared_cr}}
PDFS = {
    "Feb 2021.PDF":   dict(bank="HDFC Bank",       account_type="CC", account_number="****1234",
                           holder="Demo Cardholder",        case_label="HDFC CC Feb 2021",
                           period_start="2021-02-01", period_end="2021-02-28",
                           declared_dr=1659.80,   declared_cr=23902.00),
    "March 2021.PDF": dict(bank="HDFC Bank",       account_type="CC", account_number="****1234",
                           holder="Demo Cardholder",        case_label="HDFC CC Mar 2021",
                           period_start="2021-03-01", period_end="2021-03-31",
                           declared_dr=1792.52,   declared_cr=1660.00),
    "April 2021.PDF": dict(bank="HDFC Bank",       account_type="CC", account_number="****1234",
                           holder="Demo Cardholder",        case_label="HDFC CC Apr 2021",
                           period_start="2021-04-01", period_end="2021-04-30",
                           declared_dr=13101.00,  declared_cr=1792.00),
    "May 2021.PDF":   dict(bank="HDFC Bank",       account_type="CC", account_number="****1234",
                           holder="Demo Cardholder",        case_label="HDFC CC May 2021",
                           period_start="2021-05-01", period_end="2021-05-31",
                           declared_dr=19449.93,  declared_cr=13761.00),
    "June 2021.PDF":  dict(bank="HDFC Bank",       account_type="CC", account_number="****1234",
                           holder="Demo Cardholder",        case_label="HDFC CC Jun 2021",
                           period_start="2021-06-01", period_end="2021-06-30",
                           declared_dr=121448.00, declared_cr=21730.00),
    "IDFC Apr 2026.PDF": dict(bank="IDFC First Bank", account_type="CA", account_number="****5126",
                              holder="IDFC CA Holder",     case_label="IDFC CA Apr 2026",
                              period_start="2026-04-01", period_end="2026-04-30",
                              declared_dr=25000.00, declared_cr=0.00),
    "Acct Statement_XX3584_29042024.pdf": dict(bank="HDFC Bank", account_type="SA", account_number="****3584",
                              holder="Bilal A. K. Mohammed", case_label="HDFC Sav Oct23-Mar24",
                              period_start="2023-10-01", period_end="2024-03-31",
                              declared_dr=2302984.36, declared_cr=2282075.51),
    "ICICI_Bank_Statement_New.pdf": dict(bank="ICICI Bank",   account_type="CA", account_number="****2451",
                              holder="Atul Kabra",          case_label="ICICI CA Jul 2019",
                              period_start="2019-07-01", period_end="2019-07-31",
                              declared_dr=115000.00, declared_cr=125640.00),
    "Statement April-Aug 2021.pdf": dict(bank="Kotak Mahindra", account_type="SA", account_number="****1652",
                              holder="Suraj Shyam More",    case_label="Kotak Apr-Aug 2021",
                              period_start="2021-04-01", period_end="2021-08-25",
                              declared_dr=700583.11, declared_cr=614301.24),
}

# Cases: group PDFs. A case is an investigation; multiple statements (from one or
# more persons) land under it. Two demo cases cover all 5 banks between them.
CASES = [
    {
        "id": "c1",
        "fir_number": "FIR # 2026/AEC/0471",
        "title": "Suraj Shyam More — Kotak + HDFC Sav",
        "officer_name": "SI A. Kamat",
        "status": "active",
        "pdfs": [
            # Kotak + HDFC Savings for Suraj Shyam More (demo — holder names are illustrative)
            ("Statement April-Aug 2021.pdf",            "p1"),  # Suraj Shyam More
            ("Acct Statement_XX3584_29042024.pdf",      "p1"),  # treat as Suraj (demo)
        ],
        "persons": [
            {"id": "p1", "name": "Suraj Shyam More", "pan": "ABCDE1234F", "phone": "+91 98765 43210"},
        ],
    },
    {
        "id": "c2",
        "fir_number": "FIR # 2026/AEC/0466",
        "title": "HDFC CC demo + IDFC CA + ICICI CA",
        "officer_name": "Inspector R. Desai",
        "status": "active",
        "pdfs": [
            ("Feb 2021.PDF",   "p2"),
            ("March 2021.PDF", "p2"),
            ("April 2021.PDF", "p2"),
            ("May 2021.PDF",   "p2"),
            ("June 2021.PDF",  "p2"),
            ("IDFC Apr 2026.PDF", "p3"),
            ("ICICI_Bank_Statement_New.pdf", "p4"),
        ],
        "persons": [
            {"id": "p2", "name": "Demo Cardholder",  "pan": None, "phone": None},
            {"id": "p3", "name": "IDFC CA Holder",   "pan": None, "phone": None},
            {"id": "p4", "name": "Atul Kabra",       "pan": None, "phone": None},
        ],
    },
]


# ───────────────────────────────────────────────────────────────────
# Conversion helpers
# ───────────────────────────────────────────────────────────────────

CHANNEL_RX = re.compile(r"\b(UPI|NEFT|IMPS|RTGS|POS|ATM|ECS|NACH|CHEQUE|CHQ|CASH)\b", re.I)
CATEGORY_KEYWORDS = [
    ("salary",   ["SALARY", "SAL CREDIT", "SAL-"]),
    ("rewards",  ["CASHBACK", "REWARD", "REFERRAL"]),
    ("finance",  ["CRED", "CREDIT CARD", "LOAN", "EMI", "INTEREST"]),
    ("shopping", ["AMAZON", "FLIPKART", "SWIGGY", "ZOMATO", "MYNTRA", "MEESHO"]),
    ("food",     ["RESTAURANT", "HOTEL", "ZEPTO", "BLINKIT", "CAFE"]),
    ("rent",     ["RENT", "LANDLORD"]),
    ("transfer", ["UPI", "NEFT", "IMPS", "RTGS", "IFT"]),
    ("cash",     ["ATM", "CASH"]),
    ("charges",  ["FEE", "CHG", "CHARGE", "GST"]),
]


def iso_date(ddmmyyyy: str) -> str:
    """Normalise 'DD/MM/YYYY' → 'YYYY-MM-DD'."""
    try:
        return datetime.strptime(ddmmyyyy, "%d/%m/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return ddmmyyyy  # already ISO or unparseable — leave alone


def infer_channel(description: str) -> str:
    m = CHANNEL_RX.search(description)
    return m.group(1).upper() if m else "OTHER"


def infer_category(description: str) -> str:
    up = description.upper()
    for cat, keys in CATEGORY_KEYWORDS:
        if any(k in up for k in keys):
            return cat.title()
    return "Other"


def infer_counterparty(description: str, channel: str) -> str:
    # Strip the channel prefix and ref-number tails to get the human-readable token
    text = re.sub(r"^(UPI|NEFT|IMPS|RTGS|POS|ATM)[-/\s]*", "", description, flags=re.I)
    text = re.sub(r"[-/]\d{6,}.*$", "", text)                         # strip trailing long digit ref
    text = re.sub(r"-\d{4}-\d{10,}", "", text)                        # IFSC-based tails
    tokens = re.split(r"[-/@]", text.strip(), maxsplit=1)
    head = tokens[0].strip() if tokens else text.strip()
    return (head[:50] or "(unknown)")


# ───────────────────────────────────────────────────────────────────
# Main build
# ───────────────────────────────────────────────────────────────────

def build():
    out_cases = []
    out_persons = []
    out_accounts = []
    out_statements = []
    out_txns = []

    total_case_txns = {}

    for case in CASES:
        # One account per (bank, account_number) within a case
        seen_accounts = {}
        case_txn_count = 0
        case_stmt_count = 0
        case_flag_count = 0

        for person in case["persons"]:
            out_persons.append({
                "id": person["id"],
                "case_id": case["id"],
                "name": person["name"],
                "aliases": [],
                "pan": person.get("pan"),
                "phone": person.get("phone"),
            })

        for pdf_name, person_id in case["pdfs"]:
            meta = PDFS.get(pdf_name)
            if not meta:
                continue
            acc_key = (meta["bank"], meta["account_number"], person_id)
            if acc_key not in seen_accounts:
                acc_id = f"a{len(out_accounts) + 1}"
                seen_accounts[acc_key] = acc_id
                # extracted_txn_count filled in after reading stmts
                out_accounts.append({
                    "id": acc_id,
                    "person_id": person_id,
                    "bank": meta["bank"],
                    "account_type": meta["account_type"],
                    "account_number": meta["account_number"],
                    "holder_name": meta["holder"],
                    "currency": "INR",
                    "transaction_count": 0,  # fill later
                    "has_warnings": False,
                })
            acc_id = seen_accounts[acc_key]

            # Read parser JSON
            stem = Path(pdf_name).stem
            json_path = RESULTS / f"{stem}.json"
            if not json_path.exists():
                print(f"  MISSING: {json_path}")
                continue

            data = json.loads(json_path.read_text(encoding="utf-8"))
            parser_txns = data.get("txns", [])

            stmt_id = f"s{len(out_statements) + 1}"
            sum_dr = sum(t["amount"] for t in parser_txns if t["type"] == "Dr")
            sum_cr = sum(t["amount"] for t in parser_txns if t["type"] == "Cr")
            declared_dr = meta["declared_dr"]
            declared_cr = meta["declared_cr"]
            dr_pct = (sum_dr / declared_dr * 100) if declared_dr else 100.0
            cr_pct = (sum_cr / declared_cr * 100) if declared_cr else 100.0
            has_warnings = abs(dr_pct - 100) > 0.01 or abs(cr_pct - 100) > 0.01

            out_statements.append({
                "id": stmt_id,
                "account_id": acc_id,
                "source_file_name": pdf_name,
                "period_start": meta["period_start"],
                "period_end": meta["period_end"],
                "opening_balance": 0,  # parser doesn't expose this currently
                "closing_balance": 0,
                "extracted_txn_count": len(parser_txns),
                "sum_check_debits_pct": round(dr_pct, 2),
                "sum_check_credits_pct": round(cr_pct, 2),
                "uploaded_at": "2026-04-16T10:00:00",
                "uploaded_by": "Saurabh",
            })
            case_stmt_count += 1

            # Convert each parser txn → frontend Transaction
            running_balance = 0.0
            for idx, t in enumerate(parser_txns, start=1):
                raw = t.get("description", "")
                channel = infer_channel(raw)
                category = infer_category(raw)
                counterparty = infer_counterparty(raw, channel)
                amount = float(t["amount"])
                direction = t["type"]
                running_balance += (amount if direction == "Cr" else -amount)

                # Confidence heuristic
                conf = "high"
                flags = []
                if counterparty.startswith("(unknown") or len(counterparty) < 3:
                    conf = "low"
                    flags.append("NEEDS_REVIEW")
                elif channel == "OTHER":
                    conf = "medium"

                txn_id = f"t{len(out_txns) + 1}"
                txn = {
                    "id": txn_id,
                    "statement_id": stmt_id,
                    "account_id": acc_id,
                    "case_id": case["id"],
                    "row_index": idx,
                    "txn_date": iso_date(t.get("date", "")),
                    "amount": amount,
                    "direction": direction,
                    "running_balance": round(running_balance, 2),
                    "raw_description": raw,
                    "entities": {
                        "channel":      {"value": channel,      "source": "extracted",     "confidence": 1.0 if channel != "OTHER" else 0.4},
                        "counterparty": {"value": counterparty, "source": "extracted",     "confidence": 0.9 if conf == "high" else 0.5 if conf == "medium" else 0.25},
                        "category":     {"value": category,     "source": "auto_resolved", "confidence": 0.7},
                    },
                    "tags": [],
                    "confidence": conf,
                    "flags": flags,
                    "review_status": "unreviewed",
                    "edit_count": 0,
                }
                out_txns.append(txn)
                case_txn_count += 1
                case_flag_count += len(flags)

            # update account tx count
            for a in out_accounts:
                if a["id"] == acc_id:
                    a["transaction_count"] += len(parser_txns)
                    a["has_warnings"] = a["has_warnings"] or has_warnings

        total_case_txns[case["id"]] = (case_stmt_count, case_txn_count, case_flag_count)

        out_cases.append({
            "id": case["id"],
            "fir_number": case["fir_number"],
            "title": case["title"],
            "officer_name": case["officer_name"],
            "status": case["status"],
            "created_at": "2026-04-13T10:30:00",
            "updated_at": "2026-04-16T10:00:00",
            "statement_count": case_stmt_count,
            "transaction_count": case_txn_count,
            "flag_count": case_flag_count,
        })

    # Emit TypeScript
    header = """// AUTO-GENERATED by tools/export-for-frontend.py. Do not edit by hand.
// Run `python tools/export-for-frontend.py` from the repo root to regenerate.
//
// Shape matches mockData.ts exactly — you can swap the import in any component:
//   import { realCases as mockCases, realPersons as mockPersons, ... } from './realData';

import type { Case, Person, Account, Statement, Transaction } from './mockData';
"""

    def emit(name: str, value: list) -> str:
        return f"\nexport const {name} = {json.dumps(value, indent=2, ensure_ascii=False)} as const satisfies readonly any[];\n"

    body = "".join([
        emit("realCases", out_cases),
        emit("realPersons", out_persons),
        emit("realAccounts", out_accounts),
        emit("realStatements", out_statements),
        emit("realTransactions", out_txns),
    ])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(header + body, encoding="utf-8")

    # Summary
    print(f"Wrote {OUT}")
    print(f"  {len(out_cases)} cases")
    print(f"  {len(out_persons)} persons")
    print(f"  {len(out_accounts)} accounts")
    print(f"  {len(out_statements)} statements")
    print(f"  {len(out_txns)} transactions")
    for cid, (s, t, f) in total_case_txns.items():
        print(f"    {cid}: {s} statements, {t} txns, {f} flags")


if __name__ == "__main__":
    build()
