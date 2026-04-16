# LedgerFlow — product document

**As of:** 2026-04-16

## What it is

LedgerFlow is a forensic bank-statement analysis tool for investigators. Drop in a PDF bank statement, and the tool turns it into structured, editable transactions within seconds — with confidence flags, entity resolution, and built-in detectors for classic financial-crime patterns. Designed for law-enforcement analysts and SaaS investigation teams.

Brand family: part of the CryptoFlow / TraceFlow / LedgerFlow trio.

## Who it's for

- **Primary**: LEA analysts (EOW / Cyber Crime cells) who today re-type bank statements into Excel.
- **Secondary**: Compliance and fraud investigation teams at banks and fintechs.

## What a user does (core flow)

```
Case → Person(s) → Account(s) → Statement(s) → Transactions
```

1. Create a case with a FIR number, title, officer.
2. Add persons (name, PAN, phone).
3. Upload a bank statement PDF — the tool auto-detects the bank, holder, account number, and period, and offers to match the holder to an existing person (or create a new one inline).
4. Review the extracted transactions in the Workbench. Inline-edit counterparty, category, or amounts. Multi-select rows to mark reviewed or flag suspicious. Use the full drawer for deeper edits.
5. Review aggregated signals in the Summary tab — monthly totals, category breakdown, top counterparties, and the forensic patterns scoreboard.
6. Review resolved entities in the Entities tab — counterparties auto-clustered across statements, with aliases, linked transactions, and a drilldown drawer.

## Shipped capabilities (2026-04-16)

### Ingestion

- PDF extraction via pdfplumber + bank-aware parsers for 5 banks: HDFC CC, HDFC Savings, IDFC, ICICI, Kotak. Accuracy on the benchmark set: **99–100%** sum-check match across 858 transactions.
- Auto-detection of bank, account type (SA / CA / CC / OD), account number, holder name, statement period.
- Two upload paths:
  - "Upload statement" button on a specific person — person is pre-selected.
  - Page-level "Choose files" — no person pre-selected; the tool analyses the PDF first, suggests a matching person, or offers an inline "Add new person" dialog pre-filled with the detected holder name.
- Preview step before commit: investigator sees bank / type / account number / holder / period / txn count, and can edit any of them before confirming.
- Cascade-delete for mistaken uploads: removing a statement cleans up its transactions, audit events, entity links, and the owning account (if it had no other statements).

### Workbench (the transaction table)

- **Fixed-width table layout** — columns never reflow when cells switch between display and edit mode.
- **Inline edit** — click any cell to edit:
  - Counterparty (free text)
  - Category (dropdown from a shared taxonomy: Food, Transfer, Salary, Rent, Shopping, Finance, Cash, Rewards, Charges, Other)
  - Debit / Credit amounts (editing either column moves the txn to that direction, and triggers a running-balance cascade across the statement)
- **Full edit drawer** — double-click a row or click "Edit…" to open the 500-wide drawer with entities, tags, amount, date, notes, linked entities, audit trail, and a "Open source PDF" link.
- **Row multi-select** — checkbox per row + header select-all. Shift-click extends range. Bulk actions: Mark reviewed, Flag, Unmark.
- **Expand-in-place** — single click on a row reveals raw OCR, entity chips (colour-coded by confidence), flags, and quick-action buttons, without navigating away.
- **Inter-statement separators** when viewing a single account — "── statement s3 ends │ statement s4 begins ──".
- **Flag column** is clickable — toggles `review_status` between `flagged` and `unreviewed` directly.

### Filters

- Search (description, counterparty, category, channel, tags)
- Type (Dr / Cr / All)
- Multi-select for Counterparty, Category, Tags (with typeahead, check-any)
- Needs-Review checkbox
- Flagged-only toggle (shows `flagged` rows + extraction-flagged rows)
- "Clear all filters (N)" in a secondary strip so the filter bar never shifts when activated.

### Case overview

- Person cards with each account and its statements expanded inline.
- Per-statement row shows filename, period, txn count, an "Open source PDF" link, and a trash button.
- Drag-and-drop upload zone for casual drops.

### Summary tab

- KPI strip: credits in, debits out, net, total transactions.
- Review-status pills: unreviewed, reviewed, flagged, extraction-flags.
- **Forensic patterns scoreboard** — one card per detector, severity-tinted (high = destructive tone, medium = amber, low = slate), with count, description, and sample transaction IDs. Zero-hit detectors are still listed as compact "clean" badges so investigators see what was checked, not just what fired.
- Monthly credits-vs-debits bar chart.
- Category pie.
- Top 15 counterparties list with counts and dr/cr totals.
- "Re-run detectors" button for on-demand recomputation.

### Entities tab

- Lists every resolved counterparty entity in the case, sorted by transaction count.
- Full-text search over names and aliases.
- Click any row to open a detail drawer with aliases, KPIs (txn count, total debits, total credits), and the full list of linked transactions with dates and amounts.
- "Re-run resolver" button for on-demand reclustering.
- Manual entities (user-created) are marked, and are never auto-merged.

### Forensic patterns

Built-in detectors, auto-run after every ingest and on seed:

| Pattern                | Severity | Rule (default)                                              |
|------------------------|----------|-------------------------------------------------------------|
| `STRUCTURING_SUSPECTED` | high    | ≥3 transactions between ₹9L and ₹10L within any 30-day window — classic FIU-IND CTR dodging. |
| `VELOCITY_SPIKE`        | medium  | ≥10 transactions within any 24-hour window on the same account. |
| `ROUND_AMOUNT_CLUSTER`  | medium  | ≥5 transactions of round amounts (multiples of ₹10k / ₹50k) on the same account. |

Pattern hits live on the transaction's `flags` column (namespaced, idempotent reruns), and surface in the Summary scoreboard, the flagged-only filter, and the Flag column icon.

### Entity resolution

- Automatic clustering of extracted counterparty values by a canonical key (stop-word strip, top-3 longest tokens).
- Second-pass substring merge — entities whose canonical keys are substring-equivalent (min 5 chars) are merged into the one with more transactions, with the loser's name and aliases absorbed. Example: `AMAZON` + `AMAZONPAY` → one entity with 24 txns combined.
- Manual entities are never auto-merged.
- Per-entity stats: txn count, total debits, total credits, aliases list.

### Edit audit

Every PATCH is logged: actor, field, old value, new value, timestamp. Retrievable via `GET /api/transactions/{id}/audit` and visible in the transaction drawer.

### Source PDF access

Every statement streams its original PDF inline (`GET /api/statements/{id}/pdf`). Linked from the EditDrawer, the expanded row panel, and each statement row on the case overview.

## Data model (high level)

```
Case
 ├── Persons
 │    └── Accounts (bank, account_type, account_number)
 │         └── Statements (source_file, period, opening/closing balance)
 │              └── Transactions
 │                   ├── entities: dict[str, EntityValue(value, source, confidence)]
 │                   ├── tags: list[str]
 │                   ├── flags: list[str]   # extraction + pattern flags
 │                   ├── review_status: unreviewed | reviewed | flagged
 │                   └── audit log (EditEvent rows)
 └── Entities (resolved counterparties)
      └── TransactionEntityLinks (many-to-many)
```

## Deliberate non-features (as of today)

- No graph canvas yet — the "Graph" tab is visibly disabled with a "Coming in Phase 3" tooltip.
- No cross-case linking (Phase 4).
- No OSINT enrichment (PEP / sanctions / FIU-IND) — the `enrichment/` folder is scaffolded but empty.
- No login / auth — single-user dev mode. `core/auth/jwt.py` is synced from the crypto platform but unused.
- No keyboard shortcuts — deferred UX decision.
- No virtualised rendering — the table renders all rows. Smooth to ~2000; beyond that, we'll need `react-window`.

## Brand & design

- Forensic Ledger palette (navy primary, emerald for credits, ruby for debits, amber for warnings).
- Tri-font: Manrope headlines, Inter body, Space Grotesk mono/tabular.
- Tailwind 4 `@theme` block with dual token families (shadcn + MD3) resolving to the same palette — lets Figma Make components and Gemini/Stitch components coexist.
