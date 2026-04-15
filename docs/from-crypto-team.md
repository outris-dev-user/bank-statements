TL;DR
Ask	Effort	Recommendation
Small asks (1,2,3) — tag files, ping on changes, don't leak crypto concepts	~4 hours total, one-time	✅ Do it this week
Optional big ask (4) — move platform modules to platform/ subdir	3-5 days + risk	⚠️ Defer — revisit in 2 months when shared surface is stable
Ongoing: interface-change pings	~30 min/week	✅ Easy commitment
Reality check on the module list
Their list is broadly right but a few modules are less platform-ready than the doc implies:

Genuinely clean (tag + they copy, zero changes needed)
backend/app/models/case.py, investigation.py ✅
backend/app/analysis/signal_assembler.py ✅ (TESTED/CLEAR/NOT_TESTED is pure logic)
backend/app/analysis/velocity_analyzer.py ✅ (ratio-based math, currency-agnostic)
backend/app/analysis/transaction_pool.py ✅
backend/app/utils/auth.py ✅
Grey zone — needs cleanup before they can copy zero-change
Module	Issue	Fix effort
exposure_analyzer.py	Hardcoded to crypto entity types (mixer, exchange, DEX)	~0.5 day — inject stop_entity_types as a parameter
counterparty_triage.py	_select_for_canvas() has crypto-specific ranking	~0.5 day — extract scoring as strategy callback
pattern_detector.py	Framework is clean, but 19 crypto patterns live in same file	~1 day — split pattern_framework.py (generic) from patterns/crypto/*.py (domain). Already on our own tech debt list
entity_constants.py	EXCHANGE_BRAND_KEYWORDS is crypto-only, but resolve_entity_type() is generic	~0.5 day — rename module to entity_classification.py, move crypto keywords to crypto/entity_keywords.py
investigation_orchestrator.py	Step names backward_trace / forward_trace are crypto-flavoured. SSE machinery is generic.	~0.5 day — rename to upstream/downstream (benefits us too)
Frontend — MORE coupled than the doc admits
Module	Reality
GraphCanvas.tsx	2,500+ lines. Has UTXO node shapes, privacy chain styles, DEX swap edges, gold-path from auto-trace, subcategory borders (12 types), common-attribution hubs. Copy-and-fork is the only realistic path — they should expect to maintain their own fork.
Zustand stores	useGraphStore + useTransactionStore + useFtmStore have transaction-shaped data. useSelectionStore, useFilterStore, useInvestigationStore are clean.
NodeInspector/*	Tab structure is clean (OverviewTab, ActivityTab, IntelligenceTab, AnalysisTab, ActionsTab). Tab contents have heavy crypto assumptions — they'll reskin most of them.
CaseSelectionModal.tsx, CsvImportModal.tsx	Clean — minor FIR field renames
AutoInvestigateReport.tsx	3,000+ lines of HTML generation — lots of crypto-specific sections. Skeleton reusable, ~60% of content will be their own
What I'd actually commit to doing
Phase 1 — This week (half a day)
Add # PLATFORM — Safe to copy header to the cleanly-platform files (10-15 files). Example marker:

# PLATFORM — Safe to copy to sibling projects (bank-analyser, etc.).
# Domain-agnostic. Do not add chain-specific imports here.
# Cross-project consumers: ping #platform-sync on interface changes.
Add PLATFORM_MODULES.md at repo root with the 3-tier table (platform / grey / domain). I already did this mental mapping above — just needs polishing.
Add R28 to CLAUDE.md: "Files tagged # PLATFORM must not import from services/fetchers/, analysis/privacy_chains.py, analysis/dex_decoder.py, or any other crypto-specific module. Tests enforce this via a lint script."
Simple lint guard (30 lines of Python) that greps PLATFORM-tagged files for banned imports. Added to pre-commit.
Phase 2 — Opportunistic over next 2-4 weeks (2-3 days spread out)
The grey-zone refactors listed above. We benefit from these anyway — they're pre-existing tech debt the bank project is just giving us an excuse to pay down.

Phase 3 — Physical platform/ subdirectory extraction — DEFER
Don't do this yet. Reasons:

Imports would change across ~100+ files → risk of breaking subtle things during the move
We don't yet know the real shape of the shared surface — extracting prematurely means we'll refactor the extraction later
They said the tag approach works if the subdir is disruptive
Revisit after they've synced for ~2 months. By then we'll know:

Which modules actually get modified on their side (signs of missing abstraction)
Which signatures change frequently on our side (candidates for stabilisation)
Whether the sync script is actually painful or fine
Concerns / pushbacks to raise with Saurabh
Recent central hooks may affect sync: In the last 2 days we added R23-R27 — Arkham circuit breaker, warm_triage_batch, auto chain-probe in get_address_transactions, AdaptiveFetcher in trace_path, viewport preservation, common-attribution edges. The chain-probe and Arkham pieces are crypto-only, but AdaptiveFetcher's new call-site inside trace_path is something they'll inherit automatically if they copy graph_service.py. Worth a walk-through.

graph_service.py is a monolith. ~3,200 lines. They want "BFS section only" — that implies splitting it, which is a bigger refactor than they've scoped. Offer: we can extract bfs_trace.py as a focused module (~300 lines) — benefits us too.

Neo4j vs NetworkX-only. They want offline = no Neo4j. Our graph_storage.py is a Neo4j wrapper. They'll need to fork it with a NetworkX-backed implementation. Offer: we can define an abstract GraphStore protocol and let them implement their own — this is another pre-existing tech-debt win for us.

Cross-reference API (their question 4) is bigger than the current scope. "A single case shows crypto wallets AND bank accounts" means shared Person/Entity model with uniform ID. That's a month-long conversation, not part of this ask. Park it for now.

Push back on "signal_assembler.py unchanged": The EXPOSURE family assessor is hardcoded to crypto category names (mixer/exchange/etc.). Assembler scaffold is clean, but signal families need the same "inject domain" treatment as exposure_analyzer.

Suggested response to Saurabh
Answer to his four questions:

Split feels right, with caveats — exposure_analyzer, counterparty_triage, pattern_detector, entity_constants are grey-zone. We'll cleanup over 2-3 weeks. signal_assembler's EXPOSURE family needs the same treatment.

Tag approach this week, platform/ subdir deferred by 2 months — inline tag + PLATFORM_MODULES.md + lint guard is ~4 hours, physical extraction is 3-5 days with import breakage risk.

Recent changes to flag: 6 central hooks landed last week (R23-R27). AdaptiveFetcher now powers trace_path retries, entity resolution has fallback chain when Arkham 402s, GraphService auto-probes EVM chains on 0-tx, viewport preservation on expand, common-attribution edges. Want a 30-min walk-through before they sync.

Cross-reference API — not now. Great idea; bigger conversation; let's revisit after both products are live.

Counter-proposal: let's meet this Friday. They bring their core/ skeleton; I bring the PLATFORM_MODULES.md and walk them through the grey zones. Then two weeks later we assess Phase 2 ordering based on what they actually hit first.

One-line estimate
4 hours this week for Phase 1 + 2-3 days of opportunistic grey-zone cleanup over the next month. No blockers, no significant architectural compromises on our side, and most of the cleanup work pays off for us too.

Want me to draft the PLATFORM_MODULES.md + the # PLATFORM header template now? That's the concrete Phase 1 deliverable.

