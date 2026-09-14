# 文書案内

用途からフォルダを選び、必要な文書だけ読む。研究仕様と未解決事項は、実装の現在の挙動とは別に扱う。

| フォルダ | 内容 | 主な入口 |
|---|---|---|
| [architecture/](architecture/) | 処理構成、データフロー、Python台帳、構造整理の記録 | [責務一覧](architecture/code_inventory.md)、[パイプライン](architecture/pipeline.md) |
| [evaluations/](evaluations/) | 評価1〜10の目的、入力、指標、実行手順 | [評価一覧](../README.md#評価文書) |
| [research/](research/) | 論文採用条件と未解決の研究・互換性判断 | [パラメータ](research/paper_parameters.md)、[既知の不一致](research/known_issues.md) |
| [operations/](operations/) | 再現、成果物、Streamlit操作 | [再現手順](operations/experiment_reproduction.md)、[ダッシュボード](operations/dashboard.md) |
| [integrations/](integrations/) | 外部データセット・外部プロジェクトとの接続 | [Hestia接続](integrations/hestia_dataset_integration.md)、[SwitchBot接続](integrations/switchbot_logger.md) |
| [codex_memory/](codex_memory/) | Codexが必要な範囲だけ読む短い作業索引。研究仕様の正本ではない | [作業入口](codex_memory/CODEBASE_MAP.md)、[評価別ルート](codex_memory/EVALUATION_ROUTES.md) |
| [archive/](archive/) | 現行仕様ではない過去のレビュー記録 | [レビュー記録](archive/review_and_improvement_roadmap.md) |

評価を変更する前は、該当する`evaluations/`の文書と[既知の不一致](research/known_issues.md)を確認する。詳細なPythonファイル名が必要な場合だけ[Python台帳](architecture/python_file_inventory.md)を開く。
