# Copied from crypto/india-le-platform/backend/app/analysis/graph_store.py
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

Abstract ``GraphStore`` protocol.

Defines the minimal persistence + query surface that analysis algorithms depend
on. Any concrete backend (Neo4j, NetworkX-on-disk, SQLite-with-graph-views,
in-memory for tests) that implements these methods can be plugged in without
changes to the algorithm layer.

The crypto ``GraphStorageService`` in ``services/graph_storage.py`` is
structurally compatible with this protocol today — no code change is required
there; typing it as ``GraphStore`` in function signatures immediately works.

Bank-analyser (offline, air-gapped) will ship a NetworkX-backed implementation
that satisfies the same protocol. Algorithm code imports only ``GraphStore``,
so the same modules run in both deployments.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class GraphStore(Protocol):
    """Minimal persistence + query surface used by analysis algorithms.

    Notes on the contract:
      - Node identity is an opaque string (``address`` for crypto, ``account_id``
        for bank). Implementations must not assume a particular shape.
      - Transactions/edges are represented as plain dicts. Required keys for
        persistence: ``from_address``, ``to_address``, ``value``, ``timestamp``.
        Optional: ``tx_hash``, ``token_symbol``, ``direction``, and any
        domain-specific fields the backend is willing to persist.
      - All methods are ``async`` — implementations that wrap sync libraries
        should run them in a thread executor.
    """

    # ── Node reads / writes ───────────────────────────────────────────

    async def save_address_node(self, data: Dict[str, Any]) -> None:
        """Upsert a single node. ``data`` MUST include an ``address`` key."""
        ...

    async def get_address_node(self, address: str) -> Optional[Dict[str, Any]]:
        """Return the stored node dict, or None if not present."""
        ...

    # ── Edge reads / writes ───────────────────────────────────────────

    async def save_transactions(
        self, transactions: List[Dict[str, Any]], chain: str
    ) -> None:
        """Bulk upsert edges. ``chain`` is opaque to the protocol but MUST be
        echoed back on reads so callers can round-trip.
        """
        ...

    async def get_transaction_between(
        self, from_addr: str, to_addr: str
    ) -> Optional[Dict[str, Any]]:
        """Return a representative edge (or summary) between two nodes."""
        ...

    async def get_all_edges_between(
        self, source: str, target: str, exclude_spam: bool = True
    ) -> List[Dict[str, Any]]:
        """Return every edge between source and target."""
        ...

    # ── Topology queries ──────────────────────────────────────────────

    async def get_neighbors(
        self, address: str, direction: str = "all"
    ) -> List[Dict[str, Any]]:
        """Return 1-hop neighbours. ``direction`` ∈ {"incoming", "outgoing", "all"}."""
        ...

    async def get_shortest_path(
        self, source: str, target: str, max_hops: int = 5
    ) -> List[Dict[str, Any]]:
        """Return a list of edges representing the shortest path, or empty list."""
        ...

    async def find_paths_to_entity_types(
        self,
        source: str,
        entity_types: List[str],
        max_hops: int = 4,
        limit: int = 10,
        direction: str = "outgoing",
    ) -> List[Dict[str, Any]]:
        """Return paths from ``source`` to any node whose entity_type is in ``entity_types``."""
        ...
