---
name: baseline-implementation
description: Implement or change a comparison baseline algorithm, extraction, filtering, or fairness behavior. Do not use for running baselines or evaluation-only integration.
---

# Baseline Implementation

## Workflow

1. Read the evaluation document that consumes the baseline and `docs/known_issues.md`; inspect the current baseline producer, consumer, CLI, tests, and nearby baseline implementations.
2. Establish the comparison contract from current code: input period, split, state configuration, sequence constraints, output record shape, method identifier, and failure handling.
3. Implement reusable extraction or filtering outside the CLI entry point. Reuse the same inputs and split as compared methods unless the research specification says otherwise.
4. Prevent test labels from influencing extraction, filtering, thresholds, caches, or train-side pattern-to-label assignment.
5. Keep method identifiers and consumer-facing fields stable. Expose meaningful thresholds as CLI arguments and record them using the evaluation's existing summary convention.
6. Update focused tests and the consuming evaluation document. Update Streamlit only when its supported CLI or displayed outputs change.

## Verification

- Exercise the baseline on a small fixture and cover empty/invalid input handling.
- After confirming it is an `argparse` entry point, run the consuming CLI's `--help` and focused tests.
- Check that all compared methods use compatible periods, splits, and pattern constraints.
- Inspect the diff for unintended metric, proposed-method, or generated-result changes.
