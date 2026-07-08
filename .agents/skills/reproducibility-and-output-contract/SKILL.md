---
name: reproducibility-and-output-contract
description: Use when changing experiment commands, output directories, CSV/JSON schemas, result summaries, logging, seed/reproducibility settings, or generated artifacts in this smart-home behavior pattern mining repository.
---

# Reproducibility And Output Contract

Use this skill whenever a change can affect reproducibility, output files, or result interpretation.

## Permanent Rules

- Do not modify raw datasets, `.env`, or API keys.
- Do not delete or overwrite existing result artifacts unless the user explicitly asks.
- Put paper-facing evaluation results under `results/<number>_<name>/`.
- Put intermediate outputs, LLM responses, generated networks, and temporary state under `output/`, `picture/`, or `state/` according to existing conventions.
- Keep CSV column names stable. If a column must be renamed, keep a compatibility column unless the user approves a breaking change.
- Keep summary JSON machine-readable and include input paths, thresholds, method names, skipped methods, and counts.
- Record train/test periods and split rules in summary JSON for split-based evaluations.

## Before Editing

1. Inspect `docs/artifact_policy.md`, `docs/experiment_reproduction.md`, and the relevant `docs/evaluation_*.md`.
2. Check existing output files in `results/`.
3. Search for downstream readers with `rg "column_or_filename"`.
4. Identify whether outputs are final results or intermediate artifacts.

## After Editing

- Run focused unit tests.
- If practical, run the exact evaluation command on existing small or current outputs.
- Compare new CSV headers against documented headers.
- Update docs and summary JSON fields together.
- Report any regenerated files and any known compatibility risk.

For concrete schema and checklist details, read `references/output-checklist.md`.
