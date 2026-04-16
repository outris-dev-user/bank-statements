# Crypto sync ledger

Tracks what's been copied from the [crypto investigation platform](D:/OneDrive%20-%20Outris/Outris/Product/git-repo/crypto/crypto/india-le-platform) into `core/`, when, and from which commit.

## Sync philosophy

We **physically copy** modules from crypto rather than depending on a published package. This optimises for week-1 speed and reversibility. If sync friction becomes painful in 3-6 months, we'll extract a versioned `platform-core` package and switch both repos to consume it.

Every copied file gets a header:
```python
# Copied from crypto/india-le-platform/<original-path> at commit <sha> on <date>.
# Sync via tools/sync-from-crypto.sh. If you need to change behaviour, change
# upstream first if possible. Local changes documented at the bottom of this file.
```

## Status after crypto team delivery (2026-04-16)

**All cleanup shipped in one day.** Crypto team delivered [for-bank-team-2026-04-15.md](../crypto/india-le-platform/docs/for-bank-team-2026-04-15.md) — all Phase 1 grey-zone items refactored with injection points, plus the two Phase 2 extractions we'd asked about. Every change is additive/non-breaking on their side.

**Our sync plan now has two readiness tiers** (the AWAITING-CLEANUP bucket emptied):
- **READY** — can copy today, zero changes on either side
- **FORK** — frontend pieces that will diverge meaningfully; copy once, maintain locally

## What we plan to copy

### Phase 1 — Backend: Models and analysis framework (ALL READY)

**Tier 1 — safe to copy as-is** (carry `# PLATFORM` header upstream):

| Crypto path | Local path | Notes |
|---|---|---|
| `backend/app/models/case.py` | `core/models/case.py` | Rename `address`→`account` semantics on our side |
| `backend/app/models/investigation.py` | `core/models/investigation.py` | Rename `root_address`→`root_account`, `root_chain`→`root_bank` |
| `backend/app/analysis/velocity_analyzer.py` | `core/analysis/velocity_analyzer.py` | Pure ratio math, zero changes |
| `backend/app/analysis/transaction_pool.py` | `core/analysis/transaction_pool.py` | Per-investigation cache + dedup |
| `backend/app/analysis/signal_assembler.py` | `core/analysis/signal_assembler.py` | Now takes `transaction_fetcher=...` and `exposure_high_risk_categories=...` as constructor args — pass our bank versions |
| `backend/app/analysis/entity_classification.py` | `core/analysis/entity_classification.py` | **NEW** — extracted from entity_constants, keyword maps as parameters. `infer_category_from_name`, `resolve_entity_type`, `name_matches_keywords`, `enrich_path_edge`. |
| `backend/app/analysis/pattern_framework.py` | `core/analysis/pattern_framework.py` | **NEW** — scaffolding only (`parse_datetime`, `classify_direction`, `aggregate_risk_boost`, `severity_bucket`). We build BFSI patterns on top in `plugins/bank/patterns/` |
| `backend/app/utils/auth.py` | `core/auth/jwt.py` | Online deployment only |

**Tier 2 — copy + construct with bank-domain args** (still grey-zone but now injectable):

| Crypto path | Local path | Injection point |
|---|---|---|
| `backend/app/analysis/exposure_analyzer.py` | `core/analysis/multi_hop_exposure.py` | `ExposureAnalyzer(category_risk={bank_risk_categories}, skip_counterparty_addresses={bank_ignored_accounts})` |
| `backend/app/analysis/counterparty_triage.py` | `core/analysis/counterparty_triage.py` | `CounterpartyTriager(canvas_selector=<our callable>)` — strategy pattern |
| `backend/app/services/investigation_orchestrator.py` | `core/orchestration/pipeline.py` | `InvestigationOrchestrator(steps=[bank_step_list], step_budgets={...})`. Subclass + override `_build_step_fns()` for bank steps. |
| `backend/app/analysis/entity_constants.py` | skip | Crypto team says: import directly from `entity_classification.py` with our own keyword map. entity_constants is now a thin wrapper for crypto's own callers. |

### Phase 2 — Backend: Graph and persistence (READY)

| Crypto path | Local path | Notes |
|---|---|---|
| `backend/app/analysis/bfs_trace.py` | `core/graph/bfs_trace.py` | **NEW** — `should_stop_at_entity`, `BFSExpansionContext`, `expand_one_hop`. Full `trace_address()` is *not* extracted (500-line entangled); we assemble our own BFS from these primitives. |
| `backend/app/analysis/graph_store.py` | `core/graph/graph_store.py` | **NEW** — `GraphStore` `@runtime_checkable` Protocol. Their `GraphStorageService` satisfies it structurally. Our NetworkX/SQLite implementation just needs matching method signatures; no inheritance. |

### Phase 3 — Frontend

Frontend coupling is **higher** than initially scoped. Most UI pieces will be **forks**, not live syncs. Crypto's `GraphCanvas.tsx` contains UTXO node shapes, privacy chain styles, DEX swap edges — reskinning is 60-80% of the file, not a label swap.

| Crypto path | Local path | Readiness | Notes |
|---|---|---|---|
| `frontend/src/stores/useSelectionStore.ts` | `core/ui/stores/useSelectionStore.ts` | **READY** | Clean — no crypto-specific data |
| `frontend/src/stores/useFilterStore.ts` | `core/ui/stores/useFilterStore.ts` | **READY** | Clean |
| `frontend/src/stores/useInvestigationStore.ts` | `core/ui/stores/useInvestigationStore.ts` | **READY** | Clean |
| `frontend/src/components/cases/*` | `core/ui/cases/*` | **READY** | Minor FIR field renames |
| `frontend/src/components/CsvImportModal.tsx` | `core/ui/CsvImportModal.tsx` | **READY** | Clean |
| `frontend/src/stores/useGraphStore.ts` | `core/ui/stores/useGraphStore.ts` | **FORK** | Has transaction-shaped data assumptions |
| `frontend/src/stores/useTransactionStore.ts` | `core/ui/stores/useTransactionStore.ts` | **FORK** | Shaped around blockchain tx fields |
| `frontend/src/components/GraphCanvas.tsx` | `core/ui/GraphCanvas.tsx` | **FORK** | 2,500+ lines, crypto-specific node shapes/edges. Copy once, maintain our own. |
| `frontend/src/components/NodeInspector/*` | `core/ui/NodeInspector/*` | **FORK** | Tab structure clean, tab contents heavily crypto. We'll reskin ~70% of tab content, and (per our UX direction) may not use the right-side inspector layout at all — see [docs/ux-phases.md](docs/ux-phases.md). |
| `frontend/src/components/AutoInvestigateReport.tsx` | `core/ui/InvestigationReport.tsx` | **FORK** | 3,000+ lines of HTML. Skeleton reusable, ~60% content our own. |

## Shipped crypto-team offers (2026-04-16)

- **Tier 1 modules tagged `# PLATFORM`** in their repo, lint script prevents crypto imports leaking into them
- **`bfs_trace.py` primitives** shipped — full `trace_address` deliberately not extracted (500 lines, fetcher-entangled). We assemble our BFS from the three primitives.
- **`GraphStore` Protocol** shipped — structural-typing, no inheritance required
- **All Tier 2 grey zones now injectable** via constructor args; default construction preserves crypto behavior
- **R23-R27 walk-through** — still pending a calendar slot before first sync

## Parked for later

- **Cross-reference API** (shared `Person`/`Entity` IDs across crypto and bank cases — "one case shows both kinds of investigation side-by-side"). Correctly flagged as a month-long conversation. Revisit when both products have real users.

## Sync log

| Date | Commit synced from | Files synced | Notes |
|---|---|---|---|
| 2026-04-15 | (initial) | none yet | Repo skeleton created. Waiting on Phase 1 crypto-team cleanup. |
| 2026-04-16 | (crypto shipped all cleanup) | none yet | Crypto team delivered faster than expected. Ready to begin Tier 1 sync. Next step: R23-R27 walk-through, then copy 10 READY files. |
| 2026-04-16 | `9e7d7b8` | 10 Tier-1 files synced | `models/case.py`, `models/investigation.py`, `analysis/velocity_analyzer.py`, `analysis/signal_assembler.py`, `analysis/transaction_pool.py`, `analysis/entity_classification.py`, `analysis/pattern_framework.py`, `graph/bfs_trace.py`, `graph/graph_store.py`, `auth/jwt.py`. See [core/COMPAT_NOTES.md](core/COMPAT_NOTES.md) for per-file importability — 6 are fully clean, 4 need shims before actual backend use (only matters in Phase 2+). R23-R27 walk-through still pending. |

## Local divergence (things we changed after syncing)

(none yet — nothing synced)

## How to sync

```bash
./tools/sync-from-crypto.sh                 # interactive: shows diffs, asks before overwriting
./tools/sync-from-crypto.sh --check         # dry-run, prints what would change
./tools/sync-from-crypto.sh --force <file>  # overwrite local copy with upstream
```

Run monthly, or when crypto announces a relevant change.
