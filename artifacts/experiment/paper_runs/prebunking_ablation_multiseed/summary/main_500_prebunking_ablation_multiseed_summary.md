# main_500_prebunking_ablation_multiseed

| Case | n | IR % | RR % | Treated IR % | Untreated IR % | Treated RR % | Untreated RR % |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Role Rewrite Full | 5 | 3.38 ± 0.55 (CI ± 0.49) | 41.82 ± 2.11 (CI ± 1.85) | 3.38 ± 0.55 (CI ± 0.49) | 0.00 ± 0.00 (CI ± 0.00) | 41.82 ± 2.11 (CI ± 1.85) | 0.00 ± 0.00 (CI ± 0.00) |
| Message Exposure Full | 5 | 7.16 ± 1.68 (CI ± 1.47) | 36.98 ± 1.59 (CI ± 1.40) | 7.16 ± 1.68 (CI ± 1.47) | 0.00 ± 0.00 (CI ± 0.00) | 36.98 ± 1.59 (CI ± 1.40) | 0.00 ± 0.00 (CI ± 0.00) |
| Cautious Role Full | 5 | 1.42 ± 0.46 (CI ± 0.40) | 40.00 ± 3.21 (CI ± 2.82) | 1.42 ± 0.46 (CI ± 0.40) | 0.00 ± 0.00 (CI ± 0.00) | 40.00 ± 3.21 (CI ± 2.82) | 0.00 ± 0.00 (CI ± 0.00) |
| Message Exposure Cov10 | 5 | 8.76 ± 0.96 (CI ± 0.84) | 37.24 ± 3.52 (CI ± 3.08) | 5.78 ± 2.98 (CI ± 2.61) | 9.09 ± 0.96 (CI ± 0.84) | 37.33 ± 11.70 (CI ± 10.25) | 37.23 ± 3.45 (CI ± 3.02) |
| Message Exposure Cov25 | 5 | 9.64 ± 1.25 (CI ± 1.10) | 37.11 ± 0.90 (CI ± 0.79) | 8.21 ± 2.99 (CI ± 2.62) | 10.12 ± 1.85 (CI ± 1.62) | 38.21 ± 2.04 (CI ± 1.78) | 36.75 ± 0.82 (CI ± 0.72) |
| Message Exposure Cov50 | 5 | 8.58 ± 0.95 (CI ± 0.83) | 36.27 ± 1.60 (CI ± 1.40) | 7.11 ± 1.37 (CI ± 1.20) | 10.04 ± 0.67 (CI ± 0.59) | 37.33 ± 3.06 (CI ± 2.68) | 35.20 ± 3.13 (CI ± 2.75) |
| Message Exposure Cov75 | 5 | 7.87 ± 1.65 (CI ± 1.45) | 34.89 ± 0.98 (CI ± 0.86) | 7.57 ± 1.62 (CI ± 1.42) | 8.75 ± 2.31 (CI ± 2.03) | 35.56 ± 1.21 (CI ± 1.06) | 32.86 ± 2.71 (CI ± 2.37) |

## Notes
- Each cell reports mean ± sample std with a normal-approximation 95% confidence interval half-width.
- Treated/untreated metrics are computed from the agent CSV: role-rewritten benign agents and benign agents marked with the prebunking exposure tag count as treated.
