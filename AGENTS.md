# Repository Guidelines

## Scope and safety

- This repository contains research code for smart-home sensor-log behavior-pattern mining and evaluation. Preserve scientific validity, reproducibility, and existing behavior unless the user explicitly requests a change.
- Do not edit raw or labeled datasets, private data, secrets, credentials, `.env`, or API keys.
- Do not overwrite or commit generated artifacts under `output/`, `picture/`, `state/`, or `results/` unless explicitly requested.
- Do not change metrics, thresholds, data splits, seeds, aggregation, missing-run handling, or baseline definitions as an incidental part of another task.

## Before editing

1. Read the documentation relevant to the requested behavior. For evaluation work, start with the matching `docs/evaluation_*.md`.
2. Inspect the implementation and tests. For a CLI change, verify the actual `argparse` definition or `--help`; documentation defines research intent, while code defines currently supported arguments.
3. If documentation and implementation conflict, report the conflict instead of guessing.

## Implementation

- Make the smallest focused change and preserve public CLI and CSV/JSON contracts where possible.
- Prevent train/test leakage when changing pattern generation, mappings, thresholds, or caches.
- Keep the Streamlit dashboard a thin wrapper around existing CLI commands; do not duplicate evaluation logic in `app/`.
- Update affected documentation, tests, and dashboard wiring when behavior or interfaces change.

## Verification

- Run focused syntax checks, relevant `--help` commands, and the narrowest applicable tests.
- Inspect the final diff for unrelated edits and report anything that could not be verified.
