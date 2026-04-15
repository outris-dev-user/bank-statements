# UX wireframes — candidate layouts

Concrete ASCII wireframes to react to. Each screen shows **2-3 candidate variants** with brief tradeoff notes. Use [ux-decisions.md](ux-decisions.md) as the companion; the decisions there drive which variant wins.

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
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

**Simple and predictable.** Copied from crypto's case UX with minimal change (no "Workbench" column since bank cases are table-first). Adequate for Phase 1.

---

## Screen 2 — Inside a case (upload + list statements)

```
┌────────────────────────────────────────────────────────────────────────────┐
│  [← All cases]    FIR # 2026/AEC/0471    [⋯] [Archive]         [Saurabh] │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│   Suraj Shyam More                                                         │
│   Kotak + HDFC Sav investigation          Officer: SI A. Kamat             │
│                                                                            │
│   ┌──────────────── Upload statement ─────────────────────────────────┐   │
│   │                                                                    │   │
│   │        ⟱  drag PDF here, or click to browse                        │   │
│   │            supports HDFC, IDFC, ICICI, Kotak, SBI, Axis...        │   │
│   │                                                                    │   │
│   └────────────────────────────────────────────────────────────────────┘   │
│                                                                            │
│   Statements in this case                                                  │
│                                                                            │
│   ┌──────────────────────────────────────────────────────────────────┐   │
│   │ 📄 Statement April-Aug 2021.pdf    Kotak  ✓ Verified (240/240)   │   │
│   │    Suraj Shyam More · A/C 7894231652 · 01/04/21 — 25/08/21       │   │
│   │    Debit ₹7,00,583 · Credit ₹6,14,301 · Balance ₹3,329           │   │
│   │                                      [Review]  [Flags: 3]  [⋯]   │   │
│   ├──────────────────────────────────────────────────────────────────┤   │
│   │ 📄 Acct Statement_XX3584.pdf    HDFC Sav  ⚠ 99.1% (552/554)      │   │
│   │    Bilal A. K. Mohammed · A/C ****8420 · 01/10/23 — 31/03/24     │   │
│   │    Debit ₹23,22,984 · Credit ₹22,82,076 · Balance ₹48,513        │   │
│   │                                      [Review]  [Flags: 12] [⋯]   │   │
│   └──────────────────────────────────────────────────────────────────┘   │
│                                                                            │
│   [Case summary]  [All transactions (merged)]  [Graph (Phase 3)]           │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

Notes:
- Sum-check status is the big trust signal (✓ Verified / ⚠ 99.1%) — earns user confidence fast
- Flags count is a nudge to investigate
- Tabs at bottom for case-level views (summary, merged table, graph later)

---

## Screen 3 — Transaction review (the flagship) — THREE variants

### Variant A — Structured columns (my lean)

```
┌────────────────────────────────────────────────────────────────────────────────┐
│  ← Case · FIR # 2026/AEC/0471 / Statement April-Aug 2021.pdf        [Saurabh] │
├────────────────────────────────────────────────────────────────────────────────┤
│                                                                                │
│   Kotak  ·  A/C 7894231652  ·  Suraj Shyam More  ·  01/04/21 — 25/08/21        │
│   ✓ Verified 240/240   Dr ₹7,00,583   Cr ₹6,14,301   Bal ₹3,329                │
│                                                                                │
│   [Search...]  Type: [All▾]  Counterparty: [All▾]  Needs Review □  [3 flags]   │
│                                                                                │
│  ┌─────┬──────────┬─────┬────────────────┬───────────┬─────────┬──────────┬────┐
│  │     │  Date    │ Ch. │  Counterparty  │  Category │  Debit  │  Credit  │ ⚑  │
│  ├─────┼──────────┼─────┼────────────────┼───────────┼─────────┼──────────┼────┤
│  │▐ Dr │ 01/04/21 │ UPI │ Trilok Saxena  │  Transfer │   200.00│          │    │
│  │▐ Dr │ 01/04/21 │ UPI │ CRED           │  Finance  │ 12,683.0│          │ 🔴 │
│  │▌ Cr │ 01/04/21 │ UPI │ Sarika Lalasahe│  Transfer │         │ 10,000.00│    │
│  │▐ Dr │ 02/04/21 │ UPI │ Amazon         │  Shopping │   510.00│          │    │
│  │▐ Dr │ 05/04/21 │ ATM │ CHETAN WINES   │  Cash     │  1,350.0│          │ 🟡 │
│  │▐ Dr │ 20/04/21 │ IMPS│ [unknown-3511] │  Transfer │  1,000.0│          │ 🟡 │
│  │▐ Dr │ 22/04/21 │ UPI │ Maria Felix    │  Transfer │   550.00│          │    │
│  │▌ Cr │ 22/04/21 │ UPI │ Google Pay     │  Rewards  │         │      2.00│    │
│  │▐ Dr │ 23/04/21 │ UPI │ Ragini Pan Shop│  Food     │    20.00│          │    │
│  │▐ Dr │ 23/04/21 │ UPI │ Sitaram Rose   │  Food     │    11.00│          │    │
│  │ ... 230 more                                                                │
│  └─────┴──────────┴─────┴────────────────┴───────────┴─────────┴──────────┴────┘
│                                                                                │
│   ⌨ j/k navigate · e edit · x mark reviewed · ? flag · c open PDF             │
└────────────────────────────────────────────────────────────────────────────────┘
```

Notes:
- `▐ Dr` / `▌ Cr` — colored left-border (red/green) instead of full-row tint; less visual noise
- Counterparty is the parsed entity, not the raw description — trades OCR trust for scanability
- `[unknown-3511]` placeholder for rows where we couldn't resolve — clickable to edit
- Flag column shows 🔴 (sum-check contributor) / 🟡 (needs review) / empty (clean)
- Keyboard hints at bottom

### Variant B — Raw OCR + entity chips below (trust-first)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ← Statement April-Aug 2021.pdf                                   [Saurabh]│
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ ▐ Dr  01/04/21     200.00    Bal 3,129                          🟢 OK │  │
│  │    UPI/Trilok Saxena/109109474380/UPI                                 │  │
│  │    [UPI] [Trilok Saxena ✎] [Transfer ✎]                              │  │
│  ├───────────────────────────────────────────────────────────────────────┤  │
│  │ ▐ Dr  01/04/21   12,683.00    Bal 3,329                        🔴 flag │  │
│  │    UPI/CRED/109108427041/credit card bil                              │  │
│  │    [UPI] [CRED ✎] [Finance ✎]                                         │  │
│  ├───────────────────────────────────────────────────────────────────────┤  │
│  │ ▌ Cr  01/04/21   10,000.00    Bal 16,012                        🟢 OK │  │
│  │    UPI/SARIKA LALASAHE/109108082770/April                             │  │
│  │    [UPI] [Sarika Lalasahe ✎] [Transfer ✎]                            │  │
│  ├───────────────────────────────────────────────────────────────────────┤  │
│  │   ...                                                                 │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

Notes:
- Raw OCR line always visible (builds trust; user verifies)
- Entity chips below, each clickable to edit
- Each row is ~3 lines tall → ~20 rows per viewport vs ~40 in Variant A
- Feels like an inbox more than a spreadsheet
- Good for slow, careful review; bad for scanning 300 rows

### Variant C — Hybrid (row-expand to reveal entities)

```
┌────────────────────────────────────────────────────────────────────────────┐
│  ┌─┬──────────┬─────┬──────────────────────────────────┬─────────┬────────┐│
│  │ │  Date    │ Ch. │  Description / Counterparty      │ Debit   │ Credit ││
│  ├─┼──────────┼─────┼──────────────────────────────────┼─────────┼────────┤│
│  │▐│ 01/04/21 │ UPI │ Trilok Saxena  ▾                 │  200.00 │        ││
│  │▐│ 01/04/21 │ UPI │ CRED 🔴       ▾                  │12,683.00│        ││
│  │ │          │     │ ┌ Raw OCR ──────────────────────┐│         │        ││
│  │ │          │     │ │ UPI/CRED/109108427041/credit  ││         │        ││
│  │ │          │     │ │ card bil                      ││         │        ││
│  │ │          │     │ └───────────────────────────────┘│         │        ││
│  │ │          │     │  Counterparty: [CRED            ]│         │        ││
│  │ │          │     │  Category:     [Finance       ▾]│         │        ││
│  │ │          │     │  Ref #:        109108427041      │         │        ││
│  │ │          │     │  Notes:        [                ]│         │        ││
│  │ │          │     │  [Save]  [Flag suspicious]       │         │        ││
│  │▌│ 01/04/21 │ UPI │ Sarika Lalasahe  ▾               │         │10,000  ││
│  └─┴──────────┴─────┴──────────────────────────────────┴─────────┴────────┘│
└────────────────────────────────────────────────────────────────────────────┘
```

Notes:
- Scanability of Variant A preserved
- Full editing UI appears inline on click (expand row)
- No separate drawer
- Feels like GitHub's PR review UI (collapsed → expanded file diff)

---

## Screen 4 — Drawer view (if we go with Variant A + drawer on click)

```
┌──────────────────────────────┬─────────────────────────────────┐
│  (table — narrowed)          │  Transaction details            │
│                              │  ─────────────────────          │
│ ▐ Dr 01/04/21 ...            │  01/04/21 · UPI · Dr ₹12,683.00 │
│ ▐ Dr 01/04/21 CRED    ← sel  │  Balance after: ₹3,329          │
│ ▌ Cr 01/04/21 Sarika...      │                                 │
│ ▐ Dr 02/04/21 Amazon         │  Raw OCR                        │
│ ▐ Dr 05/04/21 CHETAN...      │  ┌───────────────────────────┐  │
│  ...                         │  │ UPI/CRED/109108427041/cr  │  │
│                              │  │ edit card bil             │  │
│                              │  └───────────────────────────┘  │
│                              │                                 │
│                              │  Parsed entities                │
│                              │  Counterparty: [CRED         ]  │
│                              │  Channel:      [UPI         ▾]  │
│                              │  Category:     [Finance     ▾]  │
│                              │  Ref number:   109108427041     │
│                              │                                 │
│                              │  Linked person/entity           │
│                              │  ◯ Not linked                   │
│                              │  ⚪ Link to existing entity...   │
│                              │  ⚪ Create new entity            │
│                              │                                 │
│                              │  Notes                          │
│                              │  [                            ] │
│                              │                                 │
│                              │  Flags                          │
│                              │  🔴 Sum-check contributor       │
│                              │                                 │
│                              │  Audit                          │
│                              │  Extracted: 15 Apr 12:04        │
│                              │  Last edited: never             │
│                              │                                 │
│                              │  [Open PDF at p.3]   [Save]     │
└──────────────────────────────┴─────────────────────────────────┘
```

Notes:
- Drawer at ~40% width on the right
- Raw OCR is always visible (trust cue)
- Linked entity is where multi-statement coherence happens ("this CRED counterparty is the same entity as in Statement 2")
- PDF jump button on the drawer; keeps source-verification within reach

---

## Screen 5 — Upload progress (inline during ingestion)

```
┌────────────────────────────────────────────────────────────────────────────┐
│  Uploading Statement April-Aug 2021.pdf                                    │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│   Size: 256 KB · 10 pages                                                  │
│                                                                            │
│   ✓ Detected bank: Kotak Mahindra                                          │
│   ✓ Extracted text (pdfplumber, 240ms)                                     │
│   ✓ Parsed 240 transactions                                                │
│   ⣾ Resolving entities...                                                  │
│   ○ Reconciling totals                                                     │
│                                                                            │
│   Account holder: Suraj Shyam More                                         │
│   Person: [Suraj Shyam More       ▾] [+ New person]                       │
│                                                                            │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

Notes:
- Stepwise progress builds trust ("I can see what it's doing")
- Person assignment is the one user input during upload — we auto-suggest, they confirm
- On failure, the failing step shows a clear error

---

## Screen 6 — Case-level merged view (Phase 2)

```
┌────────────────────────────────────────────────────────────────────────────┐
│  FIR # 2026/AEC/0471 · All transactions (merged across statements)         │
│                                                                            │
│  [Kotak ✓] [HDFC Sav ✓]  Search... Type▾ Counterparty▾ Category▾ Flags▾  │
│                                                                            │
│  ┌─┬──────────┬───────────┬─────┬─────────────────┬────────────┬─────────┐ │
│  │ │ Date     │ Source    │ Ch. │ Counterparty    │ Amount     │ Balance │ │
│  ├─┼──────────┼───────────┼─────┼─────────────────┼────────────┼─────────┤ │
│  │▐│ 01/04/21 │ Kotak CA  │ UPI │ Trilok Saxena   │   -200.00  │  3,129  │ │
│  │▐│ 01/04/21 │ Kotak CA  │ UPI │ CRED            │-12,683.00  │  3,329  │ │
│  │▐│ 05/04/21 │ HDFC Sav  │ UPI │ Amazon          │   -510.00  │126,478  │ │
│  │▌│ 05/04/21 │ HDFC Sav  │ NEFT│ SALARY ACME CO  │+35,000.00  │161,478  │ │
│  │ │ ...                                                                  │ │
│  └─┴──────────┴───────────┴─────┴─────────────────┴────────────┴─────────┘ │
│                                                                            │
│  Summary: 792 txns · In ₹28,96,376 · Out ₹30,23,567 · Net ₹-1,27,191      │
└────────────────────────────────────────────────────────────────────────────┘
```

Notes:
- `Source` column resolves "which statement did this come from"
- Balance is per-account (running balance on that account), not across accounts
- Filter chips at top let user toggle Kotak / HDFC on-off
- Bottom summary aggregates what's visible (respects filters)

---

## Open questions these wireframes prompt

1. **Which variant (A/B/C) is right for Phase 1?** I'd lean A + expand-on-click like C, skip drawer until we need it.
2. **How aggressive is entity auto-resolution?** Variant A shows clean names; if our resolver is wrong 10% of the time, user loses trust fast.
3. **Should we hide the raw description behind a toggle?** Or keep it always visible somewhere?
4. **What does "bank auto-detected" look like on an unknown bank?** Fallback to "Generic parser — please verify"?
5. **Phase 1 ships without the graph tab — do we show it disabled/coming-soon or hide entirely?**

Mark up these wireframes with changes, new variants, or open questions. This is meant to be reacted to, not adopted.
