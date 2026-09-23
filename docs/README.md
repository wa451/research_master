# 文書案内

ここでは、人が読む研究・運用文書と、コーディングAIが作業時にだけ読む内部索引を分けています。研究仕様と未解決事項は、実装の現在の挙動とは別に扱います。

## 人が読む文書

研究を初めて読む人は、まず[研究の概要](overview.md)から始めてください。専門用語、研究の流れ、読む順番を説明しています。

| 目的 | 読む文書 |
|---|---|
| 研究の狙いと全体像を知る | [研究の概要](overview.md)、[パイプライン](architecture/pipeline.md) |
| 特定の評価の目的・指標・手順を知る | [評価一覧](../README.md#評価文書)から対象の評価1〜10 |
| 実験を再現・実行する | [再現手順](operations/experiment_reproduction.md)、対象評価の文書 |
| 論文で使う条件と注意点を確認する | [論文採用パラメータ](research/paper_parameters.md)、[既知の不一致](research/known_issues.md) |
| ダッシュボードや成果物を扱う | [ダッシュボード](operations/dashboard.md)、[成果物ポリシー](operations/artifact_policy.md) |
| Hestia・SwitchBotを入力として使う | [Hestia接続](integrations/hestia_dataset_integration.md)、[SwitchBot接続](integrations/switchbot_logger.md) |
| 実装を調査・変更する | [実装の責務一覧](architecture/code_inventory.md)、必要時のみ[Python台帳](architecture/python_file_inventory.md) |

`archive/` は過去の検討記録です。現行の研究仕様や再現手順としては使いません。

## AI／エージェントだけが読む文書

リポジトリ直下の `ai/` と `AGENTS.md` は、コーディングAIが必要最小限のファイルを安全に調べるための内部指示です。`docs/` の外に置き、人が研究内容を理解したり、研究条件を判断したりする根拠にはしません。

| AIの作業 | 内部索引 |
|---|---|
| 実装・テストの場所を探す | [作業入口](../ai/CODEBASE_MAP.md) |
| 評価ごとの最短調査経路をたどる | [評価別ルート](../ai/EVALUATION_ROUTES.md) |
| 過去の作業再開時だけ確認する | [現在のチェックポイント](../ai/CURRENT_STATE.md) |
| 既存の実装上の注意を探す | [内部問題索引](../ai/KNOWN_ISSUES.md) |

評価を変更する前は、AIも人も対象の`evaluations/`文書と[既知の不一致](research/known_issues.md)を確認します。内部索引は研究仕様を置き換えません。
