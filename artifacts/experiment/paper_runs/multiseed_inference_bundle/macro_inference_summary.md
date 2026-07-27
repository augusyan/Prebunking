# multiseed_inference_bundle

## Condition Summary
| Condition | n | Seeds | IR mean | IR t-CI | IR bootstrap 95% | RR mean | RR t-CI | RR bootstrap 95% |
| --- | ---: | --- | ---: | ---: | --- | ---: | ---: | --- |
| No Defense | 5 | 42, 52, 62, 72, 82 | 10.36 | ± 2.50 | [8.80, 11.78] | 35.29 | ± 3.58 | [33.11, 37.56] |
| Debunking | 5 | 42, 52, 62, 72, 82 | 7.51 | ± 1.29 | [6.71, 8.31] | 34.22 | ± 2.52 | [32.71, 35.82] |
| Prebunking | 5 | 42, 52, 62, 72, 82 | 4.58 | ± 1.27 | [3.82, 5.33] | 39.02 | ± 4.02 | [36.62, 41.42] |
| Debunking t=5 50% post coverage | 5 | 42, 52, 62, 72, 82 | 7.51 | ± 1.29 | [6.71, 8.31] | 34.22 | ± 2.52 | [32.71, 35.82] |
| Debunking t=3 100% post coverage | 5 | 42, 52, 62, 72, 82 | 7.02 | ± 1.78 | [5.91, 8.13] | 35.60 | ± 1.67 | [34.40, 36.53] |

## Paired Deltas
| Comparison | n | Metric | Delta mean | t-CI | Bootstrap 95% | Cohen dz | Exact sign-flip p |
| --- | ---: | --- | ---: | ---: | --- | ---: | ---: |
| Debunking vs No Defense | 5 | IR | -2.84 | ± 2.60 | [-4.44, -1.24] | -1.36 | 0.1250 |
| Debunking vs No Defense | 5 | RR | -1.07 | ± 1.33 | [-1.91, -0.22] | -1.00 | 0.1875 |
| Prebunking vs No Defense | 5 | IR | -5.78 | ± 1.89 | [-7.11, -4.76] | -3.79 | 0.0625 |
| Prebunking vs No Defense | 5 | RR | +3.73 | ± 5.60 | [0.40, 7.42] | +0.83 | 0.1875 |
| Prebunking vs Debunking | 5 | IR | -2.93 | ± 1.64 | [-3.87, -1.82] | -2.22 | 0.0625 |
| Prebunking vs Debunking | 5 | RR | +4.80 | ± 5.11 | [2.04, 8.13] | +1.17 | 0.0625 |
| Debunking t=3 100% post coverage vs Debunking t=5 50% post coverage | 5 | IR | -0.49 | ± 1.69 | [-1.69, 0.53] | -0.36 | 0.5625 |
| Debunking t=3 100% post coverage vs Debunking t=5 50% post coverage | 5 | RR | +1.38 | ± 2.95 | [-0.49, 3.20] | +0.58 | 0.3125 |
| Prebunking vs Debunking t=3 100% post coverage | 5 | IR | -2.44 | ± 2.37 | [-4.04, -1.07] | -1.28 | 0.0625 |
| Prebunking vs Debunking t=3 100% post coverage | 5 | RR | +3.42 | ± 4.18 | [0.93, 6.22] | +1.02 | 0.1250 |

## Notes
- Condition summaries replace the old normal-approximation CI with Student-t intervals and bootstrap percentile intervals.
- Paired comparisons are computed on the shared seed set and include Cohen's dz plus exact two-sided sign-flip p-values.
