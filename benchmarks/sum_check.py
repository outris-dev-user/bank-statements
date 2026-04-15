"""Sum-check: verify extracted transactions match each statement's
declared totals (Total Debits / Total Credits / count). At >100 txns/file,
this beats per-row hand labeling — if the sums match, every transaction
was extracted.

Run after `run.py` so result JSON files exist.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

# Declared totals from each statement (read manually from the PDFs themselves)
# Format: filename → dict with whichever totals the bank prints.
DECLARED = {
    # HDFC Credit Card (per statement summary box)
    "Feb 2021.PDF":   {"debits": 1659.80,   "credits": 23902.00,   "count": 5,  "txn_total": 25561.80},
    "March 2021.PDF": {"debits": 1792.52,   "credits": 1660.00,    "count": 5,  "txn_total": 3452.52},
    "April 2021.PDF": {"debits": 13101.00,  "credits": 1792.00,    "count": 3,  "txn_total": 14893.00},
    "May 2021.PDF":   {"debits": 19449.93,  "credits": 13761.00,   "count": 7,  "txn_total": 33210.93},
    # June: HDFC summary excludes Finance Charges from "Purchase Debits" but our extractor counts it as Dr.
    "June 2021.PDF":  {"debits": 121448.00, "credits": 21730.00,   "count": 8,  "txn_total": 143178.00},

    # IDFC current account
    "IDFC Apr 2026.PDF": {"debits": 25000.00, "credits": 0.00, "count": 1, "txn_total": 25000.00},

    # HDFC Savings (statement summary block on last page)
    "Acct Statement_XX3584_29042024.pdf": {
        "debits": 2302984.36, "credits": 2282075.51, "count": 554,
        "dr_count": 369, "cr_count": 185,
        "opening": 69422.10, "closing": 48513.25,
    },

    # ICICI (page totals, cumulative across pages)
    "ICICI_Bank_Statement_New.pdf": {
        "debits": 115000.00, "credits": 125640.00, "count": 37,  # 38 rows minus B/F
        "opening": 16674.45, "closing": 27314.45,
    },

    # Kotak (only opening/closing printed, count from serial numbers)
    "Statement April-Aug 2021.pdf": {
        "count": 240,
        "opening": 89610.50, "closing": 3328.63,
        "net_change": 3328.63 - 89610.50,  # = -86,281.87 (debits exceed credits)
    },
}


def load_extracted(tool: str, pdf_stem: str) -> list:
    p = HERE / "results" / tool / f"{pdf_stem}.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("txns", [])


def check_file(tool: str, pdf: str) -> dict:
    declared = DECLARED.get(pdf)
    if not declared:
        return {"status": "no-truth"}
    txns = load_extracted(tool, Path(pdf).stem)
    debits = sum(t["amount"] for t in txns if t["type"] == "Dr")
    credits = sum(t["amount"] for t in txns if t["type"] == "Cr")
    count = len(txns)
    res = {
        "ext_count": count, "decl_count": declared.get("count"),
        "ext_dr": round(debits, 2), "decl_dr": declared.get("debits"),
        "ext_cr": round(credits, 2), "decl_cr": declared.get("credits"),
    }
    # Net-change check (works even when bank doesn't publish dr/cr totals)
    if "net_change" in declared:
        ext_net = round(credits - debits, 2)
        res["ext_net"] = ext_net
        res["decl_net"] = round(declared["net_change"], 2)
        res["net_match"] = abs(ext_net - declared["net_change"]) < 0.01
    if "debits" in declared and "credits" in declared:
        res["dr_match"] = abs(debits - declared["debits"]) < 0.01
        res["cr_match"] = abs(credits - declared["credits"]) < 0.01
    res["count_match"] = count == declared.get("count")
    return res


def main(tool: str = "pdfplumber_text"):
    print(f"=== Sum-check: {tool} ===\n")
    for pdf in DECLARED:
        r = check_file(tool, pdf)
        print(f"  {pdf}")
        if r.get("status") == "no-truth":
            print(f"    no declared totals")
            continue
        print(f"    count: {r['ext_count']:>6} / {r['decl_count']:>6}  "
              f"{'OK' if r['count_match'] else 'FAIL'}")
        if r.get("decl_dr") is not None:
            dr_pct = (r['ext_dr']/r['decl_dr']*100) if r['decl_dr'] else 0
            cr_pct = (r['ext_cr']/r['decl_cr']*100) if r['decl_cr'] else 100
            print(f"    debits: {r['ext_dr']:>14,.2f} / {r['decl_dr']:>14,.2f}  "
                  f"({dr_pct:6.1f}%)  {'OK' if r.get('dr_match') else 'FAIL'}")
            print(f"    credits:{r['ext_cr']:>14,.2f} / {r['decl_cr']:>14,.2f}  "
                  f"({cr_pct:6.1f}%)  {'OK' if r.get('cr_match') else 'FAIL'}")
        if "ext_net" in r:
            print(f"    net:    {r['ext_net']:>14,.2f} / {r['decl_net']:>14,.2f}  "
                  f"{'OK' if r['net_match'] else 'FAIL'}")
        print()


if __name__ == "__main__":
    tool = sys.argv[1] if len(sys.argv) > 1 else "pdfplumber_text"
    main(tool)
