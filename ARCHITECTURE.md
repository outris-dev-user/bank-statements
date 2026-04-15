# Architecture

## Constraints driving every design decision

1. **Two deployment modes, same code:**
   - **SaaS online** — multi-tenant web app, Postgres + Neo4j Aura + Anthropic API, integrates with the crypto investigation platform via a "Workbench-Bank" tab.
   - **LEA offline workstation** — single user, fully air-gapped, SQLite + NetworkX + Ollama, no external API calls of any kind.
2. **Mixable with crypto:** an investigator working a financial crime case may have crypto wallets *and* bank accounts. Both should appear as workbenches inside the same case in the SaaS product.
3. **Hackathon-clean:** the IndiaAI submission needs a self-contained repo without crypto IP leaking through.

These constraints rule out: monorepo with crypto, hard dependencies on cloud services, copying the existing annual-report stack as-is.

## Three-layer architecture

```
┌──────────────────────────────────────────────────────────┐
│  core/   (synced from crypto, periodically)               │
│   • Domain-agnostic models: Case, Investigation, Entity,  │
│     Person, Transaction, Signal, Alert, EvidencePin       │
│   • Analysis framework: signal_assembler, velocity,       │
│     pattern_detector skeleton, multi_hop_exposure         │
│   • Graph: Neo4j wrapper (online) + NetworkX (offline)    │
│   • UI: Cytoscape canvas, Zustand stores, NodeInspector,  │
│     Activity table, Investigation report                  │
│   • Provider abstractions: LLM (litellm), vector store,   │
│     OCR (pdfplumber/Tesseract/Azure)                      │
└──────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────┐
│  plugins/bank/   (this repo's actual IP)                  │
│   • extraction/  pdfplumber + bank parser router          │
│   • parsers/     HDFC_CC, IDFC, HDFC_Sav, ICICI, Kotak    │
│   • patterns/    smurfing, mule, hawala, round-tripping,  │
│                  dormant activation, layering             │
│   • enrichment/  PEP, FIU-IND STR, sanctions, CIBIL       │
│   • terminus_detector.py  (cash, wire, ATM)               │
└──────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────┐
│  deployment/                                              │
│   • saas/         Postgres, Neo4j Aura, Anthropic, multi- │
│                   tenant. Hosts both crypto + bank tabs.  │
│   • lea-offline/  SQLite, NetworkX, Ollama, no network.   │
│                   Only bank plugin loaded.                │
└──────────────────────────────────────────────────────────┘
```

## Why not just one repo with crypto

| Concern | Monorepo | Separate (this repo) |
|---|---|---|
| Week-1 ready to code | ✓ | ✓ |
| LEA offline build clean | ✗ (need build-time exclusion of crypto code) | ✓ |
| Hackathon submission clean | ✗ | ✓ |
| Atomic cross-project refactor | ✓ | ✗ (need sync) |
| Repo permissions clean | ✗ | ✓ |
| Deployment independence | ✗ | ✓ |
| Reversible later | ⚠ (untangling work) | ✓ (always can extract platform package) |

We optimise for **clean separation now, optionality later**. If sync friction becomes painful in 3-6 months, we extract a versioned `platform-core` package consumed by both repos. That decision is cheaper to make once we've seen real divergence patterns.

## Why not just inherit annual-report's stack

The annual-report code (`indiaaifinancehack/backend/`) has good patterns — LangGraph orchestration, YAML rule engine, OCR provider abstraction, litellm wrapper, Qdrant RAG, annotation system. But:

- It's tightly coupled to compliance-validation semantics (132 NFRA rules, 13 regulatory section types, XBRL parsing) that don't apply to bank statements.
- It's currently online-only (Postgres, Qdrant Cloud, Anthropic API).
- The reusable bits are ~1000 LOC of utility code — quicker to write fresh in a clean shape than to inherit the whole tree.

We **cherry-pick patterns** from annual-report (LangGraph DAG shape, YAML rule format, OCR provider interface) but don't depend on its repo. We borrow the *structure*, not the *code*.

## Why pdfplumber + per-bank parser

Validated empirically across 5 banks and 858 transactions — see [benchmarks/SUMMARY.md](benchmarks/SUMMARY.md). The headline:

- **One extractor (pdfplumber) handles every bank** — the PDF→text step is universal.
- **Five parsers** are needed because every bank lays out transactions differently (date format, single vs split amount columns, Dr/Cr signal, multi-line vs single-line).
- **Other extractors collapse on multi-bank** — Tesseract scored 0% on Kotak and HDFC Savings; Azure Document Intelligence handled HDFC CC and IDFC but missed Kotak's 3-line layout entirely.

Adding a new bank = one new function in `plugins/bank/parsers/` + one fingerprint string in the bank detector. Existing banks unaffected.

## Provider abstractions for offline parity

Every external dependency is hidden behind an abstraction in `core/`:

| Concern | Online provider | Offline provider |
|---|---|---|
| LLM | Anthropic Claude (via litellm) | Ollama (local llama3) |
| Vector store | Qdrant Cloud | FAISS on disk |
| Graph DB | Neo4j Aura | NetworkX (in-memory) |
| Persistence | Postgres | SQLite |
| OCR (cloud fallback) | Azure Document Intelligence | none — pdfplumber + Tesseract only |
| Persona/Sanctions enrichment | API lookups | static dataset bundled |

The bank plugin doesn't know which provider is wired — it just calls `core.llm.complete(...)`. A config flag at deployment time decides.

## UX orientation: table-first, graph-second

Bank-analyser's primary UX surface is the **transaction table**, not the graph canvas. This is a deliberate divergence from crypto's UX, which is graph-first with a side inspector.

Why: bank transactions are a chronological ledger. Investigators need to:
1. **Verify the OCR** (is each row correct? can we trust the data?) — table view, inline edit, confidence markers
2. **Scan for anomalies** (big debits, round numbers, unusual times) — table view with visual heuristics (green/red bands, badges)
3. **Pivot to relationships** (who is this person really transacting with?) — *then* the graph view

Crypto's problem is the opposite — addresses and flows are the primary object, tables are an auxiliary view. Same platform, different entry point.

See [docs/ux-phases.md](docs/ux-phases.md) for the phased UX plan.

**Implication for `core/ui/` sync:**
- `GraphCanvas`, `AutoInvestigateReport` — fork and maintain locally (crypto-specific visual language, not worth live-syncing)
- `NodeInspector` tab layout — we may not use the right-side inspector at all. Bank's "open a row" might be a row-expand inline, or a modal, or a dedicated drill-down page
- Shared: Zustand stores (selection, filter, investigation state), Case management components, CSV import

## Why a Workbench-Bank tab inside crypto works

In SaaS, both plugins load. The crypto team's existing case/investigation/graph layer is already domain-agnostic — same `Case` row can have a crypto investigation and a bank investigation as siblings, surfaced as two tabs in the workbench UI. Persons and entities link across via shared IDs in the `core/` layer.

For LEA offline, only the bank plugin loads. The Workbench-Bank tab is the *only* tab. Same code, different deployment config.

The **Workbench-Bank tab uses the table-first layout**, independent of how crypto's Workbench tab renders. Both coexist inside the same case view because they're tabs — each can optimise for its own domain.

## What changes from the original `bank-analyser/`

The old code at `IndiaAI/financehack/indiaaifinancehack/bank-analyser/` had a custom YOLO+EasyOCR extraction pipeline. Audit showed it added complexity without accuracy gains over plain pdfplumber. **We retire that path.** What carries forward:

- `benchmarks/` — the validation harness and ground truth (now CI for the bank plugin)
- `data/pdf/` — the test statements
- `extraction/parser.py` — the bank-aware parser router (now `plugins/bank/extraction/parser.py`)

Discarded: the old `backend/app/extraction/local_ai_provider.py` (YOLO+EasyOCR), the old monolithic FastAPI app, the docling/PaddleOCR/PaddleOCR-derived experiments. Reason: none of them worked across multi-bank as well as plain pdfplumber.
