"""Script 4 — run the checker set-ups over the benchmark (Experiments 1–3).

For every contract and every family in ``configs.FAMILIES`` it asks the model,
clause by clause, exactly what that family asks, and saves every raw verdict.
With ``--deployed`` it also runs the app's own, unmodified ``run_detect`` and
saves its findings. Turning verdicts into findings and numbers is score.py's job.

The clauses are given to the checker directly (the benchmark's own clauses and
override links), skipping PDF parsing and clause extraction, so what is
measured is the verdict step alone.

Experiment controls (from the Known Issues log):
  * exactly ONE model per run, no fallback to another model (§10.10–10.14)
  * a cache private to the run: repeat runs never reuse answers (§3); within a
    run, an identical question asked under the same system prompt is answered
    once (the variants of a base share 12 of 13 clauses), so each distinct
    clause text gets exactly one verdict per run
  * every row records the model and the date; meta.json records the set-up
  * resumable: re-running the same --run-id skips work already saved; a
    contract only counts once ALL its clauses for a family are saved

    # Experiment 1 (all set-ups, main model)
    python research\\run_verdicts.py --run-id main --provider groq --model openai/gpt-oss-120b --deployed
    # Experiment 2 (other models: before vs after only)
    python research\\run_verdicts.py --run-id m_gpt20b --provider groq --model openai/gpt-oss-20b --families A_original,C_routing
    # Experiment 3 (repeat runs on a subset)
    python research\\run_verdicts.py --run-id rep1 --provider groq --model openai/gpt-oss-120b --families A_original,C_routing --bases b1,b2
    # Plumbing test with no API calls
    python research\\run_verdicts.py --run-id dry --fake
"""

from __future__ import annotations

import argparse
import asyncio
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

from common import RUNS_DIR, REPO_DIR, append_jsonl, install_fake_llm, load_benchmark, pin_model, read_jsonl, use_backend_env, write_json

MAX_QUOTA_WAITS = 15  # consecutive waits on an exhausted model before stopping (resume later)

# The app's LLM cache key is (prompt text, schema, LLM_PROMPT_VERSION) — it does
# NOT include the system prompt. Set-ups A and B ask the identical question
# under different system prompts, so sharing one cache would hand B the answers
# A got. Each system-prompt version therefore gets its own cache folder.
_CACHE_ROOT = None


def _use_cache_for(prompt_version: str) -> None:
    if _CACHE_ROOT is None:  # fake model: no cache in play
        return
    from app.config import settings

    settings.llm_cache_dir = str(_CACHE_ROOT / prompt_version)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_DIR, capture_output=True, text=True).stdout.strip()
    except OSError:
        return "unknown"


def load_contract(store, contract: dict) -> None:
    from app.models.clause import ConfidenceLevel, ExtractedClause

    store.upsert_contract(contract["contract_id"], contract["filename"])
    for cl in contract["clauses"]:
        store.add_clause(ExtractedClause(
            clause_id=cl["clause_id"], contract_id=contract["contract_id"], clause_type=cl["clause_type"],
            page_number=cl["page_number"], section_header=cl["section_header"], raw_text=cl["raw_text"],
            confidence=ConfidenceLevel.high,
        ))
    for o in contract["overrides"]:
        store.add_override(o["src"], o["dst"], scope=o["scope"])


async def _with_quota_retry(make_call, label: str):
    """Waits out a rate limit instead of failing; stops the run if the model's
    quota stays exhausted (e.g. the daily limit) so it can be resumed later."""
    from app.llm.errors import AllLLMTiersExhaustedError

    waits = 0
    while True:
        try:
            return await make_call()
        except AllLLMTiersExhaustedError as exc:
            waits += 1
            if waits > MAX_QUOTA_WAITS:
                raise SystemExit(
                    f"\nModel quota still exhausted after {MAX_QUOTA_WAITS} waits ({label}). "
                    "Progress is saved — re-run the same command later to resume."
                ) from exc
            print(f"    rate-limited ({label}); waiting 65s [{waits}/{MAX_QUOTA_WAITS}]", flush=True)
            await asyncio.sleep(65)


async def run_family(fam_name: str, family: dict, contract: dict, bm: dict, out, model: str) -> bool:
    from app.agents.detect.detect_agent import _effective_text
    from app.agents.detect.graph_store import InMemoryGraphStore

    from configs import classify, routing_for

    _use_cache_for(family["prompt"])
    store = InMemoryGraphStore()
    load_contract(store, contract)
    routing = routing_for(family, bm)
    reqs = {r["id"]: r for r in bm["requirements"]}

    for cl in contract["clauses"]:
        req_ids = routing.get(cl["clause_type"], [])
        if not req_ids:
            continue
        clause = store.get_clause_by_id(cl["clause_id"])
        overriders = store.get_overriders(cl["clause_id"], max_hops=3) if family["effective_text"] else []
        text = _effective_text(clause, overriders)
        requirements = [(rid, reqs[rid]["kind"], reqs[rid]["label"], reqs[rid]["text"]) for rid in req_ids]

        result = None
        for attempt in range(3):  # a malformed model answer is retried, never guessed
            try:
                result = await _with_quota_retry(lambda: classify(family, text, requirements), cl["clause_id"])
                break
            except SystemExit:
                raise
            except Exception as exc:  # noqa: BLE001 - recorded, contract left incomplete
                err = f"{type(exc).__name__}: {str(exc)[:200]}"
        if result is None:
            append_jsonl(out, {"type": "error", "family": fam_name, "contract_id": contract["contract_id"],
                               "clause_id": cl["clause_id"], "error": err, "model": model, "at": _now()})
            return False

        by_id = {item.requirement_id: item for item in result.results}
        for rid in req_ids:
            item = by_id.get(rid)
            append_jsonl(out, {
                "type": "verdict", "family": fam_name, "contract_id": contract["contract_id"],
                "clause_id": cl["clause_id"], "requirement_id": rid,
                "label": item.label.value if item else "MISSING",
                "confidence": item.confidence.value if item else None,
                "explanation": item.explanation if item else None,
                "effective_text_used": bool(overriders), "model": model, "at": _now(),
            })
    append_jsonl(out, {"type": "done", "family": fam_name, "contract_id": contract["contract_id"], "at": _now()})
    return True


_LABEL_RE = re.compile(r"Playbook: (\w+)")


async def run_deployed(contract: dict, bm: dict, out, model: str) -> bool:
    """The app's own Detect agent, unmodified, on the same clauses."""
    from app.agents.detect.detect_agent import run_detect
    from app.agents.detect.graph_store import InMemoryGraphStore
    from app.agents.detect.seed_data import seed

    _use_cache_for("v3")  # run_detect asks with the app's current (v3) system prompt
    store = InMemoryGraphStore()
    seed(store)
    load_contract(store, contract)
    label_to_id = {r["label"]: r["id"] for r in bm["requirements"]}
    try:
        findings = await _with_quota_retry(lambda: run_detect(store, contract["contract_id"]), contract["contract_id"])
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        append_jsonl(out, {"type": "error", "family": "deployed", "contract_id": contract["contract_id"],
                           "error": f"{type(exc).__name__}: {str(exc)[:200]}", "model": model, "at": _now()})
        return False
    rows = []
    for f in findings:
        rid = label_to_id.get(f.rule_or_regulation_violated)
        if rid is None:
            m = _LABEL_RE.match(f.rule_or_regulation_violated)
            rid = m.group(1) if m else f.rule_or_regulation_violated
        rows.append({"requirement_id": rid, "clause_id": f.clause_id, "severity": f.severity.value,
                     "explanation": f.explanation})
    append_jsonl(out, {"type": "deployed", "contract_id": contract["contract_id"], "findings": rows,
                       "model": model, "at": _now()})
    return True


async def main_async(args) -> None:
    from configs import FAMILIES

    bm = load_benchmark()
    run_dir = RUNS_DIR / args.run_id
    out = run_dir / "verdicts.jsonl"
    families = [f for f in args.families.split(",") if f] if args.families else list(FAMILIES)
    unknown = [f for f in families if f not in FAMILIES]
    if unknown:
        raise SystemExit(f"Unknown families {unknown}; choose from {list(FAMILIES)}")

    contracts = bm["contracts"]
    if args.bases:
        keep = set(args.bases.split(","))
        contracts = [c for c in contracts if c["base"] in keep]
    if args.limit:
        contracts = contracts[: args.limit]

    if args.fake:
        install_fake_llm()
        model = "FAKE"
    else:
        pin_model(args.provider, args.model, run_dir / "cache")
        model = f"{args.provider}/{args.model}"
        global _CACHE_ROOT
        _CACHE_ROOT = run_dir / "cache"

    meta_path = run_dir / "meta.json"
    if not meta_path.exists():
        from app.config import settings

        write_json(meta_path, {
            "run_id": args.run_id, "model": model, "fake": args.fake, "started": _now(),
            "families": families, "deployed": args.deployed, "bases": args.bases or "all",
            "n_contracts": len(contracts), "benchmark_version": bm["version"],
            "git_commit": _git_commit(), "llm_prompt_version": settings.llm_prompt_version,
            "temperature": "0.2 (Groq call site in app/llm/client.py); provider default for Gemini",
            "python": sys.version.split()[0],
        })

    done = {(r["family"], r["contract_id"]) for r in read_jsonl(out) if r["type"] == "done"}
    done |= {("deployed", r["contract_id"]) for r in read_jsonl(out) if r["type"] == "deployed"}
    jobs = [(f, c) for c in contracts for f in families] + ([("deployed", c) for c in contracts] if args.deployed else [])
    todo = [(f, c) for f, c in jobs if (f, c["contract_id"]) not in done]
    print(f"Run {args.run_id} [{model}]: {len(jobs) - len(todo)}/{len(jobs)} jobs already done, {len(todo)} to go.")

    t0, failed = time.monotonic(), 0
    for i, (fam, contract) in enumerate(todo, 1):
        if fam == "deployed":
            ok = await run_deployed(contract, bm, out, model)
        else:
            ok = await run_family(fam, FAMILIES[fam], contract, bm, out, model)
        failed += not ok
        print(f"  [{i}/{len(todo)}] {fam:<11} {contract['contract_id']:<38} {'ok' if ok else 'ERROR (will retry on resume)'}"
              f"  {time.monotonic() - t0:6.0f}s", flush=True)
    print(f"Finished. {failed} job(s) with errors" + (" — re-run to retry them." if failed else "."))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True, help="folder name under research/runs/")
    ap.add_argument("--provider", default="groq", choices=["groq", "gemini"])
    ap.add_argument("--model", default="openai/gpt-oss-120b")
    ap.add_argument("--families", default="", help="comma list (default: all)")
    ap.add_argument("--deployed", action="store_true", help="also run the app's own run_detect (config P)")
    ap.add_argument("--bases", default="", help="comma list of base ids, e.g. b1,b2 (default: all)")
    ap.add_argument("--limit", type=int, default=0, help="only the first N contracts (smoke tests)")
    ap.add_argument("--fake", action="store_true", help="offline fake model — tests the plumbing, numbers are meaningless")
    args = ap.parse_args()
    use_backend_env()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
