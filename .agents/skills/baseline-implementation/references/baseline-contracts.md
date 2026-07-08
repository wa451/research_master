# Baseline Contracts

## Method Names

Use stable method IDs in CSV/JSON:

- `frequency`
- `rule_light`
- `rule_medium`
- `rule_strong`
- `fp_growth`
- `fp_growth_filtered`
- `transition_probability`
- `direct_log_baseline`
- `proposed`

If adding a new method, document the exact method string and keep it stable.

## Pattern Schema

Baseline pattern rows should normalize to:

```text
method
pattern_id
pattern_name
sequence
count
```

For Evaluation 5, optional baseline metadata may include:

```text
pattern_source
support_transactions
support_ratio
train_occurrence_count
median_duration_seconds
p90_duration_seconds
is_fp_filtered_out
fp_filter_reason
```

## FP-Growth-Style Baseline

Current Evaluation 5 implementation treats contiguous state n-grams as transaction items.

Default CLI:

```text
--enable-fp-growth-baseline
--fp-min-support 0.05
--fp-top-k 50
--fp-min-len 2
--fp-max-len 4
--fp-max-median-duration-seconds 1800
--fp-max-p90-duration-seconds 3600
```

Transaction definition:

- date-by-time-period bucket
- periods: Morning, Daytime, Night, Midnight
- item: contiguous representative-state n-gram

Filter definition:

- self transition: `A -> A`
- other round trip: `A -> その他 -> A`, `A -> Other -> A`
- alternating loop: `A -> B -> A -> B`
- median duration above threshold
- p90 duration above threshold

## Direct-Log LLM Baseline

Use `scripts/run_direct_log_baseline.py`. For Evaluation 6, use 30 days for both direct baseline and proposed method to avoid context-window mismatch.

Expected direct output example:

```text
output/llm_direct_30/1.json
```

Do not compare a 30-day direct-log baseline against a 154-day proposed-method output.

## Transition Probability Baseline

Keep transition probability threshold explicit. Existing defaults are documented in `configs/default.yaml` and `docs/paper_parameters.md`; verify current names before changing code.

## Failure Handling

If a baseline cannot be generated:

- Do not abort the full evaluation unless no valid methods remain.
- Add the method and reason to `skipped_methods`.
- Print a warning.
- Preserve output schema for other methods.
