---
name: streamlit-evaluation-dashboard
description: Change evaluation controls, command building/execution, dry-run, logs, or results under app/. Excludes evaluation-only logic.
---

# Streamlit Evaluation Dashboard

- Read affected sections of [dashboard docs](../../../docs/operations/dashboard.md), the target [evaluation route](../../../docs/codex_memory/EVALUATION_ROUTES.md), its specification/known issues, and actual CLI arguments.
- Responsibilities: `app/streamlit_app.py` UI/results; `app/command_builder.py::build_evaluationN_steps` argv; `app/utils.py::run_command` subprocess/logging. Search the target builder/renderer before reading entire files.
- Expose supported CLI options as argument lists with previews; use the execution helper, never `shell=True` or duplicated research logic. Keep inputs, outputs, step order, conditional generation and batch behavior aligned with the CLI.
- Preserve dry-run as non-executing command/log recording; retain stdout/stderr, command and exit context under the existing log root with secrets redacted. Eval9 also uses `verify_on_batch` for existing-output hash validation.
- Update affected docs and result discovery/rendering. Verify syntax, available builder tests in the evaluation route, safe CLI `--help`, previews/paths/quoting/missing inputs/logs. Use a Streamlit smoke test when practical; do not launch costly experiments just to inspect commands.
