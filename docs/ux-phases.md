# UX phases

Bank-analyser ships as a phased UX. Each phase is a complete, useful product on its own — we don't gate release on phase N+1 being done.

**Core principle:** table-first, graph-second. Investigators need to **trust the data** before they'll trust the analysis. Verification UX (clean, editable, readable table) comes before investigation UX (graph canvas, algorithms).

---

## Phase 1 — Case, Upload, Review

**Goal:** an LEA analyst can upload bank statements, see extracted transactions in a well-formatted table, correct any extraction errors, and persist everything inside a case.

**Screens:**

### Case dashboard
- List of cases (FIR #, title, officer, status, created date, # statements, # transactions, last updated)
- Create new case; open existing case; archive
- Filter/search
- Adapted from crypto's case management (READY to copy — see [CRYPTO_SYNC.md](../CRYPTO_SYNC.md))

### Statement upload
- Inside a case: drag-and-drop one or many PDFs at once
- For each uploaded PDF:
  - Bank auto-detected (via parser fingerprint)
  - Person auto-suggested (from account-holder name in PDF) — user confirms/edits
  - Password prompt if PDF is encrypted
  - Live progress: Extracting → Parsing → Reconciling → Done
- Upload multiple statements from the **same person** or **different persons** into the same case
- Sum-check result shown inline: "37 transactions extracted. Debit total matches declared total (100%). ✓"

### Transaction table view — the flagship of Phase 1
For each statement, show:
- **Header:** bank, account #, person, period, opening balance, closing balance, declared vs extracted totals (with ✓ or ⚠ badge)
- **Table columns:** Date, Description, Ref#, Debit, Credit, Balance, Counterparty (inferred), Category (inferred), Notes, Flags
- **Visual heuristics:**
  - Green left-border / row tint for credits
  - Red left-border / row tint for debits
  - Running balance column with ↗/↘ arrow
  - Confidence badge per row (high / medium / low — from parser + inference)
  - Amber highlight on rows flagged "Needs Review" (low confidence, parsing warning, sum mismatch)
- **Inline editing:**
  - Click any cell to edit (Description, Counterparty, Category, Notes)
  - Amount/Date editable for extraction fixes — triggers balance recompute and a "manually-edited" marker on the row
  - Undo per edit; audit log of who changed what, when
- **Filters/search:**
  - Full-text search on description/counterparty
  - Amount range, date range
  - Type (Dr only / Cr only)
  - "Needs Review" toggle
  - Counterparty (multi-select)
- **Bulk actions:**
  - Select rows → bulk edit category or counterparty
  - Select rows → mark as reviewed
  - Select rows → flag as suspicious
- **Export:** CSV, PDF report of the verified statement

### Statement metadata side-panel (or drawer)
- Opening/closing balance
- Sum-check status
- Edits made (count, by who, when)
- Original PDF preview (click a row to jump to source line in PDF — stretch goal)

**What we don't build in Phase 1:**
- Graph canvas
- Forensic algorithms
- Entity resolution across statements
- Multi-person linking

**Why Phase 1 alone is useful:** LEA analysts today do this manually in Excel. A reliable extraction + editable table + sum-check already saves hours per case before we add any investigation smarts.

---

## Phase 2 — Basic Analysis, Aggregate View

**Goal:** summary views across one or many statements in a case, simple pattern flags, standard forensic algorithms that LEA analysts are already familiar with.

**New screens:**

### Case-level summary view
Aggregates across all statements in the case:
- Total inflow / outflow / net
- Balance timeline (all accounts plotted on one chart)
- Top counterparties (by volume, by count, by person)
- Category breakdown (food / rent / transfers / etc.)
- Monthly volume chart
- Most active days / hours heatmap

### Basic forensic flags on the transaction table
Each row can carry one or more flags:
- **Round amount** — multiples of 1,000 / 10,000 / 1,00,000 (structuring indicator)
- **Just-below threshold** — amounts like ₹49,500 (smurfing)
- **Same-day fan-out** — many transfers on the same date
- **Dormant activation** — large debit after long inactivity
- **Unusual hour** — transfers at odd times (2am, 4am)

These are badges on rows; user can click to see "why flagged."

### Basic algorithms (implemented first)
The ones LEA actually asks for today:
1. **Structuring / Smurfing** — amounts just below reporting thresholds
2. **High-velocity** — fund-through rate, dwell time (adapted from crypto's `velocity_analyzer.py`)
3. **Round-number anomalies** — too many exact round numbers (Benford adjacent)
4. **Same-day round-tripping** — money comes in, goes out same day
5. **Top N counterparties** — simple ranking + volumes
6. **Dormant-then-active** — account inactive N months then large debit

**What we don't build in Phase 2:**
- Canvas / graph view
- Cross-statement entity resolution
- Multi-person linking

**Why Phase 2 alone is useful:** with Phase 1 + basic flags + aggregate view, an analyst can triage a case in minutes instead of days. Good enough for 80% of routine LEA investigations.

---

## Phase 3 — Graph Canvas, Advanced Algorithms, Multi-Person Linking

**Goal:** investigator-grade graph UX for tracing fund flows across multiple accounts and persons. This is where we pull in the crypto team's Cytoscape canvas.

**New screens:**

### Graph canvas (Workbench-Bank tab)
- Pulled from crypto's `GraphCanvas.tsx` (forked; see [CRYPTO_SYNC.md](../CRYPTO_SYNC.md))
- **Nodes:** accounts (shape = bank), persons (shape = person), merchants (shape = merchant), cash (shape = wallet), external entity (shape = generic)
- **Edges:** transactions (thickness = amount, color = Dr/Cr, direction = flow)
- **Interactions:** click node → side drawer with that entity's transactions; double-click → expand its neighbours; select multiple → aggregate stats
- **Filters:** amount threshold, date range, counterparty type
- **Layouts:** temporal, force-directed, bank-clustered
- **Playback:** scrub through time to see flow evolve (from crypto's playback controls)

### Entity panel
- Aggregate across statements: this person owns accounts A, B, C; this merchant received ₹X from N persons
- Across-case linking: "this counterparty UPI handle appears in 4 other cases" (PR later)

### Advanced algorithms
Build on crypto's pattern framework (see [CRYPTO_SYNC.md](../CRYPTO_SYNC.md) — `pattern_framework.py`):
1. **Circular trading** — money returns to origin through N hops
2. **Mule ring detection** — fan-in + fan-out + fast turnaround
3. **Layering** — chains of transfers with specific amounts
4. **Hawala aggregation** — many small deposits → one consolidation → external transfer
5. **Benami patterns** — temporal correlation across persons
6. **Multi-hop exposure** — how close is this account to known bad entities (PEP, sanctioned, FIU-IND STR)

### Multi-person entity resolution
- Within a case: same counterparty name/VPA/account appearing in multiple statements → merged into one entity automatically (with manual override)
- Across persons in the same case: shared counterparty → "these two persons both paid this merchant" → graph edge
- This is where the graph canvas becomes the primary view

### Investigation report generation
- One-click PDF/HTML report of findings: case summary, top flags, algorithm outputs, key entities, evidence pins
- Forked from crypto's `AutoInvestigateReport.tsx`; bank-specific sections

**What's still deferred to Phase 4:**
- Cross-case linking (entity appearing across *other* cases in the system)
- Shared Person/Entity ID with crypto cases
- Advanced ML-based anomaly detection (autoencoders, etc.)
- OSINT enrichment (PEP/sanctions live lookups)

---

## Phase 4 — Cross-case intelligence (later)

Requires the cross-reference API conversation with crypto team (currently parked). Enables:
- "This counterparty appears in 7 other bank cases and 3 crypto cases"
- Shared `Person` across crypto wallets AND bank accounts within one investigation
- Network-level patterns across the full case database

Not scoped right now. Revisit once Phase 3 is shipped and we have real LEA user feedback.

---

## Design divergences from crypto's UX (deliberate)

| Crypto | Bank |
|---|---|
| Graph canvas is the main surface | **Table is the main surface**; graph is a pivot view |
| Node inspector fixed to right side | Bank has no mandatory right panel — "drill into row" might be inline-expand, modal, or dedicated page |
| Inspector tabs: Overview / Activity / Intelligence / Analysis / Actions | Bank tabs likely simpler: Transactions / Counterparties / Timeline |
| Transactions are auxiliary (inside inspector) | Transactions are the primary data object |
| Address profile | Account profile + Person profile (two different things) |
| 19 crypto patterns in detector | 6-8 BFSI patterns, expand over time |

Both share: case management, signal framework, velocity analyzer, multi-hop exposure, pattern-detector skeleton, auth, CSV import.

---

## Sequencing rationale

- **Phase 1 is MVP.** Ships a useful product to LEA. Proves extraction accuracy in the wild. Builds trust.
- **Phase 2 is polish.** Adds the "obvious" algorithms analysts want. Reinforces daily usefulness.
- **Phase 3 is differentiation.** Graph + advanced algorithms = what makes this a forensic platform, not just a fancy Excel.
- **Phase 4 is scale.** Value compounds once the case database gets big.

Ship Phase 1 in ~4 weeks of work (once `core/` has synced models + basic wiring). Phase 2 in another ~3 weeks. Phase 3 depends on crypto-team cleanup cadence.
