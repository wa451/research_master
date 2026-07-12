# 評価5: ADLラベルを用いたパターン単位評価

## 評価の要約

頻度ベースライン、ルールフィルタ後の頻度ベースライン、FP-Growth系ベースライン、遷移確率ベースライン、提案手法が出力した系列パターンを、パターン1件単位で評価する。train期間でパターンとADL集合の対応を決め、test期間でその対応が維持されるか、また生活文脈のない系列や長い系列の断片がどの程度あるかを確認する。

## RQ

| RQ | 内容 |
|---|---|
| RQ5-1 | 提案手法は、生活文脈のある有用な非冗長パターンを抽出できるか。 |
| RQ5-2 | 提案手法は、frequency / rule-filtered / FP-Growth / transition_probability baselineと比べて断片的な部分系列を減らせるか。 |
| RQ5-3 | 提案手法の出力パターンは、test期間でもtrainで割り当てたADL集合と対応しているか。 |

## 評価指標

| 指標 | 定義 | 見ること |
|---|---|---|
| `Useful non-redundant pattern rate` | `is_adl_grounded AND NOT is_contextless_useless AND NOT is_fragmented` なパターン数 / 評価可能パターン数 | 生活文脈があり、かつ冗長な断片ではないパターンの割合。 |
| `Fragmentation rate` | `is_fragmented` なパターン数 / 評価可能パターン数 | 長いパターンの断片として出ている部分系列の割合。 |
| `Contextless useless rate` | `is_contextless_useless` なパターン数 / 評価可能パターン数 | 構造的に無意味、情報量が低い、ADLに支持されないパターンの割合。 |

### 新しい主指標の判定

```text
is_useful_non_redundant =
  is_adl_grounded
  AND NOT is_contextless_useless
  AND NOT is_fragmented
```

`is_contextless_useless` は以下のいずれかを満たす場合にtrueである。

| 判定 | 定義 |
|---|---|
| `structural_useless` | `A -> A`、`A -> Other -> A`、または `A -> B -> A -> B` を含む。 |
| `low_information` | sequence内の `Other`、`unknown`、`その他`、active sensorsなし相当の状態割合が `--low-information-threshold` 以上。既定値は `0.5`。 |
| `adl_unsupported` | `any_adl_hit_rate_test < --useless-hit-threshold` かつ `any_adl_purity_test < --useless-purity-threshold`。既定値はいずれも `0.1`。 |

`is_fragmented` は、同一手法内であるパターン `p` がより長いパターン `q` の連続部分系列であり、かつ以下を満たす場合にtrueである。

```text
occurrence_containment(p, q)
= qの出現区間に含まれるpの出現数 / pの出現数
```

`occurrence_containment(p, q) >= --fragmentation-containment-threshold` のとき、`p` をfragmentedとする。既定値は `0.7`。提案手法が `sequence × time_band` 単位で読み込まれる場合、fragmentation判定は同じtime_band内で行う。

## 入力と出力

### 入力

| 入力 | 例 | 役割 |
|---|---|---|
| ラベル付きCASAS | `new_labeled_data/aruba.txt` | ADL begin/endラベルを含む正解データ。 |
| 代表状態系列CSV | `output/5_adl_evaluation/state_series.csv` | `start_time,end_time,state_id` 形式の代表状態区間。評価5の前段ステップで作成できる。 |
| frequencyパターン | `output/aruba_15_1_154days/state_sequence_counts_15_1_154days.json` | 頻度ベースライン系列。 |
| rule-filteredパターン | `output/5_rule_filter/*.csv` | ルールフィルタ済み頻度系列。 |
| FP-Growthパターン | train期間の代表状態系列から実行時生成 | 関連研究ベースラインとして使う頻出n-gram系列。 |
| transition_probabilityパターン | train期間の代表状態系列から実行時生成 | 代表状態遷移確率が高い経路を抽出するベースライン。 |
| proposedパターン | `output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json` | 提案手法のLLM系列。`--runs 5` では `_1.json` から `_5.json` までを評価して平均を出す。 |

### 出力

| 出力 | 内容 |
|---|---|
| `results/5_pattern_quality/evaluation5_summary_by_method.csv` | 手法ごとの主指標。`--runs 2` 以上ではrun平均と標準偏差。 |
| `results/5_pattern_quality/evaluation5_summary_by_method_by_run.csv` | runごとの手法別summary。`--runs 2` 以上、または `--skip-missing-runs` 指定時に出力。 |
| `results/5_pattern_quality/evaluation5_pattern_details.csv` | 手法別・run別・パターン別の詳細結果。 |
| `results/5_pattern_quality/evaluation5_summary.json` | 入力パス、train/test期間、閾値、run情報、skipped methods、手法別集計。 |

FP-Growth系とtransition_probabilityの生成済みパターンは、既定で `output/5_adl_correspondence_baselines/` にCSVキャッシュとして保存される。同じ `state_series`、train期間、CLI設定で再実行した場合はこのCSVを読み込み、ベースライン生成時間を削減する。

## 結果の読み方

| 順序 | ファイル | 読み方 |
|---|---|---|
| 1 | `evaluation5_summary_by_method.csv` | summaryとして、`useful_non_redundant_pattern_rate`, `fragmentation_rate`, `contextless_useless_rate` を手法間で比較する。`--runs 5` では平均値と `_std` を見る。run非依存のbaselineは1回だけ評価するため、`num_runs` は通常 `1` になる。 |
| 2 | `evaluation5_summary_by_method_by_run.csv` | 5回平均の元データとして、runごとのばらつきや外れrunを確認する。 |
| 3 | `evaluation5_pattern_details.csv` | detailsとして、`run`, `is_contextless_useless`, `is_fragmented`, `fragment_parent_ids`, `is_useful_non_redundant`, `evaluation_status` を確認する。 |
| 4 | `evaluation5_summary.json` | 再現条件として、`train_period`, `test_period`, `thresholds`, `runs_completed`, `skipped_runs`, `skipped_methods`, FP-Growth設定を確認する。 |

FP-Growth系を見る場合は、supportやdurationなどのメタデータ列も確認できる。ただし評価5の集計指標として出力するのは上記3指標のみである。

## 実行手順

### 1. 🟨 **条件付き** 代表状態・状態遷移ネットワークを作成する

`state/aruba_15_1_154days.txt` や `picture/aruba_15_1_154days/state_transition_all.json` がなければ実行する。既に評価5条件の成果物がある場合はスキップしてよい。

```bash
uv run python scripts/run_build_network_from_labeled_casas.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --sensor-map configs/aruba_sensor_map.json \
  --days 154 \
  --n-states 15 \
  --hamming-threshold 1
```

### 2. 🟨 **条件付き** 提案手法LLM出力を生成する

`output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json` がなければ実行する。APIキーを使う重い処理である。

```bash
uv run python scripts/run_llm_extraction.py \
  --days 154 \
  --n-states 15 \
  --hamming-threshold 1
```

5回平均を出す場合は、提案手法LLM出力を5回分作成する。

```bash
uv run python scripts/run_llm_extraction.py \
  --days 154 \
  --n-states 15 \
  --hamming-threshold 1 \
  --runs 5
```

### 3. 🟨 **条件付き** 評価5用 `state_series.csv` を作成する

`output/5_adl_evaluation/state_series.csv` がなければ実行する。評価4を実行済みでなくても、このステップだけで評価5用の代表状態系列CSVを作成できる。

```bash
uv run python scripts/evaluate_adl_labels.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --state-table state/aruba_15_1_154days.txt \
  --sensor-map configs/aruba_sensor_map.json \
  --patterns output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json \
  --output-dir output/5_adl_evaluation \
  --write-state-series output/5_adl_evaluation/state_series.csv
```

### 4. 🟥 **必須** 評価5を実行する

手法別のパターン単位評価を作るために実行する。frequency / rule-filtered baselineは、指定した入力ファイルがない場合でも既定では `--state-series` から自動生成されるため、別Stepでは実行しない。

```bash
uv run python scripts/evaluate_adl_correspondence.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --state-series output/5_adl_evaluation/state_series.csv \
  --patterns-frequency output/aruba_15_1_154days/state_sequence_counts_15_1_154days.json \
  --patterns-rule-light output/5_rule_filter/frequency_rule_light.csv \
  --patterns-rule-medium output/5_rule_filter/frequency_rule_medium.csv \
  --patterns-rule-strong output/5_rule_filter/frequency_rule_strong.csv \
  --patterns-proposed output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json \
  --output-dir results/5_pattern_quality \
  --train-ratio 0.7 \
  --grounded-hit-threshold 0.3 \
  --grounded-purity-threshold 0.3 \
  --useless-hit-threshold 0.1 \
  --useless-purity-threshold 0.1 \
  --assigned-adl-purity-threshold 0.10 \
  --assigned-adl-max-categories 3 \
  --enable-fp-growth-baseline \
  --fp-min-support 0.05 \
  --fp-top-k 50 \
  --fp-min-len 2 \
  --fp-max-len 4 \
  --fp-max-median-duration-seconds 1800 \
  --fp-max-p90-duration-seconds 3600 \
  --enable-transition-baseline \
  --transition-top-k 50 \
  --transition-min-prob 0.0 \
  --transition-min-len 2 \
  --transition-max-len 4 \
  --baseline-cache-dir output/5_adl_correspondence_baselines \
  --use-baseline-cache \
  --fragmentation-containment-threshold 0.7 \
  --low-information-threshold 0.5 \
  --other-state-labels その他 Other Other_ADL unknown \
  --exclude-other-adl-from-any \
  --min-overlap-seconds 1
```

5回平均を出す場合は、Step 2で `_1.json` から `_5.json` までを作成したあと、評価5本体にも `--runs 5` を付ける。
このときfrequency / rule / FP-Growth / transition_probabilityはrunに依存しないため、最初に完了したrunで1回だけ評価する。2回目以降は提案手法だけを評価するため、以前より実行時間が短くなる。

```bash
uv run python scripts/evaluate_adl_correspondence.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --state-series output/5_adl_evaluation/state_series.csv \
  --patterns-frequency output/aruba_15_1_154days/state_sequence_counts_15_1_154days.json \
  --patterns-rule-light output/5_rule_filter/frequency_rule_light.csv \
  --patterns-rule-medium output/5_rule_filter/frequency_rule_medium.csv \
  --patterns-rule-strong output/5_rule_filter/frequency_rule_strong.csv \
  --patterns-proposed output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json \
  --output-dir results/5_pattern_quality \
  --runs 5 \
  --train-ratio 0.7 \
  --enable-fp-growth-baseline \
  --enable-transition-baseline \
  --baseline-cache-dir output/5_adl_correspondence_baselines \
  --use-baseline-cache
```

一部のrunだけ存在する状態で平均を確認する場合は、次を追加する。

```bash
  --skip-missing-runs
```

標準命名以外のファイルを使う場合は、`{run}` を含むテンプレートを指定できる。

```bash
  --patterns-proposed-template output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_{run}.json
```

### 5. 🟩 **スキップ可** FP-Growth系baselineなしで評価5を実行する

`fp_growth`, `fp_growth_filtered` を比較しない場合は、通常実行から `--enable-fp-growth-baseline` と `--fp-*` 引数を外して実行する。

```bash
uv run python scripts/evaluate_adl_correspondence.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --state-series output/5_adl_evaluation/state_series.csv \
  --patterns-frequency output/aruba_15_1_154days/state_sequence_counts_15_1_154days.json \
  --patterns-rule-light output/5_rule_filter/frequency_rule_light.csv \
  --patterns-rule-medium output/5_rule_filter/frequency_rule_medium.csv \
  --patterns-rule-strong output/5_rule_filter/frequency_rule_strong.csv \
  --patterns-proposed output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json \
  --output-dir results/5_pattern_quality \
  --train-ratio 0.7 \
  --grounded-hit-threshold 0.3 \
  --grounded-purity-threshold 0.3 \
  --useless-hit-threshold 0.1 \
  --useless-purity-threshold 0.1 \
  --assigned-adl-purity-threshold 0.10 \
  --assigned-adl-max-categories 3 \
  --other-state-labels その他 Other Other_ADL unknown \
  --exclude-other-adl-from-any \
  --min-overlap-seconds 1
```

## 比較対象

| method | 内容 |
|---|---|
| `frequency` | 代表状態系列上の頻出連続系列。 |
| `rule_light` | 明らかなノイズだけ除去した頻度ベースライン。 |
| `rule_medium` | 短時間往復や交互反復も除去した頻度ベースライン。 |
| `rule_strong` | `A -> B -> A` 系往復なども強く除去した頻度ベースライン。 |
| `fp_growth` | train期間の連続n-gramをtransaction itemとして抽出するFP-Growth相当ベースライン。 |
| `fp_growth_filtered` | `fp_growth` にstructural / temporal filterを適用したベースライン。 |
| `transition_probability` | train期間の代表状態系列から状態遷移確率を計算し、joint probabilityが高い経路を抽出するベースライン。 |
| `proposed` | 状態遷移ネットワークをLLMに渡す提案手法。 |

## 処理手順の内部仕様

1. ラベル付きCASASをADL区間に変換し、評価5用のmulti-label ADLへ展開する。
2. 代表状態系列CSVを読み込む。
3. ADL区間と代表状態系列を時系列順にtrain/testへ分割する。
4. 各手法のパターンを `method, pattern_id, pattern_name, sequence, count` に正規化する。
5. `--enable-fp-growth-baseline` 指定時は、train期間の状態系列から `fp_growth`, `fp_growth_filtered` を生成する。
6. train期間で各パターンを検索し、ADLカテゴリ別の重なり時間から `assigned_adl_set_train` を決める。
7. test期間で同じパターンを検索し、trainで決めた `assigned_adl_set_train` を固定してADL-groundedを判定する。
8. Contextless useless、fragmentation、useful non-redundantを判定し、手法別に3指標だけを集計する。
9. `--runs` が2以上の場合は、run別summaryを保存し、手法別に3指標の平均と標準偏差を計算する。

### assigned_adl_set_train

train期間だけを使い、各パターンにADLカテゴリ集合を割り当てる。test期間では再計算しない。

| ルール | 内容 |
|---|---|
| purity計算 | `category_purity = category_overlap_seconds / train_total_duration_seconds` |
| 閾値 | `category_purity >= --assigned-adl-purity-threshold` のADLを候補にする。 |
| 最大重なりADL | `category_overlap_seconds > 0` なら必ず候補に含める。 |
| 最大カテゴリ数 | `--assigned-adl-max-categories` まで。4カテゴリ以上は重なり時間が大きい順に残す。 |
| `Other_ADL` | 原則除外する。ただし、非Other ADLとまったく重ならず `Other_ADL` だけと重なる場合は含める。 |

### FP-Growth系baseline

| 項目 | 内容 |
|---|---|
| item | 代表状態の連続n-gram。 |
| transaction | 日付 × 時間帯。時間帯はMorning, Daytime, Night, Midnight。 |
| support | n-gram itemを含むtransaction数 / 全transaction数。 |
| structural filter | `A -> A`, `A -> その他 -> A`, `A -> Other -> A`, `A -> B -> A -> B` を除外。 |
| temporal filter | `median_duration_seconds > 1800` または `p90_duration_seconds > 3600` を除外。 |

### transition_probability baseline

| 項目 | 内容 |
|---|---|
| 入力 | train期間の代表状態系列。 |
| 遷移確率 | `P(next_state | current_state)` をtrain系列の隣接遷移カウントから計算する。 |
| path score | 各stepの遷移確率の積。 |
| 抽出 | `--transition-min-prob` 以上の遷移だけを使い、`--transition-min-len` から `--transition-max-len` の経路を列挙する。 |
| 件数 | `--transition-top-k` 件をpath score降順で採用する。既定値は `50`。 |

### multi-label ADL mapping

| raw label | ADL集合 |
|---|---|
| `Sleeping` | `Sleep` |
| `Bed_to_Toilet` | `Wake-up`, `Toileting` |
| `Bathroom` | `Wake-up`, `Hygiene` |
| `Personal_Hygiene` | `Wake-up`, `Hygiene` |
| `Bathing` | `Hygiene` |
| `Toileting` | `Toileting` |
| `Meal_Preparation` | `Meal` |
| `Wash_Dishes` | `Meal`, `Housework` |
| `Leave_Home`, `Enter_Home` | `Outing` |
| `Relax` | `Relax` |
| `Housekeeping` | `Housework` |
| unknown | `Other_ADL` |

`Sleeping` 終了後30分以内の行動は、wake-up補正により `Wake-up` も保持される場合がある。

## パラメータ

| パラメータ | 既定値 |
|---|---:|
| `--train-ratio` | `0.7` |
| `--grounded-hit-threshold` | `0.3` |
| `--grounded-purity-threshold` | `0.3` |
| `--useless-hit-threshold` | `0.1` |
| `--useless-purity-threshold` | `0.1` |
| `--assigned-adl-purity-threshold` | `0.10` |
| `--assigned-adl-max-categories` | `3` |
| `--fp-min-support` | `0.05` |
| `--fp-top-k` | `50` |
| `--fp-min-len` | `2` |
| `--fp-max-len` | `4` |
| `--fp-max-median-duration-seconds` | `1800` |
| `--fp-max-p90-duration-seconds` | `3600` |
| `--enable-transition-baseline` | enabled |
| `--transition-top-k` | `50` |
| `--transition-min-prob` | `0.0` |
| `--transition-min-len` | `2` |
| `--transition-max-len` | `4` |
| `--baseline-cache-dir` | `output/5_adl_correspondence_baselines` |
| `--use-baseline-cache` / `--no-use-baseline-cache` | enabled |
| `--fragmentation-containment-threshold` | `0.7` |
| `--low-information-threshold` | `0.5` |
| `--runs` | `1` |
| `--patterns-proposed-template` | 任意 |
| `--skip-missing-runs` | disabled |
| `--other-state-labels` | `その他 Other Other_ADL unknown` |
| `--min-overlap-seconds` | `1` |

## 注意点

- test期間でpattern -> ADLを再割り当てしない。
- `test_support=0` のパターンは、既定では主指標の分母から除外する。
- `Other_ADL` は既定で `any_adl_hit_rate` と `any_adl_purity` の意味あるADLから除外する。
- `frequency` とFP-Growth系は出現区間数が多く、フルデータでは実行に時間がかかる。
- 旧評価5のIoU/境界/hit系CSVが同じディレクトリに残っている場合でも、現在の主出力は `evaluation5_*` ファイルである。`evaluation5_summary_by_method_by_run.csv` は複数run時に出力される。
