"""Script 1 — build the benchmark.

Turns ``benchmark/spec.py`` into ``benchmark/out/benchmark.json``: every
contract (as the exact clauses the checker will see), the OVERRIDES links for
trap contracts, and the correct answer for every (contract, requirement) pair.
Also writes one readable Markdown file per contract under
``benchmark/out/contracts/``.

For each base contract it produces:
  * 1  base contract            — complies with everything
  * 9  SILENT contracts         — one topic clause removed
  * 9  BREAKS contracts         — one topic clause rewritten to break its rules
  * 4  trap contracts           — an amendment hides a violation / hides a fix

    backend\\venv\\Scripts\\python.exe research\\build_benchmark.py            # all 6 bases
    backend\\venv\\Scripts\\python.exe research\\build_benchmark.py --bases 2  # first 2 only
"""

from __future__ import annotations

import argparse
import shutil
from datetime import date

from common import BENCHMARK_DIR, BENCHMARK_FILE, write_json

from benchmark import spec

GOLD_NONE, GOLD_VIOLATES, GOLD_GAP = "NONE", "VIOLATES", "GAP"


def _requirements() -> list[dict]:
    """The 13 requirements, verbatim from the app's own seed data."""
    from app.agents.detect.seed_data import DPDP_CLAUSES, GDPR_CLAUSES, PLAYBOOK_RULES

    topic_of = {r: t for t, meta in spec.TOPICS.items() for r in meta["requirements"]}
    out = []
    for rule in PLAYBOOK_RULES:
        out.append({
            "id": rule["id"], "kind": "playbook", "label": f"Playbook: {rule['id']}",
            "text": rule["rule_text"], "topic": topic_of[rule["id"]],
        })
    for reg in DPDP_CLAUSES + GDPR_CLAUSES:
        out.append({
            "id": reg["id"], "kind": "regulation", "label": f"{reg['regulation_name']} {reg['section']}",
            "text": reg["text"], "topic": topic_of[reg["id"]],
        })
    for r in out:
        r["mandatory"] = spec.TOPICS[r["topic"]]["mandatory"]
    return out


def _fill(template: str, base: dict, **extra) -> str:
    return template.format(**base, **extra)


def _text_key(topic: str, base: dict) -> str:
    if topic != "children_data":
        return topic
    return "children_data:processed" if base["children"] == "processed" else "children_data:excluded"


def _clause_text(kind: str, topic: str, base: dict) -> str:
    table = spec.FOLLOWS if kind == "follows" else spec.BREAKS
    return _fill(table[_text_key(topic, base)][base["style"]], base)


GOLD_EXCLUDE = "EXCLUDE"


def applies(requirement: dict, base: dict | None) -> bool:
    """Whether a mandatory requirement actually binds this contract. The
    children's-data rules only bind when children's data could be processed —
    not, e.g., in an employee-payroll DPA."""
    return not (base and requirement["topic"] == "children_data" and base["children"] == "not_applicable")


def gold_label(requirement: dict, variant: dict, base: dict | None = None) -> str:
    """The correct answer for one requirement in a contract with this variant."""
    if requirement["id"] in spec.EXCLUDED.get((variant["kind"], variant["topic"]), []):
        return GOLD_EXCLUDE
    if variant["topic"] != requirement["topic"]:
        return GOLD_NONE
    kind = variant["kind"]
    if kind == "BREAKS" or kind == "TRAP_HIDDEN_VIOLATION":
        return GOLD_VIOLATES
    if kind == "SILENT":
        return GOLD_GAP if requirement["mandatory"] and applies(requirement, base) else GOLD_NONE
    return GOLD_NONE  # FOLLOWS, TRAP_HIDDEN_FIX


def _contract(base: dict, variant: dict, requirements: list[dict]) -> dict:
    cid = f"{base['id']}_{variant['name']}"
    clauses, overrides = [], []
    number_of: dict[str, int] = {}
    n = 0
    for slot, page in spec.LAYOUT:
        if slot == variant["topic"] and variant["kind"] == "SILENT":
            continue
        n += 1
        if slot in spec.TOPICS:
            meta = spec.TOPICS[slot]
            clause_type, section = meta["clause_type"], meta["section"]
            if slot == variant["topic"] and variant["kind"] == "BREAKS":
                text = _clause_text("breaks", slot, base)
            elif slot == variant["topic"] and variant["kind"] == "TRAP_HIDDEN_FIX":
                text = spec.TRAPS[slot]["hidden_fix"]["clause"]
            else:
                text = _clause_text("follows", slot, base)
            topic = slot
        else:
            clause_type, section = spec.FILLER_META[slot]
            text = _clause_text("follows", slot, base)
            topic = None
        number_of[slot] = n
        clauses.append({
            "clause_id": f"{cid}_c{n:02d}", "number": n, "clause_type": clause_type,
            "page_number": page, "section_header": f"{n}. {section}", "raw_text": text,
            "topic": topic,
        })

    if variant["kind"].startswith("TRAP_"):
        trap = spec.TRAPS[variant["topic"]]["hidden_violation" if variant["kind"] == "TRAP_HIDDEN_VIOLATION" else "hidden_fix"]
        n += 1
        ref = number_of[variant["topic"]]
        amendment_id = f"{cid}_c{n:02d}"
        clauses.append({
            "clause_id": amendment_id, "number": n, "clause_type": "OTHER", "page_number": 4,
            "section_header": f"{n}. Schedule 2 — Amendment No. 1",
            "raw_text": trap["amendment"].format(ref=ref), "topic": None, "role": "amendment",
        })
        overrides.append({"src": amendment_id, "dst": f"{cid}_c{ref:02d}", "scope": trap["scope"]})

    gold = {r["id"]: gold_label(r, variant, base) for r in requirements}
    return {
        "contract_id": cid, "base": base["id"], "sector": base["sector"],
        "filename": f"{base['CF'].replace(' ', '_')}__{base['VF'].replace(' ', '_')}__{variant['name']}.pdf",
        "parties": {"company": base["CF"], "vendor": base["VF"]},
        "variant": {"kind": variant["kind"], "topic": variant["topic"]},
        "clauses": clauses, "overrides": overrides, "gold": gold,
    }


def _variants() -> list[dict]:
    out = [{"name": "base", "kind": "FOLLOWS", "topic": None}]
    for topic in spec.TOPICS:
        out.append({"name": f"silent_{topic}", "kind": "SILENT", "topic": topic})
    for topic in spec.TOPICS:
        out.append({"name": f"breaks_{topic}", "kind": "BREAKS", "topic": topic})
    for topic in spec.TRAPS:
        out.append({"name": f"trap_violation_{topic}", "kind": "TRAP_HIDDEN_VIOLATION", "topic": topic})
        out.append({"name": f"trap_fix_{topic}", "kind": "TRAP_HIDDEN_FIX", "topic": topic})
    return out


def _update_gold(update: dict, contract: dict) -> str:
    if update["topic"] is None:
        return update["gold_all"]
    variant = contract["variant"]
    key = variant["kind"] if variant["topic"] == update["topic"] else "FOLLOWS"
    return update["gold_by_variant"][key]


def _markdown(c: dict, requirements: list[dict]) -> str:
    lines = [
        f"# {c['contract_id']}",
        "",
        f"**Data Processing Agreement** between {c['parties']['company']} (the \"Company\", Data Fiduciary) "
        f"and {c['parties']['vendor']} (the \"Vendor\", Data Processor).",
        "",
        f"Variant: **{c['variant']['kind']}**" + (f" — topic `{c['variant']['topic']}`" if c["variant"]["topic"] else ""),
        "",
    ]
    page = None
    for cl in c["clauses"]:
        if cl["page_number"] != page:
            page = cl["page_number"]
            lines += [f"## Page {page}", ""]
        lines += [f"**{cl['section_header']}** _({cl['clause_type']})_", "", cl["raw_text"], ""]
    if c["overrides"]:
        lines += ["## Overrides", ""]
        for o in c["overrides"]:
            lines.append(f"- `{o['src']}` overrides `{o['dst']}` (scope: {o['scope']})")
        lines.append("")
    lines += ["## Correct answers", "", "| Requirement | Correct answer |", "|---|---|"]
    for r in requirements:
        lines.append(f"| {r['label']} | {c['gold'][r['id']]} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bases", type=int, default=len(spec.BASES), help="how many base contracts to use")
    args = ap.parse_args()

    requirements = _requirements()
    bases = spec.BASES[: args.bases]
    contracts = [_contract(b, v, requirements) for b in bases for v in _variants()]
    for c in contracts:
        c["update_gold"] = {u["id"]: _update_gold(u, c) for u in spec.UPDATES}

    out_dir = BENCHMARK_FILE.parent
    md_dir = out_dir / "contracts"
    if md_dir.exists():
        shutil.rmtree(md_dir)
    md_dir.mkdir(parents=True)
    for c in contracts:
        (md_dir / f"{c['contract_id']}.md").write_text(_markdown(c, requirements), encoding="utf-8", newline="\n")

    write_json(BENCHMARK_FILE, {
        "name": "DPDP-DPA Silence-vs-Violation benchmark",
        "version": "1.0",
        "built": date.today().isoformat(),
        "label_meaning": {
            "NONE": "nothing wrong — the checker should raise nothing for this requirement",
            "VIOLATES": "a clause goes against the requirement — the checker should flag it",
            "GAP": "a mandatory requirement nothing in the contract addresses — the checker should report it",
            "EXCLUDE": "careful readers could disagree on this pair — left out of every score (see LABEL_REVIEW.md)",
        },
        "requirements": requirements,
        "topics": spec.TOPICS,
        "updates": spec.UPDATES,
        "contracts": contracts,
    })
    excluded = sum(1 for c in contracts for g in c["gold"].values() if g == GOLD_EXCLUDE)
    pairs = len(contracts) * len(requirements) - excluded
    print(f"Wrote {len(contracts)} contracts ({len(bases)} bases), {pairs} graded pairs "
          f"({excluded} excluded as ambiguous) -> {BENCHMARK_FILE.relative_to(BENCHMARK_DIR.parent.parent)}")


if __name__ == "__main__":
    main()
