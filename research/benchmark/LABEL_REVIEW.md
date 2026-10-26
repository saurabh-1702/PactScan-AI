# Label review — benchmark v1.0

Every correct answer in the benchmark was reviewed against the exact wording of
the 13 requirements (`backend/app/agents/detect/seed_data.py`) before any model
was run. This file records what was checked, what changed, and the
assumptions a reader of the paper should know about. It belongs in the
paper's "Benchmark" section.

## What was checked

For each of the 116 distinct clause texts in `out/review_sheet.csv` (the base
clauses of all six companies, every rewritten "breaking" clause, the nine
removed topics and the trap amendments):

1. Does the clause, as written, really satisfy / break / leave out the
   requirements of its own topic?
2. Could the clause **also** reasonably be read as affecting a requirement of a
   **different** topic? (The benchmark assumes a change touches only its own
   topic; where that is doubtful the pair is excluded — see below.)
3. For trap contracts: does the amendment really override the clause in the
   stated direction (hide a violation / cure one)?
4. For removed topics: is the topic mandatory for **this** contract?

## Changes made in the review

| # | Problem found | Fix |
|---|---|---|
| 1 | The "breaks processing details" clause let the vendor use data *for any purpose* — that also arguably breaks the lawful-purpose rules (DPDP s4, GDPR Art 6), which were labelled NONE | Rewritten to break the rule only by **leaving out** purpose, data categories, Data Principals and retention |
| 2 | The style-0 "breaks children's data" clause said "without any additional consent" — a general-consent statement | Narrowed to "without verifiable parental or guardian consent" |
| 3 | The style-0 "breaks deletion" clause kept data "for its internal analytics purposes" — own-purpose use, again touching s4 / Art 6 | Purpose removed: "may retain Personal Data indefinitely and need not return or delete it" |
| 4 | Several breaking clauses could defensibly be read as also breaking another topic's rule (list below) | Those pairs are labelled **EXCLUDE** and left out of every score |
| 5 | The payroll DPA (b5, employees' data) was labelled GAP when it says nothing about children — but no children's data is processed there, so the children's-data rules don't bind | Base b5 marked `children: not_applicable`; its "children removed" contract is now NONE |

Excluded pairs (`spec.EXCLUDED`, 42 pairs in total):

| Contract variant | Excluded requirement(s) | Why it is ambiguous |
|---|---|---|
| breaks children's data | DPDP s4, GDPR Art 6 | Processing a child's data without parental consent arguably also lacks a valid consent ground |
| breaks lawful basis | Playbook: DPA fields | Own-purpose use contradicts the purpose stated in the processing details |
| breaks deletion; trap hiding a deletion violation | Playbook: DPA fields | Keeping data after termination contradicts the stated retention period |
| breaks sub-processors; breaks cross-border | DPDP s8 | Unvetted sub-processors / unrestricted transfers arguably undermine "appropriate technical and organisational measures" |

Result: 138 contracts, **1,752 graded pairs** (1,599 NONE, 96 VIOLATES, 57 GAP), 42 excluded.

## Assumptions to state in the paper

- **Two topics are not mandatory.** A contract silent on the **liability cap**
  breaks nothing (the rule forbids a cap that is too low; no cap means
  unlimited liability). A contract silent on the **lawful basis** breaks
  nothing (having a lawful ground is the Data Fiduciary's own statutory duty,
  not a term the processor contract must restate).
- **The playbook is the company's standard.** Sub-processor approval,
  storage-location and audit clauses are treated as mandatory because the
  company's playbook requires them, not because the DPDP Act names each one.
- **GDPR is applied as a second standard, not by territorial scope.** The
  companies are Indian; GDPR rules are checked as the project's "second
  jurisdiction" demonstration, as everywhere else in PactScan.
- **DPDP s8 is read as satisfied by a security-and-breach-notice clause.** Its
  data-accuracy element is the Data Fiduciary's own duty and is not expected
  in a DPA.
- **A parental-consent clause satisfies GDPR Art 8 without naming an age.**
  Art 8 requires parental authorisation below 16 (or a Member State's lower
  age); a clause requiring verifiable parental consent for *every* child is
  stricter, so it complies. (In the live smoke test the model called such a
  clause NEUTRAL "because it does not specify the age threshold" — an example
  of the residual errors the paper analyses.)
- **Requirement-level, not legal-advice-level.** Each label says whether the
  contract text meets the stated requirement text; it is not a legal opinion.

## Who reviewed it, and what would make it stronger

The labels were written from the specification and then reviewed clause by
clause against the requirement texts by the build assistant, at the
author's request. For the paper, a **second, independent human labeller** on a
random sample (e.g. 100 pairs, drawn with `random.seed(7)`) would let you
report inter-annotator agreement (Cohen's kappa) — a standard number that
reviewers look for in a benchmark paper.
