"""Benchmark runner: runs every extractor on every PDF, scores against
ground truth, writes per-tool CSVs and a summary table."""
from __future__ import annotations
import csv
import json
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).parent
PDF_DIR = HERE.parent / "data" / "pdf"
RESULTS = HERE / "results"
RESULTS.mkdir(exist_ok=True)

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))  # repo root → plugins.bank is importable
from plugins.bank.extraction.extractors import EXTRACTORS
from plugins.bank.extraction.parser import parse_text
from scorer import load_ground_truth, score


def run_one(name, fn, pdf_path):
    t0 = time.perf_counter()
    try:
        text = fn(pdf_path)
        elapsed = time.perf_counter() - t0
        txns = parse_text(text)
        return {"ok": True, "elapsed": elapsed, "txns": txns, "text": text}
    except ImportError as e:
        return {"ok": False, "error": f"unavailable: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()}


def _is_encrypted(pdf_path):
    """Skip password-protected PDFs (decrypted copies should be added separately)."""
    try:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(str(pdf_path))
        pdf.close()
        return False
    except pdfium.PdfiumError:
        return True


def main(only=None):
    truth_by_file = load_ground_truth()
    pdfs = sorted(p for p in PDF_DIR.glob("*.[Pp][Dd][Ff]") if not _is_encrypted(p))
    tools = list(EXTRACTORS.items())
    if only:
        tools = [(n, f) for n, f in tools if n in only]

    summary_rows = []
    for tool_name, fn in tools:
        per_file = []
        total_expected = total_found = total_hits = 0
        total_time = 0.0
        any_ok = False
        first_error = None
        for pdf in pdfs:
            print(f"[{tool_name}] {pdf.name} ...", flush=True)
            r = run_one(tool_name, fn, pdf)
            if not r["ok"]:
                first_error = first_error or r["error"]
                per_file.append({"file": pdf.name, "ok": False, "error": r["error"]})
                continue
            any_ok = True
            truth = truth_by_file.get(pdf.name, [])
            s = score(r["txns"], truth)
            total_expected += s["expected"]
            total_found += s["found"]
            total_hits += s["hits"]
            total_time += r["elapsed"]
            per_file.append({"file": pdf.name, "ok": True, "elapsed": round(r["elapsed"], 2), **s})
            # Save per-tool per-file txns + raw text
            out_dir = RESULTS / tool_name
            out_dir.mkdir(exist_ok=True)
            with open(out_dir / f"{pdf.stem}.json", "w", encoding="utf-8") as f:
                json.dump({"score": s, "elapsed_s": round(r["elapsed"], 3), "txns": r["txns"]}, f, indent=2)
            with open(out_dir / f"{pdf.stem}.txt", "w", encoding="utf-8") as f:
                f.write(r["text"])

        if any_ok and total_expected:
            recall = round(total_hits / total_expected, 3)
            precision = round(total_hits / total_found, 3) if total_found else 0.0
            f1 = round(2 * precision * recall / (precision + recall), 3) if (precision + recall) else 0.0
            summary_rows.append({
                "tool": tool_name,
                "expected": total_expected,
                "found": total_found,
                "hits": total_hits,
                "missed": total_expected - total_hits,
                "spurious": total_found - total_hits,
                "recall": recall,
                "precision": precision,
                "f1": f1,
                "time_s": round(total_time, 2),
                "status": "ok",
            })
        else:
            summary_rows.append({
                "tool": tool_name,
                "expected": 0, "found": 0, "hits": 0, "missed": 0, "spurious": 0,
                "recall": 0, "precision": 0, "f1": 0, "time_s": 0,
                "status": first_error or "no data",
            })

        with open(RESULTS / f"{tool_name}_per_file.json", "w", encoding="utf-8") as f:
            json.dump(per_file, f, indent=2)

    summary_rows.sort(key=lambda r: (-r["f1"], r["time_s"]))
    with open(RESULTS / "summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        w.writeheader()
        w.writerows(summary_rows)

    # Pretty print
    print("\n=== SUMMARY (sorted by F1, then time) ===")
    print(f"{'tool':22} {'F1':>6} {'P':>6} {'R':>6} {'hits':>5} {'miss':>5} {'spur':>5} {'time(s)':>8}  status")
    print("-" * 90)
    for r in summary_rows:
        print(f"{r['tool']:22} {r['f1']:>6} {r['precision']:>6} {r['recall']:>6} "
              f"{r['hits']:>5} {r['missed']:>5} {r['spurious']:>5} {r['time_s']:>8}  {r['status']}")


if __name__ == "__main__":
    only = sys.argv[1:] or None
    main(only)
