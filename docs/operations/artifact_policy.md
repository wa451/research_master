# Artifact Policy

この文書は、研究コードで生成されるファイルをGit管理するかどうかの方針です。すべての生成物は `output/<model>/` または `results/<model>/` に置く。前者は前処理・baseline・state series・実行ログ、後者はLLM生成物、checkpoint、usage、評価結果である。モデルAの成果物をモデルBが参照しないことを最優先する。

## 分類

| 種類 | 例 | Git管理方針 |
|---|---|---|
| 入力データ | `data/aruba.csv`, OpenSHS本体 | 管理しない |
| 秘密情報 | `.env`, APIキー | 管理しない |
| 再現に必要な固定成果物 | 論文で使う代表状態表、採用したLLM出力、最終評価表、掲載図 | 必要最小限だけ管理する |
| 評価結果 | `results/<model>/5_pattern_quality_without_low_information_judgment/`, `results/<model>/6_adl_match/`, `results/<model>/7_param_search/`, `results/<model>/8_vs_llm_own_id_fixed/` | 論文で使う値だけ残す。監査時は修正前ディレクトリも比較用に保持する |
| 一時生成物 | LLM runごとの試行ファイル、再生成できる図、ログ、途中CSV | 原則管理しない |
| ダッシュボード実行管理 | `output/<model>/logs/evaluation_dashboard/**/{batch_plan,batch_status}.json` | 実行時のコマンド固定と進捗表示だけに使う一時ログ。Git管理しない。 |
| 設定・プロンプト | `configs/*.yaml`, `prompts/*.md` | 管理する |

## 出力先

新しく整理された実験では、以下を使う。

```text
output/
└── <model>/
    ├── aruba_individual_{K}_{h}_{days}days/  # baseline、state seriesなどの中間成果物
    ├── 5_adl_evaluation_15_0_154days_fixed/
    ├── 5_adl_correspondence_baselines_fixed/
    ├── 6_adl_evaluation_aruba_individual_15_0_14days/
    ├── 9_hestia/                         # 生成ログ、truth、prepared state/network
    ├── 10_switchbot/                      # preparation、state table、network、segments
    ├── cost_estimates/
    └── logs/evaluation_dashboard/

results/
└── <model>/
    ├── aruba_individual_{K}_{h}_{days}days/  # 個別センサ既定の提案手法JSON、mode checkpoint、usage
    ├── api_smoke_tests/                 # 1 API requestの疎通・JSON形式検証（論文評価外）
    ├── llm_direct_aruba_individual_{K}_{h}_{days}days_time_split/  # 個別センサ既定のdirect-log JSON、usage
    ├── 5_pattern_quality_without_low_information_judgment/
    ├── 6_adl_match_individual_holdout_test_direct_time_split/
    ├── 7_param_search_14d_5runs_individual_holdout/  # 評価7の正式な14日・全28条件・各5 run集計
    ├── 8_vs_llm_own_id_fixed/
    ├── 8_proposed_own_id_fixed/
    ├── 9_hestia/
    └── 10_switchbot/
```

ルート直下の旧 `output/*` は移行元であり、新規実行では使用しない。既存Gemini成果物を `output/gemini-2.5-pro/` へ移すときは、まず `scripts/migrate_legacy_output_namespace.py --dry-run` で対象を確認し、次に `--cleanup-verified` を実行する。この操作は全コピー先のSHA-256一致を確認してから移行元だけを削除する。旧 `results/*` のLLM依存ファイルについては `scripts/migrate_gemini_results.py --cleanup-verified` を使う。

## 現行ディレクトリの扱い

- `state/`: 現行コードの代表状態テーブル出力。すぐには移動しない。
- `picture/`: 現行コードの図とLLM入力JSON出力。すぐには移動しない。
- `output/<model>/`: 前処理、state series、network由来中間物、Hestia/SwitchBot preparation、baseline、cost estimate、ダッシュボードログ。
- `results/<model>/`: LLM出力、checkpoint、usage、評価結果。`model_metadata.json` でprovider/model IDを検証する。

## 運用ルール

1. 論文・発表で使う評価結果は `results/<model>/` に置く。
2. 中間生成物・baseline・state series・ログは `output/<model>/`、LLM runごとの試行出力・checkpoint・metricsと評価結果は `results/<model>/` に置く。
3. データセット本体とAPIキーはGit管理しない。
4. 既存の追跡済み生成物を外す場合は、先に `docs/operations/experiment_reproduction.md` の再現手順と必要成果物リストを更新する。
5. 生成物を削除する場合は、論文再現に不要であることを確認してから行う。

現在の `.gitignore` は `output/`, `picture/`, `results/` を除外しており、この文書が想定する「固定成果物の最小限管理」と運用が一致していない。正本の保管先を決めるまでは、既存成果物を一括でGitへ追加せず [known_issues.md](../research/known_issues.md) のKI-11として扱う。
