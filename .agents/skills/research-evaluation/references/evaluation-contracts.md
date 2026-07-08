# Evaluation Contracts

## Common Inputs

- Labeled CASAS: `new_labeled_data/aruba.txt`
- Representative state table: `state/aruba_15_1_154days.txt`
- State series CSV for downstream evaluation: `results/4_adl_evaluation/state_series.csv`
- Proposed method patterns: `output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json`
- Sensor map: `configs/aruba_sensor_map.json`
- ADL min duration config: `configs/adl_min_duration.json`

## Evaluation 4 Outputs

Directory: `results/4_adl_evaluation/`

- `pattern_occurrences.csv`: pattern occurrence intervals on the representative state series.
- `pattern_adl_mapping.csv`: single pattern-to-ADL assignment with support/confidence.
- `merged_predictions.csv`: same-ADL nearby predictions after merge.
- `filtered_predictions.csv`: duration-filtered predictions used for IoU evaluation.
- `adl_metrics_iou_0.3.csv`, `adl_metrics_iou_0.5.csv`: ADL Precision/Recall/F1.
- `boundary_metrics_iou_0.3.csv`, `boundary_metrics_iou_0.5.csv`: TP boundary error summaries.
- `adl_interval_hit_metrics.csv`, `adl_interval_hit_details.csv`: interval hit evaluation.
- `evaluation_summary.json`: inputs, thresholds, postprocess counts, averages.

## Evaluation 5 Outputs

Directory: `results/5_adl_correspondence/`

- `evaluation5_pattern_details.csv`: one row per method-pattern. Keep identifiers and status columns stable.
- `evaluation5_summary_by_method.csv`: one row per method. Main columns are `adl_grounded_pattern_rate` and `useless_pattern_rate`.
- `evaluation5_summary.json`: input paths, train/test periods, thresholds, skipped methods, method summaries.

Evaluation 5 must keep chronological train/test split. Pattern-to-ADL assignment is learned on train only and fixed on test.

## Evaluation 6 Outputs

Directories:

- `results/6_adl_interpretation_set_comparison/{K}_{hamming}_{days}days/`

Important files:

- `evaluation6_pattern_set_details.csv`
- `evaluation6_summary.csv`
- `evaluation6_by_pred_label.csv`
- `evaluation6_by_true_label.csv`
- `evaluation6_*_by_method.csv` for comparison
- `evaluation6_summary.json` or `evaluation6_comparison_summary.json`

Evaluation 6 is set-based. Do not add sequence-order metrics unless explicitly requested.

## Command Examples

Evaluation 4:

```bash
uv run python scripts/evaluate_adl_labels.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --state-table state/aruba_15_1_154days.txt \
  --sensor-map configs/aruba_sensor_map.json \
  --patterns output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json \
  --output-dir results/4_adl_evaluation \
  --write-state-series results/4_adl_evaluation/state_series.csv
```

Evaluation 5:

```bash
uv run python scripts/evaluate_adl_correspondence.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --state-series results/4_adl_evaluation/state_series.csv \
  --patterns-frequency output/aruba_15_1_154days/state_sequence_counts_15_1_154days.json \
  --patterns-proposed output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json \
  --output-dir results/5_adl_correspondence \
  --train-ratio 0.7 \
  --enable-fp-growth-baseline
```

Evaluation 6 comparison:

```bash
uv run python scripts/evaluate_6_compare_adl_interpretation_set.py \
  --patterns-proposed output/aruba_15_1_30days/llm_sequences_modes_15_1_30days_1.json \
  --patterns-direct output/llm_direct_15_1_30days/1.json \
  --state-series output/6_adl_evaluation_30/state_series.csv \
  --labeled-casas new_labeled_data/aruba.txt \
  --output-dir results/6_adl_interpretation_set_comparison
```

If any filename is absent in the current worktree, do not invent a replacement. Search with `rg --files` and mark unresolved paths as TODO.
