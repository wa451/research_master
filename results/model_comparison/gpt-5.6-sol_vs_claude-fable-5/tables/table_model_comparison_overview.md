# table_model_comparison_overview

| evaluation | model | method | F1_mean | F1_sd | FRR_mean | FRR_sd |
|---|---|---|---|---|---|---|
| Eval6 Full | gpt-5.6-sol | direct_log_baseline | 0.644516627163686 | 0.04171776315502466 |  |  |
| Eval6 Full | gpt-5.6-sol | proposed | 0.783960113960114 | 0.07740796315495602 |  |  |
| Eval6 Full | claude-fable-5 | direct_log_baseline | 0.6016666666666667 | 0.03101622846052561 |  |  |
| Eval6 Full | claude-fable-5 | proposed | 0.7704549936933838 | 0.04324561497683995 |  |  |
| Eval6 Strict | gpt-5.6-sol | llm_only_strict | 0.6624060150375939 | 0.0743034860142452 |  |  |
| Eval6 Strict | gpt-5.6-sol | proposed_strict | 0.8638807189542483 | 0.030920105007131087 |  |  |
| Eval6 Strict | claude-fable-5 | llm_only_strict | 0.5859917898193759 | 0.07199930675243835 |  |  |
| Eval6 Strict | claude-fable-5 | proposed_strict | 0.7592060778727445 | 0.054579266643498 |  |  |
| Eval9 | claude-fable-5 | branched_base | 0.062792 | 0.002287 |  |  |
| Eval9 | claude-fable-5 | branched_variable | 0.083629 | 0.031658 |  |  |
| Eval9 | claude-fable-5 | compact_base | 0.000000 | 0.000000 |  |  |
| Eval9 | claude-fable-5 | compact_variable | 0.024281 | 0.038631 |  |  |
| Eval9 | claude-fable-5 | corridor_base | 0.144181 | 0.045568 |  |  |
| Eval9 | claude-fable-5 | corridor_variable | 0.110480 | 0.035498 |  |  |
| Eval9 | claude-fable-5 | branched_base | 0.060657 | 0.001884 |  |  |
| Eval9 | claude-fable-5 | branched_variable | 0.065245 | 0.034958 |  |  |
| Eval9 | claude-fable-5 | compact_base | 0.006536 | 0.019608 |  |  |
| Eval9 | claude-fable-5 | compact_variable | 0.025082 | 0.029788 |  |  |
| Eval9 | claude-fable-5 | corridor_base | 0.085398 | 0.031496 |  |  |
| Eval9 | claude-fable-5 | corridor_variable | 0.063543 | 0.034433 |  |  |
| Eval9 | claude-fable-5 | branched_base | 0.053290 | 0.046163 |  |  |
| Eval9 | claude-fable-5 | branched_variable | 0.013704 | 0.027231 |  |  |
| Eval9 | claude-fable-5 | compact_base | 0.000000 | 0.000000 |  |  |
| Eval9 | claude-fable-5 | compact_variable | 0.024888 | 0.029539 |  |  |
| Eval9 | claude-fable-5 | corridor_base | 0.000000 | 0.000000 |  |  |
| Eval9 | claude-fable-5 | corridor_variable | 0.000000 | 0.000000 |  |  |
| Eval9 | claude-fable-5 | branched_base | 0.000000 | 0.000000 |  |  |
| Eval9 | claude-fable-5 | branched_variable | 0.068571 | 0.035618 |  |  |
| Eval9 | claude-fable-5 | compact_base | 0.000000 | 0.000000 |  |  |
| Eval9 | claude-fable-5 | compact_variable | 0.043643 | 0.036720 |  |  |
| Eval9 | claude-fable-5 | corridor_base | 0.127191 | 0.038203 |  |  |
| Eval9 | claude-fable-5 | corridor_variable | 0.097525 | 0.056720 |  |  |
| Eval9 | claude-fable-5 | branched_base | 0.019058 | 0.028599 |  |  |
| Eval9 | claude-fable-5 | branched_variable | 0.033047 | 0.042031 |  |  |
| Eval9 | claude-fable-5 | compact_base | 0.000000 | 0.000000 |  |  |
| Eval9 | claude-fable-5 | compact_variable | 0.018891 | 0.028363 |  |  |
| Eval9 | claude-fable-5 | corridor_base | 0.098493 | 0.028022 |  |  |
| Eval9 | claude-fable-5 | corridor_variable | 0.099598 | 0.031228 |  |  |
| Eval9 | gpt-5.6-sol | branched_base | 0.041197 | 0.039132 |  |  |
| Eval9 | gpt-5.6-sol | branched_variable | 0.059221 | 0.063103 |  |  |
| Eval9 | gpt-5.6-sol | compact_base | 0.015070 | 0.029910 |  |  |
| Eval9 | gpt-5.6-sol | compact_variable | 0.045824 | 0.034486 |  |  |
| Eval9 | gpt-5.6-sol | corridor_base | 0.133041 | 0.054466 |  |  |
| Eval9 | gpt-5.6-sol | corridor_variable | 0.104054 | 0.060686 |  |  |
| Eval9 | gpt-5.6-sol | branched_base | 0.016167 | 0.032087 |  |  |
| Eval9 | gpt-5.6-sol | branched_variable | 0.064796 | 0.042330 |  |  |
| Eval9 | gpt-5.6-sol | compact_base | 0.045264 | 0.067014 |  |  |
| Eval9 | gpt-5.6-sol | compact_variable | 0.057711 | 0.050655 |  |  |
| Eval9 | gpt-5.6-sol | corridor_base | 0.092036 | 0.031735 |  |  |
| Eval9 | gpt-5.6-sol | corridor_variable | 0.117937 | 0.057539 |  |  |
| Eval9 | gpt-5.6-sol | branched_base | 0.106792 | 0.054240 |  |  |
| Eval9 | gpt-5.6-sol | branched_variable | 0.057390 | 0.060933 |  |  |
| Eval9 | gpt-5.6-sol | compact_base | 0.020425 | 0.030656 |  |  |
| Eval9 | gpt-5.6-sol | compact_variable | 0.051247 | 0.042781 |  |  |
| Eval9 | gpt-5.6-sol | corridor_base | 0.000000 | 0.000000 |  |  |
| Eval9 | gpt-5.6-sol | corridor_variable | 0.000000 | 0.000000 |  |  |
| Eval9 | gpt-5.6-sol | branched_base | 0.000000 | 0.000000 |  |  |
| Eval9 | gpt-5.6-sol | branched_variable | 0.063806 | 0.056764 |  |  |
| Eval9 | gpt-5.6-sol | compact_base | 0.051151 | 0.043403 |  |  |
| Eval9 | gpt-5.6-sol | compact_variable | 0.051966 | 0.043047 |  |  |
| Eval9 | gpt-5.6-sol | corridor_base | 0.117116 | 0.046178 |  |  |
| Eval9 | gpt-5.6-sol | corridor_variable | 0.121507 | 0.082016 |  |  |
| Eval10 | claude-fable-5 | llm |  |  | 0.248667 | 0.063316 |
| Eval10 | gpt-5.6-sol | llm |  |  | 0.050000 | 0.100000 |
