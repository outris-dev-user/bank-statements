# bank-analyser

Forensic analysis of Indian bank statements for law-enforcement (LEA) and SaaS investigation use cases.

## What it does

1. **Ingest** PDF bank statements from any major Indian bank (HDFC CC, HDFC Savings, IDFC, ICICI, Kotak today; SBI, Axis, Yes, others to follow).
2. **Extract** transactions to a unified schema `{date, description, amount, type}` regardless of source layout.
3. **Analyse** for forensic patterns — circular trading, structuring/smurfing, mule networks, dormant activation, hawala aggregation, round-tripping.
4. **Investigate** in a Cytoscape-based graph UI (case management, multi-statement aggregation, person/entity linking).

## Why a separate repo

This started inside `IndiaAI/financehack/indiaaifinancehack/bank-analyser/` and has been carved out because:
- It needs to ship as a **fully offline LEA workstation** with no external dependencies — can't carry annual-report's cloud/SaaS-only assumptions.
- The investigation/UX layer is being borrowed from the [crypto investigation platform](D:/OneDrive%20-%20Outris/Outris/Product/git-repo/crypto/crypto/india-le-platform) and we want clean code provenance.
- Hackathon submission needs to be clean.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full reasoning.

## Repo layout

```
bank-analyser/
├── core/                     # SHARED platform code (synced from crypto, see CRYPTO_SYNC.md)
│   ├── models/               # Case, Investigation, Entity, Person, Transaction, Signal
│   ├── analysis/             # signal_assembler, velocity_analyzer, pattern framework
│   ├── graph/                # Neo4j wrapper + NetworkX offline fallback
│   └── ui/                   # Cytoscape canvas, Zustand stores, NodeInspector
├── plugins/bank/             # NEW domain-specific code (this repo's main IP)
│   ├── extraction/           # pdfplumber + bank-aware parser router (DONE)
│   ├── parsers/              # one parser per bank (HDFC_CC, IDFC, ICICI, Kotak, …)
│   ├── patterns/             # BFSI forensic patterns (smurfing, mule, hawala, …)
│   └── enrichment/           # PEP/sanctions/FIU-IND lookups
├── benchmarks/               # CI for the plugin: extract → sum-check vs declared totals
│   ├── ground_truth/         # transactions.csv (hand-labeled HDFC CC + IDFC)
│   └── results/              # per-tool, per-pdf JSON outputs
├── data/pdf/                 # test statements (5 banks, 9 PDFs, 858 transactions)
├── deployment/
│   ├── saas/                 # online: Postgres, Neo4j Aura, Anthropic API
│   └── lea-offline/          # offline: SQLite, NetworkX, Ollama, no external calls
├── docs/
│   └── for-crypto-team.md    # how the crypto team should structure modules for sharing
└── tools/
    └── sync-from-crypto.sh   # pulls latest core/ from crypto repo
```

## Status (2026-04-15)

**Built and validated:**
- pdfplumber + bank-aware parser router across 5 banks (HDFC CC, IDFC, HDFC Savings, ICICI, Kotak)
- 858 transactions extracted across 9 PDFs at **99-100% sum-check accuracy** vs declared statement totals
- Benchmark harness comparing 12 extractors (pdfplumber, tabula, EasyOCR, Tesseract, rapidocr, Azure Document Intelligence, etc.); pdfplumber + bank parser wins on all 5 banks
- See [benchmarks/SUMMARY.md](benchmarks/SUMMARY.md) for full numbers

**Pending:**
- Sync `core/` from crypto (Cytoscape UI, Case/Investigation models, signal framework, velocity, pattern detector framework) — see [CRYPTO_SYNC.md](CRYPTO_SYNC.md)
- Build BFSI-specific patterns on top of synced framework
- SaaS deployment + LEA offline bundle

## How to run benchmarks

```bash
cd benchmarks
python run.py pdfplumber_text                    # all 9 PDFs, ~10s
python sum_check.py pdfplumber_text              # validate vs declared totals
python run.py                                    # all 12 tools (slow, EasyOCR ~5min)
```

Per-tool JSON output: `benchmarks/results/<tool>/<pdf>.json`.
Consolidated multi-bank CSV: `benchmarks/results/all_banks_extracted.csv`.

## Key docs

- [ARCHITECTURE.md](ARCHITECTURE.md) — three-layer architecture (core / plugins / deployment) and why
- [CRYPTO_SYNC.md](CRYPTO_SYNC.md) — what we plan to copy from crypto, with provenance
- [docs/for-crypto-team.md](docs/for-crypto-team.md) — proposed contract: what should be platform vs domain, how syncing works
- [benchmarks/SUMMARY.md](benchmarks/SUMMARY.md) — extractor benchmark + multi-bank sum-check results

## Contact

Saurabh Sethi — saurabh@outris.com
