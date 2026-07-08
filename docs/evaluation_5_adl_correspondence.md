# 評価5: ADLラベルを用いたパターン単位評価

## 評価の要約

頻度ベースライン、ルールフィルタ後の頻度ベースライン、FP-Growth系ベースライン、提案手法が出力した系列パターンを、パターン1件単位で評価する。train期間でパターンとADL集合の対応を決め、test期間でその対応が維持されるか、また無駄なパターンがどの程度あるかを確認する。

## RQ

| RQ | 内容 |
|---|---|
| RQ5-1 | 提案手法は、頻度ベースラインで発生する無駄なパターンを減らせるか。 |
| RQ5-2 | 提案手法は、ルールフィルタ後の頻度ベースラインやFP-Growth系ベースラインと比べても無駄なパターンを減らせるか。 |
| RQ5-3 | 提案手法の出力パターンは、test期間でもtrainで割り当てたADL集合と対応しているか。 |

## 評価指標

| 指標 | 定義 | 見ること |
|---|---|---|
| `ADL-grounded pattern rate` | `ADL-grounded pattern数 / 評価可能パターン数` | trainで割り当てたADL集合とtestでも対応している割合。 |
| `Useless pattern rate` | `Useless pattern数 / 評価可能パターン数` | ADLとほぼ対応しない、または系列構造として冗長なパターンの割合。 |
| `Useless-A` | testで意味あるADLとほとんど重ならない。 | ADLラベルに基づく無駄パターン。 |
| `Useless-B` | 系列に `A -> Other -> A` を含む。 | `その他` 状態を挟む往復ノイズ。 |
| `Useless-C` | 系列に `A -> B -> A -> B` を含む。 | 交互反復ループ。 |
| `assigned_adl_hit_rate_test` | `assigned_adl_set_train` のいずれかと重なったtest出現数 / test出現数。 | trainで決めたADL対応がtestでも出るかを見る。 |
| `assigned_adl_purity_test` | `assigned_adl_set_train` のいずれかと重なったtest時間 / test出現時間。 | test出現時間のうち、割当ADLと重なる割合を見る。 |

## 入力と出力

### 入力

| 入力 | 例 | 役割 |
|---|---|---|
| ラベル付きCASAS | `new_labeled_data/aruba.txt` | ADL begin/endラベルを含む正解データ。 |
| 代表状態系列CSV | `results/4_adl_evaluation/state_series.csv` | `start_time,end_time,state_id` 形式の代表状態区間。 |
| frequencyパターン | `output/aruba_15_1_154days/state_sequence_counts_15_1_154days.json` | 頻度ベースライン系列。 |
| rule-filteredパターン | `output/5_rule_filter/*.csv` | ルールフィルタ済み頻度系列。 |
| FP-Growthパターン | train期間の代表状態系列から実行時生成 | 関連研究ベースラインとして使う頻出n-gram系列。 |
| proposedパターン | `output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json` | 提案手法のLLM系列。 |

### 出力

| 出力 | 内容 |
|---|---|
| `results/5_adl_correspondence/evaluation5_summary_by_method.csv` | 手法ごとの主指標。 |
| `results/5_adl_correspondence/evaluation5_pattern_details.csv` | 手法別・パターン別の詳細結果。 |
| `results/5_adl_correspondence/evaluation5_summary.json` | 入力パス、train/test期間、閾値、skipped methods、手法別集計。 |

## 結果の読み方

| 順序 | ファイル | 読み方 |
|---|---|---|
| 1 | `evaluation5_summary_by_method.csv` | summaryとして、`adl_grounded_pattern_rate` と `useless_pattern_rate` を手法間で比較する。 |
| 2 | `evaluation5_pattern_details.csv` | detailsとして、`is_useless`, `useless_reason`, `evaluation_status`, `fp_filter_reason` を見て、どの系列が無駄になったか確認する。 |
| 3 | `evaluation5_summary.json` | 再現条件として、`train_period`, `test_period`, `thresholds`, `skipped_methods`, FP-Growth設定を確認する。 |

FP-Growth系を見る場合は、`support_transactions`, `support_ratio`, `median_duration_seconds`, `p90_duration_seconds`, `is_fp_filtered_out`, `fp_filter_reason` も確認する。

## 実行手順

### 1. 🟨 **条件付き** 評価4で代表状態系列CSVを作成する

`results/4_adl_evaluation/state_series.csv` がなければ実行する。既に評価4で作成済みならスキップしてよい。

```bash
uv run python scripts/evaluate_adl_labels.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --state-table state/aruba_15_1_154days.txt \
  --sensor-map configs/aruba_sensor_map.json \
  --patterns output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json \
  --output-dir results/4_adl_evaluation \
  --write-state-series results/4_adl_evaluation/state_series.csv
```

### 2. 🟥 **必須** 評価5を実行する

手法別のパターン単位評価を作るために実行する。frequency / rule-filtered baselineは、指定した入力ファイルがない場合でも既定では `--state-series` から自動生成されるため、別Stepでは実行しない。

```bash
uv run python scripts/evaluate_adl_correspondence.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --state-series results/4_adl_evaluation/state_series.csv \
  --patterns-frequency output/aruba_15_1_154days/state_sequence_counts_15_1_154days.json \
  --patterns-rule-light output/5_rule_filter/frequency_rule_light.csv \
  --patterns-rule-medium output/5_rule_filter/frequency_rule_medium.csv \
  --patterns-rule-strong output/5_rule_filter/frequency_rule_strong.csv \
  --patterns-proposed output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json \
  --output-dir results/5_adl_correspondence \
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
  --other-state-labels その他 Other Other_ADL unknown \
  --exclude-other-adl-from-any \
  --min-overlap-seconds 1
```

### 3. 🟩 **スキップ可** FP-Growth系baselineなしで評価5を実行する

`fp_growth`, `fp_growth_filtered` を比較しない場合は、通常実行から `--enable-fp-growth-baseline` と `--fp-*` 引数を外して実行する。

```bash
uv run python scripts/evaluate_adl_correspondence.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --state-series results/4_adl_evaluation/state_series.csv \
  --patterns-frequency output/aruba_15_1_154days/state_sequence_counts_15_1_154days.json \
  --patterns-rule-light output/5_rule_filter/frequency_rule_light.csv \
  --patterns-rule-medium output/5_rule_filter/frequency_rule_medium.csv \
  --patterns-rule-strong output/5_rule_filter/frequency_rule_strong.csv \
  --patterns-proposed output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json \
  --output-dir results/5_adl_correspondence \
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
| `proposed` | 状態遷移ネットワークをLLMに渡す提案手法。 |

## 処理手順の内部仕様

1. ラベル付きCASASをADL区間に変換し、評価5用のmulti-label ADLへ展開する。
2. 代表状態系列CSVを読み込む。
3. ADL区間と代表状態系列を時系列順にtrain/testへ分割する。
4. 各手法のパターンを `method, pattern_id, pattern_name, sequence, count` に正規化する。
5. `--enable-fp-growth-baseline` 指定時は、train期間の状態系列から `fp_growth`, `fp_growth_filtered` を生成する。
6. train期間で各パターンを検索し、ADLカテゴリ別の重なり時間から `assigned_adl_set_train` を決める。
7. test期間で同じパターンを検索し、trainで決めた `assigned_adl_set_train` を固定してADL-groundedを判定する。
8. Useless-A/B/Cを判定し、手法別に集計する。

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
| `--other-state-labels` | `その他 Other Other_ADL unknown` |
| `--min-overlap-seconds` | `1` |

## 注意点

- test期間でpattern -> ADLを再割り当てしない。
- `test_support=0` のパターンは、既定では主指標の分母から除外する。
- `Other_ADL` は既定で `any_adl_hit_rate` と `any_adl_purity` の意味あるADLから除外する。
- `frequency` とFP-Growth系は出現区間数が多く、フルデータでは実行に時間がかかる。
- 旧評価5のIoU/境界/hit系CSVが同じディレクトリに残っている場合でも、現在の主出力は `evaluation5_*` の3ファイルである。
