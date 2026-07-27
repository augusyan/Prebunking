# supplementary_formal_comparison

## Outcome and stance
| Condition | Infection % | Resistance % | Agree % | Disagree % | Peak Infection Step | Peak Infection Value | Peak Resistance Step | Peak Resistance Value |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| supp_prebunking_t1_500 | 2.44 | 42.00 | 2.11 | 97.89 | 10 | 28.00 | 10 | 586.00 |
| supp_prebunking_t3 | 5.11 | 42.00 | 3.26 | 96.74 | 10 | 56.00 | 10 | 733.00 |
| supp_prebunking_t6 | 11.33 | 37.33 | 5.15 | 94.85 | 10 | 100.00 | 10 | 636.00 |
| supp_prebunking_fact | 4.44 | 35.11 | 2.61 | 97.39 | 10 | 41.00 | 10 | 536.00 |
| supp_prebunking_logic | 3.33 | 40.67 | 1.14 | 98.86 | 10 | 25.00 | 10 | 699.00 |
| supp_prebunking_technical | 3.11 | 41.56 | 0.86 | 99.14 | 10 | 24.00 | 10 | 610.00 |
| supp_prebunking_emotional | 4.67 | 37.56 | 2.64 | 97.36 | 10 | 39.00 | 10 | 578.00 |
| supp_prebunking_random_feed | 9.78 | 57.56 | 6.18 | 93.82 | 10 | 94.00 | 10 | 790.00 |
| main_500_prebunking | 3.11 | 42.67 | 2.11 | 97.89 | 10 | 31.00 | 10 | 660.00 |

## Emotion change
| Condition | Skepticism % | Vigilance % | Anger % | Panic % | Fanaticism % | Confusion % | Neutral % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| supp_prebunking_t1_500 | 48.94 | 17.67 | 32.02 | 0.45 | 0.60 | 0.30 | 0.00 |
| supp_prebunking_t3 | 34.38 | 22.14 | 40.68 | 0.93 | 0.93 | 0.70 | 0.12 |
| supp_prebunking_t6 | 37.73 | 17.41 | 41.95 | 1.06 | 1.06 | 0.13 | 0.66 |
| supp_prebunking_fact | 55.95 | 17.78 | 24.63 | 0.00 | 0.16 | 0.49 | 0.98 |
| supp_prebunking_logic | 54.13 | 18.81 | 26.30 | 0.13 | 0.00 | 0.25 | 0.38 |
| supp_prebunking_technical | 54.52 | 20.80 | 23.96 | 0.00 | 0.14 | 0.43 | 0.14 |
| supp_prebunking_emotional | 40.37 | 26.09 | 31.99 | 0.16 | 0.93 | 0.47 | 0.00 |
| supp_prebunking_random_feed | 42.86 | 20.04 | 33.26 | 0.43 | 2.45 | 0.53 | 0.43 |
| main_500_prebunking | 47.17 | 18.71 | 32.54 | 0.92 | 0.26 | 0.26 | 0.13 |

## Notes
- Infection: benign users who liked or reposted bad-user posts.
- Resistance: benign users who disliked or left disagree comments on bad-user posts.
- Emotion percentages are computed over benign comments on bad-user posts.
- The paper-facing summary uses a 7-dimensional emotion view: skepticism, vigilance, anger, panic, fanaticism, confusion, and neutral.
- A single out-of-schema `alarm` token appears once in the raw t=3 aggregation (0.12%) and is treated as an edge case rather than a stable modeled dimension.
