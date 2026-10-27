# The research paper (IEEE LaTeX)

`main.tex` + `references.bib`, IEEE conference format (`IEEEtran`, two columns).

## Turn it into a PDF (no install needed)

1. Go to <https://www.overleaf.com> and sign in (free).
2. **New Project → Upload Project**, and upload a `.zip` containing `main.tex` and `references.bib`
   (or create a blank project and upload the two files).
3. Overleaf compiles it automatically with pdfLaTeX — `IEEEtran` and every package used are built in.
4. **Download PDF** (or the source as a zip) when done.

Red text in the PDF marks something still to fill in.

## Before submitting — checklist

- [ ] **Authors**: replace the red author/department/email lines at the top of `main.tex`.
- [ ] **References marked `VERIFY`** in `references.bib`: confirm author lists / exact titles on arXiv or Google Scholar.
- [ ] **Repository URL** in "Data and Code Availability" (or delete that sentence).
- [ ] Your college's specific template, if different from plain IEEE conference format.
- [ ] Read it once end to end: every number in it comes from `research/results/*.json`.

## Where each number comes from

| Paper part | Source |
|---|---|
| Table I (benchmark) | `research/benchmark/out/benchmark.json` |
| Tables II–V, E1/E2 text | `research/results/exp1_2.json` (`score.py --runs main,m_gpt20b,m_qwen --compare-runs main,m_gpt20b,m_qwen --name exp1_2`) |
| Sign test 18/18 | `exp1_2.json` → `sign_test` |
| Per-requirement table | `exp1_2.json` → `diagnostics.<run>.false_alarm_by_requirement.D` |
| E3 table (stability) | `research/results/final.json` → `agreement.repeats` (runs `m_gpt20b` restricted to bases b1–b2, `rep20b_1`–`rep20b_4`; `rep20b_5` was stopped at 24/92 by the daily quota and is not used); per-run FVR range computed on the same 46 contracts |
| E4 table | `final.json` → `law.law_main` (also `exp4.json`) |
| All of the above in one file | `score.py --runs main,m_gpt20b,m_qwen,rep20b_1,rep20b_2,rep20b_3,rep20b_4 --compare-runs main,m_gpt20b,m_qwen --repeat-runs m_gpt20b,rep20b_1,rep20b_2,rep20b_3,rep20b_4 --law-runs law_main --name final` |
| Development incidents (19 findings, 9→13) | `docs/PactScan_AI_Known_Issues_And_Lessons_Learned.md` §10.13, §14.7, §14.15 |
