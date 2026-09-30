# Sanity check

| severity | check | evidence |
|---|---|---|
| INFO | model identity isolation | gpt-5.6-sol: foreign model IDs in metadata=[] |
| INFO | artifact presence | gpt-5.6-sol/eval5: 1 summary artifact(s) |
| INFO | artifact presence | gpt-5.6-sol/eval6_full: 1 summary artifact(s) |
| INFO | artifact presence | gpt-5.6-sol/eval6_strict: 1 summary artifact(s) |
| INFO | artifact presence | gpt-5.6-sol/eval7: 1 summary artifact(s) |
| INFO | artifact presence | gpt-5.6-sol/eval8_fixed: 1 summary artifact(s) |
| INFO | artifact presence | gpt-5.6-sol/eval8_tertile: 1 summary artifact(s) |
| INFO | artifact presence | gpt-5.6-sol/eval9: 1 summary artifact(s) |
| INFO | artifact presence | gpt-5.6-sol/eval10: 1 summary artifact(s) |
| INFO | model identity isolation | claude-fable-5: foreign model IDs in metadata=[] |
| INFO | artifact presence | claude-fable-5/eval5: 1 summary artifact(s) |
| INFO | artifact presence | claude-fable-5/eval6_full: 1 summary artifact(s) |
| INFO | artifact presence | claude-fable-5/eval6_strict: 1 summary artifact(s) |
| WARNING | artifact presence | claude-fable-5/eval7: 0 summary artifact(s) |
| INFO | artifact presence | claude-fable-5/eval8_fixed: 1 summary artifact(s) |
| INFO | artifact presence | claude-fable-5/eval8_tertile: 1 summary artifact(s) |
| INFO | artifact presence | claude-fable-5/eval9: 2 summary artifact(s) |
| INFO | artifact presence | claude-fable-5/eval10: 1 summary artifact(s) |
| INFO | Eval6 Strict common completed runs | gpt-5.6-sol: common=['1', '2', '3', '4', '5'] |
| INFO | Eval6 Strict fixed-contract fields | gpt-5.6-sol: missing=[] |
| INFO | Eval6 Strict common completed runs | claude-fable-5: common=['1', '2', '3', '4', '5'] |
| INFO | Eval6 Strict fixed-contract fields | claude-fable-5: missing=[] |
| INFO | Eval7 holdout isolation | gpt-5.6-sol: role=validation, validation=15--154, test=155--220 |
| WARNING | Eval7 completeness/leakage | claude-fable-5: formal Evaluation 7 summary absent |
| INFO | Eval6 Full mean/SD recomputation | gpt-5.6-sol: mismatches=[] |
| INFO | Eval6 Strict mean/SD recomputation | gpt-5.6-sol: mismatches=[] |
| INFO | Eval10 mean/SD recomputation | gpt-5.6-sol: mismatches=[] |
| INFO | Eval6 Full mean/SD recomputation | claude-fable-5: mismatches=[] |
| INFO | Eval6 Strict mean/SD recomputation | claude-fable-5: mismatches=[] |
| INFO | Eval10 mean/SD recomputation | claude-fable-5: mismatches=[] |
| INFO | metric range | eval6_full: invalid=[] |
| INFO | metric range | eval6_strict: invalid=[] |
| INFO | metric range | eval7: invalid=[] |
| INFO | metric range | eval8: invalid=[] |
| INFO | metric range | eval9: invalid=[] |
| INFO | metric range | eval10_runs: invalid=[] |
| INFO | Eval9 fragmentation N/A retention | gpt-5.6-sol: statuses=['evaluated'] |
| INFO | Eval9 duplicate condition/seed/run records | gpt-5.6-sol: duplicates=[] |
| INFO | Eval9 fragmentation N/A retention | claude-fable-5: statuses=['evaluated'] |
| INFO | Eval9 duplicate condition/seed/run records | claude-fable-5: duplicates=[] |
| WARNING | figures | No matplotlib-capable local runtime was available; source CSV tables were written, no API call was attempted. |
