# Copied from crypto/india-le-platform/backend/app/analysis/velocity_analyzer.py
# at commit 9e7d7b8 on 2026-04-16.
# Sync via tools/sync-from-crypto.sh. If you need to change behaviour,
# change upstream first if possible.
# Local changes (if any) documented at the bottom of CRYPTO_SYNC.md.

"""Transaction Velocity Analysis (C7).

Computes 6 temporal metrics characterising how money flows through an address:
  1. Fund-Through Rate — total_outflow / total_inflow (1.0 = pure relay)
  2. Consolidation Ratio — fraction of txs with ≥5 inputs
  3. Value Amplification — max_single_tx_value / median_tx_value
  4. Dwell Time (hours) — median gap between first receive and next send
  5. Regularity Score — coefficient of variation of daily tx counts (low = bot)
  6. Burst Score — max_daily_count / mean_daily_count

Derived:
  - velocity_profile: Accumulator | Relay | Distributor | Mixed | Dormant
  - velocity_risk_score: weighted composite of all 6 metrics
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

from app.analysis.address_utils import normalize_address, safe_tx_value

logger = structlog.get_logger()


class VelocityAnalyzer:
    """Compute velocity metrics for a set of transactions."""

    async def analyze(
        self,
        address: str,
        chain: str,
        transactions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Return velocity analysis for *address* given its *transactions*."""
        addr_lower = normalize_address(address, chain)
        n_txs = len(transactions)

        if n_txs == 0:
            return self._empty_result(address, chain)

        # ── Classify each tx as incoming / outgoing ──────────────────
        incoming: List[Dict[str, Any]] = []
        outgoing: List[Dict[str, Any]] = []
        timestamps: List[datetime] = []

        for tx in transactions:
            ts = self._parse_ts(tx)
            if ts:
                timestamps.append(ts)
            from_addr = normalize_address(tx.get("from") or tx.get("from_address") or "", chain)
            if from_addr == addr_lower:
                outgoing.append(tx)
            else:
                incoming.append(tx)

        total_inflow = sum(self._tx_value(tx) for tx in incoming)
        total_outflow = sum(self._tx_value(tx) for tx in outgoing)

        # ── Token-aware FTR ────────────────────────────────────────────
        # Group inflows/outflows by token to compute per-token FTR.
        # Primary token (stablecoin preferred) drives the main metric.
        from app.analysis.entity_constants import STABLECOIN_SYMBOLS
        _STABLE_PREF = ["USDT", "USDC", "DAI", "BUSD"]  # preference order

        def _tx_token(tx: Dict[str, Any]) -> str:
            return tx.get("token_symbol") or tx.get("token") or "native"

        token_in: Dict[str, float] = defaultdict(float)
        token_out: Dict[str, float] = defaultdict(float)
        for tx in incoming:
            token_in[_tx_token(tx)] += self._tx_value(tx)
        for tx in outgoing:
            token_out[_tx_token(tx)] += self._tx_value(tx)

        # Build per-token breakdown
        all_tokens = set(token_in.keys()) | set(token_out.keys())
        token_breakdown: List[Dict[str, Any]] = []
        for tok in sorted(all_tokens):
            t_in = token_in.get(tok, 0.0)
            t_out = token_out.get(tok, 0.0)
            t_ftr = round(t_out / t_in, 4) if t_in > 0 else 0.0
            token_breakdown.append({
                "token": tok,
                "inflow": round(t_in, 4),
                "outflow": round(t_out, 4),
                "fund_through_rate": t_ftr,
            })

        # Select primary token: prefer stablecoins by preference order, then highest-volume
        primary_token = None
        for stable in _STABLE_PREF:
            if stable in all_tokens and (token_in.get(stable, 0) + token_out.get(stable, 0)) > 0:
                primary_token = stable
                break
        if not primary_token:
            # Fall back to highest-volume token
            primary_token = max(all_tokens, key=lambda t: token_in.get(t, 0) + token_out.get(t, 0)) if all_tokens else "native"

        # Use primary token's FTR when available, cross-token as fallback
        primary_in = token_in.get(primary_token, 0.0)
        primary_out = token_out.get(primary_token, 0.0)
        if primary_in > 0:
            primary_ftr = round(primary_out / primary_in, 4)
        else:
            # Fallback to cross-token FTR
            primary_ftr = round(total_outflow / total_inflow, 4) if total_inflow > 0 else 0.0

        # ── Metric 1: Fund-Through Rate ──────────────────────────────
        fund_through_rate = primary_ftr

        # ── Metric 2: Consolidation Ratio ────────────────────────────
        consolidation_txs = sum(
            1 for tx in transactions
            if int(tx.get("input_count", tx.get("vin_count", 1))) >= 5
        )
        consolidation_ratio = round(consolidation_txs / n_txs, 4) if n_txs > 0 else 0.0

        # ── Metric 3: Value Amplification ────────────────────────────
        values = [self._tx_value(tx) for tx in transactions if self._tx_value(tx) > 0]
        if len(values) >= 2:
            median_val = statistics.median(values)
            max_val = max(values)
            value_amplification = round(max_val / median_val, 2) if median_val > 0 else 0.0
        else:
            value_amplification = 0.0

        # ── Metric 4: Dwell Time (hours) ─────────────────────────────
        dwell_time_hours = self._compute_dwell_time(incoming, outgoing, addr_lower)

        # ── Metric 5: Regularity Score (CV of daily counts) ──────────
        # None = insufficient data (<2 days), 0.0 = genuinely zero variance
        daily_counts = self._daily_counts(timestamps)
        if len(daily_counts) >= 2:
            mean_c = statistics.mean(daily_counts)
            std_c = statistics.pstdev(daily_counts)
            regularity_score = round(std_c / mean_c, 4) if mean_c > 0 else None
        else:
            regularity_score = None

        # ── Metric 6: Burst Score ────────────────────────────────────
        if daily_counts and len(daily_counts) >= 2:
            mean_daily = statistics.mean(daily_counts)
            burst_score = round(max(daily_counts) / mean_daily, 2) if mean_daily > 0 else None
        else:
            burst_score = None

        # ── Derived: velocity profile ────────────────────────────────
        velocity_profile = self._classify_profile(
            fund_through_rate, dwell_time_hours, n_txs, timestamps,
        )

        # ── Derived: velocity risk score ─────────────────────────────
        velocity_risk_score = self._composite_risk(
            fund_through_rate, consolidation_ratio, value_amplification,
            dwell_time_hours, regularity_score, burst_score,
        )

        # ── Analysis period ──────────────────────────────────────────
        sorted_ts = sorted(timestamps) if timestamps else []
        analysis_period = {}
        if sorted_ts:
            analysis_period = {
                "start": sorted_ts[0].isoformat(),
                "end": sorted_ts[-1].isoformat(),
                "span_days": (sorted_ts[-1] - sorted_ts[0]).days,
            }

        # ── Daily breakdown ──────────────────────────────────────────
        daily_breakdown = self._daily_breakdown(transactions, addr_lower, chain)

        return {
            "address": address,
            "chain": chain,
            "analysis_period": analysis_period,
            "transaction_count": n_txs,
            "metrics": {
                "fund_through_rate": fund_through_rate,
                "consolidation_ratio": consolidation_ratio,
                "value_amplification": value_amplification,
                "dwell_time_hours": dwell_time_hours if dwell_time_hours >= 0 else None,
                "regularity_score": regularity_score,
                "burst_score": burst_score,
            },
            "velocity_risk_score": velocity_risk_score,
            "velocity_profile": velocity_profile,
            "daily_breakdown": daily_breakdown,
            "token_breakdown": token_breakdown,
            "primary_token": primary_token,
        }

    # ── Private helpers ───────────────────────────────────────────────

    def _tx_value(self, tx: Dict[str, Any]) -> float:
        """Extract numeric value from a transaction dict (with raw-unit guard)."""
        return safe_tx_value(tx)

    def _parse_ts(self, tx: Dict[str, Any]) -> Optional[datetime]:
        raw = tx.get("timestamp") or tx.get("block_timestamp") or tx.get("timeStamp")
        if raw is None:
            return None
        try:
            n = float(raw)
            # Auto-detect seconds vs milliseconds
            if n > 1e12:
                n /= 1000
            return datetime.fromtimestamp(n, tz=timezone.utc)
        except (ValueError, TypeError, OSError):
            return None

    def _compute_dwell_time(
        self,
        incoming: List[Dict],
        outgoing: List[Dict],
        addr_lower: str,
    ) -> float:
        """Median hours between consecutive receive → send pairs."""
        in_times = sorted(
            [self._parse_ts(tx) for tx in incoming if self._parse_ts(tx)],
        )
        out_times = sorted(
            [self._parse_ts(tx) for tx in outgoing if self._parse_ts(tx)],
        )
        if not in_times or not out_times:
            return -1.0  # insufficient data

        dwells: List[float] = []
        out_idx = 0
        for recv_ts in in_times:
            # Find next outgoing tx after this receive
            while out_idx < len(out_times) and out_times[out_idx] <= recv_ts:
                out_idx += 1
            if out_idx < len(out_times):
                gap = (out_times[out_idx] - recv_ts).total_seconds() / 3600
                dwells.append(gap)

        if not dwells:
            return -1.0
        return round(statistics.median(dwells), 2)

    def _daily_counts(self, timestamps: List[datetime]) -> List[int]:
        day_map: Dict[str, int] = defaultdict(int)
        for ts in timestamps:
            day_map[ts.strftime("%Y-%m-%d")] += 1
        return list(day_map.values())

    def _classify_profile(
        self,
        ftr: float,
        dwell: float,
        n_txs: int,
        timestamps: List[datetime],
    ) -> str:
        if n_txs == 0:
            return "Dormant"
        # Check if dormant: span > 90 days but fewer than 5 txs
        if timestamps and len(timestamps) >= 2:
            span = (max(timestamps) - min(timestamps)).days
            if span > 90 and n_txs < 5:
                return "Dormant"

        if ftr >= 0.90 and dwell != -1.0 and dwell < 24:
            return "Relay"
        if ftr <= 0.20:
            return "Accumulator"
        if ftr >= 1.5:
            return "Distributor"
        return "Mixed"

    def _composite_risk(
        self,
        ftr: float,
        consolidation: float,
        amplification: float,
        dwell: float,
        regularity: float | None,
        burst: float | None,
    ) -> float:
        """Weighted composite risk score (0-1).

        When a metric is unavailable (e.g. dwell_time = -1 for insufficient
        data), it is excluded from the weighted sum and remaining weights are
        normalised.  This prevents fabricating phantom risk from missing data.
        """
        # Fund-through near 1.0 is suspicious (relay); FTR >> 1 is suspicious (distributor/exploit)
        if ftr <= 2.0:
            ftr_risk = 1.0 - abs(ftr - 1.0)
        else:
            # FTR > 2 means massive distribution — high risk (exploit, mixer, bridge hack)
            ftr_risk = min(0.5 + (ftr - 2.0) / 20.0, 0.95)

        # Consolidation is mildly suspicious
        consol_risk = min(consolidation * 2, 1.0)

        # High amplification is suspicious (whale-type outlier txs)
        amp_risk = min(amplification / 100.0, 1.0) if amplification > 0 else 0.0

        # Build weighted components — unknown metrics are excluded (not fabricated)
        components: list[tuple[float, float]] = [
            (ftr_risk, 0.25),
            (consol_risk, 0.10),
            (amp_risk, 0.10),
        ]

        # Low regularity CV means bot-like — only include when computed
        if regularity is not None:
            if regularity == 0:
                reg_risk = 0.3
            elif regularity < 0.3:
                reg_risk = 0.8
            elif regularity < 0.6:
                reg_risk = 0.5
            else:
                reg_risk = 0.1
            components.append((reg_risk, 0.15))

        # High burst is suspicious — only include when computed
        if burst is not None:
            burst_risk = min(burst / 10.0, 1.0) if burst > 0 else 0.0
            components.append((burst_risk, 0.15))

        # Dwell time: only include when we have real data (>= 0)
        if dwell >= 0:
            if dwell < 2:
                dwell_risk = 0.9
            elif dwell < 24:
                dwell_risk = 0.5
            else:
                dwell_risk = 0.1
            components.append((dwell_risk, 0.25))

        total_weight = sum(w for _, w in components)
        if total_weight == 0:
            return 0.0
        score = sum(r * w for r, w in components) / total_weight
        return round(min(score, 0.95), 3)

    def _daily_breakdown(
        self,
        transactions: List[Dict],
        addr_lower: str,
        chain: str,
    ) -> List[Dict[str, Any]]:
        """Per-day tx count + volume summary."""
        days: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"tx_count": 0, "inflow": 0.0, "outflow": 0.0}
        )
        for tx in transactions:
            ts = self._parse_ts(tx)
            if not ts:
                continue
            day_key = ts.strftime("%Y-%m-%d")
            entry = days[day_key]
            entry["tx_count"] += 1
            val = self._tx_value(tx)
            from_addr = normalize_address(tx.get("from") or tx.get("from_address") or "", chain)
            if from_addr == addr_lower:
                entry["outflow"] += val
            else:
                entry["inflow"] += val

        return [
            {"date": k, **{mk: round(mv, 4) if isinstance(mv, float) else mv for mk, mv in v.items()}}
            for k, v in sorted(days.items())
        ]

    def _empty_result(self, address: str, chain: str) -> Dict[str, Any]:
        return {
            "address": address,
            "chain": chain,
            "analysis_period": {},
            "transaction_count": 0,
            "metrics": {
                "fund_through_rate": 0.0,
                "consolidation_ratio": 0.0,
                "value_amplification": 0.0,
                "dwell_time_hours": -1.0,
                "regularity_score": None,
                "burst_score": None,
            },
            "velocity_risk_score": 0.0,
            "velocity_profile": "Dormant",
            "daily_breakdown": [],
        }


# Module-level singleton — VelocityAnalyzer is stateless (pure computation on input).
velocity_analyzer = VelocityAnalyzer()
