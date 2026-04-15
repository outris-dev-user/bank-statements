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

## What we plan to copy

### Phase 1 — Models and analysis framework

| Crypto path | Local path | Notes |
|---|---|---|
| `backend/app/models/case.py` | `core/models/case.py` | rename `address`→`account` semantics |
| `backend/app/models/investigation.py` | `core/models/investigation.py` | rename `root_address`→`root_account`, `root_chain`→`root_bank` |
| `backend/app/analysis/velocity_analyzer.py` | `core/analysis/velocity_analyzer.py` | zero changes — math is generic |
| `backend/app/analysis/signal_assembler.py` | `core/analysis/signal_assembler.py` | zero changes — TESTED/CLEAR/NOT_TESTED framework |
| `backend/app/analysis/transaction_pool.py` | `core/analysis/transaction_pool.py` | per-investigation cache + dedup |
| `backend/app/analysis/pattern_detector.py` | `core/analysis/pattern_framework.py` | extract framework only; bank patterns go in `plugins/bank/patterns/` |
| `backend/app/analysis/entity_constants.py` | `core/analysis/entity_registry.py` | structure reusable; bank-specific keywords added in plugin |
| `backend/app/analysis/exposure_analyzer.py` | `core/analysis/multi_hop_exposure.py` | reusable for PEP/sanctions distance scoring |

### Phase 2 — Graph and persistence

| Crypto path | Local path | Notes |
|---|---|---|
| `backend/app/services/graph_storage.py` | `core/graph/neo4j_store.py` | wrap with NetworkX fallback for offline |
| `backend/app/services/graph_service.py` (BFS section only) | `core/graph/bfs_trace.py` | swap "exchange terminus" stop conditions for bank-specific ones |
| `backend/app/utils/auth.py` | `core/auth/jwt.py` | online deployment only |

### Phase 3 — UI

| Crypto path | Local path | Notes |
|---|---|---|
| `frontend/src/components/GraphCanvas.tsx` | `core/ui/GraphCanvas.tsx` | rename `address`→`account` props |
| `frontend/src/components/NodeInspector/` | `core/ui/NodeInspector/` | swap "Address Profile" tab for "Account Profile" |
| `frontend/src/stores/` (all 6 Zustand) | `core/ui/stores/` | zero changes |
| `frontend/src/components/cases/` | `core/ui/cases/` | rename FIR fields |
| `frontend/src/components/AutoInvestigateReport.tsx` | `core/ui/InvestigationReport.tsx` | structure generic; sections swap |

## Sync log

| Date | Commit synced from | Files synced | Notes |
|---|---|---|---|
| 2026-04-15 | (initial) | none yet | repo skeleton created; nothing copied yet |

## Local divergence (things we changed after syncing)

(none yet)

## How to sync

```bash
./tools/sync-from-crypto.sh                 # interactive: shows diffs, asks before overwriting
./tools/sync-from-crypto.sh --check         # dry-run, prints what would change
./tools/sync-from-crypto.sh --force <file>  # overwrite local copy with upstream
```

Run monthly, or when crypto announces a relevant change.
