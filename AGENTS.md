# Repository Guidelines

## Scope and safety

- This repository contains research code for mining and evaluating behavior patterns from smart-home sensor logs. Preserve scientific validity, reproducibility, and existing behavior unless the user explicitly requests a research change.
- Do not edit raw or labeled datasets, private data, secrets, credentials, `.env`, or API keys.
- Do not overwrite or commit generated artifacts under `output/`, `picture/`, `state/`, or `results/` unless explicitly requested.
- Do not change metrics, thresholds, data splits, seeds, aggregation, missing-run handling, or baseline definitions as an incidental part of another task.

## Before editing

1. Follow the lookup order below. Evaluation behavior changes require the matching `docs/evaluation_*.md` and `docs/known_issues.md`.
2. Inspect the implementation, tests, configuration, and actual CLI definition. Run `--help` only after confirming the entry point uses `argparse` and exits safely.
3. Treat code as evidence of current behavior, not automatic proof of research intent. If sources conflict, classify and report the conflict instead of guessing or legitimizing a suspected bug as specification.

## 圧縮された外部記憶

- 本書 → 関連メモ → 対象docs → コード。既読は再読せず、十分なら探索を止める。
- メモは `docs/codex_memory/`。評価Nは `EVALUATION_ROUTES.md` の該当節だけ取得: `rg -n -A 6 '^## eval6 ' docs/codex_memory/EVALUATION_ROUTES.md`（番号を置換）。場所は `CODEBASE_MAP.md`、理由は `DECISIONS.md`、問題は `KNOWN_ISSUES.md`、再開時だけ `CURRENT_STATE.md`。全メモ・全skillsを一括読込しない。
- メモは仕様ではない。変更箇所を現行docs・CLI・コードと照合し、未確定の研究意図は不一致として残す。経緯がなお必要な時だけ `ctx-agent-history-search` / `ctx` をworkspace・キーワード限定で使う。
- 対象ディレクトリの `rg -n` / `rg --files -g '*.py'` から探索を広げ、巨大ファイルは関数・見出しで範囲読込する。通常探索にデータ・成果物・`Hestia/`・全ファイル台帳を含めない。
- 終了時は再利用できる結論＋参照先だけ保存し、古い記述・重複を置換する。ログ・diffは転載しない。`CURRENT_STATE.md` は継続用に置換し、他の作業の完了を推測しない。
- 途中説明は最小限にし、判断が必要な点・重大な問題・方針変更等を1〜3文で伝える。最終報告は変更内容・確認結果・残る問題に絞る。

## Skills

- Use `research-evaluation` for numbered evaluation logic, metrics, CLIs, or tests; `baseline-implementation` for comparison algorithms; and `streamlit-evaluation-dashboard` for `app/` changes.
- Use `evaluation-readme-formatting` for evaluation Markdown only, and `reproducibility-and-output-contract` for repository-wide artifact or shared CSV/JSON contract changes.
- Use `codex-memory-maintenance` for memory/routing upkeep only. Load skills only for responsibilities changed.

## Implementation

- Keep changes focused; preserve public CLI, defaults, formats, paths, columns and CSV/JSON contracts unless migration is explicitly requested.
- Prevent train/test leakage when changing pattern generation, mappings, thresholds, or caches.
- Keep the Streamlit dashboard a thin wrapper around existing CLI commands; do not duplicate evaluation logic in `app/`.
- Update affected documentation, tests, and dashboard wiring when behavior or interfaces change.

## Verification

- Run focused syntax/import checks, safe relevant `--help` commands, and the narrowest applicable tests. For evaluation changes, also verify output headers/keys and deterministic behavior where applicable.
- Inspect the diff for unrelated edits. Report changed files, checks, research/compatibility impact, unresolved conflicts and unverified behavior.
