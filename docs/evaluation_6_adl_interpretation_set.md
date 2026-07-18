# 評価6: LLM解釈ラベルとADL重なりラベルのSet一致評価

## 評価の要約

LLMが各パターンへ付与した `ADL系列ラベル` と、パターン出現区間がCASAS正解ADL区間と重なった結果から得られるADL集合を比較する。評価はset一致で行い、ラベル順序は使わない。評価6では提案手法単体の評価は行わず、提案手法とLLM単独ベースラインを14日版に揃えて比較する。提案手法では、同じ `遷移のパターン` が複数時間帯で抽出された場合、表示・保存上は1つのグループにまとめ、評価時には `sequence × time_band` 単位へ展開する。

## RQ

| RQ | 内容 |
|---|---|
| RQ6-1 | LLMの自然言語解釈ラベルは、実際のADL重なりラベルと意味的に整合しているか。 |
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

## 入力と出力

### 入力

| 入力 | 既定パス | 役割 |
|---|---|---|
| 提案手法LLM JSON | `output/aruba_15_1_14days/llm_sequences_modes_15_1_14days_1.json` | `time_band_interpretations` を持つ提案手法出力。 |
| LLM単独ベースラインJSON | `output/llm_direct_15_1_14days/1.json` | `ADL系列ラベル` 付きの直接ログLLM出力。 |
| 14日版状態系列 | `output/6_adl_evaluation_14/state_series.csv` | 手法間比較で両手法の出現区間を同条件で検索するために使う。 |
| ADL正解データ | `new_labeled_data/aruba.txt` | CASAS activity `begin/end` からADL正解区間を内部生成する。 |

### 出力

| 出力 | 内容 |
|---|---|
| `results/6_adl_match/15_1_14days/evaluation6_method_comparison.csv` | 提案手法とLLM単独ベースラインの主比較表。`--runs` が2以上の場合はrun平均と標準偏差。 |
| `results/6_adl_match/15_1_14days/evaluation6_method_comparison_by_run.csv` | runごとの手法別summary。5回平均の元データ。 |
| `results/6_adl_match/15_1_14days/evaluation6_llm_usage_comparison.csv` | 手法ごとの1 run合計トークン数・API応答時間をrun間で平均した比較表。`--runs 5` では5回平均と標準偏差を出す。 |
| `results/6_adl_match/15_1_14days/evaluation6_pattern_set_details_by_method.csv` | 手法別・パターン別詳細。`num_occurrences` は評価8の頻度帯分析に使う、評価レコードごとの代表状態系列上の出現回数。 |
| `results/6_adl_match/15_1_14days/evaluation6_by_pred_label_by_method.csv` | 手法別・予測ラベル別集計。 |
| `results/6_adl_match/15_1_14days/evaluation6_by_true_label_by_method.csv` | 手法別・正解ラベル別集計。 |
| `results/6_adl_match/15_1_14days/evaluation6_by_time_band_by_method.csv` | 手法別・時間帯別集計。 |
| `results/6_adl_match/15_1_14days/evaluation6_comparison_summary.json` | 比較評価の再現条件。 |

## 結果の読み方

| 順序 | ファイル | 読み方 |
|---|---|---|
| 1 | `evaluation6_method_comparison.csv` | summaryとして、手法ごとの平均 Exact Set Match, Jaccard, multilabel Precision / Recall / F1を見る。`--runs 5` の場合は5回平均と標準偏差を見る。 |
| 2 | `evaluation6_llm_usage_comparison.csv` | `num_runs_with_complete_metrics` が5であることを確認し、手法ごとの平均入力・応答・合計トークン数と平均API応答時間を比較する。 |
| 3 | `evaluation6_method_comparison_by_run.csv` | runごとのばらつきを確認する。平均値だけでなく、特定runだけ大きく外れていないかを見る。 |
| 4 | `evaluation6_pattern_set_details_by_method.csv` | detailsとして、`run`, `method`, `eval_pattern_id`, `group_pattern_id`, `time_band`, `pred_adl_labels`, `true_adl_labels`, `intersection_labels`, `union_labels` を見てズレの原因を確認する。 |
| 5 | `evaluation6_comparison_summary.json` | 再現条件として、入力パス、run数、14日版で揃っているか、`min_overlap_ratio_for_true_label`, 許可ラベル、使用量集計元を確認する。 |

時間帯別の傾向を見る場合は、`evaluation6_by_time_band*.csv` でMorning, Daytime, Night, Midnightごとの平均指標を見る。ラベル別の傾向を見る場合は、`evaluation6_by_pred_label*.csv` で付けすぎているラベル、`evaluation6_by_true_label*.csv` で拾えていない正解ラベルを見る。

## 実行手順

### 1. 🟨 **条件付き** 14日版の状態遷移ネットワークを構築する

`state/aruba_15_1_14days.txt` がなければ実行する。評価6では提案手法とLLM単独ベースラインの入力日数を14日に揃える。

```bash
uv run python scripts/run_build_network_from_labeled_casas.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --sensor-map configs/aruba_sensor_map.json \
  --days 14 \
  --smoothing-window-sec 5
```

### 2. 🟨 **条件付き** 提案手法の14日版LLM出力を生成する

`output/aruba_15_1_14days/llm_sequences_modes_15_1_14days_1.json` がなければ実行する。既に同じ条件のLLM出力がある場合はスキップしてよい。1回分だけ比較する場合はこのコマンドでよい。

```bash
uv run python scripts/run_llm_extraction.py --days 14
```

### 3. 🟩 **スキップ可** 提案手法の14日版LLM出力を5回分生成する

5回平均を出す場合に実行する。`output/aruba_15_1_14days/llm_sequences_modes_15_1_14days_1.json` から `_5.json` までを作成する。既に存在する時間帯別チェックポイントや統合JSONはスキップされる。

```bash
uv run python scripts/run_llm_extraction.py \
  --days 14 \
  --runs 5
```

### 4. 🟨 **条件付き** 評価6用の14日版パターン出現区間と状態系列を作る

`output/6_adl_evaluation_14/pattern_occurrences.csv` または `output/6_adl_evaluation_14/state_series.csv` がなければ実行する。この出力は評価6用の中間ファイルなので `output/` に保存する。

```bash
uv run python scripts/evaluate_adl_labels.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --state-table state/aruba_15_1_14days.txt \
  --sensor-map configs/aruba_sensor_map.json \
  --patterns output/aruba_15_1_14days/llm_sequences_modes_15_1_14days_1.json \
  --output-dir output/6_adl_evaluation_14 \
  --write-state-series output/6_adl_evaluation_14/state_series.csv
```

### 5. 🟨 **条件付き** LLM単独ベースラインを生成する

`output/llm_direct_15_1_14days/1.json` がなければ実行する。1回分だけ比較する場合はこのコマンドでよい。

```bash
uv run python scripts/run_direct_log_baseline.py \
  --log-days 14 \
  --extract-only
```

### 6. 🟩 **スキップ可** LLM単独ベースラインを5回分生成する

5回平均を出す場合に実行する。`output/llm_direct_15_1_14days/1.json` から `5.json` までを作成する。既にADLラベル付き出力が存在するrunはスキップされる。

```bash
uv run python scripts/run_direct_log_baseline.py \
  --log-days 14 \
  --extract-only \
  --runs 5
```

### 7. 🟥 **必須** 手法間比較を実行する

提案手法とLLM単独ベースラインを比較する。既定は1回分の出力を比較する。

```bash
uv run python scripts/evaluate_6_compare_adl_interpretation_set.py \
  --patterns-proposed output/aruba_15_1_14days/llm_sequences_modes_15_1_14days_1.json \
  --patterns-direct output/llm_direct_15_1_14days/1.json \
  --state-series output/6_adl_evaluation_14/state_series.csv \
  --labeled-casas new_labeled_data/aruba.txt \
  --output-dir results/6_adl_match/15_1_14days \
  --min-overlap-ratio-for-true-label 0.10
```

### 8. 🟩 **スキップ可** 5回分の平均を出す

Step 3とStep 6で5回分のパターン出力を作成したあとに実行する。`output/aruba_15_1_14days/llm_sequences_modes_15_1_14days_1.json` から `_5.json` まで、かつ `output/llm_direct_15_1_14days/1.json` から `5.json` までを使って平均を出す。

```bash
uv run python scripts/evaluate_6_compare_adl_interpretation_set.py \
  --patterns-proposed output/aruba_15_1_14days/llm_sequences_modes_15_1_14days_1.json \
  --patterns-direct output/llm_direct_15_1_14days/1.json \
  --state-series output/6_adl_evaluation_14/state_series.csv \
  --labeled-casas new_labeled_data/aruba.txt \
  --output-dir results/6_adl_match/15_1_14days \
  --min-overlap-ratio-for-true-label 0.10 \
  --runs 5
```

一部のrunだけ存在する状態で平均を確認する場合は、次を追加する。

```bash
  --skip-missing-runs
```

### 9. 🟩 **スキップ可** 代表状態数・ハミング距離を変えて1回実行する

評価1の感度分析と同じように、評価6でも `K` とハミング距離を変えた条件で比較できる。以下は `K=20`, `hamming=1`, `14days` の例。出力先を条件別に分け、既存の `15_1_14days` 結果を上書きしない。

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
| `direct_log_baseline` | 14日分の直接ログ入力から抽出したLLM JSON。 | 同じ `state_series.csv` 上で系列出現を検索し、同じset評価を行う。 |

## 処理手順の内部仕様

1. LLM出力JSONから `ADL系列ラベル` と `遷移のパターン` を読む。
2. 提案手法の `time_band_interpretations` は `sequence × time_band` 単位へ展開する。
3. パターン出現区間を用意する。比較スクリプトでは、両手法を同じ `state_series.csv` 上で検索し直す。詳細CSVには、この検索結果に基づく `num_occurrences` も保存する。
4. `time_band` が `All` でない評価レコードは、出現開始時刻が同じ時間帯に属するoccurrenceだけを使う。
5. `new_labeled_data/aruba.txt` からADL正解区間を内部生成する。
6. 対象occurrenceについて、ADLカテゴリ別の重なり時間を合計する。
7. `category_overlap / total_overlap >= --min-overlap-ratio-for-true-label` のカテゴリを正解ADL集合に入れる。
8. LLMの `ADL系列ラベル` を正規化し、予測ADL集合にする。
9. 予測集合と正解集合をsetとして比較する。
10. 提案手法は各runの時間帯別メトリクスを合計し、LLM単独ベースラインは各runのメトリクスを使って、run合計の平均と標準偏差を算出する。

### LLM使用量・応答時間の比較

`evaluation6_llm_usage_comparison.csv` は、入力形式の異なる2手法を「1 runの抽出全体」で比較する。

- 提案手法: Morning / Daytime / Night / Midnight の記録済み成功API呼び出しをrun内で合計する。
- LLM単独ベースライン: 直接ログを入力した記録済み成功API呼び出しをrun値とする。
- `--runs 5` の場合: 上記のrun合計を5回分平均し、標準偏差も保存する。
- `duration_sec` はGemini APIの応答待ち時間であり、前処理・プロンプト構築・ファイル保存を含む全工程時間ではない。
- パース失敗などの失敗API呼び出しは既存メトリクスに含まれない。
- 4時間帯のいずれか、または必要なメトリクス値が欠けたrunは0として補わず平均から除外し、`num_runs_with_complete_metrics` と `evaluation6_comparison_summary.json` の `missing_metrics` に記録する。

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
| ADL重なりなし | 既定で `Ambiguous` を正解集合に入れる。 |
| 複数ADLに対応するraw label | 1つの区間を複数ADLへ展開する。 |

例:

| raw label | ADL集合 |
|---|---|
| `Bed_to_Toilet` | `Wake-up`, `Hygiene` |
| `Wash_Dishes` | `Meal`, `Housework` |
| `Meal_Preparation` | `Meal`、wake-up補正時は `Wake-up` も加わる場合がある |

## パラメータ

| パラメータ | 既定値・例 |
|---|---|
| 使用日数 | `14`日 |
| 代表状態数 | 既定 `15`。条件変更時は `--n-states` で指定する。 |
| ハミング距離閾値 | 既定 `1`。条件変更時は `--hamming-threshold` で指定する。 |
| `--min-overlap-ratio-for-true-label` | `0.10` |
| time_band-aware | `true` |
| no-overlap label | `Ambiguous` |
| 提案手法JSON | `output/aruba_15_1_14days/llm_sequences_modes_15_1_14days_1.json` |
| 直接ログJSON | `output/llm_direct_15_1_14days/1.json` |
| 状態系列 | `output/6_adl_evaluation_14/state_series.csv` |
| ADL正解データ | `new_labeled_data/aruba.txt` |

LLMが出力できる主なADLラベル:

```text
Sleep
Wake-up
Meal
Relax
Outing
Hygiene
Housework
Other
Noise
Ambiguous
```

表記揺れは正規化される。未知の予測ラベルは既定で `Other` に正規化される。

## 注意点

- 評価6ではラベル順序を評価しない。`ADL系列ラベル` という名前でもsetとして扱う。
- 154日版の提案手法出力と14日版の直接ログベースラインを混ぜて比較しない。
- 既存のLLM出力に `ADL系列ラベル` がない場合は `Ambiguous` として扱われ、平均指標が低く出やすい。
- `output/6_adl_evaluation_14/` は評価6用の中間出力であり、最終結果は `results/6_adl_match/` に保存する。
