# LedgerFlow — project status

**As of:** 2026-04-16

## Where we are

Phase 1 scaffold is **buildable and runnable** with real extracted data end-to-end. Neither the backend (FastAPI) nor the graph canvas are wired yet — those are Phase 1 completion and Phase 3 respectively.

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   9 PDFs    →   pdfplumber + parser.py   →   858 transactions   │
│  (5 banks)      plugins/bank/extraction/      (99–100% sum-     │
│                                               check accuracy)   │
│                                 │                                │
│                                 ▼                                │
│                 tools/export-for-frontend.py                    │
│                                 │                                │
│                                 ▼                                │
│                    realData.ts (TypeScript,                     │
│                     858 rows, 2 cases)                          │
│                                 │                                │
│                                 ▼                                │
│                    data/index.ts facade                         │
│                                 │                                │
│                                 ▼                                │
│     frontend/ (Vite + React + Tailwind 4 + shadcn/ui)           │
│          • CaseDashboard                                        │
│          • CaseOverview (persons → accounts → files)            │
│          • Workbench (tabs, filters, flag badges)               │
│          • TransactionTable (expand-in-place, inter-file sep)   │
│          • EditDrawer (key-value entities, bulk-link suggest)   │
│          • UploadModal                                          │
│   Forensic Ledger theme applied (tri-font, navy primary,        │
│   tonal layering, Dr/Cr colored borders).                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## What works today

- **Extraction** — 99–100% sum-check accuracy across HDFC CC, IDFC, HDFC Savings, ICICI, Kotak on 9 test PDFs / 858 transactions. See [benchmarks/SUMMARY.md](benchmarks/SUMMARY.md).
- **Parser → frontend export** — `python tools/export-for-frontend.py` regenerates `frontend/src/app/data/realData.ts` from the latest benchmark output.
- **Frontend builds** — `cd frontend && npm run build` produces `dist/` (~715 KB JS / 92 KB CSS; 126 KB gzipped).
- **Frontend runs** — `npm run dev` serves on :5173 in ~580 ms.
- **Backend runs** — `cd backend && uvicorn app.main:app --reload --port 8000`. Seven endpoints live, seeded with all 858 transactions.
- **End-to-end HTTP** — `bash tools/smoke-test-e2e.sh --check` boots backend, hits the three key read endpoints, PATCHes a transaction, reads back the audit log. Currently proven green.
- **HTTP client ready** — `frontend/src/app/lib/api.ts` has typed fetchers for every backend endpoint. Not plugged into components yet; swap is one-line when we add react-query.
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
│   ├── parser.py/extractors.py      # [MOVED to plugins/bank/extraction/]
│   ├── run.py / sum_check.py
│   ├── SUMMARY.md                   # 12-tool benchmark, 9 PDFs
│   └── ground_truth/                # HDFC CC + IDFC hand-labeled
├── plugins/bank/
│   ├── extraction/
│   │   ├── parser.py                # 5-bank router + parser
│   │   └── extractors.py            # 12 PDF extractor wrappers
│   └── README.md
├── backend/                         # FastAPI stub — serves 858 txns from memory
│   ├── app/main.py                  # 7 endpoints (cases, transactions, audit)
│   ├── app/schemas.py               # Pydantic mirrors of frontend types
│   ├── app/store.py                 # in-memory store, seeded from benchmark JSON
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
    └── sync-from-crypto.sh          # placeholder sync script
```

## What's NOT in the repo yet

- **Persistence layer** (SQLite / Postgres). Backend stub is in-memory, lost on reload. No database migrations, no ORM wiring.
- **Real upload pipeline**. UploadModal is UI only — clicking upload doesn't actually ingest a PDF.
- **Edit writeback**. EditDrawer's Save button is a `console.log`. Audit log is not persisted.
- **Graph canvas**. `Graph` tab in Workbench is disabled with "Coming in Phase 3" tooltip.
- **Forensic patterns**. `plugins/bank/patterns/` is empty. Flags in the frontend come from the extraction-confidence heuristic only.
- **Enrichment**. PEP / sanctions / FIU-IND lookups not wired.
- **Authentication**. No login screen. `auth/jwt.py` is synced from crypto but not used yet.

## Git history (last 10 commits)

```
(latest — run `git log --oneline` for current state)
Add frontend HTTP client + e2e smoke test script
Phase 1 backend stub + opening-balance back-fill
Add STATUS.md — project state after Phase 1 scaffold
Wire realData via facade + fix case-scoping + generalise bank labels
Phase 1 frontend scaffold + first crypto sync + real-data adapter
CRYPTO_SYNC.md: crypto team shipped all cleanup
Lock in Phase 1 UX + data model
Add UX sprint artifacts: decisions matrix + wireframes
Incorporate crypto team feedback + add phased UX plan
Initial repo: bank-statement extraction + benchmark harness
```

## Immediate next steps (in priority order)

1. **Browser smoke test** — open `http://localhost:5173`, walk through Cases → Overview → Workbench → expand a row → open EditDrawer. Just to feel the UX. (User can do this; `npm run dev`.) ← *current bottleneck for further UX iteration.*
2. **Fix whatever breaks / looks wrong** from the smoke test — typical issues: overflow in narrow columns, flag icon placement, category colors.
3. ~~**Back-fill opening/closing balance**~~ — done. Running balance now starts from the declared opening for HDFC Savings (₹69,422.10), ICICI (₹16,674.45), Kotak (₹89,610.50), IDFC (₹11,54,791.51). HDFC CC stays at 0 (no balance concept on a card statement).
4. ~~**Wire the Python backend**~~ — **stub shipped**. 7 endpoints live in `backend/` (FastAPI + uvicorn). In-memory store seeded from the benchmark output — same 858 transactions the frontend currently reads statically.
5. **Replace `realData.ts` with HTTP fetch** — create `frontend/src/app/lib/api.ts` with the same shape the facade re-exports, then flip `data/index.ts` from `./realData` to `./lib/api`. Components don't change.
6. **Wire POST endpoints** — `/api/cases` (create case), `/api/cases/{id}/statements` (upload PDF + parse + persist). Needed before the UploadModal and "New Case" buttons do real work.
7. **Persistence — SQLite** — promote the in-memory `store` to SQLAlchemy models. Alembic migrations. Edits + audit persist across restart.
8. **Schedule R23-R27 walk-through with crypto team** — needed before we actually use synced `core/` code in the backend.

## Open UX decisions still to validate

These were decided in [docs/ux-decisions.md](docs/ux-decisions.md) but haven't been seen with real 858-row data yet. Browser smoke test will surface:

- Does the left-border Dr/Cr color read clearly at scanning distance, or does the row need more chrome?
- Does the expand-in-place feel right for row peek, or does a bottom sheet work better?
- Is the "(unknown: …)" counterparty placeholder for low-confidence rows a nag or a useful prompt?
- Does the inter-file separator `── April 2021 statement ends │ May 2021 statement begins ──` look acceptable at the real data's scale (87 + 153 rows in the Kotak case)?
- At 554 rows in the HDFC Savings account, does the table need virtualisation to scroll smoothly?

## Dependencies and blockers

- **Crypto team:** 0 blockers. They shipped all Phase 1 + Phase 2 cleanup. R23-R27 walk-through is scheduled (not yet time-boxed).
- **Internal:** 0 blockers. All decisions made.
- **External:** 0.
