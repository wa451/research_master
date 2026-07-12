---
name: streamlit-evaluation-dashboard
description: Change evaluation controls, command building or execution, dry-run, logs, or result display under app/. Excludes evaluation logic with no dashboard impact.
---

# Streamlit Evaluation Dashboard

## Workflow

1. Read `docs/evaluation_streamlit_dashboard.md`, the relevant `docs/evaluation_*.md`, and the affected CLI's `argparse` definition or `--help`.
2. Keep responsibilities separated: UI and result rendering in `app/streamlit_app.py`, command construction in `app/command_builder.py`, and subprocess/log helpers in `app/utils.py`.
3. Expose only supported CLI arguments. Build commands as argument lists, show the preview before execution, and route execution through `app.utils.run_command`; do not use `shell=True` or reimplement research logic.
4. For each changed step, keep required inputs, expected outputs, ordering, conditional generation, and batch behavior consistent with the CLI.
5. Preserve dry-run as non-executing command/log recording. Keep stdout, stderr, command, and exit context under the existing dashboard log root, with secrets redacted.
6. Update result discovery/rendering and dashboard documentation when output files or interpretation change.

## Verification

- Run `python -m py_compile app/streamlit_app.py app/command_builder.py app/utils.py`.
- Run focused command-builder tests when present and the affected CLI with `--help`.
- Smoke-test with `uv run streamlit run app/streamlit_app.py` when practical; use dry-run for command inspection and do not launch costly LLM/evaluation work.
- Inspect the preview, paths, quoting, missing-input behavior, logs, and final diff.
