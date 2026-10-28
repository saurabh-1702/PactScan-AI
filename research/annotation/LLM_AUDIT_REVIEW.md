# AI label audit — hand review of the disagreements

This is **not** a second human annotator. A model used in no experiment
(`gemini-3.5-flash-lite`, temperature 0, 2026-10-28) labelled the blind sheet
(`out/sheet.csv`) from the same rules a human annotator gets
(`llm_audit.py`, answers in `out/llm_sheet_lite.csv`, score in
`out/llm_agreement.json`).

**Result:** 101 / 120 agree (84.2%), Cohen's kappa 0.73. All 60 `NONE` pairs agree.
Every one of the 19 disagreements was checked against the contract text.
**No benchmark label was changed.**

| Kind | Items | Why |
|---|---|---|
| Model error: violation of a non-mandatory rule called NONE "because it is not mandatory" | Q006, Q035, Q068, Q072, Q094, Q109, Q118 | The rule says *silence* on a non-mandatory topic is NONE; these contracts have an explicit breaking clause (e.g. a ₹50,000 liability cap). |
| Model error: violating clause called a gap | Q024 | Clause 5 lets the vendor decide "at its sole discretion" whether to notify a breach — that is a clause, and it breaks the rule. |
| Model error: missing clause accepted | Q092, Q116 | Ed-tech contract processes students under 18 but has no parental-consent or no-tracking clause; a general "lawful ground" warranty is not verifiable parental consent. |
| Model error: missing clause accepted | Q002, Q050 | No security or breach-notice clause at all; the model treated DPDP s8 as purely the Data Fiduciary's duty. |
| Violation vs gap (both see a problem) | Q003, Q020 | Processing details "to be agreed from time to time": the benchmark calls the deferring clause a violation, the model calls it a gap. |
| Labelling convention | Q009, Q018, Q025, Q049, Q081 | Benchmark follows the playbook: every DPA (except payroll) must address children's data, so silence is a gap. The model read the rule as not applying when no children are named. Stated in the paper's Labels paragraph. |

Side check: before its free tier's 20-requests-per-day cap stopped it,
`gemini-3.5-flash` labelled the first 26 items (`out/llm_sheet.csv`):
76.9% agreement, kappa 0.63 (`out/llm_agreement_flash26.json`).
The paper reports the full 120-item run only.
