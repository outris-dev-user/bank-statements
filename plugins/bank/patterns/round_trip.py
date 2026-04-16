"""Same-day round-trip detector — an identical credit + debit with
the same counterparty on the same day. Classic layering / wash pattern.

Rule (default): if a counterparty appears with both a credit and a debit
of amounts within ±5% of each other on the same day on the same account,
flag both transactions `SAME_DAY_ROUND_TRIP`. Both must be ≥ ₹5,000.
"""
from __future__ import annotations
from collections import defaultdict

MIN_AMOUNT = 5_000.0
TOLERANCE = 0.05


def _counterparty(txn: dict) -> str:
    cp = txn.get("counterparty")
    if cp:
        return cp
    # Fallback: use first 20 chars of description
    raw = (txn.get("description") or txn.get("raw_description") or "").strip()
    return raw[:20]


def detect_round_trip(txns: list[dict]) -> dict[str, list[str]]:
    # Bucket by (account, date, counterparty)
    buckets: dict[tuple, list[dict]] = defaultdict(list)
    for t in txns:
        amt = float(t.get("amount", 0))
        if amt < MIN_AMOUNT:
            continue
        key = (t.get("account_id", "_"), t.get("txn_date"), _counterparty(t))
        buckets[key].append(t)

    flags: dict[str, list[str]] = {}
    for _key, rows in buckets.items():
        credits = [r for r in rows if r.get("direction") == "Cr"]
        debits = [r for r in rows if r.get("direction") == "Dr"]
        if not credits or not debits:
            continue
        for c in credits:
            c_amt = float(c["amount"])
            if c_amt == 0:
                continue
            for d in debits:
                d_amt = float(d["amount"])
                if abs(d_amt - c_amt) / c_amt <= TOLERANCE:
                    flags.setdefault(c["id"], []).append("SAME_DAY_ROUND_TRIP")
                    flags.setdefault(d["id"], []).append("SAME_DAY_ROUND_TRIP")
    return flags
