"""Round-amount detector — suspicious clustering of very round numbers.

Classical laundering + hawala pattern: repeated transfers of exact
round amounts (lakhs, half-lakhs, multiples of 50k). A single round
payment is not suspicious — we flag accounts that do many of them.

Rule (default): transactions of ≥₹50,000 that are exact multiples of
₹50,000 OR ≥₹10,000 that are exact multiples of ₹10,000 AND where the
account has ≥5 such round transactions, get flagged `ROUND_AMOUNT_CLUSTER`.
"""
from __future__ import annotations
from collections import defaultdict

BIG_UNIT = 50_000.0    # multiples of 50k considered suspiciously round
BIG_MIN = 50_000.0
SMALL_UNIT = 10_000.0
SMALL_MIN = 10_000.0
MIN_CLUSTER = 5


def _is_round(amt: float) -> bool:
    if amt >= BIG_MIN and amt % BIG_UNIT == 0:
        return True
    if amt >= SMALL_MIN and amt % SMALL_UNIT == 0:
        return True
    return False


def detect_round_amounts(txns: list[dict]) -> dict[str, list[str]]:
    round_by_account: dict[str, list[dict]] = defaultdict(list)
    for t in txns:
        amt = float(t.get("amount", 0))
        if _is_round(amt):
            round_by_account[t.get("account_id", "_")].append(t)

    flags: dict[str, list[str]] = {}
    for _acct, rows in round_by_account.items():
        if len(rows) >= MIN_CLUSTER:
            for r in rows:
                flags.setdefault(r["id"], []).append("ROUND_AMOUNT_CLUSTER")
    return flags
