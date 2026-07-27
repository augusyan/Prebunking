# main_500_selectivity_multiseed

## Raw Seed Rows

| Seed | Condition | Malicious IR | Benign Support | Benign Disagreement | Benign Root Posts |
| --- | --- | ---: | ---: | ---: | ---: |
| 42 | Debunking | 6.67 | 40.22 | 18.22 | 463 |
| 42 | No Defense | 9.78 | 36.44 | 21.78 | 460 |
| 42 | Prebunking | 4.22 | 32.67 | 23.11 | 468 |
| 52 | Debunking | 6.44 | 34.44 | 15.11 | 478 |
| 52 | No Defense | 11.56 | 41.56 | 20.00 | 462 |
| 52 | Prebunking | 5.56 | 28.89 | 30.44 | 458 |
| 62 | Debunking | 8.89 | 40.67 | 18.44 | 465 |
| 62 | No Defense | 10.44 | 38.00 | 20.67 | 464 |
| 62 | Prebunking | 5.56 | 33.56 | 23.78 | 473 |
| 72 | Debunking | 7.33 | 39.56 | 17.33 | 465 |
| 72 | No Defense | 7.33 | 40.00 | 21.33 | 472 |
| 72 | Prebunking | 3.11 | 29.11 | 26.44 | 464 |
| 82 | Debunking | 8.22 | 34.00 | 19.78 | 463 |
| 82 | No Defense | 12.67 | 31.33 | 17.56 | 454 |
| 82 | Prebunking | 4.44 | 30.22 | 26.22 | 468 |

## Condition Summary

| Condition | n | Malicious IR | Benign Support | Benign Disagreement |
| --- | ---: | ---: | ---: | ---: |
| No Defense | 5 | 10.36 ± 2.02 | 37.47 ± 3.94 | 20.27 ± 1.66 |
| Prebunking | 5 | 4.58 ± 1.03 | 30.89 ± 2.11 | 26.00 ± 2.88 |
| Debunking | 5 | 7.51 ± 1.04 | 37.78 ± 3.27 | 17.78 ± 1.73 |

## Paired Deltas vs No Defense

### Prebunking vs No Defense
- Shared seeds: 42, 52, 62, 72, 82
- Malicious IR delta: -5.78 ± 1.34
- Benign support delta: -6.58 ± 4.34
- Benign disagreement delta: +5.73 ± 3.32

### Debunking vs No Defense
- Shared seeds: 42, 52, 62, 72, 82
- Malicious IR delta: -2.84 ± 1.83
- Benign support delta: +0.31 ± 3.89
- Benign disagreement delta: -2.49 ± 2.46

## Notes
- Benign support counts distinct benign users who liked, reposted, or agreed with benign root posts authored by benign users in the same run.
- Benign disagreement counts distinct benign users who disliked or publicly disagreed with those benign root posts.
- This remains an in-simulator benign-flow proxy rather than a matched verified-news benchmark.
