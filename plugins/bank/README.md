# plugins/bank/

Bank-statement-specific code. **This is the actual IP of this repo.**

## Layout

```
plugins/bank/
├── extraction/         # PDF → text → unified Transaction records
│   ├── parser.py       # bank-aware parser router (5 banks today)
│   └── extractors.py   # 12 PDF extractor wrappers benchmarked
├── parsers/            # one per bank (will eventually move out of parser.py)
├── patterns/           # BFSI forensic patterns: smurfing, mule, hawala, …
├── enrichment/         # PEP, FIU-IND STR, sanctions, CIBIL lookups
└── terminus_detector.py  # cash, wire, ATM categorisation
```

## What's done (2026-04-15)

- **Extraction** — 5 banks supported (HDFC CC, IDFC, HDFC Savings, ICICI, Kotak), 858 transactions extracted at 99-100% accuracy (sum-checked vs declared totals). See [../../benchmarks/SUMMARY.md](../../benchmarks/SUMMARY.md).

## What's pending

- **Patterns** — 6-8 BFSI patterns to be implemented on top of `core/analysis/pattern_framework.py` once that's synced from crypto. Targets: smurfing, mule rings, hawala aggregation, round-tripping, dormant activation, layering, benami detection.
- **Terminus detector** — modelled on crypto's `exchange_detector.py`. Replaces "is this an exchange?" with "is this a cash terminus / international wire / merchant settlement?"
- **Enrichment** — PEP/sanctions/FIU-IND lookups via configurable provider (online API or bundled offline dataset).
- **Per-bank parser split** — the current monolithic `parser.py` will become one file per bank under `parsers/` once a 6th bank lands.

## How to add a new bank

1. Drop a sample PDF into `data/pdf/`.
2. Add a fingerprint string to `detect_bank()` in `parser.py`.
3. Write a `_parse_<bank>()` function returning `{date, description, amount, type}` records.
4. Register it in the `PARSERS` dict.
5. Add declared totals for the new file to `benchmarks/sum_check.py` `DECLARED` dict.
6. `python benchmarks/run.py pdfplumber_text && python benchmarks/sum_check.py pdfplumber_text` — should show 100% on the new bank.
