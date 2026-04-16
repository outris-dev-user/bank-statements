# Copied from crypto/india-le-platform/backend/app/analysis/pattern_framework.py
# at commit 9e7d7b8 on 2026-04-16.
# Sync via tools/sync-from-crypto.sh. If you need to change behaviour,
# change upstream first if possible.
# Local changes (if any) documented at the bottom of CRYPTO_SYNC.md.

"""
# PLATFORM — Safe to copy to sibling LEA-forensic-platform projects.
# Domain-agnostic. Do NOT add imports from services/fetchers/*,
# analysis/dex_decoder.py, analysis/privacy_chains.py, or any other
# crypto-specific module. See PLATFORM_MODULES.md at repo root.
# Cross-project consumers: ping Saurabh / #platform-sync on interface changes.

Generic pattern-detection scaffolding.

This module provides the domain-agnostic primitives for running behavioral
pattern detectors over transaction-shaped data:

  - parse_datetime(value): lenient timestamp parser
  - classify_direction(txs, self_id, id_normalizer): incoming vs outgoing split
  - aggregate_risk_boost(patterns, max_boost): bounded sum of per-pattern boosts

The crypto-specific 19 typologies (peel_chain, rug_pull, pig_butchering, …) live
in ``pattern_detector.py`` and are NOT part of this platform module. Sibling
domains (bank, hawala, etc.) compose their own pattern functions around these
primitives.

Typology signature:
    def some_pattern(
        self_id: str,
        incoming: list[dict],
        outgoing: list[dict],
        context: dict,
    ) -> list[dict]   # list of pattern hits, each with:
                      #   {pattern, confidence, risk_boost, description, ...}
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple


def parse_datetime(value: Any) -> Optional[datetime]:
    """Lenient timestamp parser — epoch seconds, epoch ms, ISO-8601, or datetime."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        try:
            return datetime.utcfromtimestamp(value / 1000 if value > 1e12 else value)
        except Exception:
            return None
    if isinstance(value, str):
        try:
            numeric = float(value)
            return datetime.utcfromtimestamp(numeric / 1000 if numeric > 1e12 else numeric)
        except (ValueError, OverflowError, OSError):
            pass
        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                return datetime.strptime(value.replace("Z", "+00:00"), fmt)
            except (ValueError, TypeError):
                continue
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def classify_direction(
    txs: List[Dict[str, Any]],
    self_id: str,
    id_normalizer: Callable[[str], str] = lambda x: (x or "").lower(),
    from_key: str = "from_address",
    to_key: str = "to_address",
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split transactions into (outgoing, incoming) lists relative to ``self_id``.

    ``id_normalizer`` is applied to both the sender/receiver field and
    ``self_id`` before comparison — crypto passes the chain-aware
    ``normalize_address``; bank can pass a generic lowercase.
    """
    self_norm = id_normalizer(self_id)
    outgoing = [t for t in txs if id_normalizer(t.get(from_key) or "") == self_norm]
    incoming = [t for t in txs if id_normalizer(t.get(to_key) or "") == self_norm]
    return outgoing, incoming


def aggregate_risk_boost(
    patterns: List[Dict[str, Any]],
    max_boost: float = 0.4,
    boost_key: str = "risk_boost",
) -> float:
    """Sum the ``risk_boost`` field across all pattern hits, capped at ``max_boost``.

    Returns a non-negative float.
    """
    total = sum(float(p.get(boost_key, 0) or 0) for p in patterns)
    if total < 0:
        total = 0.0
    return min(total, max_boost)


def severity_bucket(risk_boost: float) -> str:
    """Generic severity ranking: critical / high / medium / low / info."""
    if risk_boost >= 0.35:
        return "critical"
    if risk_boost >= 0.20:
        return "high"
    if risk_boost >= 0.10:
        return "medium"
    if risk_boost > 0:
        return "low"
    return "info"
