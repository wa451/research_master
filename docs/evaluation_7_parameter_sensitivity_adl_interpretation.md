# 評価7: 提案手法のADL解釈ラベル精度パラメータ感度分析

## 目的

提案手法単独について、代表状態数 `K` とハミング距離閾値を変化させたときのADL解釈ラベル精度を比較し、最適なパラメータ条件を選ぶ。

評価6と同じset評価を使うが、評価7ではLLM単独ベースラインとは比較しない。比較対象は提案手法のみである。

## 評価方法

各パターンについて以下を比較する。

| 種類 | 内容 |
|---|---|
| 予測ラベル | LLMが各パターンに付与した `ADL系列ラベル`。 |
| 正解ラベル | パターン出現区間がCASAS正解ADL区間と重なった結果から得られるADL集合。 |

ラベル順序は使わず、ADL集合として評価する。

| 指標 | 定義 |
|---|---|
| Accuracy / Exact Set Match | `pred_adl_set == true_adl_set` の割合。 |
| Jaccard Similarity | `|pred ∩ true| / |pred ∪ true|`。 |
| Multi-label Precision | `|pred ∩ true| / |pred|`。 |
| Multi-label Recall | `|pred ∩ true| / |true|`。 |
| Multi-label F1 | PrecisionとRecallの調和平均。 |

既定では `mean_multilabel_f1` が最適条件の選択指標である。`--selection-metric` で `mean_jaccard` や `mean_accuracy` などに変更できる。

## 入力

| 入力 | 既定・例 | 役割 |
|---|---|---|
| 提案手法LLM JSON | `output/aruba_{K}_{hamming}_{days}days/llm_sequences_modes_{K}_{hamming}_{days}days_1.json` | `ADL系列ラベル` を持つ提案手法出力。 |
| 状態系列CSV | `output/6_adl_evaluation_{K}_{hamming}_{days}days/state_series.csv` | パターン出現区間を検索する状態系列。標準条件 `15_1_30days` のみ `output/6_adl_evaluation_30/state_series.csv` も既定で使う。 |
| ADL正解データ | `new_labeled_data/aruba.txt` | CASAS activity `begin/end` からADL正解区間を内部生成する。 |

条件ごとの入力パスが既定命名と異なる場合は、`--patterns-template` と `--state-series-template` を使う。

## 実行コマンド

小さい設定で既存出力だけを使って確認する例:

```bash
uv run python scripts/evaluate_7_parameter_sensitivity_adl_interpretation.py \
  --n-states-list 15 30 \
  --hamming-thresholds 1 \
  --days 30 \
  --runs 1 \
  --labeled-casas new_labeled_data/aruba.txt \
  --output-dir results/7_param_search \
  --min-overlap-ratio-for-true-label 0.10 \
  --selection-metric mean_multilabel_f1 \
  --skip-missing-conditions
```

代表状態数とハミング距離を総当たりする例:

```bash
uv run python scripts/evaluate_7_parameter_sensitivity_adl_interpretation.py \
  --n-states-list 10,15,20,30 \
  --hamming-thresholds 0,1,2,3 \
  --days 30 \
  --runs 1 \
  --labeled-casas new_labeled_data/aruba.txt \
  --output-dir results/7_param_search \
  --skip-missing-conditions
```

複数runを平均する場合:

```bash
uv run python scripts/evaluate_7_parameter_sensitivity_adl_interpretation.py \
  --n-states-list 15 30 \
  --hamming-thresholds 1 \
  --days 30 \
  --runs 5 \
  --skip-missing-runs \
  --skip-missing-conditions
```

## 出力

出力先: `results/7_param_search/`

| 出力 | 内容 |
|---|---|
| `evaluation7_condition_summary.csv` | 条件ごとの主比較表。`rank`, `K`, hamming, Accuracy, Jaccard, Precision, Recall, F1を含む。 |
| `evaluation7_condition_summary_by_run.csv` | runごとの条件別summary。 |
| `evaluation7_pattern_set_details.csv` | 条件別・run別・パターン別詳細。 |
| `evaluation7_by_pred_label.csv` | 条件別・予測ラベル別集計。 |
| `evaluation7_by_true_label.csv` | 条件別・正解ラベル別集計。 |
| `evaluation7_by_time_band.csv` | 条件別・時間帯別集計。 |
| `evaluation7_summary.json` | 入力条件、閾値、skipped条件、最適条件、出力ファイル一覧。 |

## 最適条件の判断

`evaluation7_condition_summary.csv` の `rank=1` が、`--selection-metric` に基づく最適条件である。既定では `mean_multilabel_f1` が最大の条件を選ぶ。同点の場合は、Jaccard、Accuracy、代表状態数、ハミング距離の順に安定的に順位付けする。

`evaluation7_summary.json` の `best_condition` にも同じ情報を保存する。

## Streamlitアプリからの実行

```bash
uv run streamlit run app/streamlit_app.py
```

左サイドバーで「評価7」を選び、`代表状態数 K` と `ハミング距離閾値` をカンマ区切りまたは空白区切りで入力する。

`不足ファイル作成ステップを表示` をONにすると、各条件ごとに以下のステップが表示される。

1. 代表状態・状態遷移ネットワークを作成
2. 提案手法LLM出力を生成
3. 評価7用 `state_series.csv` を作成
4. 評価7を実行

「不足ファイル生成コマンドを一括実行」を押すと、前段3ステップのうち期待出力が不足しているコマンドだけを上から順に実行する。評価7本体は一括実行では走らないため、条件別入力が揃ったことを確認してから個別ボタンで実行する。各ステップには入力/出力ファイルの存在チェックも出るため、一部だけ再実行したい場合は個別ボタンで実行できる。Streamlitは内部処理を重複実装せず、既存CLIと評価7スクリプトを呼び出す。

結果タブでは `evaluation7_condition_summary.csv` と `evaluation7_summary.json` を確認でき、最適な代表状態数・ハミング距離も表示される。

## 注意点

- 評価7スクリプト自体は後段評価であり、状態遷移ネットワーク構築やLLM抽出は実行しない。Streamlitの前段ステップは既存CLIを呼び出して不足入力を作るための補助である。
- 必要な `state_series.csv` と提案手法JSONがない条件は、既定ではエラーになる。
- 感度分析で未生成条件を含めたい場合は、先に `run_build_network_from_labeled_casas.py`, `run_llm_extraction.py`, `evaluate_adl_labels.py --write-state-series` で条件別入力を作成する。
- `--skip-missing-conditions` を付けると、入力がない条件をsummary JSONへ記録してスキップする。
