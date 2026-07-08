---
name: research-evaluation
description: Use when adding, modifying, or debugging evaluation experiments in this smart-home behavior pattern mining repository, including Evaluation 1-6, ADL label evaluation, metrics, CSV/JSON outputs, and reproduction commands.
---

# Research Evaluation

Use this skill for changes under `scripts/evaluate_*.py`, `src/behavior_pattern_mining/evaluation/`, or `docs/evaluation_*.md`.

## Required First Steps

1. Read the relevant evaluation doc before editing:
   - Evaluation 1: `docs/evaluation_1_parameter_sensitivity.md`
   - Evaluation 2: `docs/evaluation_2_proposed_method_5runs.md`
   - Evaluation 3: `docs/evaluation_3_direct_log_baseline_comparison.md`
   - Evaluation 4: `docs/evaluation_4_labeled_casas_adl.md`
   - Evaluation 5: `docs/evaluation_5_adl_correspondence.md`
   - Evaluation 6: `docs/evaluation_6_adl_interpretation_set.md`
2. Read `docs/pipeline.md`, `docs/python_file_inventory.md`, and the target script/module.
3. Inspect existing output schema in `results/<evaluation>/` before changing columns.
4. Preserve train/test rules and output contract unless the user explicitly asks to change them.

## Evaluation Roles

- Evaluation 4: single-method ADL interval evaluation. Main files are `scripts/evaluate_adl_labels.py` and `src/behavior_pattern_mining/evaluation/adl.py`. Outputs include `adl_metrics_iou_*.csv`, `boundary_metrics_iou_*.csv`, `filtered_predictions.csv`, `adl_interval_hit_metrics.csv`, and `evaluation_summary.json`.
- Evaluation 5: pattern-level ADL-grounded/useless comparison. Main files are `scripts/evaluate_adl_correspondence.py` and `src/behavior_pattern_mining/evaluation/adl_correspondence.py`. Outputs are `evaluation5_pattern_details.csv`, `evaluation5_summary_by_method.csv`, `evaluation5_summary.json`.
- Evaluation 6: LLM ADL interpretation set match. Main files are `scripts/evaluate_6_adl_interpretation_set.py`, `scripts/evaluate_6_compare_adl_interpretation_set.py`, and `src/behavior_pattern_mining/evaluation/adl_interpretation_set.py`.

## Implementation Rules

- Add evaluation logic as a post-hoc layer where possible. Do not change preprocessing, representative-state extraction, network construction, or LLM extraction unless required.
- Keep result granularity explicit: interval-level, pattern-level, method-level, run-level.
- If adding a metric, add it to both CSV and summary JSON when it is part of the reported result.
- If changing an output column, update the corresponding docs and tests.
- Do not overwrite data files or existing generated artifacts except the intended evaluation output directory.

## Validation

Run the narrow test first:

```bash
uv run python -m unittest tests.test_adl_evaluation tests.test_adl_correspondence tests.test_evaluation6_adl_interpretation_set
```

If `uv` cannot access its cache under sandboxing, request approval and rerun the same command.

For detailed output schemas and command examples, read `references/evaluation-contracts.md`.
