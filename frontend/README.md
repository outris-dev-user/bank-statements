# LedgerFlow frontend

Next.js-style Vite + React + Tailwind 4 frontend for LedgerFlow — the forensic bank-statement analysis product built on top of `plugins/bank/` (Python extraction) and a shared `core/` synced from the crypto investigation platform.

## Provenance

This scaffold was assembled from two generated outputs:

- **Bones: Figma Make's project** — real React components, real data model types matching [docs/data-model.md](../docs/data-model.md), working state + filters + expand-in-place + inter-file separator + edit drawer + upload modal.
- **Soul: Gemini's Forensic Ledger theme** — tri-font (Manrope / Inter / Space Grotesk), MD3 palette (navy primary, tonal layering), and the utility classes (`forensic-gradient`, `ghost-border`, `text-tabular`). Lifted into [src/styles/theme.css](src/styles/theme.css) and mapped to both shadcn-style tokens (so bundled shadcn/ui components auto-retheme) and MD3-style tokens (so code ported from design mocks reads naturally).

See [../ARCHITECTURE.md](../ARCHITECTURE.md) for the bigger picture and [../docs/ux-decisions.md](../docs/ux-decisions.md) for the UX decisions this scaffold implements.

## Run

```bash
cd frontend
npm install
npm run dev     # Vite dev server (default: http://localhost:5173)
npm run build   # production build → dist/
```

Node 20+ recommended.

## Structure

```
frontend/
├── index.html                  # LedgerFlow shell
├── package.json                # React 18, react-router, Tailwind 4, shadcn/ui deps
├── vite.config.ts
├── postcss.config.mjs
└── src/
    ├── main.tsx                # entrypoint
    ├── app/
    │   ├── App.tsx             # RouterProvider
    │   ├── routes.tsx          # 3 routes: /, /cases/:id, /cases/:id/workbench
    │   ├── components/
    │   │   ├── Root.tsx               # layout shell
    │   │   ├── CaseDashboard.tsx      # list of cases
    │   │   ├── CaseOverview.tsx       # persons + accounts + file drop zone
    │   │   ├── Workbench.tsx          # the flagship — tabs + table
    │   │   ├── TransactionTable.tsx   # expand-in-place, inter-file separator, flag/confidence
    │   │   ├── EditDrawer.tsx         # key-value entity editor + bulk-link suggestion
    │   │   ├── UploadModal.tsx        # stepwise upload with sum-check
    │   │   ├── figma/                 # Figma-tooling helpers (kept for compatibility)
    │   │   └── ui/                    # shadcn/ui component library (Radix primitives)
    │   └── data/mockData.ts           # mock Cases / Persons / Accounts / Statements / Transactions
    └── styles/
        ├── fonts.css           # Google Fonts imports (Manrope / Inter / Space Grotesk)
        ├── tailwind.css        # Tailwind v4 entry
        ├── theme.css           # LedgerFlow palette — shadcn + MD3 token families
        └── index.css           # imports of the above
```

## Theming model

Two token families coexist and point to the same palette:

- **shadcn names** (`bg-background`, `bg-primary`, `text-foreground`, `border-border`, ...) — drive the bundled shadcn/ui component library without any change.
- **MD3 names** (`bg-surface`, `bg-surface-container-lowest`, `bg-primary-container`, `text-on-surface`, ...) — for code ported from Stitch/Gemini mockups, and for new components written against the Forensic Ledger design system.

Pick whichever reads naturally in the component you're working on. They resolve to the same colors.

### Dr / Cr signaling

- Debit rows: `border-destructive` or `text-destructive` (ruby)
- Credit rows: `bg-[color:var(--fl-emerald-500)]` / `text-[color:var(--fl-emerald-500)]` (emerald)

Both pulled from the Forensic Ledger palette; kept as explicit class references so anyone scanning the code sees the intent immediately.

## What's next (not shipped in this scaffold)

- Wire real parser output from `plugins/bank/` instead of `mockData.ts` — small adapter script, maybe 100 LOC (planned next)
- Sync `core/` models and components from the crypto platform (see [../CRYPTO_SYNC.md](../CRYPTO_SYNC.md))
- Phase 2 — aggregate views + forensic flags
- Phase 3 — Cytoscape graph (forked from crypto's `GraphCanvas.tsx`)

## Keeping frontend and backend separate

This folder is **self-contained** — no imports from `plugins/`, `core/`, or `benchmarks/`. Backend is Python (FastAPI, in a later `backend/` folder once `core/` syncs land); frontend is TypeScript. They communicate over HTTP (REST + SSE) only.

For the prototype phase, `src/app/data/mockData.ts` stands in for the backend. When we wire real data, the call happens through a thin client module (`src/app/lib/api.ts`, TBD) — nothing else in the tree touches the backend.
