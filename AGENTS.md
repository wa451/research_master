# Repository Guidelines

## Scope and safety

- This repository contains research code for mining and evaluating behavior patterns from smart-home sensor logs. Preserve scientific validity, reproducibility, and existing behavior unless the user explicitly requests a research change.
- Do not edit raw or labeled datasets, private data, secrets, credentials, `.env`, or API keys.
- Do not overwrite or commit generated artifacts under `output/`, `picture/`, `state/`, or `results/` unless explicitly requested.
- Do not change metrics, thresholds, data splits, seeds, aggregation, missing-run handling, or baseline definitions as an incidental part of another task.

## Before editing

1. Read the relevant documentation. For evaluation work, start with the matching `docs/evaluation_*.md` and check `docs/known_issues.md`.
2. Inspect the implementation, tests, configuration, and actual CLI definition. Run `--help` only after confirming the entry point uses `argparse` and exits safely.
3. Treat code as evidence of current behavior, not automatic proof of research intent. If sources conflict, classify and report the conflict instead of guessing or legitimizing a suspected bug as specification.

## 過去のエージェント履歴

研究条件、評価定義、分母、データ期間、パラメータ、出力仕様、または過去の設計判断に関係する変更では、作業前に `ctx-agent-history-search` スキルを使用して現在のワークスペースの関連履歴を確認する。履歴は根拠として参照するが、現在のコード、`docs/`、CLI引数、および本ファイルの指示を優先する。

## Skills

- Use `research-evaluation` for numbered evaluation logic, metrics, CLIs, or tests; `baseline-implementation` for comparison algorithms; and `streamlit-evaluation-dashboard` for `app/` changes.
- Use `evaluation-readme-formatting` for evaluation Markdown only, and `reproducibility-and-output-contract` for repository-wide artifact or shared CSV/JSON contract changes.

## Implementation

- Make the smallest focused change and preserve public CLI, defaults, file formats, paths, column names, and CSV/JSON contracts unless a requested migration explicitly says otherwise.
- Prevent train/test leakage when changing pattern generation, mappings, thresholds, or caches.
- Keep the Streamlit dashboard a thin wrapper around existing CLI commands; do not duplicate evaluation logic in `app/`.
- Update affected documentation, tests, and dashboard wiring when behavior or interfaces change.

## Verification

- Run focused syntax/import checks, safe relevant `--help` commands, and the narrowest applicable tests. For evaluation changes, also verify output headers/keys and deterministic behavior where applicable.
- Inspect the final diff for unrelated edits. Report changed files, verification results, research or compatibility impact, unresolved inconsistencies, and anything that could not be verified.
