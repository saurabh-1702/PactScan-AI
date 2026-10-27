"""Blind second-annotator sheet.

Draws a stratified sample of graded (contract, requirement) pairs and writes:

  annotation/out/sheet.csv          one row per pair; the annotator fills `your_label`
  annotation/out/contracts/K###.md  anonymised contracts (no variant, no file name,
                                    no clause types) so nothing gives the answer away
  annotation/out/key.json           item -> (contract_id, requirement_id), for scoring

The correct answers are NOT written anywhere in out/; score.py reads them from
the benchmark.

    python research\\annotation\\make_sheet.py
"""

from __future__ import annotations

import ast
import csv
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import load_benchmark  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
SEED = 11
PER_LABEL = {"NONE": 60, "VIOLATES": 36, "GAP": 24}


def _field(c: dict, key: str):
    v = c[key]
    return ast.literal_eval(v) if isinstance(v, str) else v


def render(c: dict, code: str) -> str:
    parties = _field(c, "parties")
    lines = [
        f"# Contract {code}",
        "",
        f'**Data Processing Agreement** between {parties["company"]} (the "Company", Data Fiduciary) '
        f'and {parties["vendor"]} (the "Vendor", Data Processor).',
        "",
    ]
    for cl in sorted(_field(c, "clauses"), key=lambda x: x["number"]):
        lines += [f"**{cl['section_header']}**", "", cl["raw_text"], ""]
    return "\n".join(lines)


def main() -> None:
    bm = load_benchmark()
    reqs = {r["id"]: r for r in bm["requirements"]}
    pool: dict[str, list] = {k: [] for k in PER_LABEL}
    for c in bm["contracts"]:
        for rid, lab in _field(c, "gold").items():
            if lab in pool:
                pool[lab].append((c["contract_id"], rid))
    rng = random.Random(SEED)
    picked = [p for lab, n in PER_LABEL.items() for p in rng.sample(pool[lab], n)]
    rng.shuffle(picked)

    by_id = {c["contract_id"]: c for c in bm["contracts"]}
    codes: dict[str, str] = {}
    order = list(dict.fromkeys(cid for cid, _ in picked))
    rng.shuffle(order)
    (OUT / "contracts").mkdir(parents=True, exist_ok=True)
    for i, cid in enumerate(order, 1):
        codes[cid] = f"K{i:03d}"
        (OUT / "contracts" / f"{codes[cid]}.md").write_text(render(by_id[cid], codes[cid]), encoding="utf-8")

    key = {}
    with open(OUT / "sheet.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["item", "contract", "requirement", "mandatory", "your_label", "notes"])
        for n, (cid, rid) in enumerate(picked, 1):
            item = f"Q{n:03d}"
            key[item] = {"contract_id": cid, "requirement_id": rid}
            r = reqs[rid]
            w.writerow([item, f"contracts/{codes[cid]}.md", r["text"], r["mandatory"], "", ""])
    (OUT / "key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    print(f"{len(picked)} items over {len(order)} contracts -> {OUT}")


if __name__ == "__main__":
    main()
