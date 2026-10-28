"""Agreement between the second annotator and the benchmark labels.

    python research\\annotation\\score.py                      # reads out/sheet.csv
    python research\\annotation\\score.py --sheet path\\to.csv

Prints raw agreement, Cohen's kappa (three classes) and every disagreement, and
writes annotation/out/agreement.json for the paper.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import load_benchmark  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
LABELS = ("NONE", "VIOLATES", "GAP")


def cohen_kappa(a: list[str], b: list[str]) -> float:
    n = len(a)
    p_o = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    p_e = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return 1.0 if p_e == 1 else (p_o - p_e) / (1 - p_e)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", default=str(OUT / "sheet.csv"))
    ap.add_argument("--out", default="agreement.json", help="file name under annotation/out/")
    args = ap.parse_args()

    key = json.loads((OUT / "key.json").read_text(encoding="utf-8"))
    gold = {}
    for c in load_benchmark()["contracts"]:
        g = c["gold"]
        gold[c["contract_id"]] = ast.literal_eval(g) if isinstance(g, str) else g

    ours, theirs, rows = [], [], []
    with open(args.sheet, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            lab = row["your_label"].strip().upper()
            if not lab:
                continue
            if lab not in LABELS:
                sys.exit(f"{row['item']}: label must be one of {LABELS}, got {lab!r}")
            k = key[row["item"]]
            g = gold[k["contract_id"]][k["requirement_id"]]
            ours.append(g)
            theirs.append(lab)
            if g != lab:
                rows.append((row["item"], k["contract_id"], k["requirement_id"], g, lab, row.get("notes", "")))

    if not ours:
        sys.exit("No labels filled in yet.")
    n = len(ours)
    res = {
        "items": n,
        "raw_agreement": sum(x == y for x, y in zip(ours, theirs)) / n,
        "cohen_kappa": cohen_kappa(ours, theirs),
        "confusion": {g: dict(Counter(t for o, t in zip(ours, theirs) if o == g)) for g in LABELS},
        "disagreements": [dict(zip(("item", "contract", "requirement", "benchmark", "annotator", "notes"), r)) for r in rows],
    }
    (OUT / args.out).write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"{n} items  raw agreement {100 * res['raw_agreement']:.1f}%  Cohen's kappa {res['cohen_kappa']:.2f}")
    for r in rows:
        print("  ", *r[:5])


if __name__ == "__main__":
    main()
