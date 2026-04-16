"""Fund-through-flow detector — an account that receives a credit and then
sends out a similar amount within a short window (the classic money-mule
signature). Not laundering on its own, but a strong signal when repeated.

Rule (default): for each credit of amount A on day D, if a debit of
amount within ±5% of A occurs within `WINDOW_DAYS` days on the same
account, flag both transactions `FUND_THROUGH_FLOW`. Both transactions
must be ≥ ₹10,000 so we don't flag tiny incidental txns.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime

WINDOW_DAYS = 2
MIN_AMOUNT = 10_000.0
TOLERANCE = 0.05  # 5% envelope


def detect_fund_through(txns: list[dict]) -> dict[str, list[str]]:
    by_account: dict[str, list[dict]] = defaultdict(list)
    for t in txns:
        if float(t.get("amount", 0)) < MIN_AMOUNT:
            continue
        by_account[t.get("account_id", "_")].append(t)

    flags: dict[str, list[str]] = {}
    for _acct, rows in by_account.items():
        rows.sort(key=lambda r: r.get("txn_date", ""))
        for i, credit in enumerate(rows):
            if credit.get("direction") != "Cr":
                continue
            try:
                c_date = datetime.fromisoformat(credit["txn_date"])
            except Exception:
                continue
            c_amt = float(credit["amount"])
            for j in range(i + 1, len(rows)):
                debit = rows[j]
                if debit.get("direction") != "Dr":
                    continue
                try:
                    d_date = datetime.fromisoformat(debit["txn_date"])
                except Exception:
                    continue
                if (d_date - c_date).days > WINDOW_DAYS:
                    break
                d_amt = float(debit["amount"])
                if c_amt == 0:
                    continue
                diff = abs(d_amt - c_amt) / c_amt
                if diff <= TOLERANCE:
                    flags.setdefault(credit["id"], []).append("FUND_THROUGH_FLOW")
                    flags.setdefault(debit["id"], []).append("FUND_THROUGH_FLOW")
    return flags
