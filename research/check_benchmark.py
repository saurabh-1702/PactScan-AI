"""Script 2 — check the benchmark before any experiment uses it.

Automatic checks (the script fails loudly if any break):
  * every contract differs from its base contract in exactly the one place its
    variant says (one clause removed / rewritten, or one amendment added)
  * no unfilled {placeholder} is left in any clause text
  * clause ids are unique; every OVERRIDES link points at real clauses
  * every requirement belongs to a topic, and every gold label is NONE / VIOLATES / GAP

It then prints the label balance and writes ``benchmark/out/review_sheet.csv``:
one row per clause text that decides a correct answer, with the answer and the
reasoning, and two empty columns ("agree?" / "notes") for the human check.
Wrong correct answers would make every number in the paper wrong — read it.

    backend\\venv\\Scripts\\python.exe research\\check_benchmark.py
"""

from __future__ import annotations

import csv
import sys
from collections import Counter

from common import BENCHMARK_FILE, load_benchmark

LABELS = {"NONE", "VIOLATES", "GAP", "EXCLUDE"}


def _check(bm: dict) -> list[str]:
    errors: list[str] = []
    reqs = {r["id"]: r for r in bm["requirements"]}
    bases = {c["base"]: c for c in bm["contracts"] if c["variant"]["kind"] == "FOLLOWS"}
    seen_ids: set[str] = set()

    for c in bm["contracts"]:
        ids = [cl["clause_id"] for cl in c["clauses"]]
        for cid in ids:
            if cid in seen_ids:
                errors.append(f"duplicate clause id {cid}")
            seen_ids.add(cid)
        for cl in c["clauses"]:
            if "{" in cl["raw_text"] or "}" in cl["raw_text"]:
                errors.append(f"{cl['clause_id']}: unfilled placeholder")
        for o in c["overrides"]:
            if o["src"] not in ids or o["dst"] not in ids:
                errors.append(f"{c['contract_id']}: override points at a missing clause")
        for rid, label in c["gold"].items():
            if rid not in reqs:
                errors.append(f"{c['contract_id']}: unknown requirement {rid}")
            if label not in LABELS:
                errors.append(f"{c['contract_id']}: bad label {label}")

        base = bases.get(c["base"])
        if base is None:
            errors.append(f"{c['contract_id']}: no base contract")
            continue
        kind, topic = c["variant"]["kind"], c["variant"]["topic"]
        b_text = {cl["topic"] or cl["section_header"].split(". ", 1)[1]: cl["raw_text"] for cl in base["clauses"]}
        c_text = {cl["topic"] or cl["section_header"].split(". ", 1)[1]: cl["raw_text"] for cl in c["clauses"]}
        removed = set(b_text) - set(c_text)
        added = set(c_text) - set(b_text)
        changed = {k for k in set(b_text) & set(c_text) if b_text[k] != c_text[k]}
        expect = {
            "FOLLOWS": (set(), set(), set()),
            "SILENT": ({topic}, set(), set()),
            "BREAKS": (set(), set(), {topic}),
            "TRAP_HIDDEN_VIOLATION": (set(), {"Schedule 2 — Amendment No. 1"}, set()),
            "TRAP_HIDDEN_FIX": (set(), {"Schedule 2 — Amendment No. 1"}, {topic}),
        }[kind]
        if (removed, added, changed) != expect:
            errors.append(
                f"{c['contract_id']}: expected removed/added/changed {expect}, got {(removed, added, changed)}"
            )

        # the gold labels must differ from the base only on the varied topic
        for rid, label in c["gold"].items():
            if reqs[rid]["topic"] != topic and label not in ("NONE", "EXCLUDE"):
                errors.append(f"{c['contract_id']}: {rid} should be NONE (topic not varied)")
    return errors


def _review_rows(bm: dict) -> list[dict]:
    reqs = bm["requirements"]
    topics = bm["topics"]
    rows, seen = [], set()
    for c in bm["contracts"]:
        kind, topic = c["variant"]["kind"], c["variant"]["topic"]
        if kind == "FOLLOWS":
            # every topic clause of the base contract decides "NONE" for its rules
            for cl in c["clauses"]:
                if cl["topic"]:
                    key = ("FOLLOWS", cl["raw_text"])
                    if key in seen:
                        continue
                    seen.add(key)
                    affected = [r for r in reqs if r["topic"] == cl["topic"]]
                    rows.append(_row(c, "FOLLOWS (base)", cl["topic"], cl["raw_text"], "", affected, "NONE",
                                     "The clause satisfies these rules."))
            continue
        affected = [r for r in reqs if r["topic"] == topic]
        labels = sorted({c["gold"][r["id"]] for r in affected})
        excluded = [r["label"] for r in reqs if c["gold"][r["id"]] == "EXCLUDE"]
        if kind == "SILENT":
            text = "(clause removed — nothing else in the contract covers this topic)"
            why = topics[topic]["rationale"]
        elif kind == "BREAKS":
            text = next(cl["raw_text"] for cl in c["clauses"] if cl["topic"] == topic)
            why = "The rewritten clause goes against these rules."
        else:
            text = next(cl["raw_text"] for cl in c["clauses"] if cl["topic"] == topic)
            why = ("The amendment overrides the clause and breaks the rules."
                   if kind == "TRAP_HIDDEN_VIOLATION" else
                   "The clause alone breaks the rules, but the amendment overrides it and cures that.")
        amendment = next((cl["raw_text"] for cl in c["clauses"] if cl.get("role") == "amendment"), "")
        key = (kind, topic, text, amendment)
        if key in seen:
            continue
        seen.add(key)
        rows.append(_row(c, kind, topic, text, amendment, affected, "/".join(labels), why, excluded))
    return rows


def _row(c, kind, topic, text, amendment, affected, label, why, excluded=()) -> dict:
    return {
        "example_contract": c["contract_id"], "variant": kind, "topic": topic, "clause_text": text,
        "amendment_text": amendment, "requirements": "; ".join(r["label"] for r in affected),
        "correct_answer": label, "why": why,
        "excluded_from_scoring": "; ".join(excluded), "agree? (Y/N)": "", "notes": "",
    }


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", default="review_sheet.csv", help="file name for the review sheet")
    args = ap.parse_args()
    bm = load_benchmark()
    errors = _check(bm)

    by_label = Counter(l for c in bm["contracts"] for l in c["gold"].values())
    by_kind = Counter(c["variant"]["kind"] for c in bm["contracts"])
    by_update = Counter((u, l) for c in bm["contracts"] for u, l in c["update_gold"].items())
    print(f"{len(bm['contracts'])} contracts, {sum(by_label.values())} graded pairs")
    print("  contracts by variant:", dict(by_kind))
    print("  correct answers     :", dict(by_label))
    print("  regulation updates  :", {k: v for k, v in sorted(by_update.items())})

    rows = _review_rows(bm)
    sheet = BENCHMARK_FILE.parent / args.sheet
    with sheet.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"  review sheet        : {len(rows)} rows -> {sheet}")

    if errors:
        print(f"\n{len(errors)} PROBLEM(S):")
        for e in errors[:50]:
            print("  -", e)
        sys.exit(1)
    print("\nAll automatic checks passed.")


if __name__ == "__main__":
    main()
