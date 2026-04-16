"""Forensic pattern detection over a pool of transactions.

Each detector inspects a list of parsed transactions and returns a map
{transaction_id -> list[str]} of flag strings to add. Detectors are pure
(no DB) — the caller decides where to store the output.

Conventions:
    * Flag strings are UPPER_SNAKE_CASE.
    * Detectors MUST be idempotent — running them twice on the same pool
      should yield the same flags (no counters or suffixes).
"""
from __future__ import annotations
from .structuring import detect_structuring
from .velocity import detect_velocity_spike
from .round_amount import detect_round_amounts

__all__ = ["detect_structuring", "detect_velocity_spike", "detect_round_amounts", "run_all"]


def run_all(txns: list[dict]) -> dict[str, list[str]]:
    """Run every detector and merge their flag sets, keyed by txn id.

    `txns` is a list of dicts with at least: id, txn_date, amount,
    direction, account_id (optional). Detectors tolerate extra keys.
    """
    out: dict[str, list[str]] = {}
    for detector in (detect_structuring, detect_velocity_spike, detect_round_amounts):
        result = detector(txns)
        for txn_id, flags in result.items():
            out.setdefault(txn_id, [])
            for f in flags:
                if f not in out[txn_id]:
                    out[txn_id].append(f)
    return out
