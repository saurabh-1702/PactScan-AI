# Second-annotator check (about 1–1.5 hours)

This measures whether a second person agrees with the benchmark's correct answers.
The result (Cohen's kappa) goes into the paper's Labels paragraph.

**Who:** anyone who has *not* seen the benchmark's answers: a classmate, or your mentor.
Legal training helps but isn't required. Don't show them `benchmark/`, `review_sheet.csv` or
`benchmark/out/contracts/`, because those reveal the answers.

## What to give them

The folder `research/annotation/out/` **without** `key.json`:

- `sheet.csv`: 120 questions (open in Excel)
- `contracts/`: the 83 contracts the questions refer to (`K001.md`, …)

## Instructions for the annotator

Each row asks about **one contract** and **one requirement**. Open the contract named
in the `contract` column, read the requirement, and write one word in `your_label`:

| Label | Meaning |
|---|---|
| `NONE` | Nothing is wrong. Some clause satisfies the requirement, or the requirement doesn't apply to this contract (e.g. children's-data rules for a contract that processes no children's data). |
| `VIOLATES` | A clause goes against the requirement (e.g. allows 7 days to report a breach when 72 hours is required). |
| `GAP` | The requirement is **mandatory** (`mandatory` column = True) and **nothing** in the contract deals with it. |

Rules of thumb:
- A clause that is about something else is **not** a violation. Judge the **whole contract**.
- A later clause that says "notwithstanding…" or "amends clause N" **replaces** what it amends.
  Judge the contract as amended.
- If `mandatory` is False, silence is `NONE`, never `GAP`.
- Unsure? Pick the best answer and write why in `notes`.

## Scoring (you or Claude)

Put the filled sheet back at `research/annotation/out/sheet.csv`, then run:

```bash
python research/annotation/score.py
```

It prints the agreement and Cohen's kappa, lists every disagreement, and writes
`out/agreement.json`. Reading guide: kappa above 0.8 is "almost perfect" agreement,
and 0.6–0.8 is "substantial".

## AI label audit (done, not a human annotator)

`llm_audit.py` gave the same sheet to a model used in no experiment; agreement and the
hand review of every disagreement are in `LLM_AUDIT_REVIEW.md` (84.2%, kappa 0.73,
no label errors found). A human second annotator is still the stronger check.
