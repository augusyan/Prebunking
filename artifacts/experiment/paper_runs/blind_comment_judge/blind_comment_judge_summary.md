# blind_comment_judge

## Overall Agreement
- n: 225
- Self vs judge agree exact: 92.00%
- Self vs judge emotion exact: 51.56%
- Both exact: 46.67%

## By Condition
| Condition | n | Agree exact | Emotion exact | Both exact | Self disagree | Judge disagree | Judge skepticism | Judge vigilance | Judge anger |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| No Defense | 75 | 96.00% | 48.00% | 45.33% | 85.33% | 89.33% | 40.00% | 41.33% | 16.00% |
| Debunking | 75 | 85.33% | 53.33% | 45.33% | 84.00% | 80.00% | 21.33% | 48.00% | 25.33% |
| Prebunking | 75 | 94.67% | 53.33% | 49.33% | 98.67% | 96.00% | 40.00% | 40.00% | 20.00% |

## Notes
- The judge never receives condition names, self labels, or the agent-written reasoning field.
- Agreement compares the original self labels against blind judge labels on the same sampled comment set.
- Emotion labels use the paper's closed seven-class vocabulary.
