"""Velocity-spike detector — unusual burst of transactions in a short window.

Rule (default): any account with ≥10 transactions in any 24h window has
those contributing txns flagged `VELOCITY_SPIKE`. With only dates (no
times) available, we treat same-day as the minimum resolution and
compare across consecutive days via a rolling count.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timedelta

WINDOW_HOURS = 24
MIN_COUNT = 10


def detect_velocity_spike(txns: list[dict]) -> dict[str, list[str]]:
    by_account: dict[str, list[dict]] = defaultdict(list)
    for t in txns:
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
                if (d - anchor_date).total_seconds() > WINDOW_HOURS * 3600:
                    break
                bucket.append(rows[j])
            if len(bucket) >= MIN_COUNT:
                for r in bucket:
                    flags.setdefault(r["id"], []).append("VELOCITY_SPIKE")
    return flags
