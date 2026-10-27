# The research paper (IEEE LaTeX)

`main.tex` + `references.bib`, IEEE conference format (`IEEEtran`, two columns), 8 pages, 5 authors,
2 figures (drawn in LaTeX with TikZ/pgfplots, so there are no image files), 7 tables, 34 references.

- `Silence_Is_Not_Violation.pdf`: the compiled paper (built locally with Tectonic).
- `overleaf_upload.zip`: `main.tex` + `references.bib`, ready to upload to Overleaf.

## Edit or recompile on Overleaf

1. Go to <https://www.overleaf.com> and sign in (free).
2. **New Project → Upload Project**, and upload `overleaf_upload.zip`.
3. Overleaf compiles it with pdfLaTeX; `IEEEtran`, TikZ and pgfplots are all built in.
4. **Download PDF** when done.

Red text in the PDF marks something still to fill in.

## Before submitting — checklist

- [x] Author name and email
- [x] Authors: all five, with department, institute and email.
- [x] References: every arXiv entry checked against arXiv (title and authors), 2026-10-27.
- [x] Repository URL (`saurabh-1702/PactScan-AI`, branch `research/silence-not-violation`).
      **The repository is private**: make it public on GitHub (Settings → General → Danger Zone →
      Change visibility), or reviewers won't be able to open the link.
- [ ] Second annotator (optional, recommended): see `research/annotation/README.md`. When it's
      done, put the kappa in the "Labels" paragraph of Threats to Validity.
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
