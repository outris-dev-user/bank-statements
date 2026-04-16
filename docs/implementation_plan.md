# LedgerFlow — implementation plan

**As of:** 2026-04-16

Working checklist grouped by phase. Tick items (`[x]`) as they ship. Items marked `~` are partially done — see the sub-bullets for what's left.

---

## Phase 1 — Case management, ingestion, Workbench  *(complete)*

### Ingestion
- [x] PDF extraction via pdfplumber on the hot path
- [x] 5-bank parser router (HDFC CC, HDFC Savings, IDFC, ICICI, Kotak)
- [x] Sum-check validation (99–100% accuracy across 858 benchmark txns)
- [x] Bank / account-type / account-number auto-detection
- [x] Holder-name auto-detection (labeled patterns + honorific prefix + all-caps header-line fallback)
- [x] Period detection (header regex + min/max of parsed txn dates)
- [x] Preview endpoint (`POST /api/statements/preview`) — detect without persisting
- [x] Upload endpoint (`POST /api/cases/{id}/statements`) — multipart with field overrides
- [x] Auto-match suggested person by fuzzy name containment
- [x] Inline "Add new person" in UploadModal (dialog pre-fills the detected name)
- [x] Cascade delete (`DELETE /api/statements/{id}`) — removes txns, audits, links, empty accounts

### Case management
- [x] Case dashboard
- [x] Case overview with person cards, accounts, per-statement rows
- [x] Add Person dialog with PAN + phone
- [x] Create case endpoint
- [x] Source PDF viewer (`GET /api/statements/{id}/pdf`) linked from table + drawer + case overview

### Workbench
- [x] Transaction table with fixed column widths
- [x] Filter bar with search, type, multi-select counterparty/category/tags, needs-review, flagged-only
- [x] Secondary strip for Clear-all + result count (filter bar never shifts)
- [x] Row multi-select with shift-click range
- [x] Bulk actions (mark reviewed, flag, unmark)
- [x] Inline edit: counterparty (free text)
- [x] Inline edit: category (dropdown, finite taxonomy)
- [x] Inline edit: debit/credit amount with running-balance cascade
- [x] Clickable Flag column (toggles `review_status`)
- [x] Expand-in-place row peek
- [x] Double-click or Edit button opens full EditDrawer
- [x] Per-transaction audit trail persisted + readable
- [x] Per-account tabs + "All transactions" tab
- [x] Inter-statement separators when viewing a single account

---

## Phase 2 — Summary, forensic patterns, entity resolution  *(~70% complete)*

### Summary tab
- [x] KPI strip (credits, debits, net, count)
- [x] Review-status pills (unreviewed, reviewed, flagged, extraction-flags)
- [x] Monthly credits vs debits bar chart (recharts)
- [x] Category pie chart
- [x] Top 15 counterparties list with dr/cr totals
- [x] Forensic patterns scoreboard (severity-tinted cards, zero-hit pills)
- [x] "Re-run detectors" button
- [ ] Day-of-week / hour-of-day heatmap — deferred; the PDFs only give us dates, not timestamps

### Forensic patterns (detectors)
- [x] `STRUCTURING_SUSPECTED` — ≥3 txns between ₹9L and ₹10L in a 30-day window
- [x] `VELOCITY_SPIKE` — ≥10 txns in a 24-hour window
- [x] `ROUND_AMOUNT_CLUSTER` — ≥5 round-amount txns per account
- [x] `FUND_THROUGH_FLOW` — credit in + debit out of similar amount within 2 days (≥ ₹10k, ±5% envelope)
- [x] `DORMANT_THEN_ACTIVE` — 60-day gap followed by ≥5 txns within 7 days
- [x] `SAME_DAY_ROUND_TRIP` — matching credit + debit with the same counterparty on the same day
- [x] Auto-run on every ingest + init_and_seed
- [x] Manual re-run endpoint
- [x] Patterns appear in the Summary scoreboard and flagged-only filter
- [ ] `CROSS_BORDER_EXPOSURE` — requires OSINT integration (Phase 3)
- [ ] `HAWALA_PATTERN` — requires entity resolution across cases (Phase 4)

### Entity resolution
- [x] Entities table (`entities`) + M2M links (`transaction_entity_links`)
- [x] Canonical-key clustering (stop-word strip, top-3 longest tokens)
- [x] Second-pass substring merge (e.g. AMAZON + AMAZONPAY → one entity)
- [x] Manual-created entities exempt from auto-merge
- [x] Auto-run on every ingest + init_and_seed
- [x] Entities tab in Workbench
- [x] Per-entity drawer with aliases + linked transactions + KPIs
- [x] Manual re-run (`POST /api/cases/{id}/resolve-entities`)
- [x] Manual link / unlink endpoints
- [ ] "Suggest merge" hint in the EditDrawer based on fuzzy counterparty match
- [ ] Bulk-link UI — "link these 20 rows to entity X"
- [ ] Link an entity to a Person row (foreign-key exists, UI does not)
- [ ] Manual "create entity" from an unresolved counterparty in the table

### UX polish (outstanding)
- [ ] UX decision #12 — visual flash / pulse when amount edit cascades running-balance
- [ ] Virtualised rendering (`react-window`) for tables >2000 rows
- [ ] Keyboard shortcuts — `j/k` navigate, `/` focus search, `e` edit, `f` flag, `r` reviewed
- [ ] Toast system instead of inline alert blocks (sonner is already installed)
- [x] EditDrawer audit log: wire to `GET /api/transactions/{id}/audit` with live edit history
- [x] EditDrawer suggest-merge: replace static placeholder with live entity match + one-click Link action

### Backend housekeeping
- [ ] Alembic migrations — current `create_all` is fine for dev but we need migrations before prod data matters
- [ ] Rate limit the upload endpoint (anti-DoS for SaaS deployment)
- [ ] Structured logging (current uvicorn default is noisy)

---

## Phase 3 — Graph canvas, advanced patterns, enrichment  *(not started)*

### Graph canvas
- [x] Backend `GET /api/cases/{id}/graph` — returns nodes (persons, accounts, entities) + edges (owns, flow_in, flow_out) with aggregated amounts
- [x] Graph tab in Workbench — react-flow (`@xyflow/react`) canvas with three-lane layout
- [x] Edge thickness scales with log(amount); colour-coded by direction
- [x] Filter by node type (persons / accounts / entities) + minimum flow amount
- [ ] Wire `core/graph/graph_store.py` Protocol — swap the aggregation above for the shared in-process `NetworkXStore` (and Neo4j for the online SaaS target)
- [ ] Click-through from a graph node to the transaction list scoped to that node
- [ ] Date-range filter on the graph
- [ ] Export graph view to PNG / PDF for case reports
- [ ] Better layout — Dagre or force-directed (three-lane is only a Phase 3 scaffold)

### Advanced forensic patterns
- [ ] Multi-hop exposure (BFS over the transaction graph, bounded by hop count + amount threshold)
- [ ] Circular trading detector (cycle detection)
- [ ] Mule ring detector (fan-out + rapid drain)
- [ ] Layering detector (A → B → C → A within T days)
- [ ] Benami indicator (person-entity mismatch signals)

### Enrichment (plugins/bank/enrichment/)
- [ ] PEP list lookup (Politically Exposed Persons)
- [ ] FIU-IND sanctions list lookup
- [ ] Global sanctions list (OFAC, UN)
- [ ] Enrich entities post-resolution; surface hits as pattern flags

### Report generation
- [ ] "Export case report" — PDF with summary + flagged txns + entity map + audit log
- [ ] Pre-built templates for FIR-style annexures

---

## Phase 4 — Cross-case intelligence, multi-tenant SaaS  *(not started)*

### Cross-case
- [ ] Shared Person / Entity IDs across cases (with LEA-level privacy guards)
- [ ] "This entity also appears in case X" hint
- [ ] Cross-case graph view
- [ ] Shared flags (a flagged entity in one case auto-highlights in others)

### Auth + multi-tenant
- [ ] Wire `core/auth/jwt.py` — login screen, session refresh
- [ ] Role-based access: officer / supervisor / admin
- [ ] Tenant isolation at the DB level (row-level `tenant_id` or per-tenant SQLite)
- [ ] Audit log for non-transaction actions (logins, case opens, exports)

### Deployment
- [ ] `deployment/saas/` — Docker / k8s manifests for the hosted target
- [ ] `deployment/lea-offline/` — single-binary offline build (PyInstaller for backend + static SPA)
- [ ] CI/CD — GitHub Actions for test + build + benchmark regression

---

## Known bugs / followups

- [x] Period stamping: previously fell back to today's date when the header regex missed (fixed 2026-04-16 — now derives from transaction min/max dates)
- [ ] `CROSS_BORDER_EXPOSURE` / `HAWALA_PATTERN` — detectors are called out in product but not implemented (Phase 3+)
- [ ] HDFC CC holder name appears as concatenated string (`BILALABDULKUDDUSKHANMOHAMMED`) — no whitespace splitter
- [ ] ICICI business accounts don't produce a holder match — the name is spread across multiple address lines
- [ ] STATUS.md undercounts endpoint totals — source of truth should be `docs/architecture.md` and `product_document.md` going forward

---

## Suggested next sprint (ordered)

1. **Finish Phase 2 patterns** — `FUND_THROUGH_FLOW`, `DORMANT_THEN_ACTIVE`, `SAME_DAY_ROUND_TRIP` (uses the same plumbing as the existing three)
2. **EditDrawer audit wiring + suggest-merge hint** — small but high-value UX wins
3. **Table virtualisation** — once we cross 2000 rows on a real case, this becomes urgent
4. **Alembic migrations + structured logging** — before prod
5. **Phase 3 graph scaffolding** — stub the canvas tab with NetworkX on the backend and cytoscape on the frontend, no filters yet
6. **Phase 3 multi-hop BFS** — reuses `core/graph/bfs_trace.py` from the sync
