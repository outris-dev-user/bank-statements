"""Structuring detector — repeated transactions just under a reporting
threshold, classically used to dodge FIU-IND CTR reporting at ₹10L.

Rule (default): any account with ≥3 transactions between ₹9L and ₹10L
within any rolling 30-day window gets each contributing txn flagged
`STRUCTURING_SUSPECTED`.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timedelta

LOWER = 900_000.0
UPPER = 1_000_000.0
WINDOW_DAYS = 30
MIN_COUNT = 3


def detect_structuring(txns: list[dict]) -> dict[str, list[str]]:
    by_account: dict[str, list[dict]] = defaultdict(list)
    for t in txns:
        amt = float(t.get("amount", 0))
        if LOWER <= amt < UPPER:
            by_account[t.get("account_id", "_")].append(t)

    flags: dict[str, list[str]] = {}
    for _acct, rows in by_account.items():
        rows.sort(key=lambda r: r.get("txn_date", ""))
        for i, anchor in enumerate(rows):
            try:
                anchor_date = datetime.fromisoformat(anchor["txn_date"])
            except Exception:
                continue
            bucket = [anchor]
            for j in range(i + 1, len(rows)):
                try:
                    d = datetime.fromisoformat(rows[j]["txn_date"])
                except Exception:
                    continue
                if (d - anchor_date).days > WINDOW_DAYS:
                    break
                bucket.append(rows[j])
            if len(bucket) >= MIN_COUNT:
                for r in bucket:
                    flags.setdefault(r["id"], []).append("STRUCTURING_SUSPECTED")
    return flags
