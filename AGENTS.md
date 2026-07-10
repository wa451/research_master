# Repository Agent Notes

## Purpose

- This repository contains research code for smart-home sensor-log behavior pattern mining and evaluation.
- The Streamlit app is a local dashboard that runs existing evaluation CLI commands.
- Preserve scientific validity, reproducibility, and existing behavior unless the user explicitly requests a change.
- Do not edit raw datasets, `.env`, API keys, credentials, or private data.

## Required Workflow

1. Read the relevant `docs/evaluation_*.md`.
2. Inspect the affected script's `--help` or `argparse` definition.
3. Determine whether the request is UI-only or changes evaluation logic.
4. Make the smallest focused change.
5. Update the Streamlit app when commands, arguments, execution order, outputs, or result display change.
6. Run relevant syntax checks and tests.
7. Inspect the final diff for unrelated changes.

## Research Safeguards

- Treat evaluation docs as the source of truth for research purpose, metric definitions, and execution order.
- Treat the implementation as the source of truth for currently supported CLI arguments.
- If docs and implementation conflict, identify the inconsistency rather than silently choosing one.
- Do not change metric definitions, thresholds, data splits, random seeds, baseline generation, aggregation rules, or missing-run handling unless explicitly requested.
- Avoid train/test leakage when generating patterns, mappings, thresholds, or caches.
- Preserve CSV/JSON schemas where possible; prefer adding fields over renaming or removing them.
- Do not overwrite existing experiment results unless explicitly requested.
- Keep generated data and results out of Git unless already tracked or explicitly requested.

## Streamlit Rules

- Keep the app a thin wrapper around existing CLI scripts.
- Do not break existing CLI execution paths.
- Prefer changes under `app/` for UI-only requests.
- Keep evaluation-specific controls separated by evaluation number.
- Expose only arguments actually supported by the target CLI.
- Do not add pre-run `config.yaml` or `config.json` saving.
- Show the command preview before execution.
- In dry-run mode, display and log the command without executing it.
- Use `subprocess` through `app/utils.py::run_command`; avoid `shell=True`.
- Save stdout, stderr, command, and exit-code context under `output/logs/evaluation_dashboard/`.
- Redact secrets from commands and logs.

## Main Locations

- Streamlit UI: `app/streamlit_app.py`
- Command builders: `app/command_builder.py`
- Execution helpers: `app/utils.py`
- Evaluation specifications: `docs/evaluation_*.md`
- CLI entry points: `scripts/`
- Reusable code: `src/behavior_pattern_mining/`
- Tests: `tests/`
- Research results: `results/`
- Intermediate outputs: `output/`, `picture/`, `state/`

## Verification

Run checks relevant to the modified files:

```bash
python -m py_compile app/streamlit_app.py app/command_builder.py app/utils.py
uv run python <modified-script> --help
uv run python -m unittest <relevant-test-module>

For dashboard changes, also verify:

uv run streamlit run app/streamlit_app.py

If a path, CLI argument, or evaluation rule cannot be verified, do not guess or add placeholder behavior. Report the uncertainty clearly.