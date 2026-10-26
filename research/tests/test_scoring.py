"""The paper's numbers come from score.py — these tests pin its arithmetic on
cases whose right answer is known by construction.

    backend\\venv\\Scripts\\python.exe -m pytest research\\tests -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import common  # noqa: E402,F401 - puts backend/ on sys.path
from build_benchmark import gold_label  # noqa: E402
from configs import clause_rule, contract_rule  # noqa: E402
from score import agreement, mcnemar, metrics  # noqa: E402


@pytest.fixture(scope="module")
def bm():
    if not common.BENCHMARK_FILE.exists():
        pytest.skip("run research/build_benchmark.py first")
    return common.load_benchmark()


def _oracle(bm):
    return {(c["contract_id"], r): int(g in ("VIOLATES", "GAP")) for c in bm["contracts"] for r, g in c["gold"].items()}


def _ids(bm):
    return [c["contract_id"] for c in bm["contracts"]]


# --- turning verdicts into findings -------------------------------------------
def _v(label, conf="medium"):
    return {"label": label, "confidence": conf}


def test_clause_rule_counts_contradictions_and_confident_neutrals():
    assert clause_rule([_v("CONTRADICTS"), _v("NEUTRAL", "high"), _v("NEUTRAL"), _v("ENTAILS")]) == 2
    assert clause_rule([]) == 0


@pytest.mark.parametrize(
    "verdicts, mandatory, expected",
    [
        ([_v("NEUTRAL"), _v("CONTRADICTS"), _v("CONTRADICTS")], True, 2),  # violations flagged per clause
        ([_v("NEUTRAL", "high"), _v("ENTAILS")], True, 0),  # covered somewhere -> nothing
        ([_v("NEUTRAL", "high"), _v("NEUTRAL", "high")], True, 1),  # silent everywhere -> ONE gap
        ([], True, 1),  # no clause on the subject at all -> one gap
        ([_v("NEUTRAL"), _v("NEUTRAL")], False, 0),  # silent but not mandatory -> nothing
        ([], False, 0),
    ],
)
def test_contract_rule(verdicts, mandatory, expected):
    assert contract_rule(verdicts, mandatory) == expected


# --- correct answers -----------------------------------------------------------
@pytest.mark.parametrize(
    "kind, mandatory, expected",
    [("BREAKS", True, "VIOLATES"), ("SILENT", True, "GAP"), ("SILENT", False, "NONE"),
     ("TRAP_HIDDEN_VIOLATION", True, "VIOLATES"), ("TRAP_HIDDEN_FIX", True, "NONE"), ("FOLLOWS", True, "NONE")],
)
def test_gold_label_on_the_varied_topic(kind, mandatory, expected):
    req = {"id": "x", "topic": "t", "mandatory": mandatory}
    assert gold_label(req, {"kind": kind, "topic": "t"}) == expected
    assert gold_label(req, {"kind": kind, "topic": "other"}) == "NONE"


# --- metrics -------------------------------------------------------------------
def test_a_perfect_checker_scores_perfectly(bm):
    m = metrics(_oracle(bm), bm, _ids(bm))
    assert m["false_violation_rate"] == 0
    assert m["missed_gap_rate"] == 0
    assert m["violation_recall"] == 1
    assert m["f1"] == 1
    assert m["findings_per_clean_contract"] == 0
    excluded = sum(1 for c in bm["contracts"] for g in c["gold"].values() if g == "EXCLUDE")
    assert m["n_pairs"] == len(bm["contracts"]) * len(bm["requirements"]) - excluded


def test_flagging_everything_is_all_false_violations_and_no_missed_gaps(bm):
    pred = {k: 1 for k in _oracle(bm)}
    m = metrics(pred, bm, _ids(bm))
    assert m["false_violation_rate"] == 1
    assert m["missed_gap_rate"] == 0
    assert m["findings_per_clean_contract"] == len(bm["requirements"])


def test_flagging_nothing_misses_every_gap(bm):
    m = metrics({}, bm, _ids(bm))
    assert m["false_violation_rate"] == 0
    assert m["missed_gap_rate"] == 1
    assert m["recall"] == 0
    assert m["f1"] == 0


def test_false_violation_categories_partition_the_none_pairs(bm):
    m = metrics({}, bm, _ids(bm))
    none_total = sum(1 for c in bm["contracts"] for g in c["gold"].values() if g == "NONE")
    cats = m["counts"]
    assert cats["none_covered"]["total"] + cats["none_silent_ok"]["total"] + cats["none_trap_fix"]["total"] == none_total


# --- statistics ----------------------------------------------------------------
def test_mcnemar_exact_values(bm):
    oracle = _oracle(bm)
    ids = _ids(bm)
    # make the second set-up wrong on exactly 10 pairs the first gets right
    wrong = dict(oracle)
    for key in list(oracle)[:10]:
        wrong[key] = 1 - oracle[key]
    t = mcnemar(oracle, wrong, bm, ids)
    assert (t["x_only_correct"], t["y_only_correct"]) == (10, 0)
    assert t["p_value"] == pytest.approx(2 * 0.5**10)
    assert mcnemar(oracle, oracle, bm, ids)["p_value"] == 1.0


def test_agreement_identical_and_split(bm):
    oracle = _oracle(bm)
    ids = _ids(bm)
    same = agreement([oracle, oracle, oracle], bm, ids)
    assert same["all_agree_pct"] == 1 and same["fleiss_kappa"] == pytest.approx(1.0)
    flipped = {k: 1 - v for k, v in oracle.items()}
    split = agreement([oracle, flipped], bm, ids)
    assert split["all_agree_pct"] == 0 and split["fleiss_kappa"] < 0


def test_ambiguous_pairs_are_excluded_and_applicability_is_respected(bm):
    from benchmark import spec

    req_s4 = next(r for r in bm["requirements"] if r["id"] == "dpdp_s4")
    assert gold_label(req_s4, {"kind": "BREAKS", "topic": "children_data"}) == "EXCLUDE"
    req_s9 = next(r for r in bm["requirements"] if r["id"] == "dpdp_s9")
    payroll = next(b for b in spec.BASES if b["children"] == "not_applicable")
    assert gold_label(req_s9, {"kind": "SILENT", "topic": "children_data"}, payroll) == "NONE"
    assert gold_label(req_s9, {"kind": "SILENT", "topic": "children_data"}, spec.BASES[0]) == "GAP"
    # excluded pairs never count, whatever the prediction
    ids = [c["contract_id"] for c in bm["contracts"]]
    flag_excluded = {(c["contract_id"], r): 1 for c in bm["contracts"] for r, g in c["gold"].items() if g == "EXCLUDE"}
    assert metrics(flag_excluded, bm, ids)["false_violation_rate"] == 0
