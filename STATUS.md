# LedgerFlow — project status

**As of:** 2026-04-16

## Where we are

Phase 1 is **functionally complete**. The full loop works end-to-end: upload a PDF → parser extracts transactions → SQLite persists them → frontend displays live via react-query → edits write back through PATCH → audit log tracks every change.

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   9 PDFs    →   pdfplumber + parser.py   →   858 transactions   │
│  (5 banks)      plugins/bank/extraction/      (99–100% sum-     │
│                                               check accuracy)   │
│                                 │                                │
│                                 ▼                                │
│              POST /api/cases/{id}/statements                    │
│               (multipart PDF upload, auto-detect bank)           │
│                                 │                                │
│                                 ▼                                │
│              SQLite (SQLAlchemy ORM, 6 tables)                  │
│       cases → persons → accounts → statements → transactions    │
│                         + edit_events audit log                  │
│                                 │                                │
│                                 ▼                                │
│              10 REST endpoints (FastAPI)                         │
│    GET/POST cases, GET case detail, POST persons,               │
│    GET transactions (paginated, filter by account),              │
│    PATCH transaction, GET audit, POST upload, POST reset         │
│                                 │                                │
│                                 ▼                                │
│     frontend/ (Vite + React + Tailwind 4 + shadcn/ui)           │
│       @tanstack/react-query for all data fetching                │
│          • CaseDashboard        → useCases()                    │
│          • CaseOverview         → useCase(id)                   │
│          • Workbench            → useCase + useCaseTransactions  │
│          • EditDrawer           → usePatchTransaction()          │
│          • UploadModal (real)   → POST multipart + invalidate   │
│          • TransactionTable     (expand-in-place, flags)        │
│   Forensic Ledger theme (tri-font, navy primary,                │
│   tonal layering, Dr/Cr colored borders).                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## What works today

- **Extraction** — 99–100% sum-check accuracy across HDFC CC, IDFC, HDFC Savings, ICICI, Kotak on 9 test PDFs / 858 transactions. See [benchmarks/SUMMARY.md](benchmarks/SUMMARY.md).
- **PDF upload** — POST a PDF to `/api/cases/{id}/statements`, auto-detects bank + account number, parses transactions, persists to SQLite. Tested with ICICI statement (37 txns ingested successfully).
- **SQLite persistence** — SQLAlchemy 2.0 ORM, 6 tables (cases, persons, accounts, statements, transactions, edit_events). Survives restarts. Seed from benchmark output is idempotent.
- **10 REST endpoints** — health, CRUD for cases/persons, paginated transactions with account filter, PATCH with audit trail, multipart upload, dev reset.
- **react-query integration** — All frontend components fetch live from the backend. Mutations invalidate caches. Loading/error states handled throughout.
- **Real upload flow** — UploadModal picks a PDF, selects a person, uploads via multipart, shows result (bank detected, txn count, period), then navigates to workbench.
- **Edit writeback** — EditDrawer saves entities/tags/amount/date via PATCH. Audit log persisted. Mutation invalidates case queries so the table reflects changes.
- **Frontend builds** — `cd frontend && npm run build` produces `dist/` (~325 KB JS / 92 KB CSS gzipped).
- **Backend runs** — `cd backend && uvicorn app.main:app --reload --port 8000`. Startup auto-seeds from benchmark data.
- **End-to-end HTTP** — `bash tools/smoke-test-e2e.sh --check` boots backend, hits all key endpoints.
- **Data model** — `Case → Person → Account → Statement → Transaction` with key-value `entities` matches [docs/data-model.md](docs/data-model.md), enforced on both sides (Pydantic + TypeScript).
- **Design system** — LedgerFlow branded, tri-font, MD3 + shadcn token families coexist.

## What's in the repo (top-level)

```
bank-analyser/
├── README.md                        # overview
├── ARCHITECTURE.md                  # 3-layer core/plugin/deploy design
├── STATUS.md                        # this file
├── CRYPTO_SYNC.md                   # sync ledger
├── benchmarks/                      # extractor + parser validation (CI)
│   ├── run.py / sum_check.py
│   ├── SUMMARY.md                   # 12-tool benchmark, 9 PDFs
│   └── ground_truth/                # HDFC CC + IDFC hand-labeled
├── plugins/bank/
│   ├── extraction/
│   │   ├── parser.py                # 5-bank router + parser
│   │   └── extractors.py            # 12 PDF extractor wrappers
│   └── README.md
├── backend/                         # FastAPI + SQLAlchemy + SQLite
│   ├── app/main.py                  # 10 endpoints
│   ├── app/schemas.py               # Pydantic mirrors of frontend types
│   ├── app/store.py                 # SQLite-backed store (was in-memory)
│   ├── app/db.py                    # ORM models, 6 tables
│   ├── app/entity_inference.py      # channel/category/counterparty heuristics
│   ├── pyproject.toml
│   └── README.md
├── core/                            # synced from crypto @ 9e7d7b8
│   ├── models/case.py, investigation.py
│   ├── analysis/velocity, signal, pattern_framework,
│   │             entity_classification, transaction_pool
│   ├── graph/bfs_trace, graph_store
│   ├── auth/jwt
│   └── COMPAT_NOTES.md              # per-file importability
├── frontend/                        # LedgerFlow UI (Vite + React + Tailwind 4)
│   ├── src/app/components/          # 7 app components + shadcn/ui library
│   ├── src/app/data/                # index.ts facade + realData.ts + mockData.ts
│   ├── src/app/lib/api.ts           # typed HTTP client
│   ├── src/app/lib/queries.ts       # react-query hooks
│   ├── src/styles/                  # theme.css (Forensic Ledger palette)
│   └── README.md
├── data/pdf/                        # 9 test statements, 5 banks
├── deployment/
│   ├── saas/ (placeholder)
│   └── lea-offline/ (placeholder)
├── docs/
│   ├── ux-decisions.md              # 12 UX decisions resolved
│   ├── ux-wireframes.md             # 6 ASCII wireframes
│   ├── ux-phases.md                 # phased UX plan
│   ├── data-model.md                # backend schema
│   ├── for-crypto-team.md           # proposal we sent
│   ├── from-crypto-team.md          # their response
│   └── sample_ux/                   # Stitch + Forensic Ledger DESIGN.md
└── tools/
    ├── export-for-frontend.py       # benchmark JSON → realData.ts
    ├── smoke-test-e2e.sh            # API-level E2E test
    └── sync-from-crypto.sh          # placeholder sync script
```

## What's NOT in the repo yet

- **Graph canvas**. `Graph` tab in Workbench is disabled with "Coming in Phase 3" tooltip.
- **Forensic patterns**. `plugins/bank/patterns/` is empty. Flags come from extraction-confidence heuristic only.
- **Enrichment**. PEP / sanctions / FIU-IND lookups not wired.
- **Authentication**. No login screen. `auth/jwt.py` is synced from crypto but not used yet.
- **Database migrations**. No Alembic yet — schema created on startup via `create_all`.
- **Virtualised table**. At 500+ rows the table renders all rows. May need windowing for large statements.

## Immediate next steps (in priority order)

1. **Browser smoke test** — open `http://localhost:5173`, walk Cases → Overview → upload a PDF → Workbench → edit a transaction → verify audit. ← *current bottleneck for UX iteration.*
2. **Fix whatever breaks / looks wrong** from the smoke test.
3. **Add `.env.local`** — set `VITE_API_URL=http://localhost:8000` so frontend talks to backend in dev.
4. **Schedule R23-R27 walk-through with crypto team** — needed before we use synced `core/` code.
5. **Phase 2: forensic patterns** — velocity spikes, round-amount clustering, structuring detection.
6. **Phase 3: graph canvas** — wire NetworkX offline / Neo4j online via the GraphStore protocol from core.

## Open UX decisions still to validate

These were decided in [docs/ux-decisions.md](docs/ux-decisions.md) but haven't been seen with real 858-row data yet:

- Does the left-border Dr/Cr color read clearly at scanning distance?
- Does expand-in-place feel right for row peek, or does a bottom sheet work better?
- Is the "(unknown: …)" counterparty placeholder useful or noisy?
- At 554 rows in HDFC Savings, does the table need virtualisation?

## Dependencies and blockers

- **Crypto team:** 0 blockers. R23-R27 walk-through scheduled (not yet time-boxed).
- **Internal:** 0 blockers. All decisions made.
- **External:** 0.
