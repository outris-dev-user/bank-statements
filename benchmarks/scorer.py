"""Score extracted transactions against ground truth."""
import csv
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

GROUND_TRUTH = Path(__file__).parent / "ground_truth" / "transactions.csv"


def load_ground_truth() -> Dict[str, List[Dict]]:
    by_file = defaultdict(list)
    with open(GROUND_TRUTH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            row["amount"] = float(row["amount"])
            by_file[row["file"]].append(row)
    return dict(by_file)


def _key(t: Dict) -> Tuple[str, float, str]:
    """Match key: date + amount + type. Description is fuzzy."""
    return (t["date"], round(t["amount"], 2), t["type"])


def score(extracted: List[Dict], truth: List[Dict]) -> Dict:
    """Match by (date, amount, type). Allow many-to-many on duplicates."""
    truth_keys = [_key(t) for t in truth]
    extracted_keys = [_key(t) for t in extracted]

    truth_pool = list(truth_keys)
    hits = 0
    for k in extracted_keys:
        if k in truth_pool:
            truth_pool.remove(k)
            hits += 1

    expected = len(truth_keys)
    found = len(extracted_keys)
    recall = hits / expected if expected else 0.0
    precision = hits / found if found else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    return {
        "expected": expected,
        "found": found,
        "hits": hits,
        "missed": expected - hits,
        "spurious": found - hits,
        "recall": round(recall, 3),
        "precision": round(precision, 3),
        "f1": round(f1, 3),
    }
