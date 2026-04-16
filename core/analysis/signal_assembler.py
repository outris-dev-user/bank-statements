# Copied from crypto/india-le-platform/backend/app/analysis/signal_assembler.py
# at commit 9e7d7b8 on 2026-04-16.
# Sync via tools/sync-from-crypto.sh. If you need to change behaviour,
# change upstream first if possible.
# Local changes (if any) documented at the bottom of CRYPTO_SYNC.md.

"""Signal Assembler — aggregates all available signals for an address into a structured per-family report.

Called before AI narrative generation to provide the LLM with structured, server-side intelligence
instead of relying on naive client-side flags. Each of the 8 signal families is independently
assessed and can be triggered, clear, or not-available.

Taxonomy:
  1. Entity/Attribution — known entity DB + scraped ChainAbuse data
  2. Behavioral Pattern — PatternDetector typologies + VelocityAnalyzer profile
  3. Exposure Composition — 1-hop source/destination risk breakdown
  4. Graph Topology — frontend-provided summary (server can't compute without full graph)
  5. Temporal Anomaly — cadence regularity, burst score from velocity metrics
  6. External Intelligence — scraped DB entities + live GoPlus/Etherscan feeds
  7. P2P/UPI Behavioral — P2P advertisement presence
  8. OSINT/Social — manual only, always not_available
"""
# PLATFORM — Safe to copy to sibling LEA-forensic-platform projects.
# Domain-agnostic scaffolding. The 8-family assessor shape is platform;
# individual assessor bodies that reference crypto-specific categories are
# grey-zone (see PLATFORM_MODULES.md). Do NOT add imports from
# services/fetchers/*, analysis/dex_decoder.py, analysis/privacy_chains.py,
# or any other crypto-specific module.
# Cross-project consumers: ping Saurabh / #platform-sync on interface changes.

from __future__ import annotations

import asyncio
import structlog
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = structlog.get_logger()

TransactionFetcher = Callable[[str, str], Awaitable[List[Dict[str, Any]]]]

# Default exposure high-risk category vocabulary is crypto-flavoured.
# Bank-analyser (or any sibling domain) passes its own set through the
# SignalAssembler constructor — no keyword lives inside signal logic itself.
_DEFAULT_EXPOSURE_HIGH_RISK_CATEGORIES: frozenset = frozenset(
    {"mixer", "sanctioned", "scam", "darknet_market", "ransomware"}
)


class SignalAssembler:
    """Aggregate all available signals for an address into a structured per-family report."""

    def __init__(
        self,
        transaction_fetcher: Optional[TransactionFetcher] = None,
        exposure_high_risk_categories: Optional[frozenset] = None,
    ) -> None:
        # Both injected by the domain layer so this module stays domain-agnostic.
        # Crypto callers pass a thin wrapper around GraphService.get_address_transactions
        # and accept the default exposure category vocabulary.
        self._transaction_fetcher = transaction_fetcher
        self._exposure_high_risk_categories = (
            frozenset(exposure_high_risk_categories)
            if exposure_high_risk_categories is not None
            else _DEFAULT_EXPOSURE_HIGH_RISK_CATEGORIES
        )

    async def assemble(
        self,
        address: str,
        chain: str,
        transactions: Optional[List[Dict[str, Any]]] = None,
        graph_summary: Optional[Dict[str, Any]] = None,
        counterparty_entities: Optional[List[Dict[str, Any]]] = None,
        entity_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run all signal families and return structured report.

        Args:
            address: The blockchain address to assess.
            chain: Chain identifier (ETH, BTC, TRX, etc.).
            transactions: Pre-fetched transactions (avoids re-fetch if caller has them).
            graph_summary: Frontend graph_data.summary dict (node_count, edge_count, etc.).
            counterparty_entities: Known counterparty entities from prior investigation
                steps (e.g. counterparty_triage). Each dict should have at minimum
                ``entity`` (name) and optionally ``address``, ``risk_tier``, ``volume``.
            entity_snapshot: Pre-investigation entity DB snapshot for the target address.
                When provided, _assess_entity uses this instead of live DB lookup,
                ensuring signal assessment is not affected by entity mutations from
                earlier pipeline steps (C3 fix).

        Returns:
            Structured dict with per-family results, trigger counts, and escalation recommendation.
        """
        # Fetch transactions if not provided (needed for families 2 and 5)
        if transactions is None:
            transactions = await self._fetch_transactions(address, chain)

        # Run independent IO families concurrently (1, 6, 7)
        entity_task = self._assess_entity(address, chain, counterparty_entities=counterparty_entities, entity_snapshot=entity_snapshot)
        external_task = self._assess_external_intelligence(address, chain)
        p2p_task = self._assess_p2p(address)

        io_results = await asyncio.gather(
            entity_task, external_task, p2p_task,
            return_exceptions=True,
        )

        entity_result = io_results[0] if not isinstance(io_results[0], Exception) else self._error_family(io_results[0])
        external_result = io_results[1] if not isinstance(io_results[1], Exception) else self._error_family(io_results[1])
        p2p_result = io_results[2] if not isinstance(io_results[2], Exception) else self._error_family(io_results[2])

        # Family 2 — Behavioral (needs transactions)
        behavioral_result = await self._assess_behavioral(address, chain, transactions)

        # Family 3 — Exposure (pass transactions to avoid redundant fetch)
        exposure_result = await self._assess_exposure(address, chain, transactions=transactions)

        # Family 4 — Graph Topology (from frontend summary, with fallback from behavioral data)
        topology_result = self._assess_graph_topology(graph_summary, behavioral_result)

        # Family 5 — Temporal Anomaly (uses velocity metrics from behavioral + pattern data)
        temporal_result = self._assess_temporal(behavioral_result)

        # Family 8 — OSINT (always not available on server side)
        # No OSINT scraping pipeline integrated — social media, dark-web forums,
        # and P2P ad platforms are not automatically indexed. Analysts must
        # manually cross-reference findings. Tracking issue: V2 backlog #22.
        osint_result = {"triggered": None, "signals": [], "details": {}}

        families = {
            "entity_attribution": entity_result,
            "behavioral_pattern": behavioral_result,
            "exposure_composition": exposure_result,
            "graph_topology": topology_result,
            "temporal_anomaly": temporal_result,
            "external_intelligence": external_result,
            "p2p_behavioral": p2p_result,
            "osint_social": osint_result,
        }

        # Count
        families_triggered = sum(1 for f in families.values() if f.get("triggered") is True)
        families_tested = sum(1 for f in families.values() if f.get("triggered") is not None)
        families_not_available = sum(1 for f in families.values() if f.get("triggered") is None)

        # Escalation recommendation
        escalation = self._compute_escalation(
            families_triggered, families_not_available, graph_summary,
            families=families, behavioral_result=behavioral_result,
        )

        # Score contradiction detection (#18)
        score_contradictions = self._detect_contradictions(behavioral_result, address, chain, families)

        # Strip internal-only keys before sending to frontend
        # _velocity_raw is used by _assess_temporal / _assess_graph_topology above
        # but contains huge nested data (daily_breakdown, metrics) that causes
        # [object Object] rendering issues on the frontend.
        behavioral_details = behavioral_result.get("details", {})
        behavioral_details.pop("_velocity_raw", None)

        return {
            "address": address,
            "chain": chain,
            "signal_families": families,
            "families_triggered": families_triggered,
            "families_tested": families_tested,
            "families_not_available": families_not_available,
            "escalation_recommendation": escalation,
            "score_contradictions": score_contradictions,
        }

    # ── Family assessors ──

    async def _assess_entity(
        self,
        address: str,
        chain: str,
        counterparty_entities: Optional[List[Dict[str, Any]]] = None,
        entity_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Family 1 — Entity/Attribution: known entity DB + scraped ChainAbuse data.

        When ``entity_snapshot`` is provided, uses that pre-investigation snapshot
        instead of live DB lookup (C3 fix — prevents entity attribution regression
        between investigation runs).

        When ``counterparty_entities`` is provided (from prior investigation steps
        like counterparty_triage), we incorporate those findings as *contextual*
        signals.  This prevents the family from returning CLEAR when the root
        address itself is unattributed but transacts directly with known exchanges,
        sanctioned wallets, or flagged entities.
        """
        signals: List[str] = []
        details: Dict[str, Any] = {}
        try:
            from app.services.entities import entity_database_service, entity_service

            # C3: Use pre-investigation snapshot if provided, else live DB lookup
            db_entity = entity_snapshot if entity_snapshot is not None else await entity_database_service.lookup_address(address, chain)
            if db_entity:
                db_confidence = db_entity.get("confidence")
                db_confidence = float(db_confidence) if db_confidence is not None else 0.0
                details["db_entity"] = {
                    "name": db_entity.get("name"),
                    "category": db_entity.get("category"),
                    "source": db_entity.get("source"),
                    "risk_level": db_entity.get("risk_level"),
                    "confidence": db_confidence,
                }
                source = db_entity.get("source", "")
                if "chainabuse" in source:
                    signals.append("chainabuse_scraped")
                risk_level = db_entity.get("risk_level", "")
                category = db_entity.get("category", "")
                if risk_level in ("high", "critical") or category in ("scam", "mixer", "ransomware", "phishing"):
                    signals.append("known_entity")
                # Exchange entity match — meaningful for fund-flow even if low risk
                if category in ("exchange", "high_risk_exchange") and source != "heuristic":
                    signals.append("known_exchange")
                elif category in ("exchange", "high_risk_exchange") and source == "heuristic":
                    # Only trigger if heuristic confidence is meaningful (>=0.5)
                    if db_confidence >= 0.5:
                        signals.append("heuristic_exchange")

            # In-memory entity lookup (sync, covers known_entities.json)
            mem_entity = entity_service.lookup(address)
            if mem_entity and not db_entity:
                details["mem_entity"] = {
                    "name": mem_entity.get("name"),
                    "type": mem_entity.get("type"),
                }
                risk_score = mem_entity.get("risk_score", 0)
                if risk_score >= 0.6:
                    signals.append("known_entity")

            # Sanctions check
            from app.services.sanctions_service import sanctions_service
            sanctions_hit = sanctions_service.check_address(address)
            if sanctions_hit:
                signals.append("sanctions_hit")
                details["sanctions"] = sanctions_hit

            # ── Contextual counterparty attribution ──
            # When prior investigation steps (counterparty_triage) have already
            # identified named entities among direct counterparties, incorporate
            # that context.  This is separate from the root address's own
            # attribution — it signals that the address *interacts with* known
            # entities, which is material for LE risk assessment.
            if counterparty_entities:
                cp_named = [
                    cp for cp in counterparty_entities
                    if cp.get("entity") and cp["entity"] not in ("Unknown", "unknown", None)
                ]
                if cp_named:
                    cp_exchange = [cp for cp in cp_named if "exchange" in (cp.get("entity") or "").lower()
                                   or "binance" in (cp.get("entity") or "").lower()
                                   or "coinbase" in (cp.get("entity") or "").lower()]
                    cp_risky = [cp for cp in cp_named if cp.get("risk_tier") in ("severe", "high")]
                    if cp_exchange:
                        signals.append("counterparty_exchange")
                        details["counterparty_exchanges"] = [
                            {"entity": cp.get("entity"), "address": cp.get("address")}
                            for cp in cp_exchange[:3]
                        ]
                    if cp_risky:
                        signals.append("counterparty_high_risk")
                        details["counterparty_high_risk"] = [
                            {"entity": cp.get("entity"), "risk_tier": cp.get("risk_tier"),
                             "address": cp.get("address")}
                            for cp in cp_risky[:3]
                        ]
                    # Even non-exchange, non-risky named counterparties are
                    # evidence of attribution context
                    if len(cp_named) >= 2 and not cp_exchange and not cp_risky:
                        signals.append("counterparty_attributed")
                        details["counterparty_attributed_count"] = len(cp_named)

        except Exception as exc:
            logger.debug("Entity family assessment failed", error=str(exc))
            # Exception means we couldn't check — truly not tested
            return {"triggered": None, "signals": [], "details": {"error": str(exc)}}

        # If we reached here, the check DID run. Distinguish "checked, clean" from "not checked".
        triggered = bool(signals)
        return {"triggered": triggered, "signals": signals, "details": details}

    async def _assess_behavioral(
        self, address: str, chain: str, transactions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Family 2 — Behavioral Pattern: PatternDetector + VelocityAnalyzer."""
        signals: List[str] = []
        details: Dict[str, Any] = {}
        try:
            from app.analysis.pattern_detector import pattern_detector
            patterns = await pattern_detector.analyze_address(address, chain, transactions=transactions)
            if patterns:
                for p in patterns:
                    signals.append(f"pattern_{p.get('pattern', 'unknown')}")
                details["patterns"] = patterns
        except Exception as exc:
            logger.debug("Pattern detection failed in signal assembly", error=str(exc))

        # Velocity analysis
        velocity_data = None
        if len(transactions) >= 5:
            try:
                from app.analysis.velocity_analyzer import velocity_analyzer
                velocity = await velocity_analyzer.analyze(
                    address=address, chain=chain, transactions=transactions,
                )
                velocity_data = velocity
                details["velocity"] = {
                    "profile": velocity.get("velocity_profile"),
                    "risk_score": velocity.get("velocity_risk_score"),
                    "fund_through_rate": velocity.get("metrics", {}).get("fund_through_rate"),
                    "dwell_time_hours": velocity.get("metrics", {}).get("dwell_time_hours"),
                    "regularity_score": velocity.get("metrics", {}).get("regularity_score"),
                    "burst_score": velocity.get("metrics", {}).get("burst_score"),
                }
                v_profile = velocity.get("velocity_profile", "Mixed")
                if v_profile in ("Relay", "Distributor"):
                    signals.append(f"velocity_profile_{v_profile.lower()}")
                if velocity.get("metrics", {}).get("fund_through_rate", 0) >= 0.90:
                    signals.append("high_fund_through_rate")
            except Exception as exc:
                logger.debug("Velocity analysis failed in signal assembly", error=str(exc))

        # Store velocity_data in details for temporal family to reference
        details["_velocity_raw"] = velocity_data

        triggered = bool(signals)
        return {"triggered": triggered, "signals": signals, "details": details}

    async def _assess_exposure(
        self, address: str, chain: str,
        transactions: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Family 3 — Exposure Composition: 1-hop source/destination risk."""
        signals: List[str] = []
        details: Dict[str, Any] = {}
        try:
            from app.analysis.exposure_analyzer import exposure_analyzer
            exposure = await exposure_analyzer.analyze(address, chain, limit=50, transactions=transactions)
            if exposure:
                src_risk = exposure.get("source_risk_score", 0)
                dst_risk = exposure.get("destination_risk_score", 0)
                risky_cps = exposure.get("risky_counterparties", [])
                details["source_risk"] = src_risk
                details["destination_risk"] = dst_risk
                details["risky_counterparty_count"] = len(risky_cps)

                if src_risk > 0.4 or dst_risk > 0.4:
                    signals.append("high_risk_exposure")
                if risky_cps:
                    signals.append(f"risky_counterparties_{len(risky_cps)}")

                # Check unknown percentage in BOTH source and destination exposure
                for direction in ("source_exposure", "destination_exposure"):
                    for entry in exposure.get(direction, []):
                        if entry.get("category") == "Unknown" and entry.get("pct", 0) > 60:
                            signal_key = f"high_unknown_{direction.split('_')[0]}_pct"
                            signals.append(signal_key)
                            details[f"unknown_{direction.split('_')[0]}_pct"] = entry["pct"]
                            break  # only first match per direction

                # Also flag specific high-risk categories in exposure.
                # Vocabulary is domain-injected (see __init__ default for crypto set).
                high_risk_cats = self._exposure_high_risk_categories
                for direction in ("source_exposure", "destination_exposure"):
                    for entry in exposure.get(direction, []):
                        cat = (entry.get("category") or "").lower().replace(" ", "_")
                        if cat in high_risk_cats and entry.get("pct", 0) > 5:
                            signals.append(f"exposure_{cat}_{direction.split('_')[0]}")
                            details.setdefault("risky_exposure_categories", []).append(
                                {"category": cat, "direction": direction.split("_")[0], "pct": entry["pct"]}
                            )
        except Exception as exc:
            logger.debug("Exposure assessment failed in signal assembly", error=str(exc))
            return {"triggered": None, "signals": [], "details": {"error": str(exc)}}

        # If we have details (exposure ran), distinguish "checked, clean" from "not checked"
        triggered = bool(signals) if details else None
        return {"triggered": triggered, "signals": signals, "details": details}

    def _assess_graph_topology(
        self,
        graph_summary: Optional[Dict[str, Any]],
        behavioral_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Family 4 — Graph Topology: from frontend-provided summary.

        Falls back to proxy metrics derived from transaction/velocity data when
        no graph_summary is provided (server-side invocation without a graph).
        """
        if graph_summary:
            signals: List[str] = []
            details: Dict[str, Any] = {
                "node_count": graph_summary.get("node_count"),
                "edge_count": graph_summary.get("edge_count"),
                "unique_counterparties": graph_summary.get("unique_counterparties"),
            }
            node_count = graph_summary.get("node_count", 0) or 0
            counterparties = graph_summary.get("unique_counterparties", 0) or 0
            if node_count > 50:
                signals.append("large_graph")
            if counterparties > 30:
                signals.append("many_counterparties")
            triggered = bool(signals)
            return {"triggered": triggered, "signals": signals, "details": details}

        # Fallback: derive proxy topology signals from velocity/transaction data
        velocity = behavioral_result.get("details", {}).get("_velocity_raw") if behavioral_result else None
        if not velocity:
            return {"triggered": None, "signals": [], "details": {}}

        metrics = velocity.get("metrics", {})
        tx_count = velocity.get("transaction_count", 0) or 0
        ftr = metrics.get("fund_through_rate", 0) or 0

        signals = []
        details = {"computed_from": "transaction_data", "tx_count": tx_count, "fund_through_rate": ftr}

        if tx_count > 100:
            signals.append("high_tx_volume")
        if ftr >= 0.9:
            signals.append("relay_topology")

        triggered = bool(signals) if tx_count > 0 else None
        return {"triggered": triggered, "signals": signals, "details": details}

    def _assess_temporal(self, behavioral_result: Dict[str, Any]) -> Dict[str, Any]:
        """Family 5 — Temporal Anomaly: cadence regularity, burst score from velocity."""
        signals: List[str] = []
        details: Dict[str, Any] = {}

        velocity = behavioral_result.get("details", {}).get("_velocity_raw")
        patterns = behavioral_result.get("details", {}).get("patterns", [])

        # Check for automated cadence pattern
        for p in patterns:
            if p.get("pattern") == "automated_cadence":
                signals.append("regular_cadence")
                details["cadence_confidence"] = p.get("confidence")
                break

        if velocity:
            metrics = velocity.get("metrics", {})
            regularity = metrics.get("regularity_score")
            burst = metrics.get("burst_score")

            if regularity is not None:
                details["regularity_score"] = regularity
                if regularity < 0.4:
                    signals.append("high_regularity")
            if burst is not None:
                details["burst_score"] = burst
                if burst > 3.0:
                    signals.append("high_burst")

        triggered = bool(signals) if (velocity or patterns) else None
        return {"triggered": triggered, "signals": signals, "details": details}

    async def _assess_external_intelligence(self, address: str, chain: str) -> Dict[str, Any]:
        """Family 6 — External Intelligence: scraped DB entities + live feeds."""
        signals: List[str] = []
        details: Dict[str, Any] = {}
        try:
            # Check entity DB for scraped sources (ChainAbuse, Reddit, BitcoinTalk)
            from app.services.entities import entity_database_service
            db_entity = await entity_database_service.lookup_address(address, chain)
            if db_entity:
                source = db_entity.get("source", "")
                if "chainabuse" in source:
                    signals.append("chainabuse_reports")
                    details["chainabuse_entity"] = db_entity.get("name")
                if "reddit" in source:
                    signals.append("reddit_reports")
                if "bitcointalk" in source:
                    signals.append("bitcointalk_reports")

            # Live external feeds (GoPlus, Etherscan labels)
            from app.services.external_feeds import external_feeds_service
            feed_hit = await external_feeds_service.check_address(address, chain)
            if feed_hit:
                for src in feed_hit.get("sources", []):
                    if "goplus" in src:
                        signals.append("goplus_flags")
                    if "etherscan" in src:
                        signals.append("etherscan_label")
                    if "scraped" in src:
                        signals.append("scraped_intelligence")
                details["feed_categories"] = feed_hit.get("categories", [])
                details["feed_risk_score"] = feed_hit.get("risk_score", 0)
        except Exception as exc:
            logger.debug("External intelligence assessment failed", error=str(exc))
            return {"triggered": None, "signals": [], "details": {"error": str(exc)}}

        # If we reached here, at least one check ran. Distinguish "checked, clean" from "not checked".
        triggered = bool(signals)
        return {"triggered": triggered, "signals": signals, "details": details}

    async def _assess_p2p(self, address: str) -> Dict[str, Any]:
        """Family 7 — P2P/UPI Behavioral: check P2P advertisement platforms."""
        signals: List[str] = []
        details: Dict[str, Any] = {}
        _check_ran = False
        try:
            from app.services.p2p_ingestion import p2p_service
            ads = await p2p_service.check_address(address)
            _check_ran = True
            if ads:
                signals.append("active_p2p_trader")
                details["ad_count"] = len(ads)
                details["platforms"] = list({a.get("platform") for a in ads if a.get("platform")})
        except Exception as exc:
            logger.debug("P2P assessment failed in signal assembly", error=str(exc))

        # R10: True=TRIGGERED, False=CLEAR (check ran, nothing found), None=NOT TESTED
        triggered = True if signals else (False if _check_ran else None)
        return {"triggered": triggered, "signals": signals, "details": details}

    # ── Helpers ──

    # Signals that are structurally inherent to Accumulator-profile addresses
    # (high fan-in, many counterparties, regular cadence).  When ALL triggered
    # signals fall within this set and the velocity profile is "Accumulator",
    # ESCALATE is misleading — downgrade to INVESTIGATE.  Only ESCALATE when
    # there is scam exposure, sanctions, external intelligence, or other
    # non-inherent evidence.
    _ACCUMULATOR_INHERENT_SIGNALS = {
        # behavioral_pattern family
        "pattern_fan_in", "pattern_honeypot", "pattern_automated_cadence",
        "pattern_consolidate_disperse", "pattern_whale_alert",
        # graph_topology family
        "many_counterparties", "large_graph", "high_tx_volume",
        # temporal_anomaly family — high_burst is inherent for accumulators because
        # sporadic large deposits (e.g. 30 ETH followed by weeks of quiet) naturally
        # produce high burst_score without indicating suspicious activity.
        "regular_cadence", "high_regularity", "high_burst",
        # entity_attribution — counterparty context (exchange interaction is normal for accumulators)
        "counterparty_exchange", "counterparty_attributed",
        "known_exchange", "heuristic_exchange",
    }

    def _compute_escalation(
        self,
        families_triggered: int,
        families_not_available: int,
        graph_summary: Optional[Dict[str, Any]],
        families: Optional[Dict[str, Any]] = None,
        behavioral_result: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Compute escalation recommendation, distinguishing data gaps from clean results.

        When several transaction-dependent families are "not tested" because
        the upstream API failed (data_quality metadata shows 'unavailable' or
        'error'), returning DEPRIORITIZE is misleading — it implies the address
        was checked and found clean. Instead we return INSUFFICIENT_DATA so the
        AI narrative and LE report accurately convey data uncertainty.

        Accumulator gate: when the velocity profile is "Accumulator" and ALL
        triggered signals are structurally inherent to accumulator behaviour
        (fan_in, many_counterparties, cadence), cap at INVESTIGATE.  Only
        ESCALATE when there is scam exposure, sanctions, or external
        intelligence that goes beyond accumulator-inherent patterns.
        """
        if families_triggered >= 3:
            # ── Accumulator gate ──
            # Check if this is an Accumulator profile with only inherent signals
            if self._is_accumulator_inherent_only(families, behavioral_result):
                logger.info(
                    "signal_assembler.accumulator_gate_downgrade",
                    families_triggered=families_triggered,
                    msg="All triggered signals are accumulator-inherent — capping at INVESTIGATE",
                )
                return "INVESTIGATE"
            return "ESCALATE"
        if families_triggered == 2:
            return "INVESTIGATE"
        if families_triggered == 1:
            return "MONITOR"

        # 0 families triggered — but was this because the address is clean,
        # or because we couldn't check?
        if families_not_available >= 3:
            # 3+ families couldn't even run — likely a systemic data issue.
            # Check data_quality to confirm upstream failures vs. inherent limits.
            data_quality = (graph_summary or {}).get("data_quality") or {}
            upstream_failures = sum(
                1 for v in data_quality.values()
                if v in ("error", "unavailable")
            )
            if upstream_failures >= 2:
                return "INSUFFICIENT_DATA"
            # Even without explicit data_quality, 3+ "not tested" families
            # means we had very little to work with.
            return "INSUFFICIENT_DATA"

        return "DEPRIORITIZE"

    async def _fetch_transactions(self, address: str, chain: str) -> List[Dict[str, Any]]:
        """Fetch transactions via the injected fetcher (domain-agnostic)."""
        if self._transaction_fetcher is None:
            logger.debug(
                "Signal assembly has no transaction_fetcher injected; families 2/5 will be NOT_TESTED",
                address=address,
                chain=chain,
            )
            return []
        try:
            return await self._transaction_fetcher(address, chain)
        except Exception as exc:
            logger.debug("Injected transaction fetch failed in signal assembly", error=str(exc))
            return []

    def _is_accumulator_inherent_only(
        self,
        families: Optional[Dict[str, Any]],
        behavioral_result: Optional[Dict[str, Any]],
    ) -> bool:
        """Return True if velocity profile is Accumulator and ALL triggered
        signals across all families are accumulator-inherent.

        Non-inherent signals (scam exposure, sanctions, external intelligence,
        pattern_mixer_hop, etc.) indicate genuine risk beyond what an
        accumulator address would naturally exhibit.
        """
        if not families or not behavioral_result:
            return False

        # Check velocity profile
        velocity_profile = (
            behavioral_result.get("details", {})
            .get("velocity", {})
            .get("profile", "")
        )
        if velocity_profile != "Accumulator":
            return False

        # Collect ALL signals from triggered families
        all_triggered_signals: list = []
        for family_result in families.values():
            if family_result.get("triggered") is True:
                all_triggered_signals.extend(family_result.get("signals", []))

        if not all_triggered_signals:
            return False

        # Check if every signal is in the inherent set
        for signal in all_triggered_signals:
            if signal not in self._ACCUMULATOR_INHERENT_SIGNALS:
                return False

        return True

    def _detect_contradictions(
        self, behavioral_result: Dict[str, Any], address: str, chain: str,
        families: Dict[str, Any] = None,
    ) -> List[str]:
        """Detect score contradictions between velocity risk and static risk indicators."""
        contradictions: List[str] = []
        velocity = behavioral_result.get("details", {}).get("_velocity_raw")
        if not velocity:
            return contradictions

        v_score = velocity.get("velocity_risk_score", 0)
        # Collect signals from ALL families (entity attribution, behavioral, external, etc.)
        all_signals: List[str] = []
        if families:
            for family_result in families.values():
                all_signals.extend(family_result.get("signals", []))
        else:
            all_signals = behavioral_result.get("signals", [])
        # Check if any entity-related signal fired across all families
        entity_keywords = ("known_entity", "known_exchange", "heuristic_exchange", "chainabuse", "sanctions", "arkham")
        if v_score >= 0.5 and not any(kw in s for s in all_signals for kw in entity_keywords):
            contradictions.append(
                f"Velocity risk ({v_score:.2f}) is elevated but no known-entity match — "
                f"behavioral signals outweigh attribution factors"
            )

        # Check if high_unknown_destination_pct is triggered but forward trace found exchanges
        has_unknown_dest = any("high_unknown_destination_pct" in s for s in all_signals)
        dest_entities = [s for s in all_signals if s.startswith("destination_entity:")]
        if has_unknown_dest and dest_entities:
            entity_names = [s.split(":", 1)[1] for s in dest_entities[:5]]
            contradictions.append(
                f"Exposure shows 100% unknown destinations (direct counterparties), "
                f"but forward trace found identified entities at deeper hops: "
                f"{', '.join(entity_names)} — funds ultimately reach known exchanges"
            )

        return contradictions

    @staticmethod
    def _error_family(exc: Exception) -> Dict[str, Any]:
        """Return a not-available family result for failed assessments."""
        return {"triggered": None, "signals": [], "details": {"error": str(exc)}}
