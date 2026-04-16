# Copied from crypto/india-le-platform/backend/app/analysis/transaction_pool.py
# at commit 9e7d7b8 on 2026-04-16.
# Sync via tools/sync-from-crypto.sh. If you need to change behaviour,
# change upstream first if possible.
# Local changes (if any) documented at the bottom of CRYPTO_SYNC.md.

"""TransactionPool — central data broker for investigation sessions.

Algorithms request data via pool.get_transactions(address).
Pool deduplicates concurrent requests, uses session cache,
and delegates to GraphService (DB cache -> live API) on miss.
"""
import asyncio
import structlog
from typing import Any, Dict, List, Optional

from app.analysis.address_utils import normalize_address
from app.services.fetchers.evm import UpstreamConfigError

logger = structlog.get_logger()


class TransactionPool:
    """Per-investigation session cache and deduplication layer.

    Usage:
        pool = TransactionPool(chain="BTC")
        await pool.prefetch(root_address, limit=200)   # warm cache
        txs = await pool.get_transactions(some_address) # cache hit or fetch
    """

    def __init__(self, chain: str):
        self.chain = chain
        self._cache: Dict[str, Dict[str, Any]] = {}      # addr -> {transactions, total}
        self._inflight: Dict[str, asyncio.Event] = {}     # addr -> event (dedup)
        self._stats = {"cache_hits": 0, "api_fetches": 0, "dedup_waits": 0}

    async def get_transactions(
        self, address: str, min_count: int = 200,
    ) -> List[Dict[str, Any]]:
        """Get transactions for an address. Deduplicates concurrent callers."""
        key = normalize_address(address, self.chain)

        # 1. Session cache hit
        if key in self._cache:
            cached_txs = self._cache[key].get("transactions", [])
            if len(cached_txs) >= min_count or self._cache[key].get("total", 0) <= len(cached_txs):
                self._stats["cache_hits"] += 1
                return cached_txs[:min_count]

        # 2. Another caller is already fetching — wait for it
        if key in self._inflight:
            self._stats["dedup_waits"] += 1
            await self._inflight[key].wait()
            cached = self._cache.get(key, {}).get("transactions", [])
            return cached[:min_count]

        # 3. First caller — fetch via GraphService (DB cache -> API)
        event = asyncio.Event()
        self._inflight[key] = event
        try:
            from app.services.graph_service import graph_service as gs
            result = await gs.get_address_transactions(
                self.chain, address,
                limit=max(min_count, 200),
                offset=0, persist_graph=False,
            )
            self._cache[key] = result
            self._stats["api_fetches"] += 1
            return result.get("transactions", [])[:min_count]
        except UpstreamConfigError:
            # Config errors (missing chainid, invalid API key) must propagate
            # so callers can detect degraded state instead of silent empty data.
            logger.error("transaction_pool.config_error", address=address, chain=self.chain)
            self._cache[key] = {"transactions": [], "total": 0}
            raise
        except Exception:
            logger.warning("transaction_pool.fetch_failed", address=address, chain=self.chain)
            self._cache[key] = {"transactions": [], "total": 0}
            return []
        finally:
            event.set()
            self._inflight.pop(key, None)

    async def prefetch(self, address: str, limit: int = 200) -> int:
        """Pre-warm pool with root address transactions. Returns tx count."""
        txs = await self.get_transactions(address, min_count=limit)
        return len(txs)

    def get_cached(self, address: str) -> Optional[List[Dict[str, Any]]]:
        """Sync: return cached txs or None (no fetch)."""
        entry = self._cache.get(normalize_address(address, self.chain))
        return entry.get("transactions") if entry else None

    @property
    def stats(self) -> Dict[str, Any]:
        return {**self._stats, "cached_addresses": len(self._cache)}
