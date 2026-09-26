# Artifact Policy

この文書は、研究コードで生成されるファイルをGit管理するかどうかの方針です。`output/` はLLM実行前から共有できる入力・前処理・準備済みデータ、`results/<model>/` はLLM生成物、checkpoint、usage、モデル依存評価結果を置く。モデルAの成果物をモデルBが参照しないことを最優先する。

## 分類

| 種類 | 例 | Git管理方針 |
|---|---|---|
| 入力データ | `data/aruba.csv`, OpenSHS本体 | 管理しない |
| 秘密情報 | `.env`, APIキー | 管理しない |
| 再現に必要な固定成果物 | 論文で使う代表状態表、採用したLLM出力、最終評価表、掲載図 | 必要最小限だけ管理する |
| 評価結果 | `results/<model>/5_pattern_quality_without_low_information_judgment/`, `results/<model>/6_adl_match/`, `results/<model>/7_param_search/`, `results/<model>/8_vs_llm_own_id_fixed/` | 論文で使う値だけ残す。監査時は修正前ディレクトリも比較用に保持する |
| 一時生成物 | LLM runごとの試行ファイル、再生成できる図、ログ、途中CSV | 原則管理しない |
| 設定・プロンプト | `configs/*.yaml`, `prompts/*.md` | 管理する |

## 出力先

新しく整理された実験では、以下を使う。

```text
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

output/
├── 5_rule_filter/
├── 5_adl_evaluation_15_0_154days_fixed/
├── 5_adl_correspondence_baselines_fixed/
├── 6_adl_evaluation_aruba_individual_15_0_14days/
├── aruba_15_0_154days/
├── aruba_individual_15_0_14days/
├── tmp/
└── logs/
```

上記 `output/llm_direct_*` や旧 `output/aruba_*/llm_*` は移行元としてのみ残すlegacy成果物であり、新規実行は `results/<model>/` に書く。Gemini移行後に元ファイルを消す場合は、`scripts/migrate_gemini_results.py --cleanup-verified` が全移行先のSHA-256一致を確認してから、モデル依存ファイルだけを削除する。`output/cost_estimates/` は複数モデルの実行前見積もりなので例外として `output/` に維持する。

## 現行ディレクトリの扱い

- `state/`: 現行コードの代表状態テーブル出力。すぐには移動しない。
- `picture/`: 現行コードの図とLLM入力JSON出力。すぐには移動しない。
- `output/`: 入力、前処理、state series、network、Hestia/SwitchBot preparation、モデル非依存baseline、cost estimate。
- `results/<model>/`: LLM出力、checkpoint、usage、モデル依存の評価結果。`model_metadata.json` でprovider/model IDを検証する。

## 運用ルール

1. 論文・発表で使う評価結果は `results/` に置く。
2. LLM runごとの試行出力・checkpoint・metricsは `results/<model>/`、モデル非依存の中間生成物とログは `output/` に置く。
3. データセット本体とAPIキーはGit管理しない。
4. 既存の追跡済み生成物を外す場合は、先に `docs/operations/experiment_reproduction.md` の再現手順と必要成果物リストを更新する。
5. 生成物を削除する場合は、論文再現に不要であることを確認してから行う。

現在の `.gitignore` は `output/`, `picture/`, `results/` を除外しており、この文書が想定する「固定成果物の最小限管理」と運用が一致していない。正本の保管先を決めるまでは、既存成果物を一括でGitへ追加せず [known_issues.md](../research/known_issues.md) のKI-11として扱う。
