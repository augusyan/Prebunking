# ablation_selectivity_probe

## Raw Seed Rows

| Seed | Condition | Malicious IR | Benign Support | Benign Disagreement | Benign Root Posts |
| --- | --- | ---: | ---: | ---: | ---: |
| 42 | Cautious Role Full | 1.78 | 28.67 | 25.56 | 461 |
| 42 | Message Exposure Full | 6.67 | 32.44 | 18.89 | 459 |
| 42 | No Defense | 9.78 | 36.44 | 21.78 | 460 |
| 42 | Prebunking | 4.22 | 32.67 | 23.11 | 468 |
| 42 | Role Rewrite Full | 2.67 | 31.33 | 21.33 | 460 |
| 52 | Cautious Role Full | 0.67 | 26.67 | 20.67 | 465 |
| 52 | Message Exposure Full | 4.44 | 33.56 | 25.11 | 459 |
| 52 | No Defense | 11.56 | 41.56 | 20.00 | 462 |
| 52 | Prebunking | 5.56 | 28.89 | 30.44 | 458 |
| 52 | Role Rewrite Full | 3.78 | 26.22 | 25.78 | 468 |

## Condition Summary

| Condition | n | Malicious IR | Benign Support | Benign Disagreement |
| --- | ---: | ---: | ---: | ---: |
| No Defense | 2 | 10.67 ± 1.26 | 39.00 ± 3.61 | 20.89 ± 1.26 |
| Prebunking | 2 | 4.89 ± 0.94 | 30.78 ± 2.67 | 26.78 ± 5.19 |
| Role Rewrite Full | 2 | 3.22 ± 0.79 | 28.78 ± 3.61 | 23.56 ± 3.14 |
| Cautious Role Full | 2 | 1.22 ± 0.79 | 27.67 ± 1.41 | 23.11 ± 3.46 |
| Message Exposure Full | 2 | 5.56 ± 1.57 | 33.00 ± 0.79 | 22.00 ± 4.40 |

## Paired Deltas vs No Defense

### Prebunking vs No Defense
- Shared seeds: 42, 52
- Malicious IR delta: -5.78 ± 0.44
- Benign support delta: -8.22 ± 8.71
- Benign disagreement delta: +5.89 ± 8.93

### Role Rewrite Full vs No Defense
- Shared seeds: 42, 52
- Malicious IR delta: -7.44 ± 0.65
- Benign support delta: -10.22 ± 10.02
- Benign disagreement delta: +2.67 ± 6.10

### Cautious Role Full vs No Defense
- Shared seeds: 42, 52
- Malicious IR delta: -9.44 ± 2.83
- Benign support delta: -11.33 ± 6.97
- Benign disagreement delta: +2.22 ± 3.05

### Message Exposure Full vs No Defense
- Shared seeds: 42, 52
- Malicious IR delta: -5.11 ± 3.92
- Benign support delta: -6.00 ± 3.92
- Benign disagreement delta: +1.11 ± 7.84

## Notes
- Benign support counts distinct benign users who liked, reposted, or agreed with benign root posts authored by benign users in the same run.
- Benign disagreement counts distinct benign users who disliked or publicly disagreed with those benign root posts.
- This remains an in-simulator benign-flow proxy rather than a matched verified-news benchmark.
