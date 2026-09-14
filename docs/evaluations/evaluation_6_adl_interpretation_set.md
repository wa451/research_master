# 評価6: LLM解釈ラベルとADL重なりラベルのSet一致評価

## 評価の要約

LLMが各パターンへ付与した `ADL系列ラベル` と、パターン出現区間がCASAS正解ADL区間と重なった結果から得られるADL集合を比較する。評価はset一致で行い、ラベル順序は使わない。パターン名、ADL集合、解釈根拠は同じ系列解釈に基づく一体的な出力であり、本評価をパターン名と根拠の意味的正当性を確認する主要な定量代理評価として位置付ける。ただし、自然言語根拠の文単位の忠実性を直接評価するものではない。評価6では提案手法単体の評価は行わず、提案手法と、同じ期間の前処理済み代表状態系列を直接LLMへ入力するLLM単独ベースラインを、先頭14日の入力条件に揃えて比較する。抽出・LLM入力は14日だが、出現検索とADL照合には、この14日条件の代表状態定義で写像した全220日の状態系列を使う。提案手法では、同じ `遷移のパターン` が複数時間帯で抽出された場合、表示・保存上は1つのグループにまとめ、評価時には `sequence × time_band` 単位へ展開する。

## RQ

| RQ | 内容 |
|---|---|
| RQ6-1 | 一体的に生成した解釈のADL集合は、実際のADL重なり集合とどの程度整合するか。 |
| RQ6-2 | LLMは余計なADLラベルを付けすぎていないか。 |
| RQ6-3 | LLMは正解ADLラベルを拾えているか。 |
| RQ6-4 | 提案手法はLLM単独ベースラインよりADL解釈ラベルのset一致が高いか。 |

## 評価指標

| 指標 | 定義 |
|---|---|
| Exact Set Match | `pred_adl_set == true_adl_set` の割合。 |
| Jaccard Similarity | `|pred ∩ true| / |pred ∪ true|`。 |
| Multi-label Precision | `|pred ∩ true| / |pred|`。 |
| Multi-label Recall | `|pred ∩ true| / |true|`。 |
| Multi-label F1 | PrecisionとRecallの調和平均。 |

`["Meal", "Relax"]` と `["Relax", "Meal"]` は同じ集合として扱う。

同じ5つのset指標を、次の2つの分母で出力する。

| 指標スコープ | 分母と0点の扱い |
|---|---|
| conditional ADL consistency | `occurrence_status=matched` かつ `truth_status=defined` のレコード。`prediction_status=missing` と `unknown` は除外せず0点にする。 |
| end-to-end ADL consistency | 全レコードから、正解集合を定義できない `occurrence_status=matched, truth_status=no_adl_overlap` だけを除く。`no_occurrence`、`missing`、`unknown` は0点にする。 |

`no_adl_overlap` はモデルの正誤を決める正解集合そのものがないため、conditionalだけでなくend-to-endからも除外する。この方針は、モデル失敗を隠さないための除外ではなく、未定義の正解を恣意的に誤りへ変えないためのものである。従来列 `mean_accuracy`, `mean_jaccard`, `mean_multilabel_*` は後方互換性のため残し、明示的な `end_to_end_mean_*` の別名とする。

併せて、`occurrence_coverage`, `truth_coverage`, `no_occurrence_rate`, `no_adl_overlap_rate`, `missing_prediction_rate`, `unknown_label_rate`、各状態の件数、時間帯境界横断出現の件数・割合を出力する。`truth_coverage` と `no_adl_overlap_rate` の分母は出現ありのレコード数、それ以外の状態率の分母は全評価レコード数である。

## 入力と出力

### 入力

| 入力 | 正式14日評価で明示するパス | 役割 |
|---|---|---|
| 提案手法LLM JSON | `output/aruba_15_0_14days/llm_sequences_modes_15_0_14days_1.json` | `time_band_interpretations` を持つ提案手法出力。 |
| LLM単独ベースラインJSON | `output/llm_direct_15_0_14days/1.json` | 同期間の前処理済み代表状態系列をLLMへ直接入力した出力。 |
| 14日条件の全220日照合系列 | `output/6_adl_evaluation_15_0_14days/state_series.csv` | 先頭14日で作成した代表状態定義を固定し、全220日で両手法の出現区間を同条件検索する。 |
| ADL正解データ | `new_labeled_data/aruba.txt` | CASAS activity `begin/end` からADL正解区間を内部生成する。 |

この表はargparse既定値ではない。省略時の現行CLIは、提案手法に `output/aruba_15_1_14days/llm_sequences_modes_15_1_14days_1.json`、LLM単独に `output/llm_direct_15_1_14days/1.json`、state seriesに互換パス `output/6_adl_evaluation_14/state_series.csv` を使う。`--labeled-casas` を省略した場合は `output/adl_label_intervals.csv` を使い、出力先は設定値から `results/6_adl_match/15_1_14days/` へ解決される。さらに `--n-states` と `--hamming-threshold` のargparse既定値は未指定（summaryではnull）である。正式14日評価ではStep 7--8のとおり `--days 14 --n-states 15 --hamming-threshold 0` と各パスを明示する。既定値と正式条件の不一致は [KI-01](../research/known_issues.md#ki-01) および [KI-08](../research/known_issues.md#ki-08) で追跡している。

### 出力

| 出力 | 内容 |
|---|---|
| `results/6_adl_match/15_0_14days/evaluation6_method_comparison.csv` | 提案手法とLLM単独ベースラインの主比較表。`--runs` が2以上の場合はrun平均と標準偏差。 |
| `results/6_adl_match/15_0_14days/evaluation6_method_comparison_by_run.csv` | runごとの手法別summary。5回平均の元データ。 |
| `results/6_adl_match/15_0_14days/evaluation6_llm_usage_comparison.csv` | 手法ごとの記録済み1 run合計トークン数・API応答時間。`prompt_tokens`、`response_tokens`、`total_tokens` はそれぞれGemini APIの `promptTokenCount`、`candidatesTokenCount`、`totalTokenCount` に対応する。欠損runは0で補完せず、完全な記録があるrun数を併記する。 |
| `results/6_adl_match/15_0_14days/evaluation6_pattern_set_details_by_method.csv` | 手法別・パターン別詳細。4状態、raw/unknown予測ラベル、conditional/end-to-end指標、境界横断監査を含む。`num_occurrences` は評価8の監査前件数として保持する。 |
| `results/6_adl_match/15_0_14days/evaluation6_by_pred_label_by_method.csv` | 手法別・予測ラベル別集計。 |
| `results/6_adl_match/15_0_14days/evaluation6_by_true_label_by_method.csv` | 手法別・正解ラベル別集計。 |
| `results/6_adl_match/15_0_14days/evaluation6_by_time_band_by_method.csv` | 手法別・時間帯別集計。 |
| `results/6_adl_match/15_0_14days/evaluation6_comparison_summary.json` | 比較評価の再現条件。 |

## 結果の読み方

| 順序 | ファイル | 読み方 |
|---|---|---|
| 1 | `evaluation6_method_comparison.csv` | `conditional_mean_*` と `end_to_end_mean_*` を区別して見る。`--runs 5` の場合は5回平均と標準偏差、およびcoverage/rateの平均も確認する。 |
| 2 | `evaluation6_llm_usage_comparison.csv` | `num_runs_with_complete_metrics` を手法ごとに確認して入力・応答・合計トークン数を比較する。現保存結果では両手法とも第1--5試行の完全な使用量記録を用いるが、実装は共通run集合へ自動制限しない。期間による入力規模の比較では、提案手法の各時間帯の入力を期間ごとに合計し、LLM単独の上限超過は実行ログに記録されたAPIエラーに基づいて判定する。 |
| 3 | `evaluation6_method_comparison_by_run.csv` | runごとのばらつきを確認する。平均値だけでなく、特定runだけ大きく外れていないかを見る。 |
| 4 | `evaluation6_pattern_set_details_by_method.csv` | `occurrence_status`, `truth_status`, `prediction_status`, `is_metric_evaluable`, `is_end_to_end_evaluable`, `raw_pred_adl_labels`, `unknown_pred_adl_labels` と2種類の指標列を見てズレの原因を確認する。 |
| 5 | `evaluation6_comparison_summary.json` | 再現条件として、入力パス、run数、14日版で揃っているか、`min_overlap_ratio_for_true_label`, 許可ラベル、使用量集計元を確認する。 |

時間帯別の傾向を見る場合は、`evaluation6_by_time_band*.csv` でMorning, Daytime, Night, Midnightごとの平均指標を見る。ラベル別の傾向を見る場合は、`evaluation6_by_pred_label*.csv` で付けすぎているラベル、`evaluation6_by_true_label*.csv` で拾えていない正解ラベルを見る。

## 実行手順

### 1. 🟨 **条件付き** 14日版の状態遷移ネットワークを構築する

`state/aruba_15_0_14days.txt` がなければ実行する。評価6では提案手法とLLM単独ベースラインの入力日数を14日に揃える。

```bash
uv run python scripts/run_build_network_from_labeled_casas.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --sensor-map configs/aruba_sensor_map.json \
  --days 14 \
  --hamming-threshold 0 \
  --smoothing-window-sec 5
```

### 2. 🟨 **条件付き** 提案手法の14日版LLM出力を生成する

`output/aruba_15_0_14days/llm_sequences_modes_15_0_14days_1.json` がなければ実行する。既に同じ条件のLLM出力がある場合はスキップしてよい。1回分だけ比較する場合はこのコマンドでよい。

```bash
uv run python scripts/run_llm_extraction.py --days 14 --hamming-threshold 0
```

### 3. 🟩 **スキップ可** 提案手法の14日版LLM出力を5回分生成する

5回平均を出す場合に実行する。`output/aruba_15_0_14days/llm_sequences_modes_15_0_14days_1.json` から `_5.json` までを作成する。既に存在する時間帯別チェックポイントや統合JSONはスキップされる。

```bash
uv run python scripts/run_llm_extraction.py \
  --days 14 \
  --hamming-threshold 0 \
  --runs 5
```

### 4. 🟨 **条件付き** 評価6用の全220日照合系列を作る

`output/6_adl_evaluation_15_0_14days/pattern_occurrences.csv` または `output/6_adl_evaluation_15_0_14days/state_series.csv` がなければ実行する。この系列は、先頭14日で作成した代表状態表を全220日のセンサログへ適用した照合用中間ファイルであり、`output/` に保存する。ディレクトリ名の `14days` は抽出・LLM入力条件を表し、照合系列の長さを表さない。

次のコマンドは `--state-series-preprocessing` を指定しないため、現行CLIの `event-driven` 既定を使う。抽出系の1秒Sample-and-Hold・遅延OFF系列とどちらへ統一するかは未解決であり、[KI-06](../research/known_issues.md#ki-06) で追跡している。

```bash
uv run python scripts/evaluate_adl_labels.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --state-table state/aruba_15_0_14days.txt \
  --sensor-map configs/aruba_sensor_map.json \
  --patterns output/aruba_15_0_14days/llm_sequences_modes_15_0_14days_1.json \
  --output-dir output/6_adl_evaluation_15_0_14days \
  --write-state-series output/6_adl_evaluation_15_0_14days/state_series.csv \
  --hamming-threshold 0
```

### 5. 🟨 **条件付き** LLM単独ベースラインを生成する

`output/llm_direct_15_0_14days/1.json` がなければ実行する。1回分だけ比較する場合はこのコマンドでよい。

```bash
uv run python scripts/run_direct_log_baseline.py \
  --log-days 14 \
  --hamming-threshold 0 \
  --extract-only
```

### 6. 🟩 **スキップ可** LLM単独ベースラインを5回分生成する

5回平均を出す場合に実行する。`output/llm_direct_15_0_14days/1.json` から `5.json` までを作成する。既にADLラベル付き出力が存在するrunはスキップされる。

```bash
uv run python scripts/run_direct_log_baseline.py \
  --log-days 14 \
  --hamming-threshold 0 \
  --extract-only \
  --runs 5
```

### 7. 🟥 **必須** 手法間比較を実行する

提案手法とLLM単独ベースラインを比較する。既定は1回分の出力を比較する。

```bash
uv run python scripts/evaluate_6_compare_adl_interpretation_set.py \
  --patterns-proposed output/aruba_15_0_14days/llm_sequences_modes_15_0_14days_1.json \
  --patterns-direct output/llm_direct_15_0_14days/1.json \
  --state-series output/6_adl_evaluation_15_0_14days/state_series.csv \
  --labeled-casas new_labeled_data/aruba.txt \
  --output-dir results/6_adl_match/15_0_14days \
  --min-overlap-ratio-for-true-label 0.10 \
  --days 14 \
  --n-states 15 \
  --hamming-threshold 0
```

### 8. 🟩 **スキップ可** 5回分の平均を出す

Step 3とStep 6で5回分のパターン出力を作成したあとに実行する。`output/aruba_15_0_14days/llm_sequences_modes_15_0_14days_1.json` から `_5.json` まで、かつ `output/llm_direct_15_0_14days/1.json` から `5.json` までを使って平均を出す。

```bash
uv run python scripts/evaluate_6_compare_adl_interpretation_set.py \
  --patterns-proposed output/aruba_15_0_14days/llm_sequences_modes_15_0_14days_1.json \
  --patterns-direct output/llm_direct_15_0_14days/1.json \
  --proposed-metrics-template 'output/aruba_15_0_14days/llm_modes_metrics_15_0_14days_run{run}.csv' \
  --direct-metrics output/llm_direct_15_0_14days/llm_direct_metrics_14days.csv \
  --state-series output/6_adl_evaluation_15_0_14days/state_series.csv \
  --labeled-casas new_labeled_data/aruba.txt \
  --output-dir results/6_adl_match/15_0_14days \
  --min-overlap-ratio-for-true-label 0.10 \
  --days 14 \
  --n-states 15 \
  --hamming-threshold 0 \
  --runs 5
```

一部のrunだけ存在する状態で平均を確認する場合は、次を追加する。

```bash
  --skip-missing-runs
```

### 9. 🟩 **スキップ可** 代表状態数・ハミング距離を変えて1回実行する

評価1の感度分析と同じように、評価6でも `K` とハミング距離を変えた条件で比較できる。以下は `K=20`, `hamming=1`, `14days` の例。出力先を条件別に分け、採用条件の `15_0_14days` 結果を上書きしない。

```bash
uv run python scripts/run_build_network_from_labeled_casas.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --sensor-map configs/aruba_sensor_map.json \
  --days 14 \
  --n-states 20 \
  --hamming-threshold 1

uv run python scripts/run_llm_extraction.py \
  --days 14 \
  --n-states 20 \
  --hamming-threshold 1

uv run python scripts/evaluate_adl_labels.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --state-table state/aruba_20_1_14days.txt \
  --sensor-map configs/aruba_sensor_map.json \
  --patterns output/aruba_20_1_14days/llm_sequences_modes_20_1_14days_1.json \
  --output-dir output/6_adl_evaluation_20_1_14days \
  --write-state-series output/6_adl_evaluation_20_1_14days/state_series.csv \
  --hamming-threshold 1

uv run python scripts/run_direct_log_baseline.py \
  --log-days 14 \
  --state-days 14 \
  --extract-only \
  --n-states 20 \
  --hamming-threshold 1

uv run python scripts/evaluate_6_compare_adl_interpretation_set.py \
  --patterns-proposed output/aruba_20_1_14days/llm_sequences_modes_20_1_14days_1.json \
  --patterns-direct output/llm_direct_20_1_14days/1.json \
  --state-series output/6_adl_evaluation_20_1_14days/state_series.csv \
  --labeled-casas new_labeled_data/aruba.txt \
  --output-dir results/6_adl_match/20_1_14days \
  --min-overlap-ratio-for-true-label 0.10 \
  --days 14 \
  --n-states 20 \
  --hamming-threshold 1
```

### 10. 🟩 **スキップ可** 代表状態数・ハミング距離を変えて5回平均を出す

同じ条件で5回平均を出す場合は、提案手法とLLM単独ベースラインの両方で `--runs 5` を付けてパターン出力を作成し、比較評価にも `--runs 5` を付ける。以下は `K=20`, `hamming=1`, `14days` の例。

```bash
uv run python scripts/run_build_network_from_labeled_casas.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --sensor-map configs/aruba_sensor_map.json \
  --days 14 \
  --n-states 20 \
  --hamming-threshold 1

uv run python scripts/run_llm_extraction.py \
  --days 14 \
  --n-states 20 \
  --hamming-threshold 1 \
  --runs 5

uv run python scripts/evaluate_adl_labels.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --state-table state/aruba_20_1_14days.txt \
  --sensor-map configs/aruba_sensor_map.json \
  --patterns output/aruba_20_1_14days/llm_sequences_modes_20_1_14days_1.json \
  --output-dir output/6_adl_evaluation_20_1_14days \
  --write-state-series output/6_adl_evaluation_20_1_14days/state_series.csv \
  --hamming-threshold 1

uv run python scripts/run_direct_log_baseline.py \
  --log-days 14 \
  --state-days 14 \
  --extract-only \
  --n-states 20 \
  --hamming-threshold 1 \
  --runs 5

uv run python scripts/evaluate_6_compare_adl_interpretation_set.py \
  --patterns-proposed output/aruba_20_1_14days/llm_sequences_modes_20_1_14days_1.json \
  --patterns-direct output/llm_direct_20_1_14days/1.json \
  --state-series output/6_adl_evaluation_20_1_14days/state_series.csv \
  --labeled-casas new_labeled_data/aruba.txt \
  --output-dir results/6_adl_match/20_1_14days \
  --min-overlap-ratio-for-true-label 0.10 \
  --days 14 \
  --n-states 20 \
  --hamming-threshold 1 \
  --runs 5
```

## 比較対象

| 手法 | 入力 | 評価方法 |
|---|---|---|
| `proposed` | 14日版状態遷移ネットワークから抽出したLLM JSON。 | `time_band_interpretations` を `sequence × time_band` に展開し、対象時間帯内の出現だけでset比較する。 |
| `direct_log_baseline` | 14日分の前処理済み代表状態系列を直接LLMへ入力して抽出したJSON。 | 同じ `state_series.csv` 上で系列出現を検索し、同じset評価を行う。 |

## 処理手順の内部仕様

1. LLM出力JSONから `ADL系列ラベル` と `遷移のパターン` を読む。
2. 提案手法の `time_band_interpretations` は `sequence × time_band` 単位へ展開する。
3. パターン出現区間を用意する。比較スクリプトでは、両手法を同じ `state_series.csv` 上で検索し直す。詳細CSVには、この検索結果に基づく `num_occurrences` も保存する。
4. `time_band` が `All` でない評価レコードは、半開区間 `[start,end)` の開始時刻と `end-\epsilon` がともに当該時間帯へ属するoccurrenceだけを使う。境界を横断する出現は除外し、件数と割合を保存する。`All` は時間帯制約を持たないため除外しないが、監査用の横断件数は保存する。
5. `new_labeled_data/aruba.txt` からADL正解区間を内部生成する。
6. 対象occurrenceについて、ADLカテゴリ別の重なり時間を合計する。
7. `category_overlap / total_overlap >= --min-overlap-ratio-for-true-label` のカテゴリを正解ADL集合に入れる。
8. LLMの `ADL系列ラベル` を10カテゴリ語彙に対して検証する。欠落は `prediction_status=missing`、語彙外を1つでも含む場合は `prediction_status=unknown` とし、rawラベルを保持して警告する。
9. 出現なし、正解ADL重なりなし、予測欠落、語彙外を別々の評価状態として記録し、定義済みの分母規則でset指標を計算する。
10. 提案手法は各runの時間帯別メトリクスを合計し、LLM単独ベースラインは各runのメトリクスを使って、run合計の平均と標準偏差を算出する。

欠損パターンrunは手法ごとに独立してskipされ、LLM使用量も手法ごとの完全runだけで平均される。また、ラベル別・時間帯別CSVは全runのdetail行をpoolして集計する。pairedな共通run、run等重み、detail poolのどれを正式集計とするかは未解決であり、[KI-09](../research/known_issues.md#ki-09) で追跡している。

既定の `match_mode=exact` は、状態系列の全開始位置を1つずつずらして連続部分系列を照合する。開始位置の異なる重なり一致は別出現として数える。パターン途中への別状態の挿入、状態の置換・削除・飛び越しは認めない。保存済み主評価も `exact` を使用する。`skip-other` は感度確認用の互換オプションであり、主評価には用いない。

### LLM使用量・応答時間の比較

`evaluation6_llm_usage_comparison.csv` は、入力形式の異なる2手法を「1 runの抽出全体」で比較する。

- 提案手法: Morning / Daytime / Night / Midnight の記録済み成功API呼び出しをrun内で合計する。
- LLM単独ベースライン: 同期間の前処理済み代表状態系列を直接入力した記録済み成功API呼び出しをrun値とする。
- `--runs 5` の場合: 上記のrun合計を、各手法で完全な記録があるrunについて平均し、標準偏差も保存する。
- `duration_sec` はGemini APIの応答待ち時間であり、前処理・プロンプト構築・ファイル保存を含む全工程時間ではない。
- パース失敗などの失敗API呼び出しは既存メトリクスに含まれない。
- 4時間帯のいずれか、または必要なメトリクス値が欠けたrunは0として補わず平均から除外し、`num_runs_with_complete_metrics` と `evaluation6_comparison_summary.json` の `missing_metrics` に記録する。
- Gemini APIでは `totalTokenCount = promptTokenCount + thoughtsTokenCount + candidatesTokenCount` である。`cachedContentTokenCount` はキャッシュ部分の内数であり `promptTokenCount` に含まれる。本実験はツール呼出し、コンテキストキャッシュ、および `systemInstruction` を設定していない。プロンプト文面は `contents` として入力側に渡す。既存CSVは思考トークン列を保存していないため、既存結果については `total_tokens - prompt_tokens - response_tokens` を思考トークン数として復元する。したがって、`total_tokens` を入力と可視出力の単純和として扱わない。

### 提案手法LLM JSONの統合形式

同じ `sequence` は1つのグループにまとめる。ただし、時間帯別の解釈は削除せず `time_band_interpretations` に保持する。

```json
{
  "pattern_id": "P001",
  "sequence": ["状態8", "状態13", "状態8"],
  "time_band_interpretations": {
    "Morning": {
      "パターン名": "朝の家中の巡回行動",
      "ADL系列ラベル": ["Wake-up", "Housework"],
      "解釈の根拠": "..."
    },
    "Midnight": {
      "パターン名": "深夜のトイレ利用と再就寝",
      "ADL系列ラベル": ["Hygiene", "Sleep"],
      "解釈の根拠": "..."
    }
  }
}
```

評価時には以下のようなレコードへ展開する。

| eval_pattern_id | group_pattern_id | time_band | sequence |
|---|---|---|---|
| `P001_Morning` | `P001` | `Morning` | `状態8->状態13->状態8` |
| `P001_Midnight` | `P001` | `Midnight` | `状態8->状態13->状態8` |

### 正解ADL集合

| 条件 | 動作 |
|---|---|
| ADL重なりあり | 重なり割合が閾値以上のADLを `true_adl_set` に入れる。 |
| パターン出現なし | `occurrence_status=no_occurrence`。正解集合は定義せず、conditionalから除外、end-to-endでは0点。 |
| 出現あり・ADL重なりなし | `truth_status=no_adl_overlap`。正解集合は定義せず、両指標から除外。 |
| 予測集合欠落 | `prediction_status=missing`。空集合予測として、両指標で0点かつ分母に含める。 |
| 語彙外予測あり | `prediction_status=unknown`。`Other` へ変換せずrawラベルを保存し、両指標で0点かつ分母に含める。 |
| 複数ADLに対応するraw label | 1つの区間を複数ADLへ展開する。 |

例:

| raw label | ADL集合 |
|---|---|
| `Bed_to_Toilet` | `Wake-up`, `Toileting` |
| `Bathroom`, `Personal_Hygiene` | `Wake-up`, `Hygiene` |
| `Wash_Dishes` | `Meal`, `Housework` |
| `Meal_Preparation` | `Meal`、wake-up補正時は `Wake-up` も加わる場合がある |

## パラメータ

| パラメータ | 既定値・例 |
|---|---|
| 正式評価の使用日数 | `--days 14` を明示 |
| 正式評価の代表状態数 | `--n-states 15` を明示 |
| 正式評価のハミング距離閾値 | `--hamming-threshold 0` を明示 |
| `--min-overlap-ratio-for-true-label` | `0.10` |
| time_band-aware | `true` |
| 時間帯境界 | `[start,end)` 全体が同じ時間帯に含まれる出現だけを採用 |
| `--no-overlap-label`, `--missing-pred-label`, `--unknown-pred-label` | CLI互換性のため受理するが無視する非推奨引数 |
| 提案手法JSON | `output/aruba_15_0_14days/llm_sequences_modes_15_0_14days_1.json` |
| LLM単独JSON | `output/llm_direct_15_0_14days/1.json` |
| 状態系列 | `output/6_adl_evaluation_15_0_14days/state_series.csv` |
| ADL正解データ | `new_labeled_data/aruba.txt` |

評価で許可するLLM出力ADLラベル:

```text
Sleep
Wake-up
Meal
Relax
Outing
Hygiene
Toileting
Housework
Work
Other
```

大文字小文字と `Wake-up` のハイフン等の軽微な表記差だけを正規化する。CASASのraw activity名を予測語彙の別名としては受理しない。`Noise`, `Ambiguous` を含む語彙外ラベルは `unknown` として記録し、`Other` へ自動変換しない。

## 注意点

- 評価6ではラベル順序を評価しない。`ADL系列ラベル` という名前でもsetとして扱う。
- 154日版の提案手法出力と14日版の前処理済み代表状態系列ベースラインを混ぜて比較しない。
- 既存のLLM出力に `ADL系列ラベル` がない場合は `prediction_status=missing` として0点にし、分母から除外しない。
- 予測ラベル集合を \(C\) と書く場合、\(C\) は10カテゴリへの軽微な表記正規化後の集合である。語彙外ラベルを含むレコードでは \(C\) を有効な予測集合として採点せず、`unknown` として0点にする。
- `output/6_adl_evaluation_15_0_14days/` は評価6用の中間出力であり、最終結果は `results/6_adl_match/` に保存する。
