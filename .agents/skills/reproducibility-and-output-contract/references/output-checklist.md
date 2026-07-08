# Output Checklist

## Directory Policy

- `results/4_adl_evaluation/`: final Evaluation 4 ADL interval metrics.
- `results/5_adl_correspondence/`: final Evaluation 5 pattern-level method comparison.
- `results/6_adl_interpretation_set_comparison/{K}_{hamming}_{days}days/`: final Evaluation 6 proposed/direct comparison.
- `output/`: LLM outputs, baselines, intermediate generated files.
- `picture/`: network JSON and visualizations.
- `state/`: representative state tables.
- `new_labeled_data/` and `data/`: input data. Do not edit.

## CSV Contract

When changing a CSV:

1. Keep row grain explicit.
2. Preserve identifier columns:
   - method-level: `method`
   - pattern-level: `method`, `pattern_id`, `pattern_name`, `sequence`
   - interval-level: `start_time`, `end_time`, ADL/category columns
3. Append new columns where possible.
4. Do not change numeric fields to formatted prose.
5. Use empty string for non-applicable optional fields, not ad hoc text.

## JSON Summary Contract

Every evaluation summary should include:

- input paths
- output directory or method list
- thresholds and important CLI args
- split period if applicable
- method counts or pattern counts
- skipped methods with reasons
- notes/warnings when generated automatically

## Reproducibility Checklist

- Are train/test periods unchanged?
- Are K, hamming threshold, days, pattern length, model name, and prompt path documented?
- Did any command write to `output/`, `picture/`, `state/`, or `results/`?
- Did generated outputs overwrite paper-facing results?
- Did summary JSON record new thresholds?
- Did docs mention new columns and how to interpret them?
- Did tests cover the new metric or baseline on dummy data?

## Common Verification Commands

```bash
uv run python -m unittest tests.test_adl_evaluation
uv run python -m unittest tests.test_adl_correspondence
uv run python -m unittest tests.test_evaluation6_adl_interpretation_set
```

If `uv` fails because it cannot access the user cache under sandboxing, rerun with approval rather than changing the environment.
