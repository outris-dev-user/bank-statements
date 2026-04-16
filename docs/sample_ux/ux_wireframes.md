# UX wireframes — decided layouts

Concrete ASCII wireframes reflecting the **decided UX direction** from [ux-decisions.md](ux-decisions.md). These guide the Phase 1 build.

Key decisions expressed here:
- Table-first landing — user uploads → sees table → reviews → journey begins
- Multi-account tabs + merged view + inter-file separators
- Structured promoted columns (Counterparty, Category) + compact entity chips on expand
- Expand-in-place for peek, drawer for full edit
- Tiered confidence (green / amber / bright amber / red)
- Silent recompute + transient visual indicator

---

## Screen 1 — Case dashboard

```
┌────────────────────────────────────────────────────────────────────────────┐
│  [bank-analyser]                                     [+ New Case]  [Saurabh]│
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│   Cases                                                                    │
│   ─────                                                  [Search...     ]  │
│                                                                            │
│   ┌──────────────────────────────────────────────────────────────────────┐ │
│   │ FIR # 2026/AEC/0471     •  Active          Updated 2 hours ago      │ │
│   │ Suraj Shyam More — Kotak + HDFC Sav                                 │ │
│   │ 2 statements · 792 txns · 3 flags                                   │ │
│   ├──────────────────────────────────────────────────────────────────────┤ │
│   │ FIR # 2026/AEC/0466     •  Active          Updated yesterday        │ │
│   │ Bilal A. K. Mohammed — HDFC Savings (Oct 23 - Mar 24)               │ │
│   │ 1 statement · 554 txns · 12 flags                                   │ │
│   ├──────────────────────────────────────────────────────────────────────┤ │
│   │ FIR # 2025/MPN/1201     •  Archived        Closed 14 days ago       │ │
│   │ Atul Kabra — ICICI Current                                          │ │
│   │ 1 statement · 37 txns · 0 flags                                     │ │
│   └──────────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## Screen 2 — Case overview (persons + accounts + upload)

Persons are first-class; accounts live under persons; statements live under accounts. A single case can investigate multiple persons.

```
┌────────────────────────────────────────────────────────────────────────────┐
│  [← All cases]    FIR # 2026/AEC/0471                          [Saurabh] │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│   Suraj Shyam More investigation       Officer: SI A. Kamat                │
│                                                                            │
│   Persons in this case                                    [+ Add person]   │
│   ─────────────────                                                        │
│                                                                            │
│   👤 Suraj Shyam More                                 [+ Upload statement] │
│     ┌────────────────────────────────────────────────────────────────┐   │
│     │ 🏦 Kotak A/C 7894231652 (CA)          ✓ 240 txns · 1 statement │   │
│     │ 🏦 HDFC Savings A/C ****8420 (SA)     ⚠ 554 txns · 1 statement │   │
│     └────────────────────────────────────────────────────────────────┘   │
│                                                                            │
│   👤 Meera Patel                                       [+ Upload statement]│
│     ┌────────────────────────────────────────────────────────────────┐   │
│     │ (no statements yet)                                              │   │
│     └────────────────────────────────────────────────────────────────┘   │
│                                                                            │
│   ┌──────────────────── Drag & drop PDFs here ──────────────────────┐   │
│   │                                                                   │   │
│   │   Auto-detects bank + account holder. Supports HDFC, IDFC,        │   │
│   │   ICICI, Kotak, SBI, Axis…                                        │   │
│   │                                                                   │   │
│   └───────────────────────────────────────────────────────────────────┘   │
│                                                                            │
│   [Open case workbench →]                                                  │
└────────────────────────────────────────────────────────────────────────────┘
```

Notes:
- Persons as containers lets one case cover multiple people naturally
- Click any account → Screen 3 (workbench opens on that account's tab)
- Drop zone auto-creates persons if the PDF's account-holder name doesn't match an existing person — prompts "new person?" or "link to existing?"

---

## Screen 3 — The workbench (table-first, flagship screen)

This is where LEA spends most of their time. Opens immediately after upload.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ [← Case]  FIR # 2026/AEC/0471 · Suraj Shyam More                       [Saurabh]     │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  [ All transactions ] [ Kotak 7894 ▣ ] [ HDFC Sav ****8420 ] [ Summary ] [ Graph ⓘ ]  │
│                          ═══════════════                                               │
│                                                                                        │
│  Kotak A/C 7894231652 · Suraj Shyam More · CA · INR                                    │
│  ✓ Verified 240/240 · Dr ₹7,00,583 · Cr ₹6,14,301 · Bal ₹3,329                         │
│                                                                                        │
│  [Search...]  Type▾  Counterparty▾  Category▾  Tags▾  □ Needs Review  [3 flags ⚑]    │
│                                                                                        │
│ ┌─┬──────────┬─────┬──────────────────┬───────────┬─────────┬─────────┬─────────┬───┐  │
│ │ │  Date    │ Ch  │ Counterparty     │ Category  │  Debit  │ Credit  │ Balance │⚑ │  │
│ ├─┼──────────┼─────┼──────────────────┼───────────┼─────────┼─────────┼─────────┼───┤  │
│ │▐│ 01/04/21 │ UPI │ Trilok Saxena    │ Transfer  │  200.00 │         │  3,129  │   │  │
│ │▐│ 01/04/21 │ UPI │ CRED             │ Finance   │12,683.00│         │  3,329  │🔴 │  │
│ │▌│ 01/04/21 │ UPI │ Sarika Lalasahe  │ Transfer  │         │10,000.00│ 16,012  │   │  │
│ ├─┴──────────┴─────┴──────────────────┴───────────┴─────────┴─────────┴─────────┴───┤  │
│ │      ── April 2021 statement ends  │  May 2021 statement begins ──   [⋯ file]    │  │
│ ├─┬──────────┬─────┬──────────────────┬───────────┬─────────┬─────────┬─────────┬───┤  │
│ │▐│ 02/05/21 │ UPI │ Amazon           │ Shopping  │  510.00 │         │ 15,502  │   │  │
│ │▐│ 05/05/21 │ ATM │ CHETAN WINES     │ Cash      │ 1,350.00│         │ 14,152  │🟡 │  │
│ │▐│ 20/05/21 │ IMPS│ (unknown: 3511…) │ Transfer  │ 1,000.00│         │ 13,152  │🟡 │  │
│ │▌│ 22/05/21 │ UPI │ Google Pay       │ Rewards   │         │     2.00│ 13,154  │   │  │
│ │ ... 232 more                                                                        │  │
│ └─┴──────────┴─────┴──────────────────┴───────────┴─────────┴─────────┴─────────┴───┘  │
│                                                                                        │
│  [j/k navigate · click row to peek · double-click to edit · / search]                 │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

Notes:
- **Tabs across the top** — "All transactions" (merged across all accounts in case) + one tab per account (Kotak 7894, HDFC Sav 8420) + Summary + Graph (disabled in Phase 1, tooltip says "coming Phase 3")
- **Inter-file separator** inside an account tab when multiple statements span the same account. `[⋯ file]` opens Screen 6 (per-file actions).
- **Dr/Cr signaled by left-border color** — `▐` red for debit, `▌` green for credit. Less visual noise than full-row tint.
- **Promoted columns** — Counterparty + Category are always shown (derived entities). Every other entity type (tags, custom) lives in the expand-peek.
- **Flag column** — 🔴 hard error / sum-check contributor, 🟡 needs review / low confidence, blank = clean.
- **Unresolved entities** show as `(unknown: 3511…)` — clickable to resolve.

---

## Screen 3a — Row expand-in-place (peek)

Click a row once → expands to show raw OCR + all entity chips. Click again or press Escape to collapse. Multiple rows can be expanded simultaneously.

```
│▐│ 01/04/21 │ UPI │ CRED             │ Finance   │12,683.00│         │  3,329  │🔴 │
│ ├─────────────────────────────────────────────────────────────────────────────────┤ │
│ │  Raw OCR:  UPI/CRED/109108427041/credit card bil                                │ │
│ │  Entities: [UPI] [CRED] [Finance] [credit-card] [+ tag]                         │ │
│ │  Ref: 109108427041                                                              │ │
│ │  Flags: 🔴 Sum-check contributor                                                │ │
│ │  [Edit…]  [📄 Open source PDF p.4]  [✓ Mark reviewed]  [⚑ Flag suspicious]     │ │
│ ├─────────────────────────────────────────────────────────────────────────────────┤ │
│▌│ 01/04/21 │ UPI │ Sarika Lalasahe  │ Transfer  │         │10,000.00│ 16,012  │   │
```

Notes:
- Expansion is inline — keeps table context visible
- **All entities as chips** — promoted columns (Counterparty, Category) AND custom tags appear here
- `[+ tag]` inline adds a custom tag
- `[Edit…]` opens the heavy edit drawer (Screen 3b)

---

## Screen 3b — Edit drawer (heavy edit mode)

Triggered by double-click on row, or Edit button from expanded row. ~40% width on the right.

```
┌─────────────────────────────────────────────┬─────────────────────────────────────┐
│  (table narrowed)                           │  Edit transaction                   │
│                                             │  ─────────────────                  │
│ ▐ 01/04/21 ... CRED        ← selected       │  01/04/21 · UPI · Dr ₹12,683.00     │
│ ▌ 01/04/21 ... Sarika...                    │  Balance after: ₹3,329              │
│ ▐ 02/04/21 ... Amazon                       │                                     │
│  ...                                        │  Raw OCR         [📄 Source PDF p.4]│
│                                             │  ┌─────────────────────────────────┐│
│                                             │  │ UPI/CRED/109108427041/credit    ││
│                                             │  │ card bil                        ││
│                                             │  └─────────────────────────────────┘│
│                                             │                                     │
│                                             │  Entities (key-value)               │
│                                             │  ┌─────────────────────────────────┐│
│                                             │  │ Channel:       [UPI          ▾] ││
│                                             │  │ Counterparty:  [CRED         ✎] ││
│                                             │  │ Category:      [Finance      ▾] ││
│                                             │  │ Ref number:    109108427041     ││
│                                             │  │ Tags:   [credit-card ×] [+ tag] ││
│                                             │  │ [+ Add custom entity]           ││
│                                             │  └─────────────────────────────────┘│
│                                             │                                     │
│                                             │  Linked person / entity             │
│                                             │  ◉ Not linked                       │
│                                             │  ○ Link to existing…                │
│                                             │    ℹ "CRED" appears in 3 other rows │
│                                             │      [Link all 4 to same entity]    │
│                                             │  ○ Create new counterparty entity   │
│                                             │                                     │
│                                             │  Amount & date                      │
│                                             │  Debit:  [12,683.00]                │
│                                             │  Date:   [01/04/2021]               │
│                                             │  ⓘ Editing these recomputes balance │
│                                             │                                     │
│                                             │  Notes                              │
│                                             │  [                                ] │
│                                             │                                     │
│                                             │  Audit: extracted 15 Apr 12:04      │
│                                             │  Last edited: never                 │
│                                             │                                     │
│                                             │  [Cancel]              [Save]       │
└─────────────────────────────────────────────┴─────────────────────────────────────┘
```

Notes:
- **Entity section is key-value**, not fixed — new entity types (`[+ Add custom entity]`) or tags (`[+ tag]`) extend without schema change.
- **Auto-suggest merge** when an entity value appears across multiple rows — "CRED appears in 3 other rows — Link all 4" bulk action.
- **Amount/date edit** triggers balance recompute (see Screen 3c).
- Escape closes; Save persists; Cancel discards.

---

## Screen 3c — Silent recompute + transient indicator

User edits ₹12,683.00 to ₹12,683.50 and saves. Balance for this row + all subsequent rows in the same account/statement recomputes.

```
  Before save:
  ┌─┬──────────┬─────┬─────────┬───────────┬──────────┬─────────┬────────┐
  │▐│ 01/04/21 │ UPI │ CRED    │ Finance   │12,683.00 │         │ 3,329  │🔴
  │▌│ 01/04/21 │ UPI │ Sarika  │ Transfer  │          │10,000.00│16,012  │
  │▐│ 02/05/21 │ UPI │ Amazon  │ Shopping  │   510.00 │         │15,502  │

  After save (rows 1–3 briefly italicised + light-yellow highlight for 2-3s):
  ┌─┬──────────┬─────┬─────────┬───────────┬──────────┬─────────┬────────┐
  │▐│ 01/04/21 │ UPI │ CRED *  │ Finance   │12,683.50 │         │ 3,328.50│🔴   ← changed
  │▌│ 01/04/21 │ UPI │ Sarika  │ Transfer  │          │10,000.00│16,011.50│     ← recomputed
  │▐│ 02/05/21 │ UPI │ Amazon  │ Shopping  │   510.00 │         │15,501.50│     ← recomputed
  ...
  (after 3s the italics/highlight fade; the * on CRED stays as "edited" marker)

  Top banner:
  ⚠  Sum-check now 99.96% (was 100%) — your edit shifted debit total by +₹0.50.
     [Undo]  [Accept as intentional]
```

Notes:
- **`*` prefix marks edited cell** — persists as audit cue
- **Italics + highlight flash** on recomputed balance cells, for 2-3 seconds
- **Sum-check flip is loud** — banner at top with Undo / Accept
- Audit log silently records `{user, timestamp, field, old_value=12683.00, new_value=12683.50}`

---

## Screen 4 — Upload progress (inline during ingestion)

```
┌────────────────────────────────────────────────────────────────────────────┐
│  Uploading: Statement April-Aug 2021.pdf                                   │
├────────────────────────────────────────────────────────────────────────────┤
│   Size: 256 KB · 10 pages                                                  │
│                                                                            │
│   ✓ Detected bank: Kotak Mahindra                                          │
│   ✓ Extracted text (pdfplumber, 240ms)                                     │
│   ✓ Parsed 240 transactions                                                │
│   ✓ Sum-check: 100% (matches declared totals)                              │
│   ⣾ Resolving entities...                                                  │
│   ○ Reconciling across case                                                │
│                                                                            │
│   Account holder detected: Suraj Shyam More                                │
│   Link to person: [Suraj Shyam More         ▾]  [+ New person]             │
│   Account:        Kotak A/C 7894231652                                     │
│                   [+ Create new account under this person]                 │
│                                                                            │
│                                                [Cancel]  [Open workbench]  │
└────────────────────────────────────────────────────────────────────────────┘
```

Notes:
- Stepwise progress earns trust
- Account holder + account linking happens during upload with sensible auto-suggestions
- On failure at any step, show the failing step with a clear error + "re-upload" action
- On success, "Open workbench" jumps straight to Screen 3 on the newly-loaded account's tab

---

## Screen 5 — All transactions (merged timeline)

The first tab of the workbench. Shows every transaction in the case, chronologically merged across all accounts.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ FIR # 2026/AEC/0471 · All transactions                                 [Saurabh]     │
│                                                                                        │
│ [ All ▣ ] [ Kotak 7894 ] [ HDFC Sav 8420 ] [ Summary ] [ Graph ⓘ ]                     │
│                                                                                        │
│ Show: [✓ Kotak 7894]  [✓ HDFC Sav 8420]     (toggle accounts on/off)                  │
│ Search...  Type▾ Counterparty▾ Category▾ Tags▾ Person▾                                 │
│                                                                                        │
│ ┌─┬──────────┬──────────────┬─────┬─────────────┬──────────┬──────────┬──────┐         │
│ │ │ Date     │ Source       │ Ch  │ Counterparty│ Amount   │ Balance* │ Flag │         │
│ ├─┼──────────┼──────────────┼─────┼─────────────┼──────────┼──────────┼──────┤         │
│ │▐│ 01/04/21 │ Kotak 7894   │ UPI │ Trilok Sax…│   -200.00│   3,129  │      │         │
│ │▐│ 01/04/21 │ Kotak 7894   │ UPI │ CRED        │-12,683.00│   3,329  │ 🔴   │         │
│ │▐│ 05/10/23 │ HDFC Sav 8420│ UPI │ Amazon      │   -510.00│ 126,478  │      │         │
│ │▌│ 05/10/23 │ HDFC Sav 8420│ NEFT│ SALARY ACME │+35,000.00│ 161,478  │      │         │
│ └─┴──────────┴──────────────┴─────┴─────────────┴──────────┴──────────┴──────┘         │
│                                                                                        │
│ * Balance column is per-account (each row's own account's running balance)             │
│                                                                                        │
│ Summary: 792 txns · In ₹28,96,376 · Out ₹30,23,567 · Net ₹-1,27,191                   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

Notes:
- `Source` column answers "which account did this come from"
- Toggle chips let users quickly include/exclude per-account rows
- Signed amount (`-200.00`, `+35,000.00`) rather than Dr/Cr columns — cleaner for merged view
- Bottom summary respects current filters
- Balance is **per-account** not globally summed — clarified in footnote

---

## Screen 6 — File-level actions (per-statement controls)

Triggered from `[⋯ file]` on the inter-file separator.

```
┌────────────────────────────────────────────────────────────────────────────┐
│  Statement: April 2021.PDF                                                  │
├────────────────────────────────────────────────────────────────────────────┤
│   Kotak A/C 7894231652 · Suraj Shyam More                                  │
│   Uploaded: 15 Apr 12:04 by Saurabh                                        │
│   Period: 01/04/21 — 30/04/21                                              │
│   Transactions: 87 (2 manually edited)                                     │
│   Sum-check: ✓ 100% (Dr ₹1,23,456 matches declared)                        │
│                                                                            │
│   Actions                                                                  │
│   [📄 View original PDF]                                                   │
│   [⟳ Re-extract]       (re-run latest parser on the same file)             │
│   [🔄 Re-upload]       (replace this file with a new upload, same account) │
│   [⚠ Delete statement] (removes this statement and its 87 transactions)    │
└────────────────────────────────────────────────────────────────────────────┘
```

Notes:
- **Re-upload** is the key flow when the original file was bad — cascade-deletes old rows, ingests new file
- **Re-extract** is for when the file is fine but the parser improved (newer bank plugin)
- **Delete** requires confirmation ("this will remove 87 transactions; continue?")

---

## What's deliberately NOT shown (Phase 2/3)

- Graph canvas (Cytoscape) — Phase 3 after crypto sync
- Advanced algorithms (circular trading, mule rings, hawala) — Phase 3
- Cross-case intelligence — Phase 4
- ML-based anomaly detection — Phase 3+
- OSINT enrichment — Phase 2+

## Component inventory for Phase 1 build

| Component | Used on | Reuse from crypto? |
|---|---|---|
| CaseList | Screen 1 | Fork (rename FIR fields) |
| CaseOverview / PersonGroup / AccountCard | Screen 2 | New |
| FileDropZone | Screen 2, 4 | New |
| WorkbenchTabs | Screen 3, 5 | New |
| TransactionTable (virtualized, inline expand, drawer trigger) | Screen 3, 5 | New (can heavy-fork crypto's ActivityTab) |
| InterFileSeparator | Screen 3 | New |
| EntityChip / EntityEditor | Screen 3a, 3b | New |
| EditDrawer | Screen 3b | Fork crypto's NodeInspector shell |
| RecomputeIndicator | Screen 3c | New (small) |
| SumCheckBanner | Screen 3c | New (small) |
| UploadProgressModal | Screen 4 | New |
| StatementActionsPanel | Screen 6 | New |

~10 new components + 2 crypto forks. ~3-4 weeks of focused frontend build.
