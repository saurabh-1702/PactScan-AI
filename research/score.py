"""Script 6 — turn saved verdicts into the paper's numbers.

The unit of measurement is a (contract, requirement) pair with a correct
answer of NONE, VIOLATES or GAP (pairs marked EXCLUDE in the label review are
left out of every number). A set-up "flags" a pair if it produced at
least one finding for that requirement in that contract.

Numbers reported per set-up:
  false_violation_rate   share of NONE pairs that were flagged (the error this paper is about),
                          also split by WHY nothing was wrong:
                            covered    the requirement's clause is present and compliant
                            silent_ok  the topic is absent and that is acceptable (non-mandatory)
                            trap_fix   the clause alone breaks the rule but an amendment cures it
  missed_gap_rate        share of GAP pairs NOT flagged (the opposite failure)
  violation_recall       share of VIOLATES pairs flagged (also for trap contracts alone)
  precision / recall / f1  over all problems (VIOLATES + GAP)
  findings_per_contract  how many findings a contract gets on average, and on the clean base contracts

95% confidence intervals: cluster bootstrap over contracts (pairs from one
contract are not independent). Paired comparisons between set-ups: exact
McNemar test on per-pair correctness. Stability: % of pairs answered the
same way across runs, and Fleiss' kappa.

    python research\\score.py --runs main
    python research\\score.py --runs main --compare-runs main,m_gpt20b,m_qwen --repeat-runs rep1,rep2,rep3,rep4,rep5 --law-runs law_main
"""

from __future__ import annotations

import argparse
import math
import random
from collections import defaultdict

from common import RESULTS_DIR, RUNS_DIR, load_benchmark, read_jsonl, write_json

BOOTSTRAP_SAMPLES = 2000
SEED = 7


# --------------------------------------------------------------------------- #
# Predictions
# --------------------------------------------------------------------------- #
def load_run(run_id: str) -> dict:
    rows = read_jsonl(RUNS_DIR / run_id / "verdicts.jsonl")
    if not rows:
        raise SystemExit(f"No verdicts found for run {run_id!r} (research/runs/{run_id}/verdicts.jsonl).")
    # A job interrupted part-way (e.g. the machine shut down) is redone in full
    # on resume, so some (clause, requirement) verdicts can be saved twice. Keep
    # one per clause — the latest — so nothing is counted twice.
    latest: dict[tuple[str, str, str, str], dict] = {}
    done: dict[str, set[str]] = defaultdict(set)
    deployed: dict[str, list[dict]] = {}
    for r in rows:
        if r["type"] == "verdict":
            latest[(r["family"], r["contract_id"], r["clause_id"], r["requirement_id"])] = r
        elif r["type"] == "done":
            done[r["family"]].add(r["contract_id"])
        elif r["type"] == "deployed":
            deployed[r["contract_id"]] = r["findings"]
    verdicts: dict[tuple[str, str], dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for (family, cid, _clause, rid), r in latest.items():
        verdicts[(family, cid)][rid].append(r)
    return {"run_id": run_id, "verdicts": verdicts, "done": done, "deployed": deployed}


def predictions(run: dict, config_id: str, bm: dict) -> dict[tuple[str, str], int]:
    """(contract_id, requirement_id) -> number of findings, for contracts the
    set-up fully completed in this run."""
    from configs import CONFIGS, clause_rule, contract_rule

    cfg = CONFIGS[config_id]
    reqs = bm["requirements"]
    out: dict[tuple[str, str], int] = {}
    if cfg["rule"] == "deployed":
        for cid, findings in run["deployed"].items():
            for r in reqs:
                out[(cid, r["id"])] = sum(1 for f in findings if f["requirement_id"] == r["id"])
        return out
    for cid in run["done"].get(cfg["family"], set()):
        per_req = run["verdicts"].get((cfg["family"], cid), {})
        for r in reqs:
            v = per_req.get(r["id"], [])
            out[(cid, r["id"])] = clause_rule(v) if cfg["rule"] == "clause" else contract_rule(v, r["mandatory"])
    return out


def available_configs(run: dict) -> list[str]:
    from configs import CONFIGS

    out = []
    for cid, cfg in CONFIGS.items():
        if cfg["rule"] == "deployed":
            if run["deployed"]:
                out.append(cid)
        elif run["done"].get(cfg["family"]):
            out.append(cid)
    return out


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def pair_category(contract: dict, req: dict) -> str:
    gold = contract["gold"][req["id"]]
    kind, topic = contract["variant"]["kind"], contract["variant"]["topic"]
    on_topic = topic == req["topic"]
    if gold == "NONE":
        if on_topic and kind == "SILENT":
            return "none_silent_ok"
        if on_topic and kind == "TRAP_HIDDEN_FIX":
            return "none_trap_fix"
        return "none_covered"
    if gold == "VIOLATES":
        return "violates_trap" if kind.startswith("TRAP_") else "violates"
    return "gap"


def _rate(num: int, den: int) -> float | None:
    return num / den if den else None


def metrics(pred: dict[tuple[str, str], int], bm: dict, contract_ids: list[str]) -> dict:
    contracts = {c["contract_id"]: c for c in bm["contracts"]}
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # category -> [flagged, total]
    tp = fp = fn = 0
    total_findings, clean_findings, n_clean = 0, 0, 0
    for cid in contract_ids:
        c = contracts[cid]
        c_findings = 0
        for r in bm["requirements"]:
            n = pred.get((cid, r["id"]), 0)
            c_findings += n
            if c["gold"][r["id"]] == "EXCLUDE":
                continue
            flagged = n > 0
            cat = pair_category(c, r)
            counts[cat][0] += flagged
            counts[cat][1] += 1
            positive = c["gold"][r["id"]] != "NONE"
            tp += flagged and positive
            fp += flagged and not positive
            fn += (not flagged) and positive
        total_findings += c_findings
        if c["variant"]["kind"] == "FOLLOWS":
            clean_findings += c_findings
            n_clean += 1

    def flagged(*cats):
        return sum(counts[k][0] for k in cats), sum(counts[k][1] for k in cats)

    none_f, none_t = flagged("none_covered", "none_silent_ok", "none_trap_fix")
    gap_f, gap_t = flagged("gap")
    vio_f, vio_t = flagged("violates", "violates_trap")
    precision = _rate(tp, tp + fp)
    recall = _rate(tp, tp + fn)
    f1 = (2 * precision * recall / (precision + recall)) if precision and recall else 0.0
    return {
        "n_contracts": len(contract_ids),
        "n_pairs": sum(v[1] for v in counts.values()),
        "false_violation_rate": _rate(none_f, none_t),
        "fvr_covered": _rate(*counts["none_covered"]),
        "fvr_silent_ok": _rate(*counts["none_silent_ok"]),
        "fvr_trap_fix": _rate(*counts["none_trap_fix"]),
        "missed_gap_rate": _rate(gap_t - gap_f, gap_t),
        "violation_recall": _rate(vio_f, vio_t),
        "violation_recall_trap": _rate(*counts["violates_trap"]),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "findings_per_contract": _rate(total_findings, len(contract_ids)),
        "findings_per_clean_contract": _rate(clean_findings, n_clean),
        "counts": {k: {"flagged": v[0], "total": v[1]} for k, v in sorted(counts.items())},
    }


CI_KEYS = ("false_violation_rate", "missed_gap_rate", "violation_recall", "f1", "findings_per_clean_contract")


def bootstrap(pred: dict, bm: dict, contract_ids: list[str], samples: int = BOOTSTRAP_SAMPLES) -> dict:
    """95% interval for each key metric, resampling whole contracts."""
    rng = random.Random(SEED)
    draws: dict[str, list[float]] = defaultdict(list)
    for _ in range(samples):
        sample = [rng.choice(contract_ids) for _ in contract_ids]
        m = metrics(pred, bm, sample)
        for k in CI_KEYS:
            if m[k] is not None:
                draws[k].append(m[k])
    ci = {}
    for k, vals in draws.items():
        vals.sort()
        ci[k] = [vals[int(0.025 * (len(vals) - 1))], vals[int(0.975 * (len(vals) - 1))]]
    return ci


def mcnemar(pred_x: dict, pred_y: dict, bm: dict, contract_ids: list[str], categories: set[str] | None = None) -> dict:
    """Exact two-sided McNemar test on per-pair correctness of two set-ups."""
    contracts = {c["contract_id"]: c for c in bm["contracts"]}
    b = c_ = 0  # b: X right & Y wrong ; c_: X wrong & Y right
    for cid in contract_ids:
        for r in bm["requirements"]:
            if contracts[cid]["gold"][r["id"]] == "EXCLUDE":
                continue
            if categories and pair_category(contracts[cid], r) not in categories:
                continue
            truth = contracts[cid]["gold"][r["id"]] != "NONE"
            x_ok = (pred_x.get((cid, r["id"]), 0) > 0) == truth
            y_ok = (pred_y.get((cid, r["id"]), 0) > 0) == truth
            b += x_ok and not y_ok
            c_ += y_ok and not x_ok
    n = b + c_
    if n == 0:
        return {"x_only_correct": b, "y_only_correct": c_, "p_value": 1.0}
    k = min(b, c_)
    log_terms = [math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) - n * math.log(2) for i in range(k + 1)]
    top = max(log_terms)
    tail = math.exp(top) * sum(math.exp(t - top) for t in log_terms)
    return {"x_only_correct": b, "y_only_correct": c_, "p_value": min(1.0, 2 * tail)}


def agreement(preds: list[dict], bm: dict, contract_ids: list[str]) -> dict:
    """% of pairs every run flagged the same way, and Fleiss' kappa (flag / no flag)."""
    m = len(preds)
    gold = {c["contract_id"]: c["gold"] for c in bm["contracts"]}
    items = [(cid, r["id"]) for cid in contract_ids for r in bm["requirements"] if gold[cid][r["id"]] != "EXCLUDE"]
    if m < 2 or not items:
        return {}
    same = 0
    p_e_yes = 0.0
    p_i_sum = 0.0
    for key in items:
        yes = sum(1 for p in preds if p.get(key, 0) > 0)
        same += yes in (0, m)
        p_e_yes += yes
        p_i_sum += (yes * (yes - 1) + (m - yes) * (m - yes - 1)) / (m * (m - 1))
    n = len(items)
    p_yes = p_e_yes / (n * m)
    p_bar = p_i_sum / n
    p_e = p_yes**2 + (1 - p_yes) ** 2
    kappa = (p_bar - p_e) / (1 - p_e) if p_e < 1 else 1.0
    return {"runs": m, "pairs": n, "all_agree_pct": same / n, "fleiss_kappa": kappa}


def diagnostics(run: dict, preds: dict[str, dict], bm: dict) -> dict:
    """Where the numbers come from, for the paper's analysis section:
      * how each family's raw verdicts split across labels (does the prompt
        actually change what the model says?)
      * each set-up's false-alarm rate per requirement (which rules drive the
        remaining errors?)
      * how the full method's GAP calls were made — no clause on the subject
        at all (decided without the model) vs. from the model's verdicts."""
    from configs import CONFIGS

    contracts = {c["contract_id"]: c for c in bm["contracts"]}
    out: dict = {"verdict_labels": {}, "false_alarm_by_requirement": {}, "gap_provenance": {}}
    for fam in {cfg["family"] for cfg in CONFIGS.values() if cfg["family"]}:
        cnt: dict[str, int] = defaultdict(int)
        for (f, _cid), per in run["verdicts"].items():
            if f != fam:
                continue
            for vs in per.values():
                for v in vs:
                    key = v["label"] + (f"-{v['confidence']}" if v["label"] == "NEUTRAL" else "")
                    cnt[key] += 1
        if cnt:
            total = sum(cnt.values())
            out["verdict_labels"][fam] = {"n": total, **{k: n / total for k, n in sorted(cnt.items())}}
    for cfg, pred in preds.items():
        flagged: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for (cid, rid), n in pred.items():
            if contracts[cid]["gold"][rid] == "NONE":
                flagged[rid][0] += n > 0
                flagged[rid][1] += 1
        out["false_alarm_by_requirement"][cfg] = {
            rid: {"flagged": f, "total": t, "rate": f / t} for rid, (f, t) in sorted(flagged.items())
        }
    fam = CONFIGS["D"]["family"]
    no_clause = from_model = 0
    for cid in run["done"].get(fam, set()):
        for rid, gold in contracts[cid]["gold"].items():
            if gold == "GAP":
                if run["verdicts"].get((fam, cid), {}).get(rid):
                    from_model += 1
                else:
                    no_clause += 1
    out["gap_provenance"] = {"no_clause_on_subject": no_clause, "from_model_verdicts": from_model}
    return out


# --------------------------------------------------------------------------- #
# Experiment 4 — regulation updates
# --------------------------------------------------------------------------- #
def law_metrics(run_id: str, bm: dict) -> dict:
    rows = read_jsonl(RUNS_DIR / run_id / "law_verdicts.jsonl")
    hits: dict[tuple[str, str], list[dict]] = defaultdict(list)
    done = set()
    for r in rows:
        if r["type"] == "hit":
            hits[(r["update_id"], r["contract_id"])].append(r)
        elif r["type"] == "done":
            done.add((r["update_id"], r["contract_id"]))
    contracts = {c["contract_id"]: c for c in bm["contracts"]}

    def rule_count(rule: str, rel: list[dict]) -> int:
        labels = [h["label"] for h in rel]
        if rule == "every_non_entails":  # first implementation (Known Issues §14.7)
            return sum(1 for l in labels if l != "ENTAILS")
        if rule == "contradicts_only":  # interim fix (§14.15)
            return labels.count("CONTRADICTS")
        if labels.count("CONTRADICTS"):  # final per-contract rule
            return labels.count("CONTRADICTS")
        if "ENTAILS" in labels:
            return 0
        return 1 if rel else 0

    out = {"run_id": run_id, "pairs": len(done), "rules": {}}
    for rule in ("every_non_entails", "contradicts_only", "contract_level"):
        c = defaultdict(lambda: [0, 0])
        findings = 0
        for (uid, cid) in done:
            rel = [h for h in hits[(uid, cid)] if h.get("relevant")]
            n = rule_count(rule, rel)
            findings += n
            gold = contracts[cid]["update_gold"][uid]
            c[gold][0] += n > 0
            c[gold][1] += 1
        tp = c["VIOLATES"][0] + c["GAP"][0]
        fp = c["NONE"][0]
        fn = (c["VIOLATES"][1] - c["VIOLATES"][0]) + (c["GAP"][1] - c["GAP"][0])
        precision = _rate(tp, tp + fp)
        recall = _rate(tp, tp + fn)
        out["rules"][rule] = {
            "false_violation_rate": _rate(*c["NONE"]),
            "missed_gap_rate": _rate(c["GAP"][1] - c["GAP"][0], c["GAP"][1]),
            "violation_recall": _rate(*c["VIOLATES"]),
            "precision": precision, "recall": recall,
            "f1": (2 * precision * recall / (precision + recall)) if precision and recall else 0.0,
            "findings_per_check": _rate(findings, len(done)),
        }
    # retrieval: for real violations, was the relevant clause ever put in front of the model?
    vio = [(u, c) for (u, c) in done if contracts[c]["update_gold"][u] == "VIOLATES"]
    found = sum(1 for k in vio if any(h["is_topic_clause"] and h.get("relevant") for h in hits[k]))
    out["retrieval_recall_on_violations"] = _rate(found, len(vio))
    return out


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", default="", help="comma list of runs to score individually")
    ap.add_argument("--compare-runs", default="", help="runs of DIFFERENT models (Experiment 2)")
    ap.add_argument("--repeat-runs", default="", help="repeat runs of the SAME model (Experiment 3)")
    ap.add_argument("--law-runs", default="", help="Experiment 4 runs")
    ap.add_argument("--name", default="results", help="output file name under research/results/")
    ap.add_argument("--bootstrap", type=int, default=BOOTSTRAP_SAMPLES)
    args = ap.parse_args()

    bm = load_benchmark()
    report: dict = {"benchmark_version": bm["version"], "runs": {}, "mcnemar": {}, "agreement": {}, "law": {}}

    for run_id in [r for r in args.runs.split(",") if r]:
        run = load_run(run_id)
        report["runs"][run_id] = {}
        preds = {}
        for cfg in available_configs(run):
            preds[cfg] = predictions(run, cfg, bm)
            cids = sorted({cid for cid, _ in preds[cfg]})
            m = metrics(preds[cfg], bm, cids)
            m["ci95"] = bootstrap(preds[cfg], bm, cids, args.bootstrap)
            report["runs"][run_id][cfg] = m
        tests = {}
        for x, y, cats in [("A", "D", None), ("C", "D", None), ("A", "B", None), ("B", "C", None),
                           ("D_noET", "D", {"violates_trap", "none_trap_fix"}), ("P", "D", None)]:
            if x in preds and y in preds:
                common = sorted({c for c, _ in preds[x]} & {c for c, _ in preds[y]})
                tests[f"{x}_vs_{y}"] = mcnemar(preds[x], preds[y], bm, common, cats)
        report["mcnemar"][run_id] = tests
        report.setdefault("diagnostics", {})[run_id] = diagnostics(run, preds, bm)

    for label, ids in (("models", args.compare_runs), ("repeats", args.repeat_runs)):
        ids = [r for r in ids.split(",") if r]
        if len(ids) < 2:
            continue
        runs = [load_run(r) for r in ids]
        report["agreement"][label] = {"runs": ids, "configs": {}}
        for cfg in ("A", "B", "C", "D", "D_noET", "P"):
            if not all(cfg in available_configs(r) for r in runs):
                continue
            preds = [predictions(r, cfg, bm) for r in runs]
            common = sorted(set.intersection(*[{c for c, _ in p} for p in preds]))
            report["agreement"][label]["configs"][cfg] = agreement(preds, bm, common)

    for run_id in [r for r in args.law_runs.split(",") if r]:
        report["law"][run_id] = law_metrics(run_id, bm)

    out = RESULTS_DIR / f"{args.name}.json"
    write_json(out, report)
    _print_summary(report)
    print(f"\nSaved -> {out}")


def _pct(v) -> str:
    return "  n/a" if v is None else f"{100 * v:5.1f}%"


def _print_summary(report: dict) -> None:
    for run_id, cfgs in report["runs"].items():
        print(f"\n== Run {run_id} ==")
        print(f"{'set-up':<8}{'contracts':>10}{'FalseViol':>11}{'MissedGap':>11}{'ViolRecall':>12}{'F1':>8}{'find/clean':>12}")
        for cfg, m in cfgs.items():
            print(f"{cfg:<8}{m['n_contracts']:>10}{_pct(m['false_violation_rate']):>11}{_pct(m['missed_gap_rate']):>11}"
                  f"{_pct(m['violation_recall']):>12}{_pct(m['f1']):>8}{(m['findings_per_clean_contract'] or 0):>12.1f}")
        for name, t in report["mcnemar"].get(run_id, {}).items():
            print(f"  McNemar {name:<14} only-first-right={t['x_only_correct']:<5} only-second-right={t['y_only_correct']:<5} p={t['p_value']:.2g}")
    for label, block in report["agreement"].items():
        print(f"\n== Agreement across {label}: {', '.join(block['runs'])} ==")
        for cfg, a in block["configs"].items():
            print(f"  {cfg:<8} all-agree {_pct(a.get('all_agree_pct'))}  Fleiss kappa {a.get('fleiss_kappa', float('nan')):.2f}")
    for run_id, law in report["law"].items():
        print(f"\n== Regulation updates {run_id} ({law['pairs']} checks) ==")
        for rule, m in law["rules"].items():
            print(f"  {rule:<18} FalseViol {_pct(m['false_violation_rate'])}  MissedGap {_pct(m['missed_gap_rate'])}"
                  f"  ViolRecall {_pct(m['violation_recall'])}  F1 {_pct(m['f1'])}  findings/check {m['findings_per_check'] or 0:.2f}")
        print(f"  retrieval recall on violations {_pct(law['retrieval_recall_on_violations'])}")


if __name__ == "__main__":
    main()
