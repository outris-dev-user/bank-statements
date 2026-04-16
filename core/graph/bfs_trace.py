# Copied from crypto/india-le-platform/backend/app/analysis/bfs_trace.py
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

Generic BFS-trace primitives.

The full ``trace_address()`` implementation currently lives in
``services/graph_service.py`` (~500 lines) and is tightly coupled to the crypto
fetcher/storage layer. This module exposes the domain-agnostic *primitives*
that trace relies on, so sibling LEA-forensic-platform projects can assemble
their own trace using the same building blocks:

  - ``should_stop_at_entity(...)`` — stop-condition evaluator
  - ``BFSExpansionContext`` — per-trace bookkeeping (visited, hop index, etc.)
  - ``expand_one_hop(...)`` — pure function: given a frontier + fetch callback,
    return the next-hop frontier and an updated context.

Full extraction of ``trace_address()`` into this module is on the
platform-cleanup roadmap — see PLATFORM_MODULES.md. Until then, crypto callers
continue to use ``graph_service.trace_address()`` unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, FrozenSet, List, Optional, Set


def should_stop_at_entity(
    entity_type: Optional[str],
    entity_name: Optional[str],
    stop_types_lower: Set[str],
    stop_name_predicate: Optional[Callable[[str], bool]] = None,
) -> bool:
    """Decide whether a BFS traversal should terminate at this entity.

    Two dimensions are evaluated:
      1. ``entity_type`` matches one of the configured ``stop_types_lower``
         (caller lower-cases before passing, so the compare is case-insensitive).
      2. ``entity_name`` satisfies ``stop_name_predicate`` — catches entities
         whose ``entity_type`` is generic ("other", "labeled", "unknown") but
         whose name clearly identifies them as a stop target (e.g. for crypto,
         an exchange brand keyword).

    The ``stop_name_predicate`` keeps this function vocabulary-free: crypto
    passes ``is_exchange_by_name`` from ``entity_constants``; bank-analyser
    passes ``is_known_bank_account``; etc.
    """
    if entity_type and entity_type.lower() in stop_types_lower:
        return True
    if entity_name and stop_name_predicate is not None and stop_name_predicate(entity_name):
        return True
    return False


@dataclass
class BFSExpansionContext:
    """Per-trace bookkeeping shared across hop expansions."""

    visited: Set[str] = field(default_factory=set)
    hop_index: int = 0
    addresses_fetched: int = 0
    cache_hits: int = 0
    api_calls: int = 0
    stopped_at: List[str] = field(default_factory=list)

    def mark_visited(self, addr: str) -> bool:
        """Return True if this address was newly added to the visited set."""
        if addr in self.visited:
            return False
        self.visited.add(addr)
        return True


FetchTxsCallback = Callable[[str], Awaitable[List[Dict[str, Any]]]]
CounterpartiesCallback = Callable[[Dict[str, Any], str], List[str]]


async def expand_one_hop(
    frontier: List[str],
    context: BFSExpansionContext,
    fetch_txs: FetchTxsCallback,
    counterparties_of: CounterpartiesCallback,
    id_normalizer: Callable[[str], str] = lambda x: (x or "").lower(),
    max_frontier_size: Optional[int] = None,
) -> List[str]:
    """Expand one BFS hop over ``frontier`` addresses.

    Pure w.r.t. the caller's data layer: ``fetch_txs`` returns a list of
    transaction dicts for a given address, and ``counterparties_of`` extracts
    the set of counterparty identifiers from a single transaction relative to
    the self-address.

    Returns the next-hop frontier (deduplicated, new addresses only). Mutates
    ``context.visited`` / ``context.hop_index`` / ``context.addresses_fetched``.
    """
    context.hop_index += 1
    next_frontier: List[str] = []
    seen_this_hop: Set[str] = set()

    for self_addr in frontier:
        self_norm = id_normalizer(self_addr)
        txs = await fetch_txs(self_addr)
        context.addresses_fetched += 1
        for tx in txs or []:
            for cp in counterparties_of(tx, self_norm):
                if not cp:
                    continue
                cp_norm = id_normalizer(cp)
                if cp_norm in seen_this_hop:
                    continue
                if context.mark_visited(cp_norm):
                    seen_this_hop.add(cp_norm)
                    next_frontier.append(cp)
                    if max_frontier_size is not None and len(next_frontier) >= max_frontier_size:
                        return next_frontier

    return next_frontier
