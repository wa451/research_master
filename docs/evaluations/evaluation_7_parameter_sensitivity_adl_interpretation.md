# 評価7: 14日・全28条件・各5 runのADL解釈ラベル精度パラメータ感度分析

> **モデル別保存:** 条件別LLM JSON/checkpointは `results/<model>/aruba_{K}_{h}_{days}days/`、正式な複数run集計は `results/<model>/7_param_search_14d_5runs/` に保存する。state seriesとnetworkは `output/` / `picture/` に残し、全モデルで共有する。

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

評価状態と分母は評価6と共通である。conditionalは出現あり・正解定義可能なレコードを分母とし、end-to-endは `no_adl_overlap` だけを正解未定義として除外して、`no_occurrence` を0点で含める。両方とも `prediction_status=missing|unknown` を0点で分母に含める。coverage、各状態の件数・割合、時間帯境界横断件数も条件別に保存する。

既定では後方互換列 `mean_multilabel_f1`、すなわち `end_to_end_mean_multilabel_f1` が最適条件の選択指標である。`--selection-metric` で `mean_jaccard` や `mean_accuracy` などに変更できる。

## 入力

| 入力 | 既定・例 | 役割 |
|---|---|---|
| 提案手法LLM JSON | `output/aruba_{K}_{hamming}_{days}days/llm_sequences_modes_{K}_{hamming}_{days}days_1.json` | `ADL系列ラベル` を持つ提案手法出力。 |
| 状態系列CSV | `output/6_adl_evaluation_{K}_{hamming}_{days}days/state_series.csv` | 当該入力条件の代表状態定義を固定して全220日を写像し、パターン出現区間を検索する照合系列。 |
| ADL正解データ | `new_labeled_data/aruba.txt` | CASAS activity `begin/end` からADL正解区間を内部生成する。 |

条件ごとの入力パスが既定命名と異なる場合は、`--patterns-template` と `--state-series-template` を使う。

| 実行区分 | 条件 | run | state series | 出力先 |
|---|---|---:|---|---|
| 正式評価 | `K=10,15,20,25,30,35,40` と `hamming=0,1,2,3` の全28条件、`days=14` | 各条件 `1--5` | 条件別パス | `results/<model>/7_param_search_14d_5runs/` |

`output/6_adl_evaluation_{K}_{hamming}_{days}days/state_series.csv` を各条件の入力に使う。全条件を同じ5 runで評価し、条件ごとの平均と標準偏差から最適条件を選ぶ。評価5・6の正式条件 `hamming=0` との不一致は [KI-01](../research/known_issues.md#ki-01)、state seriesの前処理差は [KI-06](../research/known_issues.md#ki-06) で追跡している。

## 実行コマンド

`--days 14` は状態遷移ネットワークの構築およびLLM入力に使う先頭14日を表す。各条件の `evaluate_adl_labels.py --write-state-series` は、その14日条件で作成した代表状態定義を固定して全220日を写像した照合系列を生成し、評価7のADL集合整合性は全220日で算出する。

`evaluate_adl_labels.py` のstate-series前処理を明示しない現行フローは `event-driven` 既定を使う。抽出系と同じ1秒Sample-and-Hold・遅延OFFへ統一するかは [KI-06](../research/known_issues.md#ki-06) の未解決事項である。

小さい設定で既存出力だけを使って確認する例（正式条件外）:

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

正式な全条件・5 runの実行:

```bash
uv run python scripts/evaluate_7_parameter_sensitivity_adl_interpretation.py \
  --n-states-list 10,15,20,25,30,35,40 \
  --hamming-thresholds 0,1,2,3 \
  --days 14 \
  --runs 5 \
  --labeled-casas new_labeled_data/aruba.txt \
  --output-dir results/<model>/7_param_search_14d_5runs
```

上記の条件はCLI既定でも使われる。既存の30日・二段階探索の成果物を上書きしないよう、正式出力先は `7_param_search_14d_5runs/` とする。

## 旧二段階探索との互換性

`--conditions-file` と `run_evaluation7_top_condition_repeats.py` は、過去の30日・上位10条件二段階探索を再評価するために残す。正式な評価7の入力・出力・見積もりには使わない。

## 出力

出力先: `results/7_param_search/`

| 出力 | 内容 |
|---|---|
| `evaluation7_condition_summary.csv` | 条件ごとの主比較表。順位、conditional/end-to-end指標、coverage、各状態の件数・割合を含む。従来の `mean_*` はend-to-endの別名。 |
| `evaluation7_condition_summary_by_run.csv` | runごとの条件別summary。 |
| `evaluation7_pattern_set_details.csv` | 条件別・run別・パターン別詳細。 |
| `evaluation7_by_pred_label.csv` | 条件別・予測ラベル別集計。 |
| `evaluation7_by_true_label.csv` | 条件別・正解ラベル別集計。 |
| `evaluation7_by_time_band.csv` | 条件別・時間帯別集計。 |
| `evaluation7_summary.json` | 入力条件、閾値、skipped条件、最適条件、出力ファイル一覧。 |

正式結果は `results/<model>/7_param_search_14d_5runs/` に保存する。各条件のsummaryには `num_runs=5`、run別summaryにはrun 1--5が記録される。旧二段階探索の結果は比較用に既存ディレクトリへ残す。

## 最適条件の判断

`evaluation7_condition_summary.csv` の `rank=1` が、`--selection-metric` に基づく最適条件である。既定ではend-to-endの `mean_multilabel_f1` が最大の条件を選ぶ。同点の場合は、end-to-endのJaccard、Accuracy、代表状態数、ハミング距離の順に安定的に順位付けする。conditional指標は併記するが、現CLIの条件選択には使用しない。

`evaluation7_summary.json` の `best_condition` にも同じ情報を保存する。

## Streamlitアプリからの実行

```bash
uv run streamlit run app/streamlit_app.py
```

左サイドバーで「評価7」を選ぶ。正式条件の `days=14`、全28の `K/hamming` 条件、各5 runは画面で固定される。`チャタリング除去時間（秒）` は全条件の代表状態・状態遷移ネットワーク作成コマンドへ共通で渡される。

画面では、以下の正式手順を表示する。

1. 代表状態・状態遷移ネットワークを作成
2. 全条件の提案手法LLM run 1--5を生成
3. 評価7用 `state_series.csv` を作成
4. 全28条件をrun 1--5で評価し、条件ごとの平均と標準偏差を集計

「不足ファイル生成 + 評価本体」を使うと、不足しているステップだけを上から実行し、最後に全条件の5回平均を計算する。各ステップには入力/出力ファイルの存在チェックも出るため、一部だけ再実行したい場合は個別ボタンで実行できる。Streamlitは内部処理を重複実装せず、既存CLIと評価7スクリプトを呼び出す。

結果タブでは `evaluation7_condition_summary.csv` と `evaluation7_summary.json` を確認でき、最適な代表状態数・ハミング距離も表示される。

同じ画面の「API疎通・JSON形式テスト」は、評価実験と切り離した事前確認用である。`K=15, hamming=0, Morning` を既定として、選んだ1条件・1 run・1時間帯のプロンプトを実APIへ1回だけ送り、初回応答がJSON配列のみで返り、各要素が `パターン名`、`ADL系列ラベル`、`解釈の根拠`、`遷移のパターン` の4キーとプロンプトの値制約を満たすかを検証する。API許可は既定OFFで、失敗時もraw responseと検証JSONを `results/<model>/api_smoke_tests/` に保存する。これは正式な評価7の5 runやcheckpointを更新しない。

## 注意点

- 評価7スクリプト自体は後段評価であり、状態遷移ネットワーク構築やLLM抽出は実行しない。Streamlitの前段ステップは既存CLIを呼び出して不足入力を作るための補助である。
- 必要な `state_series.csv` と提案手法JSONがない条件は、既定ではエラーになる。
- 許可語彙は `Sleep, Wake-up, Meal, Relax, Outing, Hygiene, Toileting, Housework, Work, Other` の10カテゴリである。`Noise`, `Ambiguous` およびその他の語彙外予測は `unknown` として警告・記録し、`Other` へ変換しない。
- time-band awareレコードは、半開区間 `[start,end)` 全体が同じ時間帯に含まれるexact出現だけを使う。境界横断は除外し、件数・割合を保存する。
- 感度分析で未生成条件を含めたい場合は、先に `run_build_network_from_labeled_casas.py`, `run_llm_extraction.py`, `evaluate_adl_labels.py --write-state-series` で条件別入力を作成する。
- `--skip-missing-conditions` を付けると、入力がない条件をsummary JSONへ記録してスキップする。
- `--conditions-file` は過去の選抜条件を再評価する互換用であり、正式な全28条件評価には使用しない。
