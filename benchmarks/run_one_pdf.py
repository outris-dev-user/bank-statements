"""Run a subset of tools on a single PDF (fills gaps in benchmark)."""
import sys
import json
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from plugins.bank.extraction.extractors import EXTRACTORS
from plugins.bank.extraction.parser import parse_text
from scorer import load_ground_truth, score


def main(pdf_name, *tool_names):
    pdf = HERE.parent / "data" / "pdf" / pdf_name
    if not pdf.exists():
        sys.exit(f"PDF not found: {pdf}")

    truth = load_ground_truth().get(pdf.name, [])
    for tool_name in tool_names:
        fn = EXTRACTORS[tool_name]
        out_dir = HERE / "results" / tool_name
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"[{tool_name}] {pdf.name} ...", flush=True)
        t0 = time.perf_counter()
        try:
            text = fn(pdf)
            elapsed = time.perf_counter() - t0
            txns = parse_text(text)
            s = score(txns, truth)
            print(f"  -> hits={s['hits']}/{s['expected']} spur={s['spurious']} time={elapsed:.1f}s")
            (out_dir / f"{pdf.stem}.txt").write_text(text, encoding="utf-8")
            (out_dir / f"{pdf.stem}.json").write_text(
                json.dumps({"score": s, "elapsed_s": round(elapsed, 3), "txns": txns}, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"  -> ERROR: {type(e).__name__}: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("Usage: python run_one_pdf.py <pdf_filename> <tool> [<tool> ...]")
    main(sys.argv[1], *sys.argv[2:])
