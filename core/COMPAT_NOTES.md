# core/ compat notes

Synced 2026-04-16 from crypto/india-le-platform at commit `9e7d7b8`.

## Importability status

| File | Crypto-internal imports | Notes |
|---|---|---|
| `models/case.py` | 0 | **Ready** — pure Pydantic schema |
| `models/investigation.py` | 0 | **Ready** |
| `analysis/entity_classification.py` | 0 | **Ready** — keyword maps are all parameters |
| `analysis/pattern_framework.py` | 0 | **Ready** — scaffolding only |
| `graph/bfs_trace.py` | 0 | **Ready** — generic BFS primitives |
| `graph/graph_store.py` | 0 | **Ready** — runtime-checkable Protocol |
| `auth/jwt.py` | 1 (`app.config`) | **1-line shim** — config is just JWT secret + algo |
| `analysis/velocity_analyzer.py` | 2 | Needs `address_utils` (hash helpers — crypto-flavoured but generic enough to copy) + `entity_constants` (now deprecated upstream; use `entity_classification` here) |
| `analysis/signal_assembler.py` | 8 | **Grey zone** — scaffolding is clean but EXPOSURE family hardcodes crypto category names. Per crypto team, `transaction_fetcher` and `exposure_high_risk_categories` are now constructor args; pass our bank versions. The 8 imports are to services we'd inject/stub at construction time. |
| `analysis/transaction_pool.py` | 3 | **Heaviest shim** — imports `address_utils`, `services.fetchers.evm`, `services.graph_service`. Fine for the cache skeleton, but we'd need to strip the crypto-specific fetcher calls or fork. |

## What to do about the crypto-internal imports

**Don't fix them yet.** Phase 1 (table view + review UX) does not load these modules. `signal_assembler`, `transaction_pool`, `velocity_analyzer` come online in Phase 2 when we build the forensic pipeline.

When we get there:

1. Write a tiny `core/compat/shims.py` that stubs out `app.config`, `app.services.entities`, etc. for the bank context.
2. Or fork the 3-4 problematic files locally (mark them `FORK` in [../CRYPTO_SYNC.md](../CRYPTO_SYNC.md) and add why).
3. Or push a PR upstream pulling those imports behind their own injection points — the crypto team was explicit they'd rather fix upstream than have us fork.

## Don't import core/ from the frontend

`frontend/` is TypeScript. Backend communicates to frontend over HTTP only. These Python modules are for the future `backend/` service (FastAPI) once Phase 1 UX validates.
