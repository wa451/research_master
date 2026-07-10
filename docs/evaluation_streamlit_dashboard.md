# Streamlit Evaluation Dashboard

Python + Streamlitで評価4、評価5、評価6、評価7をローカル実行するための薄いGUIラッパーです。既存の研究ロジックは変更せず、画面上で設定した値から既存CLIコマンドを組み立てて `subprocess` で実行します。

## 起動方法

初回は依存関係を同期します。

```bash
uv sync
```

起動します。

```bash
streamlit run app/streamlit_app.py
```

`streamlit` コマンドが見つからない場合は次を使います。

```bash
uv run streamlit run app/streamlit_app.py
```

## 評価番号の選択

左サイドバーの「評価を選択」から以下を選びます。

| 評価 | 内容 |
|---|---|
| 評価4 | 1つのパターンJSONをADL区間と照合し、IoU、境界、interval hitを出す。 |
| 評価5 | frequency / rule-filtered / FP-Growth / transition_probability / proposedを、Useful non-redundant rateとFragmentation rateで比較する。 |
| 評価6 | proposedとdirect-log baselineのADL解釈ラベルset一致を比較する。 |
| 評価7 | proposedのみについて、Kとハミング距離を変えたADL解釈ラベル精度を比較する。 |

サイドバーの `dry-run` が有効な場合、コマンドと履歴だけを保存し、実処理は実行しません。重いLLM処理を走らせる前にコマンド確認に使ってください。

「ステップ実行」タブには一括実行モードがあります。

| モード | 内容 |
|---|---|
| 不足ファイル生成のみ | 評価本体や比較本体を実行せず、前段ステップのうち期待出力が不足しているコマンドだけを上から順に実行する。 |
| 不足ファイル生成 + 評価本体 | 前段ステップは不足分だけ生成し、その後に評価本体または比較本体を実行する。通常はこのモードで最初から最後まで実行できる。 |
| 全ステップを再実行 | 表示中の全ステップを上から順に実行する。既存出力があっても再実行するため、LLM抽出や結果上書きに注意する。 |

評価本体だけを再実行したい場合は、各ステップの個別ボタンも引き続き使えます。

## 共通設定

| 項目 | 説明 |
|---|---|
| Python実行方法 | READMEの既定に合わせて `uv run python` を既定にしています。 |
| run名 | ログディレクトリ名に使います。CLI引数には渡しません。 |
| dry-run | 実行せず、コマンドとログファイルだけを保存します。 |

`seed` や `overwrite` は対象CLIに実在する引数がないため、UI項目として追加していません。

## 評価4のステップ

参照ドキュメント: `docs/evaluation_4_labeled_casas_adl.md`

1. 代表状態・状態遷移ネットワークを作成  
   `scripts/run_build_network_from_labeled_casas.py` を実行します。入力は `--labeled-casas`, `--sensor-map`, `--days`, `--n-states`, `--hamming-threshold` です。

2. 提案手法LLMパターンを抽出  
   `scripts/run_llm_extraction.py` を実行します。APIキーを使う重い処理です。

3. 評価4を実行  
   `scripts/evaluate_adl_labels.py` を実行します。主な出力は `pattern_occurrences.csv`, `pattern_adl_mapping.csv`, `filtered_predictions.csv`, `adl_metrics_iou_*.csv`, `boundary_metrics_iou_*.csv`, `adl_interval_hit_metrics.csv`, `evaluation_summary.json`, `state_series.csv` です。

## 評価5のステップ

参照ドキュメント: `docs/evaluation_5_adl_correspondence.md`

1. 代表状態・状態遷移ネットワークを作成  
   `scripts/run_build_network_from_labeled_casas.py` を評価5条件で実行します。`state/aruba_{K}_{hamming}_{days}days.txt` と `picture/aruba_{K}_{hamming}_{days}days/state_transition_all.json` を作成します。

2. 提案手法LLM出力を生成  
   `scripts/run_llm_extraction.py` を実行し、評価5で使う proposed JSON を作成します。APIキーを使う重い処理です。

3. 評価5用 `state_series.csv` を作成  
   `scripts/evaluate_adl_labels.py --write-state-series` を使い、評価5専用の中間出力 `output/5_adl_evaluation/state_series.csv` を作成します。

4. 評価5を実行  
   `scripts/evaluate_adl_correspondence.py` を実行します。主な出力は `evaluation5_summary_by_method.csv`, `evaluation5_pattern_details.csv`, `evaluation5_summary.json` です。

変更可能な主な引数は、run数、train/test split、grounded/useless閾値、assigned ADL閾値、FP-Growth設定、transition_probability設定、baseline cache設定、fragmentation閾値、low-information閾値、Other状態・Other ADLの扱いです。評価5画面の `runs` は既定で5です。`runs=5` にすると、`run_llm_extraction.py --runs 5` で提案手法JSONを5回分作成し、評価本体も `--runs 5` で `evaluation5_summary_by_method.csv` に平均と標準偏差、`evaluation5_summary_by_method_by_run.csv` にrun別summaryを出力します。frequency / rule / FP-Growth / transition_probability はrun非依存のため最初の評価runだけで評価し、2回目以降は提案手法だけを評価します。FP-Growth / transition_probability の生成済みパターンは、既定で `output/5_adl_correspondence_baselines/` に保存して再利用します。複数run用テンプレート欄では、評価に使うrun別LLM JSONの存在確認も表示します。

結果タブでは `evaluation5_summary_by_method.csv` を選ぶと、`useful_non_redundant_pattern_rate`, `fragmentation_rate`, `contextless_useless_rate` を手法別に表示・グラフ化できます。`evaluation5_summary_by_method_by_run.csv` ではrunごとのばらつきを確認できます。`evaluation5_pattern_details.csv` では各パターンの `run`, `is_contextless_useless`, `is_fragmented`, `fragment_parent_ids`, `is_useful_non_redundant` を確認できます。

## 評価6のステップ

参照ドキュメント: `docs/evaluation_6_adl_interpretation_set.md`

1. 30日版の代表状態・状態遷移ネットワークを作成  
   `scripts/run_build_network_from_labeled_casas.py --days 30` を実行します。

2. 提案手法LLM出力を生成  
   `scripts/run_llm_extraction.py --days 30` を実行します。`--runs` で複数runを生成できます。

3. 評価6用 `state_series.csv` を作成  
   `scripts/evaluate_adl_labels.py` で比較用の状態系列を `output/6_adl_evaluation_30/state_series.csv` へ保存します。

4. LLM単独ベースラインを生成  
   `scripts/run_direct_log_baseline.py --log-days 30 --extract-only` を実行します。

5. 評価6の手法間比較を実行  
   `scripts/evaluate_6_compare_adl_interpretation_set.py` を実行します。主な出力は `evaluation6_method_comparison.csv`, `evaluation6_method_comparison_by_run.csv`, `evaluation6_pattern_set_details_by_method.csv`, `evaluation6_by_*_by_method.csv`, `evaluation6_comparison_summary.json` です。

標準条件の中間出力はREADMEに合わせて `output/6_adl_evaluation_30/` を使います。Kやハミング距離を変えた場合は `output/6_adl_evaluation_{K}_{hamming}_{days}days/` を使えます。

## 評価7のステップ

参照ドキュメント: `docs/evaluation_7_parameter_sensitivity_adl_interpretation.md`

1. 条件別の代表状態・状態遷移ネットワークを作成  
   `scripts/run_build_network_from_labeled_casas.py` を条件ごとに実行します。`state/aruba_{K}_{hamming}_{days}days.txt` や `picture/aruba_{K}_{hamming}_{days}days/state_transition_all.json` がない場合に使います。

2. 条件別の提案手法LLM出力を生成  
   `scripts/run_llm_extraction.py` を条件ごとに実行します。`output/aruba_{K}_{hamming}_{days}days/llm_sequences_modes_{K}_{hamming}_{days}days_1.json` がない場合に使います。

3. 条件別の `state_series.csv` を作成  
   `scripts/evaluate_adl_labels.py --write-state-series` を条件ごとに実行します。`output/6_adl_evaluation_{K}_{hamming}_{days}days/state_series.csv` がない場合に使います。

4. 評価7を実行  
   `scripts/evaluate_7_parameter_sensitivity_adl_interpretation.py` を実行します。代表状態数Kとハミング距離を複数指定し、提案手法JSONと状態系列CSVを条件ごとに読み込んでADL解釈ラベルset一致を比較します。

主な出力は `evaluation7_condition_summary.csv`, `evaluation7_condition_summary_by_run.csv`, `evaluation7_pattern_set_details.csv`, `evaluation7_by_pred_label.csv`, `evaluation7_by_true_label.csv`, `evaluation7_by_time_band.csv`, `evaluation7_summary.json` です。

Streamlit画面では、`代表状態数 K` と `ハミング距離閾値` を `10,15,20,30` のようにカンマ区切りまたは空白区切りで指定できます。`不足ファイル作成ステップを表示` をONにすると、各条件ごとの前段3ステップも表示されます。一括実行の「不足ファイル生成 + 評価本体」では、既に出力が揃っている前段ステップを対象外にし、不足している条件別ファイルを作ったうえで評価7本体を実行します。結果タブでは条件別summaryと `evaluation7_summary.json` の `best_condition` を確認できます。

## ログとコマンド履歴

ログは以下に保存されます。

```text
output/logs/evaluation_dashboard/
```

各ステップのログはrun名付きのサブディレクトリに保存されます。一括実行では `{run名}_batch` のログディレクトリに、実行したコマンドを番号付きログで保存します。コマンド履歴は `output/logs/evaluation_dashboard/command_history.jsonl` に追記されます。

## 結果表示と過去run比較

「結果比較」タブでは、既存の `results/` と評価6の中間 `output/` からCSV/JSONを自動検出します。

- CSVは `st.dataframe` で表示します。
- CSVは「表示するカラム」で、見たい列だけに絞り込めます。
- JSONは整形表示します。
- `method` と F1 / precision / recall / Jaccard などの列があるCSVは棒グラフ表示できます。
- 複数の summary CSV を選ぶと、source列付きで結合表示できます。
- 評価4、評価5、評価6、評価7の各READMEにある「結果の読み方」に合わせて、見るべきファイル順と読み方を結果タブ内に表示します。
- 表示ファイルのプルダウンは、READMEで推奨している確認順を優先して並べます。

## トラブルシューティング

| 症状 | 確認点 |
|---|---|
| `streamlit` が見つからない | `uv sync` 後に `uv run streamlit run app/streamlit_app.py` を使う。 |
| 入力ファイルがmissingになる | 前段ステップが未実行か、K / hamming / days の条件が入力ファイル名とずれていないか確認する。評価7では `skip-missing-conditions` で未生成条件をスキップできる。 |
| LLM抽出で失敗する | `.env` の `GEMINI_API_KEY` とネットワーク接続を確認する。ログにはAPIキー値を出さないよう簡易redactionしています。 |
| 評価5/6でrunが足りない | `--runs` と実在するJSON数を揃えるか、`skip-missing-runs` を有効化する。 |
| CLIでは動くが画面では動かない | コマンドプレビューをコピーし、同じworking directoryで実行して差分を見る。 |

## 既存CLIとの関係

このアプリは既存CLIを呼び出すだけです。従来通り以下のようなコマンド実行も可能です。

```bash
uv run python scripts/evaluate_adl_labels.py --help
uv run python scripts/evaluate_adl_correspondence.py --help
uv run python scripts/evaluate_6_compare_adl_interpretation_set.py --help
uv run python scripts/evaluate_7_parameter_sensitivity_adl_interpretation.py --help
```
