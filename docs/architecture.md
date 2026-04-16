# LedgerFlow — architecture

**As of:** 2026-04-16

## Shape at a glance

```
┌──────────────────────────────────────────────────────────────────────┐
│  frontend/                                                           │
│    Vite + React 18 + react-router + Tailwind 4 + shadcn/ui          │
│    @tanstack/react-query for all data fetching                       │
│    recharts for the Summary charts                                   │
└──────────────────────────────────────────────────────────────────────┘
            │  HTTP/JSON (Pydantic ↔ TypeScript mirrored types)
            ▼
┌──────────────────────────────────────────────────────────────────────┐
│  backend/                                                            │
│    FastAPI (routes in app/main.py)                                  │
│    Pydantic 2 schemas in app/schemas.py  (the wire contract)         │
│    SQLAlchemy 2 ORM in app/db.py         (storage shape)             │
│    Store layer in app/store.py           (domain logic)              │
│    Bank heuristics in app/entity_inference.py                        │
└──────────────────────────────────────────────────────────────────────┘
            │
   ┌────────┼───────────────────────────────────────────┐
   ▼        ▼                                            ▼
 SQLite    plugins/bank/                         core/   (synced)
 ledger-    extraction/  parser.py + extractors   from crypto @9e7d7b8
 flow.      patterns/    structuring, velocity,   models / analysis /
 sqlite     parsers/     round_amount              graph / auth
            enrichment/  (empty — Phase 3)         COMPAT_NOTES.md
```

## Layers and responsibilities

### 1. `core/` — synced from the crypto investigation platform

Imported as-is (with provenance headers) at commit `9e7d7b8`. Today, **zero modules are actively imported from our backend** — they're staged for Phase 2/3 use. See `core/COMPAT_NOTES.md` for per-file readiness.

Modules:
- `models/case.py`, `models/investigation.py` — case/investigation base types
- `analysis/velocity_analyzer.py`, `analysis/signal_assembler.py`, `analysis/transaction_pool.py`, `analysis/entity_classification.py`, `analysis/pattern_framework.py`
- `graph/bfs_trace.py`, `graph/graph_store.py` — runtime-checkable `GraphStore` Protocol (Neo4j online / NetworkX offline)
- `auth/jwt.py`

### 2. `plugins/bank/` — domain-specific bank logic

Kept deliberately separate from `core/` so the crypto and banking teams can evolve independently.

- **`extraction/parser.py`** — 5-bank router: `detect_bank(text)` + `parse_text(text)`. Each bank has its own line-level parser.
- **`extraction/extractors.py`** — 12 PDF-extractor wrappers (pdfplumber, pdftotext, Tika, PaddleOCR, EasyOCR, Tesseract, docling, …). Today only pdfplumber is hot-path; the others are benchmark fodder.
- **`patterns/`** — forensic detectors. Each exposes a pure `detect_*(txns) -> {txn_id: [flag_name, ...]}` function. The `run_all` helper in `plugins/bank/patterns/__init__.py` fans out to every detector and merges flags. Detectors are idempotent; each owns a namespaced flag name so reruns don't double-count.
- **`parsers/`** — placeholder for format-specific parsers (credit-card layouts vs. savings layouts). Currently inlined in `extraction/parser.py`.
- **`enrichment/`** — placeholder for PEP / sanctions / FIU-IND lookups. Phase 3.

### 3. `backend/app/` — API service

**Six ORM tables** in `app/db.py`:

| Table                         | Purpose                                                         |
|-------------------------------|-----------------------------------------------------------------|
| `cases`                       | Investigation cases (FIR, title, officer)                      |
| `persons`                     | Natural / juristic persons under a case                         |
| `accounts`                    | Bank accounts attached to persons                               |
| `statements`                  | PDF statement uploads attached to accounts                      |
| `transactions`                | Parsed transactions (entities/tags/flags stored as JSON strings) |
| `edit_events`                 | Per-field audit trail for transaction PATCHes                   |
| `entities`                    | Resolved counterparty entities (clustered)                     |
| `transaction_entity_links`    | Many-to-many between transactions and entities                  |

Schema is created via `Base.metadata.create_all(engine)` on startup. No Alembic yet — schema changes are applied via `LEDGERFLOW_RESET_DB=1` in dev. Will need Alembic once prod data starts mattering.

**Public store API** (`app/store.py`) — the boundary between HTTP and storage:
- Case / Person / Account / Statement / Transaction CRUD
- `ingest_statement(...)` — persist a parsed PDF and fan out to pattern + entity resolvers
- `patch_transaction(id, patch)` — field-level update, running-balance cascade, audit log write
- `case_summary(id)` — pure aggregation, used by the Summary tab
- `run_patterns_for_case(id)` — invokes `plugins.bank.patterns.run_all`, updates `flags_json`
- `resolve_entities_for_case(id)` — canonical-key clustering, second-pass substring merge
- `delete_statement(id)` — cascade-deletes txns, audits, links, and the account if it becomes empty
- `get_statement_pdf_path(id)` — for the source-PDF streaming endpoint
- `seed_from_benchmarks()` — idempotent seed that re-uses `tools/export-for-frontend.py` to load the benchmark data

**REST endpoints** (grouped — see `app/main.py` for signatures):

- Health & dev: `GET /api/health`, `POST /api/dev/reset`
- Cases: `GET|POST /api/cases`, `GET /api/cases/{id}`, `GET /api/cases/{id}/summary`, `GET /api/cases/{id}/transactions`
- Persons: `POST /api/cases/{id}/persons`
- Statements: `POST /api/statements/preview`, `POST /api/cases/{id}/statements` (multipart upload), `GET /api/statements/{id}`, `GET /api/statements/{id}/pdf`, `DELETE /api/statements/{id}`
- Transactions: `PATCH /api/transactions/{id}`, `GET /api/transactions/{id}/audit`, `GET /api/transactions/{id}/entities`, `POST /api/transactions/{id}/entity-links`, `DELETE /api/transactions/{id}/entity-links/{entity_id}`
- Entities: `GET|POST /api/cases/{id}/entities`, `GET /api/entities/{id}`, `POST /api/cases/{id}/resolve-entities`
- Patterns: `POST /api/cases/{id}/run-patterns`

### 4. `frontend/src/app/` — UI

- **Routes** in `routes.tsx`:
  - `/` → `CaseDashboard`
  - `/cases/:caseId` → `CaseOverview`
  - `/cases/:caseId/workbench` → `Workbench`
- **Data flow**: components call hooks from `lib/queries.ts` → hooks call typed fetchers in `lib/api.ts` → `BASE = VITE_API_URL`.
- **Mutation hooks** invalidate the relevant query keys so edits show up without manual refresh.
- **Components**:
  - `CaseDashboard` — case list
  - `CaseOverview` — person cards, accounts, per-statement rows with delete + PDF link, Add Person + Upload modals
  - `AddPersonDialog` — standalone person-creation modal
  - `UploadModal` — 4-step flow (pick file → preview → confirm overrides → commit) with inline Add Person
  - `Workbench` — tab bar (All / per-account / Summary / Entities / Graph), filter bar, bulk-action bar, transaction table
  - `TransactionTable` — the big one; fixed columns, inline edits, expand-in-place, drawer trigger, bulk select
  - `MultiSelect` — reusable checkbox-popover with typeahead, used in the filter bar
  - `EditDrawer` — full-field transaction editor
  - `SummaryView` — KPIs, Patterns scoreboard, monthly chart, category pie, top counterparties
  - `EntitiesView` — entity list + EntityDrawer

### 5. `deployment/`

- `saas/` (placeholder) — intended for the hosted SaaS target
- `lea-offline/` (placeholder) — for air-gapped LEA deployments

## Key cross-cutting decisions

- **Key-value entities, not columns**: `Transaction.entities: dict[str, EntityValue]` stores channel / counterparty / category / ref_number / anything else. Each value carries `{value, source, confidence}`. Storage is a JSON string; Pydantic hydrates on read.
- **Flag namespacing**: extraction-time flags (`SUM_CHECK_CONTRIBUTOR`, `NEEDS_REVIEW`) live alongside pattern flags (`STRUCTURING_SUSPECTED`, `VELOCITY_SPIKE`, `ROUND_AMOUNT_CLUSTER`). Re-running pattern detection clears *only* the pattern namespace; extraction flags persist.
- **Running-balance cascade on amount edit**: we don't re-walk the statement from the declared opening (bank print order varies — Kotak is latest-first, HDFC is oldest-first). Instead we shift the delta across all rows with `row_index >= edited_row`. Preserves the PDF's own walk direction.
- **Auto-run resolvers after every ingest**: pattern detection + entity resolution run at the case level after each new statement. Both are idempotent.
- **Period derivation**: the header regex is a hint; the authoritative source is the parsed transactions' min/max dates. Fixes the bug where PDFs without "From: X To: Y" headers were stamped with today's date.
- **Dual token theme**: Tailwind `@theme` exposes both shadcn names (`--primary`, `--foreground`) and MD3 names (`--color-surface`, `--color-on-surface`) pointing at the same Forensic Ledger palette. Either vocabulary works.

## How requests flow

### Upload path

```
User picks PDF
  → POST /api/statements/preview (multipart)
      ├── pdfplumber → text
      ├── detect_bank(text)         plugin
      ├── parse_text(text)          plugin (full extraction, just to count + date-range)
      ├── _guess_holder_name(text)  main.py heuristics
      ├── _guess_account_number(text)
      ├── _guess_period(text) + _period_from_txns(parser_txns)
      └── _suggest_person_match(holder, case.persons)
  → User confirms / edits overrides
  → POST /api/cases/{id}/statements (multipart, with confirmed fields)
      → store.ingest_statement(...)
          ├── find-or-create account
          ├── for each parser_txn: infer channel/category/counterparty, insert TransactionRow
          ├── run_patterns_for_case(case_id)       # writes flags_json
          └── resolve_entities_for_case(case_id)   # updates entities + links
```

### PATCH path

```
User edits a cell or the drawer
  → PATCH /api/transactions/{id}
      → store.patch_transaction(id, patch)
          ├── apply updates to TransactionRow
          ├── EditEventRow per changed field (field, old_value, new_value, actor, at)
          ├── if amount or direction changed:
          │   └── _shift_balances_from(statement_id, row_index, delta)
          └── return refreshed Transaction
  → react-query invalidates ["case", caseId]
  → CaseOverview + Workbench + SummaryView refetch
```

## Testing

- `benchmarks/` — 9 PDFs × 12 extractors, with sum-check ground truth for HDFC CC + IDFC. Source of our 99–100% accuracy claim.
- `tools/smoke-test-e2e.sh` — API-level smoke: boots backend, hits health + cases + transactions + PATCH + audit readback.
- No frontend tests yet — UI is validated by running the dev server and clicking through.

## Runtime

- **Dev**: two terminals. Backend: `cd backend && python -m uvicorn app.main:app --reload --port 8000`. Frontend: `cd frontend && npm run dev`. Environment: `VITE_API_URL=http://localhost:8000` in `.env.local`.
- **Reset**: `LEDGERFLOW_RESET_DB=1 python -m uvicorn …` drops and reseeds the SQLite file.
- **Data files**: `backend/ledgerflow.sqlite` (DB), `data/uploads/` (persisted PDFs), `data/pdf/` (benchmark sources).
