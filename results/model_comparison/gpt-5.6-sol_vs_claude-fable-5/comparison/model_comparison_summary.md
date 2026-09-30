# GPT-5.6 Sol vs Claude Fable 5: artifact-only comparison

This report was generated from existing manifests, summaries, run CSVs, and scorer metadata. No model/API call or pattern generation was performed.

## Evaluation 6 Full

| model | method | mean_multilabel_precision | mean_multilabel_recall | mean_multilabel_f1 | mean_jaccard | mean_exact_set_match |
|---|---|---|---|---|---|---|
| gpt-5.6-sol | direct_log_baseline | 0.6497780650721827 | 0.711768656180421 | 0.644516627163686 | 0.5728201537025066 | 0.3624692954104719 |
| gpt-5.6-sol | proposed | 0.8516239316239316 | 0.7517948717948718 | 0.783960113960114 | 0.7517948717948718 | 0.6586324786324786 |
| claude-fable-5 | direct_log_baseline | 0.6059090909090908 | 0.6475757575757577 | 0.6016666666666667 | 0.5468181818181818 | 0.3936363636363637 |
| claude-fable-5 | proposed | 0.7916202270381837 | 0.8018770783167067 | 0.7704549936933838 | 0.7164522417153997 | 0.5539525283797729 |

## Evaluation 6 Strict

| model | method | mean_multilabel_precision | mean_multilabel_recall | mean_multilabel_f1 | mean_jaccard | mean_exact_set_match |
|---|---|---|---|---|---|---|
| gpt-5.6-sol | llm_only_strict | 0.709548872180451 | 0.6588972431077694 | 0.6624060150375939 | 0.6187719298245614 | 0.4878696741854636 |
| gpt-5.6-sol | proposed_strict | 0.9483333333333335 | 0.8258986928104577 | 0.8638807189542483 | 0.8258986928104577 | 0.7204411764705883 |
| claude-fable-5 | llm_only_strict | 0.5664072249589491 | 0.6674674329501915 | 0.5859917898193759 | 0.5224022988505748 | 0.33578981937602626 |
| claude-fable-5 | proposed_strict | 0.7983475783475783 | 0.7818518518518519 | 0.7592060778727445 | 0.703338081671415 | 0.5441025641025641 |

### Paired Delta F1

| model | paired_runs | mean_paired_delta_f1 | sd_paired_delta_f1 |
|---|---|---|---|
| gpt-5.6-sol | 5 | 0.201475 | 0.089225 |
| claude-fable-5 | 5 | 0.173214 | 0.073242 |

## Evaluation 9 (condition × duration mean ± SD source table)

| model | experiment | train_days | test_days | condition | f1_mean | f1_sd | jaccard_mean | test_target_episode_coverage_mean | fragmentation_rate_mean |
|---|---|---|---|---|---|---|---|---|---|
| claude-fable-5 | duration_54f94fee_6ae9208d | 14 | 7 | branched_base | 0.062792 | 0.002287 | 0.032415 | 0.185185 | 0.022676 |
| claude-fable-5 | duration_54f94fee_6ae9208d | 14 | 7 | branched_variable | 0.083629 | 0.031658 | 0.043895 | 0.291005 | 0.015470 |
| claude-fable-5 | duration_54f94fee_6ae9208d | 14 | 7 | compact_base | 0.000000 | 0.000000 | 0.000000 | 0.555556 | 0.070922 |
| claude-fable-5 | duration_54f94fee_6ae9208d | 14 | 7 | compact_variable | 0.024281 | 0.038631 | 0.012641 | 0.521164 | 0.058333 |
| claude-fable-5 | duration_54f94fee_6ae9208d | 14 | 7 | corridor_base | 0.144181 | 0.045568 | 0.078283 | 0.425926 | 0.009070 |
| claude-fable-5 | duration_54f94fee_6ae9208d | 14 | 7 | corridor_variable | 0.110480 | 0.035498 | 0.058801 | 0.555556 | 0.023939 |
| claude-fable-5 | duration_54f94fee_6ae9208d | 28 | 7 | branched_base | 0.060657 | 0.001884 | 0.031278 | 0.166667 | 0.020408 |
| claude-fable-5 | duration_54f94fee_6ae9208d | 28 | 7 | branched_variable | 0.065245 | 0.034958 | 0.034023 | 0.351852 | 0.025124 |
| claude-fable-5 | duration_54f94fee_6ae9208d | 28 | 7 | compact_base | 0.006536 | 0.019608 | 0.003367 | 0.611111 | 0.075650 |
| claude-fable-5 | duration_54f94fee_6ae9208d | 28 | 7 | compact_variable | 0.025082 | 0.029788 | 0.012906 | 0.484127 | 0.049691 |
| claude-fable-5 | duration_54f94fee_6ae9208d | 28 | 7 | corridor_base | 0.085398 | 0.031496 | 0.044856 | 0.314815 | 0.009070 |
| claude-fable-5 | duration_54f94fee_6ae9208d | 28 | 7 | corridor_variable | 0.063543 | 0.034433 | 0.033105 | 0.410053 | 0.010445 |
| claude-fable-5 | duration_54f94fee_6ae9208d | 3 | 7 | branched_base | 0.053290 | 0.046163 | 0.027890 | 0.203704 | 0.011338 |
| claude-fable-5 | duration_54f94fee_6ae9208d | 3 | 7 | branched_variable | 0.013704 | 0.027231 | 0.007071 | 0.113757 | 0.004978 |
| claude-fable-5 | duration_54f94fee_6ae9208d | 3 | 7 | compact_base | 0.000000 | 0.000000 | 0.000000 | 0.592593 | 0.075650 |
| claude-fable-5 | duration_54f94fee_6ae9208d | 3 | 7 | compact_variable | 0.024888 | 0.029539 | 0.012803 | 0.619048 | 0.076005 |
| claude-fable-5 | duration_54f94fee_6ae9208d | 3 | 7 | corridor_base | 0.000000 | 0.000000 | 0.000000 | 0.018519 | 0.004444 |
| claude-fable-5 | duration_54f94fee_6ae9208d | 3 | 7 | corridor_variable | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| claude-fable-5 | duration_54f94fee_6ae9208d | 7 | 7 | branched_base | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| claude-fable-5 | duration_54f94fee_6ae9208d | 7 | 7 | branched_variable | 0.068571 | 0.035618 | 0.035815 | 0.222222 | 0.007340 |
| claude-fable-5 | duration_54f94fee_6ae9208d | 7 | 7 | compact_base | 0.000000 | 0.000000 | 0.000000 | 0.611111 | 0.078014 |
| claude-fable-5 | duration_54f94fee_6ae9208d | 7 | 7 | compact_variable | 0.043643 | 0.036720 | 0.022629 | 0.595238 | 0.064506 |
| claude-fable-5 | duration_54f94fee_6ae9208d | 7 | 7 | corridor_base | 0.127191 | 0.038203 | 0.068311 | 0.407407 | 0.006803 |
| claude-fable-5 | duration_54f94fee_6ae9208d | 7 | 7 | corridor_variable | 0.097525 | 0.056720 | 0.052090 | 0.452381 | 0.012760 |
| claude-fable-5 | full_4d35fa98_e4a41f40 |  |  | branched_base | 0.019058 | 0.028599 | 0.009810 | 0.203704 | 0.024943 |
| claude-fable-5 | full_4d35fa98_e4a41f40 |  |  | branched_variable | 0.033047 | 0.042031 | 0.017220 | 0.291005 | 0.023740 |
| claude-fable-5 | full_4d35fa98_e4a41f40 |  |  | compact_base | 0.000000 | 0.000000 | 0.000000 | 0.740741 | 0.094563 |
| claude-fable-5 | full_4d35fa98_e4a41f40 |  |  | compact_variable | 0.018891 | 0.028363 | 0.009721 | 0.539683 | 0.062346 |
| claude-fable-5 | full_4d35fa98_e4a41f40 |  |  | corridor_base | 0.098493 | 0.028022 | 0.051998 | 0.444444 | 0.020408 |
| claude-fable-5 | full_4d35fa98_e4a41f40 |  |  | corridor_variable | 0.099598 | 0.031228 | 0.052659 | 0.388889 | 0.007092 |
| gpt-5.6-sol | duration | 14 | 7 | branched_base | 0.041197 | 0.039132 | 0.021393 | 0.129630 | 0.015873 |
| gpt-5.6-sol | duration | 14 | 7 | branched_variable | 0.059221 | 0.063103 | 0.031496 | 0.148148 | 0.000000 |
| gpt-5.6-sol | duration | 14 | 7 | compact_base | 0.015070 | 0.029910 | 0.007800 | 0.148148 | 0.016548 |
| gpt-5.6-sol | duration | 14 | 7 | compact_variable | 0.045824 | 0.034486 | 0.023730 | 0.055556 | 0.005247 |
| gpt-5.6-sol | duration | 14 | 7 | corridor_base | 0.133041 | 0.054466 | 0.072039 | 0.333333 | 0.004535 |
| gpt-5.6-sol | duration | 14 | 7 | corridor_variable | 0.104054 | 0.060686 | 0.055846 | 0.322751 | 0.010445 |
| gpt-5.6-sol | duration | 28 | 7 | branched_base | 0.016167 | 0.032087 | 0.008389 | 0.111111 | 0.009070 |
| gpt-5.6-sol | duration | 28 | 7 | branched_variable | 0.064796 | 0.042330 | 0.033921 | 0.190476 | 0.000000 |
| gpt-5.6-sol | duration | 28 | 7 | compact_base | 0.045264 | 0.067014 | 0.024280 | 0.166667 | 0.014184 |
| gpt-5.6-sol | duration | 28 | 7 | compact_variable | 0.057711 | 0.050655 | 0.030339 | 0.203704 | 0.016358 |
| gpt-5.6-sol | duration | 28 | 7 | corridor_base | 0.092036 | 0.031735 | 0.048499 | 0.240741 | 0.006803 |
| gpt-5.6-sol | duration | 28 | 7 | corridor_variable | 0.117937 | 0.057539 | 0.063567 | 0.309524 | 0.004630 |
| gpt-5.6-sol | duration | 3 | 7 | branched_base | 0.106792 | 0.054240 | 0.057164 | 0.148148 | 0.000000 |
| gpt-5.6-sol | duration | 3 | 7 | branched_variable | 0.057390 | 0.060933 | 0.030454 | 0.119048 | 0.000000 |
| gpt-5.6-sol | duration | 3 | 7 | compact_base | 0.020425 | 0.030656 | 0.010535 | 0.240741 | 0.030733 |
| gpt-5.6-sol | duration | 3 | 7 | compact_variable | 0.051247 | 0.042781 | 0.026738 | 0.166667 | 0.015839 |
| gpt-5.6-sol | duration | 3 | 7 | corridor_base | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| gpt-5.6-sol | duration | 3 | 7 | corridor_variable | 0.000000 | 0.000000 | 0.000000 | 0.055556 | 0.015152 |
| gpt-5.6-sol | duration | 7 | 7 | branched_base | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| gpt-5.6-sol | duration | 7 | 7 | branched_variable | 0.063806 | 0.056764 | 0.033750 | 0.126984 | 0.000000 |
| gpt-5.6-sol | duration | 7 | 7 | compact_base | 0.051151 | 0.043403 | 0.026701 | 0.129630 | 0.014184 |
| gpt-5.6-sol | duration | 7 | 7 | compact_variable | 0.051966 | 0.043047 | 0.027122 | 0.166667 | 0.018519 |
| gpt-5.6-sol | duration | 7 | 7 | corridor_base | 0.117116 | 0.046178 | 0.062774 | 0.259259 | 0.000000 |
| gpt-5.6-sol | duration | 7 | 7 | corridor_variable | 0.121507 | 0.082016 | 0.066505 | 0.253968 | 0.000000 |

## Evaluation 10

| model | method | pattern_count_mean | supported_pattern_count_mean | test_supported_pattern_fraction_mean | mean_test_day_recurrence_mean |
|---|---|---|---|---|---|
| claude-fable-5 | llm | 9.400000 | 3.600000 | 0.388889 | 0.248667 |
| gpt-5.6-sol | llm | 1.000000 | 0.200000 | 0.125000 | 0.050000 |

## Completeness caveat

Claude Fable 5 has no discovered formal Evaluation 7 summary. It is therefore not complete for Evaluation 5--10 and its model-specific parameter-selection comparison cannot be claimed.
