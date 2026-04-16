"""Dormant-then-active detector — accounts that go quiet for a while then
suddenly burst with activity. A classic mule-account reactivation or a
planted-money pattern.

Rule (default): an account with a gap of `DORMANT_DAYS` or more between
two txn dates, followed by ≥ `BURST_COUNT` transactions within
`BURST_DAYS` of the gap-ending date, has the burst transactions flagged
`DORMANT_THEN_ACTIVE`.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime

DORMANT_DAYS = 60
BURST_COUNT = 5
BURST_DAYS = 7


def detect_dormant_active(txns: list[dict]) -> dict[str, list[str]]:
    by_account: dict[str, list[dict]] = defaultdict(list)
    for t in txns:
        by_account[t.get("account_id", "_")].append(t)

    flags: dict[str, list[str]] = {}
    for _acct, rows in by_account.items():
        # Sort chronologically; abort if any date is unparseable.
        parsed = []
        for r in rows:
            try:
                parsed.append((datetime.fromisoformat(r["txn_date"]), r))
            except Exception:
                continue
        parsed.sort(key=lambda p: p[0])
        if len(parsed) < BURST_COUNT + 1:
            continue

        for i in range(1, len(parsed)):
            gap = (parsed[i][0] - parsed[i - 1][0]).days
            if gap < DORMANT_DAYS:
                continue
            # Burst candidates start at i; collect until we step outside BURST_DAYS
            start = parsed[i][0]
            burst = []
            for j in range(i, len(parsed)):
                if (parsed[j][0] - start).days > BURST_DAYS:
                    break
                burst.append(parsed[j][1])
            if len(burst) >= BURST_COUNT:
                for r in burst:
                    flags.setdefault(r["id"], []).append("DORMANT_THEN_ACTIVE")
    return flags
