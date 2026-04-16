# Copied from crypto/india-le-platform/backend/app/analysis/entity_classification.py
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

Generic entity-classification primitives.

All keyword vocabularies are parameters — no domain vocabulary is embedded here.
Crypto defaults live in ``entity_constants.py`` (which delegates to this module).
Other domains (bank, hawala, gold-smuggling) pass their own keyword sets.
"""
from __future__ import annotations

from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Set, Union

# Entity-type strings that carry no classification signal. A caller that gets
# one of these back from its upstream must fall through to name-based inference.
UNINFORMATIVE_ENTITY_TYPES: FrozenSet[str] = frozenset({"labeled", "other", "unknown", ""})


def infer_category_from_name(
    entity_name: Optional[str],
    keywords_by_category: Dict[str, Union[FrozenSet[str], Set[str], Iterable[str]]],
) -> Optional[str]:
    """Infer a category label from an entity name using a caller-supplied keyword map.

    Returns the first matching category key, or None if no keyword matched.
    Matching is substring-based, case-insensitive.
    """
    if not entity_name:
        return None
    name_lower = entity_name.lower()
    for category, keywords in keywords_by_category.items():
        if any(kw in name_lower for kw in keywords):
            return category
    return None


def name_matches_keywords(
    entity_name: Optional[str],
    keywords: Union[FrozenSet[str], Set[str], Iterable[str]],
) -> bool:
    """Return True if any keyword is a substring of the lower-cased entity name."""
    if not entity_name:
        return False
    name_lower = entity_name.lower()
    return any(kw in name_lower for kw in keywords)


def resolve_entity_type(
    entity_type: Optional[str],
    entity_name: Optional[str],
    keywords_by_category: Dict[str, Union[FrozenSet[str], Set[str], Iterable[str]]],
    uninformative_types: FrozenSet[str] = UNINFORMATIVE_ENTITY_TYPES,
) -> Optional[str]:
    """Canonical type resolution with domain-injected keyword map.

    - If ``entity_type`` is informative, return it as-is.
    - Else infer from ``entity_name`` using ``keywords_by_category``.
    - Else return the original ``entity_type`` (may be None).
    """
    if entity_type and entity_type.lower() not in uninformative_types:
        return entity_type
    inferred = infer_category_from_name(entity_name, keywords_by_category)
    if inferred:
        return inferred
    return entity_type or None


def enrich_path_edge(
    all_txs: List[Dict[str, Any]],
    preferred_token_symbols: FrozenSet[str] = frozenset(),
    preferred_weight: float = 1.01,
) -> Dict[str, Any]:
    """Token-aware enrichment of a multi-transaction edge.

    Groups ``all_txs`` by ``token_symbol``, picks a primary token (tokens in
    ``preferred_token_symbols`` get a ``preferred_weight`` multiplier on their
    total value for tie-breaking), and returns a single enriched edge dict.

    For crypto the preferred set is stablecoins; other domains can pass their
    own preferred-currency set (or an empty set to skip the bias entirely).
    """
    if not all_txs:
        return {"value": 0, "token_symbol": None, "tx_count": 0}

    token_groups: Dict[str, List[Dict[str, Any]]] = {}
    for t in all_txs:
        tok = t.get("token_symbol") or "native"
        token_groups.setdefault(tok, []).append(t)

    best_tok: Optional[str] = None
    best_val = -1.0
    for tok, txs_for_tok in token_groups.items():
        tok_total = sum(t.get("value", 0) for t in txs_for_tok)
        adj = tok_total * preferred_weight if tok in preferred_token_symbols else tok_total
        if adj > best_val:
            best_val = adj
            best_tok = tok

    primary_txs = token_groups.get(best_tok, all_txs)
    primary = dict(max(primary_txs, key=lambda x: x.get("value", 0)))
    primary_total = sum(t.get("value", 0) for t in primary_txs)

    primary["total_value"] = primary_total
    primary["token_symbol"] = best_tok
    primary["tx_count"] = len(all_txs)
    primary["all_transactions"] = [
        {
            "tx_hash": t.get("tx_hash"),
            "value": t.get("value", 0),
            "timestamp": t.get("timestamp"),
            "token_symbol": t.get("token_symbol"),
        }
        for t in all_txs
    ]

    secondary: Dict[str, Dict[str, Any]] = {}
    for tok, txs_for_tok in token_groups.items():
        if tok != best_tok:
            secondary[tok] = {
                "total_value": sum(t.get("value", 0) for t in txs_for_tok),
                "tx_count": len(txs_for_tok),
            }
    if secondary:
        primary["secondary_tokens"] = secondary

    return primary
