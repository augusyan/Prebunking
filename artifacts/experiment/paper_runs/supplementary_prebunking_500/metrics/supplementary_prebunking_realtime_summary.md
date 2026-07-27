# supplementary_prebunking_realtime

## Headline
- Earlier prebunking stays consistently lower on the infection proxy curve: across the shared observed window, `t1 < t3 < t6`.
- At `+1` step after inoculation, the infection proxy is t1=3.00, t3=28.00, t6=74.00.
- Protection is measured against the no-defense infection proxy at the same absolute simulation step.

## Absolute Infection Proxy
| Simulation Step | No Defense | t1 | t3 | t6 |
| --- | ---: | ---: | ---: | ---: |
| 1 | 0.00 | 0.00 | 0.00 | 0.00 |
| 2 | 17.00 | 3.00 | 16.00 | 20.00 |
| 3 | 31.00 | 7.00 | 22.00 | 36.00 |
| 4 | 50.00 | 13.00 | 28.00 | 47.00 |
| 5 | 68.00 | 17.00 | 38.00 | 55.00 |
| 6 | 81.00 | 20.00 | 42.00 | 68.00 |
| 7 | 90.00 | 22.00 | 49.00 | 74.00 |
| 8 | 98.00 | 25.00 | 52.00 | 83.00 |
| 9 | 113.00 | 27.00 | 53.00 | 92.00 |
| 10 | 115.00 | 28.00 | 56.00 | 100.00 |

## Relative Protection Vs No Defense
| Elapsed Steps After Inoculation | t1 | t3 | t6 |
| --- | ---: | ---: | ---: |
| 0 |  | 29.03 | 16.05 |
| 1 | 82.35 | 44.00 | 17.78 |
| 2 | 77.42 | 44.12 | 15.31 |
| 3 | 74.00 | 48.15 | 18.58 |
| 4 | 75.00 | 45.56 | 13.04 |
| 5 | 75.31 | 46.94 |  |
| 6 | 75.56 | 53.10 |  |
| 7 | 74.49 | 51.30 |  |
| 8 | 76.11 |  |  |
| 9 | 75.65 |  |  |

## Notes
- `Simulation Step` is the shared absolute simulation timeline.
- `Elapsed Steps After Inoculation` aligns each prebunking run by its own injection step.
- Infection proxy = good likes + good reposts + agree comments on bad-user-authored posts.
- Resistance proxy = disagree comments on bad-user-authored posts.
