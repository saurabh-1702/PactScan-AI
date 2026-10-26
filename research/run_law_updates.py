"""Script 5 — Experiment 4: re-checking existing contracts when a law changes.

For each simulated regulation update (``benchmark/spec.py::UPDATES``) and each
contract, this reproduces the app's Horizon-Scanning re-check step by step,
using the app's own pieces:

  1. embed the contract's clauses and the new rule   (app.llm.client.generate_embedding)
  2. find the clauses related to the rule            (GraphStore.vector_search_similar_clauses,
                                                       with the app's own top_k and threshold)
  3. ask the model about each related clause          (horizon_scanning.rediff._classify_single)

and saves every similarity score and verdict. score.py then applies three
ways of turning those verdicts into findings — the three versions the app
actually went through (Known Issues §14.7, §14.15).

Retrieval is scoped to one contract at a time, so that a clause the search
never surfaced (a retrieval miss, Known Issues §11.2/§11.4/§13.1) is recorded
separately from a clause the model judged wrongly.

    python research\\run_law_updates.py --run-id law_main --provider groq --model openai/gpt-oss-120b --bases b1,b2
    python research\\run_law_updates.py --run-id law_dry --fake --bases b1
"""

from __future__ import annotations

import argparse
import asyncio
import time

from common import RUNS_DIR, append_jsonl, install_fake_llm, load_benchmark, pin_model, read_jsonl, use_backend_env, write_json
from run_verdicts import _now, _with_quota_retry, load_contract


async def main_async(args) -> None:
    from app.agents.detect.graph_store import InMemoryGraphStore
    from app.agents.horizon_scanning.rediff import _classify_single
    from app.config import settings
    from app.llm import client as llm

    bm = load_benchmark()
    run_dir = RUNS_DIR / args.run_id
    out = run_dir / "law_verdicts.jsonl"

    if args.fake:
        install_fake_llm()
        model = "FAKE"
    else:
        pin_model(args.provider, args.model, run_dir / "cache")
        model = f"{args.provider}/{args.model}"

    contracts = bm["contracts"]
    if args.bases:
        keep = set(args.bases.split(","))
        contracts = [c for c in contracts if c["base"] in keep]
    updates = bm["updates"]
    if args.updates:
        keep_u = set(args.updates.split(","))
        updates = [u for u in updates if u["id"] in keep_u]

    if not (run_dir / "meta.json").exists():
        write_json(run_dir / "meta.json", {
            "run_id": args.run_id, "experiment": "law_updates", "model": model, "fake": args.fake,
            "started": _now(), "updates": [u["id"] for u in updates], "bases": args.bases or "all",
            "top_k": settings.horizon_scan_top_k, "similarity_threshold": settings.horizon_scan_similarity_threshold,
            "embedding_model": settings.gemini_embedding_model,
        })

    done = {(r["update_id"], r["contract_id"]) for r in read_jsonl(out) if r["type"] == "done"}
    todo = [(u, c) for u in updates for c in contracts if (u["id"], c["contract_id"]) not in done]
    print(f"Run {args.run_id} [{model}]: {len(todo)} (update, contract) jobs to go.")

    rule_embeddings: dict[str, list[float]] = {}
    t0 = time.monotonic()
    for i, (u, c) in enumerate(todo, 1):
        store = InMemoryGraphStore()
        load_contract(store, c)
        for cl in c["clauses"]:
            emb = await _with_quota_retry(lambda: llm.generate_embedding(cl["raw_text"]), cl["clause_id"])
            store.set_clause_embedding(cl["clause_id"], emb)
        if u["id"] not in rule_embeddings:
            rule_embeddings[u["id"]] = await _with_quota_retry(lambda: llm.generate_embedding(u["text"]), u["id"])

        hits = store.vector_search_similar_clauses(
            rule_embeddings[u["id"]], top_k=settings.horizon_scan_top_k, contract_id=c["contract_id"]
        )
        topic_ids = {cl["clause_id"] for cl in c["clauses"] if cl["topic"] == u["topic"] or cl.get("role") == "amendment"}
        for h in hits:
            relevant = h["similarity"] >= settings.horizon_scan_similarity_threshold
            row = {
                "type": "hit", "update_id": u["id"], "contract_id": c["contract_id"], "clause_id": h["clause_id"],
                "similarity": round(h["similarity"], 4), "relevant": relevant,
                "is_topic_clause": h["clause_id"] in topic_ids, "model": model, "at": _now(),
            }
            if relevant:
                nli = await _with_quota_retry(lambda: _classify_single(h["raw_text"], u["text"]), h["clause_id"])
                row.update({"label": nli.label.value, "confidence": nli.confidence.value, "explanation": nli.explanation})
            append_jsonl(out, row)
        append_jsonl(out, {"type": "done", "update_id": u["id"], "contract_id": c["contract_id"], "at": _now()})
        print(f"  [{i}/{len(todo)}] {u['id']:<22} {c['contract_id']:<38} {time.monotonic() - t0:6.0f}s", flush=True)
    print("Finished.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--provider", default="groq", choices=["groq", "gemini"])
    ap.add_argument("--model", default="openai/gpt-oss-120b")
    ap.add_argument("--bases", default="", help="comma list of base ids (default: all)")
    ap.add_argument("--updates", default="", help="comma list of update ids (default: all)")
    ap.add_argument("--fake", action="store_true")
    args = ap.parse_args()
    use_backend_env()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
