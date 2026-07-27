# debunking_fairness_multiseed

## Condition Summary
| Condition | n | Seeds | IR % | RR % | Agree % | Disagree % | Peak Infection | Peak Resistance |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| No Defense | 5 | 42, 52, 62, 72, 82 | 10.36 ± 2.02 (t-CI ± 2.50) | 35.29 ± 2.88 (t-CI ± 3.58) | 8.84 ± 2.48 (t-CI ± 3.08) | 91.16 ± 2.48 (t-CI ± 3.08) | 105.80 ± 25.43 (t-CI ± 31.57) | 540.80 ± 65.97 (t-CI ± 81.90) |
| Debunking t=5 50% post coverage | 5 | 42, 52, 62, 72, 82 | 7.51 ± 1.04 (t-CI ± 1.29) | 34.22 ± 2.03 (t-CI ± 2.52) | 9.89 ± 2.67 (t-CI ± 3.31) | 90.11 ± 2.67 (t-CI ± 3.31) | 102.20 ± 12.13 (t-CI ± 15.06) | 535.40 ± 50.45 (t-CI ± 62.63) |
| Prebunking Full Coverage | 5 | 42, 52, 62, 72, 82 | 4.58 ± 1.03 (t-CI ± 1.27) | 39.02 ± 3.24 (t-CI ± 4.02) | 3.10 ± 1.36 (t-CI ± 1.69) | 96.90 ± 1.36 (t-CI ± 1.69) | 42.20 ± 14.24 (t-CI ± 17.68) | 629.40 ± 63.12 (t-CI ± 78.36) |
| Debunking t=3 100% post coverage | 5 | 42, 52, 62, 72, 82 | 7.02 ± 1.44 (t-CI ± 1.78) | 35.60 ± 1.35 (t-CI ± 1.67) | 9.32 ± 2.42 (t-CI ± 3.01) | 90.68 ± 2.42 (t-CI ± 3.01) | 104.00 ± 24.20 (t-CI ± 30.04) | 610.40 ± 40.53 (t-CI ± 50.31) |

## Paired Deltas
| Comparison | n | IR Δ | RR Δ |
| --- | ---: | ---: | ---: |
| Debunking t=3 100% post coverage vs Debunking t=5 50% post coverage | 5 | -0.49 ± 1.36 (t-CI ± 1.69; dz=-0.36) | +1.38 ± 2.38 (t-CI ± 2.95; dz=+0.58) |
| Debunking t=3 100% post coverage vs Prebunking Full Coverage | 5 | +2.44 ± 1.91 (t-CI ± 2.37; dz=+1.28) | -3.42 ± 3.37 (t-CI ± 4.18; dz=-1.02) |

## Notes
- Summary cells report mean ± sample std with Student-t 95% confidence interval half-widths.
- Paired deltas reuse the shared seed set between each comparison pair and report Cohen's dz over seed-level differences.
- `post coverage` means the share of bad-actor posts that receive the reactive debunking intervention once the trigger timestep is reached.
