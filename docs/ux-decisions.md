# UX decisions — **RESOLVED 2026-04-15**

All 12 decisions locked in. Each section below shows the resolution first, then preserves the original options as historical context.

## Summary of decisions

| # | Decision | Resolution |
|---|---|---|
| 1 | Entity model | **Key-value pairs, extensible**. Core promoted entities: Counterparty, Channel, Category. Users can define custom entity types and tags. |
| 2 | Visual display | **Structured columns for promoted entities + compact chips for the rest**. Avoid per-entity-type columns (sparse cells). |
| 3 | Edit pattern | **Hybrid** — inline for typos (amount/date/description), drawer for entity resolution. |
| 4 | Correction vs enrichment | **Option C** — single edit surface, audit log distinguishes. |
| 5 | Confidence signaling | **Tiered** (green / amber / bright amber / red). |
| 6 | Multi-statement view | **Both merged timeline AND per-account tabs**. Within an account tab: inter-file separators between statements. Enables per-file re-upload. |
| 7 | Entity resolution | **Auto-merge on exact** (VPA, account, phone). **Suggest-merge on fuzzy name**. Bulk-accept for multiple suggestions. |
| 8 | Drill-in | **Expand-in-place for peek, drawer for full edit**. Key framing: table is the **primary entry point after upload** — LEA reviews/approves there before journey begins. |
| 9 | Audit trail | **Minimal** (user, timestamp, old value, new value). Forensic-grade deferred. |
| 10 | Keyboard shortcuts | **Deferred** to post-Phase-1 usage patterns. |
| 11 | PDF source linking | **Page-level only** in Phase 1. Line-level is Phase 2. |
| 12 | Amount-edit recompute | **Silent recompute + transient visual indicator** (bold/italic/highlight for 2-3s on changed rows). Warn loudly on sum-check flip. |

## Architectural consequences (the big ones)

1. **Entity data model is key-value, not rigid columns** — the backend `Transaction` row stores `entities: Dict[str, EntityValue]` with the type registry separate. New entity types can be added without schema migration. See [data-model.md](data-model.md).

2. **Journey is table-first** — unlike crypto where the graph opens first and tables are an inspector tab, bank opens the transaction table immediately after upload. This is the LEA's daily driver surface; everything else (graph, algorithms) is a pivot *from* the table.

3. **File-level operations matter** — user must be able to re-upload a specific statement (e.g. corrupted PDF, wrong password). Tabs-per-account + inter-file separator is the UI surface; backend `Statement` is a first-class entity inside a `Case`, with cascade-delete of its transactions.

4. **User-defined categories and LEA-pattern tags** — category is not a fixed enum; users register new categories. Tags are similar — LEA analysts can define tags ("possible-hawala", "round-tripping", etc.) that can be applied to rows and surfaced in filters/aggregates. These are just another key-value entity type.

---

# Original decision sections (historical)

Preserved for context. Below was the state before resolution.

## Decision 1 — What counts as an "entity" in a transaction? [RESOLVED]

## Decision 1 — What counts as an "entity" in a transaction?

When we extract a row, what should we surface as "tagged entities" the user can edit?

| Candidate entity | Always present? | Example | User value |
|---|---|---|---|
| Counterparty (person/merchant name) | Yes (mostly) | "AMAZON", "Ragini pan shop", "MARIA FELIX" | High — this is "who was this with" |
| Counterparty bank handle (VPA / account) | If present | `mariafelix@ybl`, `SCBL0036046` | Medium — disambiguates identical names |
| Transaction channel | Yes | `UPI / NEFT / IMPS / ATM / POS / Cheque` | High — type of activity |
| Reference number | Yes | `327302563522` | Low for users, high for audit |
| Category (inferred) | Optional | `food / rent / transfer / salary` | High — summarisation |
| Location (ATM city, merchant city) | Sometimes | `VIRAR`, `THANE` | Medium — geographical patterns |
| Phone number | If embedded | `7977137150` (in UPI handles) | Medium — cross-statement linking |
| Merchant brand (normalised) | Optional | `Amazon`, `Paytm`, `Google Pay` | High — clusters many rows |

**Open question:** Which of these do we extract and edit in Phase 1? My default: **Counterparty + Channel + Category**. Everything else is Phase 2+.

## Decision 2 — How are entities visually displayed?

| Option | Example | Pros | Cons |
|---|---|---|---|
| **A. Chips inline** in description cell | `UPI › [AMAZON] › request from Am` | Dense; immediate visual; editable on click | Busy if 4+ entities; tight horizontal space |
| **B. Dedicated columns** per entity type | `Desc \| Counterparty \| Channel \| Category` | Scannable, sortable, filterable | Description loses context; more columns = wider table |
| **C. Entity column only** (hide raw description) | `Counterparty \| Channel \| Amount \| ...` | Clean; forces structured review | Loses original OCR text for verification |
| **D. Raw desc + entity chips below** | Two-line row with description on top, chips underneath | Both contexts visible | Doubles row height; table feels heavier |
| **E. Inspector panel on row select** | Table minimal; drawer opens with entities when row clicked | Clean table; full entity context on demand | Click cost per row; splits attention |

**My lean:** **B (dedicated columns) for the primary view, with option to toggle "raw OCR" column on/off.** Inline chips look cool but fail at scale — analysts scan hundreds of rows per statement.

**Counter-argument worth testing:** If Phase 1 success hinges on "user trusts the extraction," maybe the raw OCR *needs* to be visible alongside parsed entities to build that trust. Then D becomes the answer.

## Decision 3 — Inline editing vs modal/drawer

| Option | Pros | Cons |
|---|---|---|
| **Excel-style inline** (click cell, type, tab to next) | Fast; familiar; keyboard-first | Hard for complex edits (split a row, merge rows); harder to show context |
| **Row-click opens drawer** with all fields editable | Rich context (can show the PDF snippet); easier validation; supports multi-entity editing | Slower per-edit; mouse-heavy |
| **Both, by column type** | Amount/date/description → inline; Counterparty/Category → drawer with suggestions | Flexible | More to explain; dual model |

**My lean:** **Hybrid.** Amount, date, description → inline. Counterparty and Category → drawer with auto-complete from case-level known entities. Reason: amount/date corrections are typo-sized; entity resolution is conceptual and benefits from a bigger surface.

## Decision 4 — Correction vs enrichment: same UI or separate?

Two user actions that currently collide:
- **Correction** — "OCR said ₹13,761 but the actual is ₹13,761.00, or the counterparty is 'MARIE' not 'MARIA' — fix the raw data"
- **Enrichment** — "this is a salary credit, tag it as category=salary; link counterparty to the 'Acme Ltd' person entity I created"

| Option | Implementation |
|---|---|
| **A. Same field, same edit** | User edits whatever they want; we track all changes as "edits" |
| **B. Two distinct layers** | "Raw OCR" row (read-only after correction is accepted) + "Analyst view" row (freely editable); toggle between them |
| **C. Single edit, dual history** | One visible field, but audit log separates "correction" (amount/date/raw text changed) from "enrichment" (category/notes added) |

**My lean:** **C.** Users shouldn't need to know which bucket their edit falls into. Audit log + labels handle the regulatory integrity question behind the scenes.

## Decision 5 — Confidence signaling

What makes us tint a row amber ("needs review")?

- OCR extraction confidence below threshold (per character / per field)
- Parser fallback fired (e.g. HDFC Savings balance-change heuristic didn't match, used keyword heuristic)
- Sum-check mismatch (row's amount contributed to a sum-check failure)
- Unusually long description (possible multi-line merge error)
- Amount has odd formatting (negative sign, commas in weird places)
- Counterparty not recognised against any known entity

| Option | Behaviour |
|---|---|
| **A. Aggressive** | Flag any trigger above → many amber rows, user feels burdened |
| **B. Conservative** | Flag only if multiple triggers OR sum-check mismatch → misses subtle errors |
| **C. Tiered** | Green (confident), light amber (1 trigger), bright amber (2+ triggers), red (sum-check mismatch) |

**My lean:** **C.** Investigator eyes scan red first, amber second, green ignored. Map visual intensity to attention priority.

## Decision 6 — Multi-statement view in one case

Three statements uploaded for "Saurabh Sethi" (his HDFC CC, HDFC savings, ICICI). How do we show them?

| Option | Pros | Cons |
|---|---|---|
| **A. Separate tabs** per statement | Simple mental model; clean context per file | Hard to see cross-statement patterns |
| **B. Unified timeline** (all transactions interleaved chronologically) | Shows "flow across accounts" naturally | Loses "this row came from this statement" clarity |
| **C. Tabs + a "Merged" view tab** | Both | More UI |
| **D. Always-merged** + "Source" column showing origin statement | Best of both without tab proliferation | Source column adds width; filter-by-source needed |

**My lean:** **D, with a filter-by-statement dropdown prominent.** The merge is the high-value view; source tracking is just a column. Crypto's case view works this way.

## Decision 7 — Entity resolution across statements within a case

If "NAFIS.APPS-1@OKAXIS" appears in 3 of the person's statements, do we auto-merge them?

| Option | Behaviour |
|---|---|
| **A. Auto-merge** on exact string match | Zero friction; risky if OCR has small variations |
| **B. Suggest merge** ("looks like same entity — confirm?") | Safer, slower, user-driven |
| **C. Manual** entity creation; user links rows to entities | Most control, most work |
| **D. Auto-merge on exact VPA/account match; suggest-merge on fuzzy name** | Best of all | Most complex |

**My lean:** **D.** Exact structured identifiers (VPA, account, phone) → auto-merge. Name-only matches → suggest. Never auto-merge if only names match.

## Decision 8 — The "drill into row" interaction

If we go with the table-first layout, what happens on row-click?

| Option | What opens |
|---|---|
| **A. Right drawer** (crypto-style inspector) | Familiar pattern; splits screen |
| **B. Expand-in-place** (row grows to show details) | Keeps table context; limited vertical room |
| **C. Modal overlay** | Full focus on the detail; blocks table |
| **D. Dedicated route** `/case/123/statement/45/txn/678` | Shareable URL; heavy for quick checks |
| **E. Bottom sheet** | Table stays readable; common pattern in mobile-first apps |

**My lean:** **B (expand-in-place) for quick peek; drawer (A) for full detail / editing / linked entities.** Click once to peek, click again (or an icon) to open the drawer.

## Decision 9 — Audit trail granularity

Regulatory / LEA context: edits to financial evidence need trails. How detailed?

- **Minimum viable:** who, when, what changed (old → new), rationale (optional free text)
- **Richer:** all of above + case ID + session ID + soft-delete on revert + exports audit log as CSV
- **Forensic-grade:** cryptographic hash chain; signed diffs; tamper-evident

**My lean:** Phase 1 ships **minimum viable** (user + timestamp + old/new). Forensic-grade becomes a Phase 3 concern once LEA partners ask for it.

## Decision 10 — Keyboard-first bindings

For analysts processing 100s of rows per day:

- **j / k** — next / previous row
- **e** — open editor for focused cell
- **Enter** — commit edit
- **Esc** — cancel edit
- **x** — mark reviewed
- **?** — flag as suspicious
- **c** — open PDF source at this row
- **/** — focus search box
- **g c** / **g s** — go to Case list / Statement list

**My lean:** Ship these five (j, k, e, Enter, Esc) in Phase 1. Rest follow usage patterns.

## Decision 11 — PDF source linking

Clicking a row should show the original PDF line. Requires:
- Tracking page number + y-coordinate during extraction (currently not done)
- PDF viewer component (can use `react-pdf` or similar)
- Highlight overlay on the extracted line

**Cost:** ~1 week to implement well. Low cost upfront if we store coordinates during extraction — our parser currently doesn't.

**My lean:** Phase 1 ships **page-level link only** (click row → open PDF at correct page). Line-level highlighting is Phase 2.

## Decision 12 — Editing an amount: what recomputes?

User edits a row's amount from ₹13,761 to ₹13,761.50. Downstream effects:
- Running balance for this row + all subsequent rows
- Sum of debits / credits (aggregates)
- Sum-check status (might flip from OK to FAIL or vice versa)
- Pattern flags (might appear or disappear)

**Questions:**
- Do we show a preview of what will change ("this will recompute running balances for 47 rows")?
- Do we warn loudly if the edit causes sum-check failure?
- Do we prevent edits that break declared-totals check, or allow them with a warning?

**My lean:** **Recompute silently; warn loudly on sum-check flip.** Don't prevent — user might have a reason. Show a dismissable banner: "Your edit caused the sum-check to fail (was 100%, now 99.97%)."

---

# Proposed 2-day UX sprint

## Day 1 — Decisions & wireframes

**Session 1 (2h)** — Decide the 12 open questions above. Paper/whiteboard.
- Bring to the session: 3 sample bank statements in paper form (HDFC CC, HDFC Sav, Kotak) and pretend to review them. Note friction.

**Session 2 (3h)** — Sketch the 3 core screens:
1. Case dashboard
2. Statement review (the table-first view)
3. Expand/drawer for a single transaction

Produce Figma or paper sketches. For each, produce 2 variants based on the decisions above.

**Session 3 (1h)** — Prioritise. What ships in Phase 1 vs Phase 2.

## Day 2 — Prototype & test

**Session 4 (4h)** — Clickable prototype in Figma (or similar). 3 screens, 2 task flows:
- Task A: "Upload a new statement, review 10 rows, correct 2, mark all as reviewed"
- Task B: "Open existing case, filter to a specific counterparty, look at all transactions with them"

**Session 5 (2h)** — Dry-run with 1-2 non-team people (friends who are analysts or could pretend). Iterate.

**Session 6 (1h)** — Document the decisions. Update this file with outcomes.

## Artifacts the sprint produces

1. This file, updated with decisions
2. Figma file (or equivalent) with high-fi mockups
3. Updated [ux-phases.md](ux-phases.md) with any re-scoping
4. A component inventory for Phase 1 frontend build (table, drawer, chip input, etc.)

---

# Alternative: "let Claude draft wireframes first"

If running the sprint offline is too much ceremony, a cheaper alternative:
1. Use the ASCII wireframes in [ux-wireframes.md](ux-wireframes.md) (next file) as a starting position
2. React to specific screens/flows there
3. Iterate 1-2 rounds until a clear direction emerges
4. Skip to build

This is the right path if you trust your gut and want momentum more than validation. Proper sprint is the right path if Phase 1 is high-stakes (e.g., you're going to demo to LEA soon and want to get it right first try).
