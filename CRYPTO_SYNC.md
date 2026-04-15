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

## Status after crypto team response (2026-04-15)

The crypto team [accepted the proposal in principle](docs/from-crypto-team.md) but flagged accurate corrections about module readiness. Most items we asked for aren't "copy zero-change" yet — they need small refactors first. Crypto team is committing to those refactors over 2-4 weeks as opportunistic cleanup (benefits them too).

**Our sync plan now has three readiness tiers:**
- **READY** — can copy today, zero changes on either side
- **AWAITING CLEANUP** — crypto team has committed to refactor; sync after they ship
- **FORK** — will diverge meaningfully from upstream; copy once, maintain locally

## What we plan to copy

### Phase 1 — Backend: Models and analysis framework

| Crypto path | Local path | Readiness | Notes |
|---|---|---|---|
| `backend/app/models/case.py` | `core/models/case.py` | **READY** | Rename `address`→`account` semantics on our side |
| `backend/app/models/investigation.py` | `core/models/investigation.py` | **READY** | Rename `root_address`→`root_account`, `root_chain`→`root_bank` |
| `backend/app/analysis/velocity_analyzer.py` | `core/analysis/velocity_analyzer.py` | **READY** | Confirmed generic by crypto team — pure ratio math |
| `backend/app/analysis/transaction_pool.py` | `core/analysis/transaction_pool.py` | **READY** | Per-investigation cache + dedup |
| `backend/app/utils/auth.py` | `core/auth/jwt.py` | **READY** | Online deployment only |
| `backend/app/analysis/signal_assembler.py` | `core/analysis/signal_assembler.py` | **AWAITING CLEANUP** | Scaffold is clean, but EXPOSURE family assessor hardcodes crypto category names. Crypto team adding "inject domain" hook. |
| `backend/app/analysis/pattern_detector.py` | `core/analysis/pattern_framework.py` | **AWAITING CLEANUP** | Framework is clean, 19 crypto patterns live in same file. Crypto team splitting into `pattern_framework.py` + `patterns/crypto/*.py`. Already on their tech debt list. |
| `backend/app/analysis/entity_constants.py` | `core/analysis/entity_classification.py` | **AWAITING CLEANUP** | `resolve_entity_type()` is generic; `EXCHANGE_BRAND_KEYWORDS` is crypto-only. Crypto team renaming module + moving crypto keywords out. |
| `backend/app/analysis/exposure_analyzer.py` | `core/analysis/multi_hop_exposure.py` | **AWAITING CLEANUP** | Hardcoded to crypto entity types (mixer, exchange, DEX). Crypto team injecting `stop_entity_types` as a parameter. |
| `backend/app/analysis/counterparty_triage.py` | `core/analysis/counterparty_triage.py` | **AWAITING CLEANUP** | `_select_for_canvas()` has crypto-specific ranking. Crypto team extracting scoring as strategy callback. |
| `backend/app/services/investigation_orchestrator.py` (SSE pipeline) | `core/orchestration/pipeline.py` | **AWAITING CLEANUP** | Step names `backward_trace`/`forward_trace` are crypto-flavoured; SSE machinery is generic. Crypto team renaming to `upstream`/`downstream`. |

### Phase 2 — Backend: Graph and persistence

| Crypto path | Local path | Readiness | Notes |
|---|---|---|---|
| `backend/app/services/graph_service.py` (BFS only) | `core/graph/bfs_trace.py` | **AWAITING CLEANUP** | `graph_service.py` is a 3,200-line monolith. Crypto team offered to extract `bfs_trace.py` (~300 lines) as a focused module. Benefits both sides. |
| `backend/app/services/graph_storage.py` | `core/graph/graph_store.py` | **AWAITING CLEANUP** | Currently Neo4j-only. Crypto team offered to define abstract `GraphStore` protocol so we can plug in NetworkX-backed implementation for offline. |

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

## Open offers from the crypto team (accepted)

- **`bfs_trace.py` extraction** — split the 3,200-line `graph_service.py` so we can copy a focused BFS module. Offered by them; tech debt for them anyway.
- **`GraphStore` protocol** — abstract Neo4j and NetworkX behind one interface. Offered; lets them future-proof, lets us go offline.
- **R23-R27 walk-through** — they added 6 central hooks recently (AdaptiveFetcher in `trace_path`, Arkham fallback, auto chain-probe, viewport preservation, common-attribution edges). Scheduled 30 min before first sync.

## Parked for later

- **Cross-reference API** (shared `Person`/`Entity` IDs across crypto and bank cases — "one case shows both kinds of investigation side-by-side"). Correctly flagged as a month-long conversation. Revisit when both products have real users.

## Sync log

| Date | Commit synced from | Files synced | Notes |
|---|---|---|---|
| 2026-04-15 | (initial) | none yet | Repo skeleton created. Waiting on Phase 1 crypto-team cleanup (~2-3 days of their time over next 2-4 weeks). |

## Local divergence (things we changed after syncing)

(none yet — nothing synced)

## How to sync

```bash
./tools/sync-from-crypto.sh                 # interactive: shows diffs, asks before overwriting
./tools/sync-from-crypto.sh --check         # dry-run, prints what would change
./tools/sync-from-crypto.sh --force <file>  # overwrite local copy with upstream
```

Run monthly, or when crypto announces a relevant change.
