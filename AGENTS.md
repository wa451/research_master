# Repository Agent Rules

- This repository is research code for smart-home sensor-log behavior pattern mining. Preserve existing research logic unless the user explicitly requests a behavioral change.
- Do not edit raw datasets, `.env`, API keys, or private data. Keep data files and generated results out of Git unless already tracked or explicitly requested.
- Use `scripts/` as CLI entry points and `src/behavior_pattern_mining/` for reusable implementation.
- Keep `results/` for paper-facing evaluation outputs. Keep intermediate artifacts in `output/`, `picture/`, or `state/` according to current conventions.
- Before changing an evaluation or baseline, read the relevant `docs/evaluation_*.md` and update docs when commands, outputs, or metrics change.
- Preserve CSV/JSON output schemas where possible. Append columns instead of renaming/removing existing columns.
- Prefer focused tests under `tests/` for evaluation logic and baseline logic.
