# variant_selectivity_seed42

## Raw Seed Rows

| Seed | Condition | Malicious IR | Benign Support | Benign Disagreement | Benign Root Posts |
| --- | --- | ---: | ---: | ---: | ---: |
| 42 | No Defense | 9.78 | 36.44 | 21.78 | 460 |
| 42 | Prebunking | 4.22 | 32.67 | 23.11 | 468 |
| 42 | Supp Prebunking Emotional | 4.67 | 29.33 | 23.56 | 481 |
| 42 | Supp Prebunking Fact | 4.44 | 30.67 | 30.67 | 458 |
| 42 | Supp Prebunking Logic | 3.33 | 29.78 | 25.33 | 463 |
| 42 | Supp Prebunking Random Feed | 9.78 | 20.22 | 28.67 | 450 |
| 42 | Supp Prebunking T1 500 | 2.44 | 31.56 | 28.89 | 460 |
| 42 | Supp Prebunking T3 | 5.11 | 30.89 | 25.78 | 460 |
| 42 | Supp Prebunking T6 | 11.33 | 32.67 | 23.56 | 462 |
| 42 | Supp Prebunking Technical | 3.11 | 26.44 | 29.78 | 464 |

## Condition Summary

| Condition | n | Malicious IR | Benign Support | Benign Disagreement |
| --- | ---: | ---: | ---: | ---: |
| No Defense | 1 | 9.78 ± 0.00 | 36.44 ± 0.00 | 21.78 ± 0.00 |
| Prebunking | 1 | 4.22 ± 0.00 | 32.67 ± 0.00 | 23.11 ± 0.00 |
| Supp Prebunking T1 500 | 1 | 2.44 ± 0.00 | 31.56 ± 0.00 | 28.89 ± 0.00 |
| Supp Prebunking T3 | 1 | 5.11 ± 0.00 | 30.89 ± 0.00 | 25.78 ± 0.00 |
| Supp Prebunking T6 | 1 | 11.33 ± 0.00 | 32.67 ± 0.00 | 23.56 ± 0.00 |
| Supp Prebunking Fact | 1 | 4.44 ± 0.00 | 30.67 ± 0.00 | 30.67 ± 0.00 |
| Supp Prebunking Logic | 1 | 3.33 ± 0.00 | 29.78 ± 0.00 | 25.33 ± 0.00 |
| Supp Prebunking Technical | 1 | 3.11 ± 0.00 | 26.44 ± 0.00 | 29.78 ± 0.00 |
| Supp Prebunking Emotional | 1 | 4.67 ± 0.00 | 29.33 ± 0.00 | 23.56 ± 0.00 |
| Supp Prebunking Random Feed | 1 | 9.78 ± 0.00 | 20.22 ± 0.00 | 28.67 ± 0.00 |

## Paired Deltas vs No Defense

### Prebunking vs No Defense
- Shared seeds: 42
- Malicious IR delta: -5.56 ± 0.00
- Benign support delta: -3.78 ± 0.00
- Benign disagreement delta: +1.33 ± 0.00

### Supp Prebunking T1 500 vs No Defense
- Shared seeds: 42
- Malicious IR delta: -7.33 ± 0.00
- Benign support delta: -4.89 ± 0.00
- Benign disagreement delta: +7.11 ± 0.00

### Supp Prebunking T3 vs No Defense
- Shared seeds: 42
- Malicious IR delta: -4.67 ± 0.00
- Benign support delta: -5.56 ± 0.00
- Benign disagreement delta: +4.00 ± 0.00

### Supp Prebunking T6 vs No Defense
- Shared seeds: 42
- Malicious IR delta: +1.56 ± 0.00
- Benign support delta: -3.78 ± 0.00
- Benign disagreement delta: +1.78 ± 0.00

### Supp Prebunking Fact vs No Defense
- Shared seeds: 42
- Malicious IR delta: -5.33 ± 0.00
- Benign support delta: -5.78 ± 0.00
- Benign disagreement delta: +8.89 ± 0.00

### Supp Prebunking Logic vs No Defense
- Shared seeds: 42
- Malicious IR delta: -6.44 ± 0.00
- Benign support delta: -6.67 ± 0.00
- Benign disagreement delta: +3.56 ± 0.00

### Supp Prebunking Technical vs No Defense
- Shared seeds: 42
- Malicious IR delta: -6.67 ± 0.00
- Benign support delta: -10.00 ± 0.00
- Benign disagreement delta: +8.00 ± 0.00

### Supp Prebunking Emotional vs No Defense
- Shared seeds: 42
- Malicious IR delta: -5.11 ± 0.00
- Benign support delta: -7.11 ± 0.00
- Benign disagreement delta: +1.78 ± 0.00

### Supp Prebunking Random Feed vs No Defense
- Shared seeds: 42
- Malicious IR delta: +0.00 ± 0.00
- Benign support delta: -16.22 ± 0.00
- Benign disagreement delta: +6.89 ± 0.00

## Notes
- Benign support counts distinct benign users who liked, reposted, or agreed with benign root posts authored by benign users in the same run.
- Benign disagreement counts distinct benign users who disliked or publicly disagreed with those benign root posts.
- This remains an in-simulator benign-flow proxy rather than a matched verified-news benchmark.
