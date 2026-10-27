### Benchmark

| Item | Count |
|---|---|
| Base contracts | 6 |
| Contracts | 138 |
| Requirements per contract | 13 |
| Graded (contract, requirement) pairs | 1752 |
| ... correct answer NONE | 1599 |
| ... correct answer VIOLATES | 96 |
| ... correct answer GAP | 57 |
| ... excluded as ambiguous | 42 |
| Trap contracts (amendment hides a violation / a fix) | 12 / 12 |

### Experiment 1: false violations and missed gaps per set-up (%, 95% CI)

| Set-up | False violation rate | Missed gap rate | Violation recall | F1 | Findings on a clean contract |
|---|---|---|---|---|---|
| A: Original (v1) | 60.9 [59.9, 61.8] | 52.6 [38.6, 69.8] | 100.0 [100.0, 100.0] | 19.7 [16.6, 22.9] | 21.7 |
| B: + conservative prompt | 59.9 [58.9, 60.9] | 52.6 [38.6, 69.8] | 100.0 [100.0, 100.0] | 19.9 [16.8, 23.2] | 21.8 |
| C: + subject routing | 51.7 [50.4, 52.8] | 63.2 [46.4, 81.2] | 99.0 [96.6, 100.0] | 21.2 [17.6, 24.9] | 12.5 |
| D: + contract-level findings (full) | 19.6 [17.4, 21.7] | 0.0 [0.0, 0.0] | 99.0 [96.6, 100.0] | 49.2 [44.6, 53.6] | 2.5 |
| D_noET: full, without override-aware reading | 20.3 [18.1, 22.5] | 0.0 [0.0, 0.0] | 86.5 [78.6, 92.9] | 45.3 [40.4, 50.0] | 2.5 |
| P: PactScan as deployed | 14.1 [12.1, 16.1] | 80.7 [67.7, 95.2] | 77.1 [66.3, 87.1] | 36.6 [29.5, 43.6] | 1.8 |

### Experiment 1: where false alarms come from (%)

| Set-up | Clause present & compliant | Topic absent, acceptable | Amendment cures clause | Hidden violation caught |
|---|---|---|---|---|
| A | 60.7 | 100.0 | 33.3 | 100.0 |
| B | 59.8 | 90.5 | 33.3 | 100.0 |
| C | 51.7 | 66.7 | 33.3 | 94.4 |
| D | 19.4 | 23.8 | 33.3 | 94.4 |
| D_noET | 19.4 | 23.8 | 100.0 | 27.8 |
| P | 13.9 | 14.3 | 33.3 | 77.8 |

### Paired comparisons (exact McNemar test)

| Comparison | Only first right | Only second right | p-value |
|---|---|---|---|
| A vs D | 1 | 691 | 6.7e-206 |
| C vs D | 0 | 549 | 1.1e-165 |
| A vs B | 6 | 22 | 0.0037 |
| B vs C | 28 | 153 | 4.7e-22 |
| D_noET vs D | 1 | 25 | 8e-07 |
| P vs D | 125 | 105 | 0.21 |

### Stability across models (main, m_gpt20b, m_qwen)

| Set-up | Pairs answered identically | Fleiss' kappa |
|---|---|---|
| A | 99.3 | 0.99 |
| C | 91.0 | 0.88 |
| D | 82.0 | 0.70 |

### Experiment 2: before (A) vs after (D) on each model

| Run | Set-up | False violation rate | Missed gap rate | F1 |
|---|---|---|---|---|
| main | A | 60.9 | 52.6 | 19.7 |
| main | D | 19.6 | 0.0 | 49.2 |
| m_gpt20b | A | 60.8 | 52.6 | 19.7 |
| m_gpt20b | D | 27.1 | 0.0 | 41.2 |
| m_qwen | A | 61.2 | 52.6 | 19.5 |
| m_qwen | D | 14.1 | 0.0 | 54.5 |

### Stability across repeats (m_gpt20b, rep20b_1, rep20b_2)

| Set-up | Pairs answered identically | Fleiss' kappa |
|---|---|---|
| A | 99.7 | 1.00 |
| C | 92.0 | 0.89 |
| D | 86.3 | 0.79 |

### Experiment 4: re-checking contracts after a regulation update (law_main; retrieval recall on violations 100.0)

| Rule | False violation rate | Missed gap rate | Violation recall | F1 | Findings per check |
|---|---|---|---|---|---|
| every_non_entails | 100.0 | 0.0 | 100.0 | 50.4 | 12.15 |
| contradicts_only | 31.1 | 96.2 | 100.0 | 21.4 | 0.31 |
| contract_level | 31.1 | 0.0 | 100.0 | 76.5 | 0.58 |
