"""Script 7 — the paper's tables, straight from score.py's output.

Writes Markdown (to read) and LaTeX (to paste into the paper) versions of:
  T1  the benchmark                   (contracts, pairs, correct answers)
  T2  Experiment 1 — the ablation     (each set-up, with 95% intervals)
  T3  Experiment 1 — where the false alarms come from
  T4  paired significance tests       (McNemar)
  T5  Experiment 2/3 — stability      (across models, across repeat runs)
  T6  Experiment 4 — regulation updates

    python research\\make_tables.py --results results --main-run main
"""

from __future__ import annotations

import argparse
import json
from collections import Counter

from common import RESULTS_DIR, load_benchmark
from configs import CONFIGS


def _pct(v, ci=None) -> str:
    if v is None:
        return "n/a"
    s = f"{100 * v:.1f}"
    if ci:
        s += f" [{100 * ci[0]:.1f}, {100 * ci[1]:.1f}]"
    return s


def _table(title: str, header: list[str], rows: list[list[str]]) -> tuple[str, str]:
    md = [f"### {title}", "", "| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    md += ["| " + " | ".join(r) + " |" for r in rows]
    tex = [
        "\\begin{table}[t]", "\\centering", f"\\caption{{{title}}}",
        "\\begin{tabular}{" + "l" + "r" * (len(header) - 1) + "}", "\\toprule",
        " & ".join(header) + " \\\\", "\\midrule",
    ]
    tex += [" & ".join(c.replace("%", "\\%").replace("_", "\\_") for c in r) + " \\\\" for r in rows]
    tex += ["\\bottomrule", "\\end{tabular}", "\\end{table}"]
    return "\n".join(md) + "\n", "\n".join(tex) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", default="results")
    ap.add_argument("--main-run", default="main")
    args = ap.parse_args()

    bm = load_benchmark()
    report = json.loads((RESULTS_DIR / f"{args.results}.json").read_text(encoding="utf-8"))
    tables: list[tuple[str, str]] = []

    labels = Counter(l for c in bm["contracts"] for l in c["gold"].values())
    kinds = Counter(c["variant"]["kind"] for c in bm["contracts"])
    tables.append(_table(
        "Benchmark", ["Item", "Count"],
        [["Base contracts", str(kinds["FOLLOWS"])], ["Contracts", str(len(bm["contracts"]))],
         ["Requirements per contract", str(len(bm["requirements"]))],
         ["Graded (contract, requirement) pairs", str(sum(labels.values()) - labels["EXCLUDE"])],
         ["... correct answer NONE", str(labels["NONE"])], ["... correct answer VIOLATES", str(labels["VIOLATES"])],
         ["... correct answer GAP", str(labels["GAP"])],
         ["... excluded as ambiguous", str(labels["EXCLUDE"])],
         ["Trap contracts (amendment hides a violation / a fix)", f"{kinds['TRAP_HIDDEN_VIOLATION']} / {kinds['TRAP_HIDDEN_FIX']}"]],
    ))

    run = report["runs"].get(args.main_run, {})
    if run:
        rows = []
        for cfg, m in run.items():
            ci = m.get("ci95", {})
            rows.append([f"{cfg}: {CONFIGS[cfg]['name']}", _pct(m["false_violation_rate"], ci.get("false_violation_rate")),
                         _pct(m["missed_gap_rate"], ci.get("missed_gap_rate")),
                         _pct(m["violation_recall"], ci.get("violation_recall")), _pct(m["f1"], ci.get("f1")),
                         f"{m['findings_per_clean_contract'] or 0:.1f}"])
        tables.append(_table(
            "Experiment 1: false violations and missed gaps per set-up (%, 95% CI)",
            ["Set-up", "False violation rate", "Missed gap rate", "Violation recall", "F1", "Findings on a clean contract"], rows,
        ))
        rows = [[cfg, _pct(m["fvr_covered"]), _pct(m["fvr_silent_ok"]), _pct(m["fvr_trap_fix"]), _pct(m["violation_recall_trap"])]
                for cfg, m in run.items()]
        tables.append(_table(
            "Experiment 1: where false alarms come from (%)",
            ["Set-up", "Clause present & compliant", "Topic absent, acceptable", "Amendment cures clause", "Hidden violation caught"], rows,
        ))
        tests = report["mcnemar"].get(args.main_run, {})
        if tests:
            rows = [[k.replace("_vs_", " vs "), str(t["x_only_correct"]), str(t["y_only_correct"]), f"{t['p_value']:.2g}"]
                    for k, t in tests.items()]
            tables.append(_table("Paired comparisons (exact McNemar test)",
                                 ["Comparison", "Only first right", "Only second right", "p-value"], rows))

    for label, block in report.get("agreement", {}).items():
        rows = [[cfg, _pct(a.get("all_agree_pct")), f"{a.get('fleiss_kappa', 0):.2f}"] for cfg, a in block["configs"].items()]
        tables.append(_table(f"Stability across {label} ({', '.join(block['runs'])})",
                             ["Set-up", "Pairs answered identically", "Fleiss' kappa"], rows))
        if label == "models":
            rows = []
            for rid in block["runs"]:
                for cfg in ("A", "D"):
                    m = report["runs"].get(rid, {}).get(cfg)
                    if m:
                        rows.append([rid, cfg, _pct(m["false_violation_rate"]), _pct(m["missed_gap_rate"]), _pct(m["f1"])])
            if rows:
                tables.append(_table("Experiment 2: before (A) vs after (D) on each model",
                                     ["Run", "Set-up", "False violation rate", "Missed gap rate", "F1"], rows))

    for rid, law in report.get("law", {}).items():
        rows = [[rule, _pct(m["false_violation_rate"]), _pct(m["missed_gap_rate"]), _pct(m["violation_recall"]),
                 _pct(m["f1"]), f"{m['findings_per_check'] or 0:.2f}"] for rule, m in law["rules"].items()]
        tables.append(_table(
            f"Experiment 4: re-checking contracts after a regulation update ({rid}; retrieval recall on violations {_pct(law['retrieval_recall_on_violations'])})",
            ["Rule", "False violation rate", "Missed gap rate", "Violation recall", "F1", "Findings per check"], rows,
        ))

    out_dir = RESULTS_DIR / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{args.results}.md").write_text("\n".join(t[0] for t in tables), encoding="utf-8", newline="\n")
    (out_dir / f"{args.results}.tex").write_text("\n".join(t[1] for t in tables), encoding="utf-8", newline="\n")
    print(f"Wrote {len(tables)} tables -> {out_dir}")


if __name__ == "__main__":
    main()
