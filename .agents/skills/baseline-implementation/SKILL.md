---
name: baseline-implementation
description: Use when adding or modifying comparison baselines such as PrefixSpan, FP-Growth, transition-probability, frequency, rule-filtered frequency, or direct-log LLM baselines for this smart-home behavior pattern mining repository.
---

# Baseline Implementation

Use this skill for new methods compared against the proposed state-transition-network plus LLM approach.

## Required First Steps

1. Read `docs/evaluation_3_direct_log_baseline_comparison.md`, `docs/evaluation_5_adl_correspondence.md`, and `docs/pipeline.md`.
2. Inspect existing baseline modules:
   - `src/behavior_pattern_mining/baselines/frequency.py`
   - `src/behavior_pattern_mining/baselines/transition_probability.py`
   - `src/behavior_pattern_mining/evaluation/adl_correspondence.py`
   - `src/behavior_pattern_mining/llm/direct_log_extractor.py`
3. Identify the comparison surface: sequence-level Precision/Recall/F1, Evaluation 5 pattern-level uselessness, Evaluation 6 set-match, or direct-log baseline comparison.

## Fair Comparison Rules

- Use the same input period, dataset, representative-state configuration, and pattern length range as the proposed method unless the evaluation doc states otherwise.
- Keep train/test split identical for all methods in the same evaluation.
- Normalize every baseline output to a common pattern record:
  - `method`
  - `pattern_id`
  - `pattern_name`
  - `sequence`
  - `count` or support when available
- Do not let test labels influence baseline pattern extraction or train-side pattern-to-ADL assignment.
- If a baseline needs filtering, expose thresholds as CLI arguments and record them in summary JSON.

## Common Baseline Locations

- Frequency and rule-filtered frequency: `src/behavior_pattern_mining/baselines/frequency.py` and Evaluation 5 helpers.
- Transition probability: `src/behavior_pattern_mining/baselines/transition_probability.py`.
- LLM direct-log baseline: `scripts/run_direct_log_baseline.py`, `src/behavior_pattern_mining/llm/direct_log_extractor.py`, `prompts/direct_log_pattern_extraction_prompt.md`.
- FP-Growth-style baseline in Evaluation 5: `build_fp_growth_baseline_patterns` in `src/behavior_pattern_mining/evaluation/adl_correspondence.py`.

## Implementation Pattern

1. Add extraction logic in a reusable module or evaluation helper, not only inside a script.
2. Add CLI flags with conservative defaults.
3. Convert output into the existing pattern schema.
4. Include the method in summary JSON and skipped-method handling.
5. Add focused unit tests with small state intervals.
6. Update docs for the evaluation that consumes the baseline.

For known baseline-specific contracts and filter examples, read `references/baseline-contracts.md`.
