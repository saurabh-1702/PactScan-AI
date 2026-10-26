# Research harness — "Silence Is Not Violation"

Measures how often an LLM compliance checker mistakes a contract's **silence**
on a requirement for a **violation** of it, and how much PactScan's method
(conservative prompt + subject routing + override-aware reading +
contract-level findings) reduces that without hiding genuinely missing
protections. Separate from the app: nothing here changes `backend/` or
`frontend/`; the app's own Detect and Horizon-Scanning functions are imported
and measured.

Run everything from the repo root with the backend's virtualenv:

```
backend\venv\Scripts\python.exe research\<script>.py ...
```

## The scripts, in order

| # | Script | What it does |
|---|---|---|
| 1 | `build_benchmark.py` | Builds the benchmark from `benchmark/spec.py`: 6 base DPAs × 23 variants = 138 contracts, 1,794 graded (contract, requirement) pairs → `benchmark/out/benchmark.json` + one readable `.md` per contract |
| 2 | `check_benchmark.py` | Automatic consistency checks + `benchmark/out/review_sheet.csv` for the **human check of every correct answer** |
| 3 | `configs.py` | The set-ups compared: A original (commit 9bbc499) → B + conservative prompt → C + subject routing → D + contract-level findings; D_noET ablation; P = the app as deployed |
| 4 | `run_verdicts.py` | Experiments 1–3: runs the set-ups on one pinned model, saves every verdict (resumable) |
| 5 | `run_law_updates.py` | Experiment 4: the Horizon-Scanning re-check on simulated regulation updates |
| 6 | `score.py` | All numbers: false-violation rate, missed-gap rate, violation recall, F1, bootstrap 95% CIs, McNemar, agreement / Fleiss' kappa |
| 7 | `make_tables.py` | Paper tables (Markdown + LaTeX) from `score.py`'s output |

`tests/test_scoring.py` checks the arithmetic in `score.py` on cases with a
known right answer (`python -m pytest research\tests -q`).

## Before any live run

1. **Review the correct answers.** Done once — see `benchmark/LABEL_REVIEW.md`
   (and `benchmark/out/review_sheet.csv`, 116 rows). To change a label, edit
   `benchmark/spec.py` and re-run scripts 1 and 2.
2. **Check your free-tier limits** at console.groq.com (requests *and tokens*
   per day for each model). More keys in `GROQ_API_KEYS` = more daily capacity.
   Experiment 4 also needs `GEMINI_API_KEYS` (embeddings).
3. **Smoke test** a few contracts live: `run_verdicts.py --run-id smoke --limit 2`.

## Experiment plan

| Exp. | Command (add `--provider/--model`) | Approx. model calls |
|---|---|---|
| 1 | `run_verdicts.py --run-id main --deployed` | ~600–800 (all 138 contracts) |
| 2 | `run_verdicts.py --run-id m_<model> --families A_original,C_routing` per extra model | ~300 each |
| 3 | `run_verdicts.py --run-id rep<N> --families A_original,C_routing` × 5 | ~300 each |
| 4 | `run_law_updates.py --run-id law_main` | ~600 + ~200 embeddings |

Why so few: the variants of one base contract share 12 of their 13 clauses,
and within a run an identical question under the same system prompt is
answered once (each system-prompt version has its own cache folder, because
the app's cache key does not include the system prompt). On Groq's free tier
the rate limit (~30 requests/minute) is the bottleneck: the 2-contract smoke
test took ~4 minutes, so Experiment 1 is roughly 30–60 minutes.

All runs are resumable: if the daily quota runs out the script stops and
saves; the same command continues later.

```
python research\score.py --runs main,m_gpt20b --compare-runs main,m_gpt20b --repeat-runs rep1,rep2,rep3,rep4,rep5 --law-runs law_main
python research\make_tables.py --results results --main-run main
```

## Experiment controls (from `docs/PactScan_AI_Known_Issues_And_Lessons_Learned.md`)

- One model per run, no silent fallback to another model (§10.10–10.14); model and date saved on every row.
- A cache private to each run, so repeat runs are genuinely repeated (§3).
- The checker is given the benchmark's clauses directly — parsing and clause
  extraction are not measured, only the verdict.
- Experiment 4 records retrieval misses separately from wrong verdicts (§11.2, §11.4, §13.1).
- The benchmark has all three correct answers in every topic, so over-flagging can't hide (§14.7, §14.14).
