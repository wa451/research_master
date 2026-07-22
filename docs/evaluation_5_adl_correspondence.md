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
| `Useful non-redundant pattern rate` | `is_adl_grounded AND NOT is_structural_useless AND NOT is_fragmented` なパターン数 / 評価可能パターン数 | ADLに支持され、構造的に無意味でも断片的でもないパターンの割合。low-information状態の割合は条件に含めない。 |
| `Fragmentation rate` | `is_fragmented` なパターン数 / 評価可能パターン数。比較可能な短系列―長系列対が0件の場合も、断片数0として0を出力する。 | 長いパターンの断片として出ている部分系列の割合。比較可能対数と比較可能な子パターン数も診断情報として併記する。 |
| `Contextless useless rate` | `is_contextless_useless` なパターン数 / 評価可能パターン数 | 構造的に無意味、またはADLに支持されないパターンの割合。low-information状態の割合は条件に含めない。 |

### 新しい主指標の判定

```text
is_useful_non_redundant =
  is_adl_grounded
  AND NOT is_structural_useless
  AND NOT is_fragmented
```

`is_contextless_useless` は以下のいずれかを満たす場合にtrueである。

| 判定 | 定義 |
|---|---|
| `structural_useless` | `A -> A`、`A -> Other -> A`、または `A -> B -> A -> B` を含む。 |
| `adl_unsupported` | `any_adl_hit_rate_test < --useless-hit-threshold` かつ `any_adl_purity_test < --useless-purity-threshold`。既定値はいずれも `0.1`。 |

`low_information_ratio` は、active sensorsが空の状態および明示Other等の状態が系列に占める割合として詳細CSVへ残すが、診断専用である。閾値によるlow-information真偽判定は行わず、UsefulおよびContextlessのどちらにも使用しない。後方互換のため `is_low_information` と `num_low_information` の列名は残すが、値は空欄とする。`--low-information-threshold` も受理するが無視する非推奨引数である。

`is_fragmented` は、同一手法・同一run・同一時間帯内であるパターン `p` がより長いパターン `q` の連続部分系列であり、かつ以下を満たす場合にtrueである。同じ `(p, q)` の組は1回だけ数える。

```text
occurrence_containment(p, q)
= qの出現区間に含まれるpの出現数 / pの出現数
```

`occurrence_containment(p, q) >= --fragmentation-containment-threshold` のとき、`p` をfragmentedとする。既定値は `0.7`。提案手法が `sequence × time_band` 単位で読み込まれる場合、半開区間 `[start,end)` の開始時刻と `end-\epsilon` がともに当該time bandに属する出現だけをtrain/testのADL照合およびfragmentation判定に用いる。例えば09:59開始・10:00終了はMorningに含め、10:00を超えて継続する出現は除外する。

比較可能な `(p, q)` が0件の手法・runでも、断片数を0、分母を評価可能パターン数として `fragmentation_rate=0`、`fragmentation_status=evaluated` とする。親候補を持たない各パターンは「同じ出力集合内では冗長な断片ではない」と扱う。ただし、比較機会自体がないため、この0を断片化抑制の実証とは解釈しない。複数run集計では全runのFragmentation rateから平均と標準偏差を計算する。後方互換のため `fragmentation_rate_num_valid_runs` と `fragmentation_rate_num_na_runs` は残すが、修正後の出力では全runがvalid、N/A runは0となる。

## 入力と出力

### 入力

| 入力 | 例 | 役割 |
|---|---|---|
| ラベル付きCASAS | `new_labeled_data/aruba.txt` | ADL begin/endラベルを含む正解データ。 |
| 代表状態系列CSV | `output/5_adl_evaluation_15_0_154days_fixed/state_series_220days.csv` | `start_time,end_time,state_id` 形式の代表状態区間。抽出と同じ前処理・代表状態定義から生成した系列を全手法の照合に共用する。 |
| 代表状態定義または状態遷移ネットワーク | `state/aruba_15_0_154days.txt` または `picture/aruba_15_0_154days/state_transition_all.json` | 状態IDに対応するactive sensorsを解決し、診断用 `low_information_ratio` を算出する。どちらか一方を必ず指定する。 |
| frequencyパターン | `output/aruba_15_0_154days/state_sequence_counts_15_0_154days.json` | 頻度ベースライン系列。 |
| rule-filteredパターン | `output/5_rule_filter/*.csv` | ルールフィルタ済み頻度系列。 |
| FP-Growthパターン | train期間の代表状態系列から実行時生成 | 関連研究ベースラインとして使う頻出n-gram系列。 |
| transition_probabilityパターン | train期間の代表状態系列から実行時生成 | 代表状態遷移確率が高い経路を抽出するベースライン。 |
| proposedパターン | `output/aruba_15_0_154days/llm_sequences_modes_15_0_154days_1.json` | 提案手法のLLM系列。`--runs 5` では `_1.json` から `_5.json` までを評価して平均を出す。 |

上表とStep 1--4は、`K=15`, `hamming=0`, `154days` を各入力パスで明示する正式再現条件である。一方、評価CLIで省略可能なパターン入力を省略すると、`configs/default.yaml` 由来の `K=15`, `hamming=1`, `154days` のパスを使い、`--output-dir` の既定値は `results/5_pattern_quality_fixed/` となる。正式出力先 `results/5_pattern_quality_without_low_information_judgment/` は自動では選ばれない。`hamming=0` とCLI既定由来の `hamming=1` の不一致は [KI-01](known_issues.md#ki-01) で追跡しているため、正式再現では本書の入力パスと出力先を省略しない。

### 出力

| 出力 | 内容 |
|---|---|
| `results/5_pattern_quality_without_low_information_judgment/evaluation5_summary_by_method.csv` | 手法ごとの主指標、対象数、比較可能pair数、系列長分布。`--runs 2` 以上ではrun平均と標準偏差。 |
| `results/5_pattern_quality_without_low_information_judgment/evaluation5_summary_by_method_by_run.csv` | runごとの手法別主指標、対象数、比較可能pair数、系列長分布。`--runs 2` 以上、または欠損runが `--skip-missing-runs` により実際にskipされた場合に出力。`--runs 1 --skip-missing-runs` だけでは、欠損がなければ出力しない。 |
| `results/5_pattern_quality_without_low_information_judgment/evaluation5_pattern_details.csv` | 手法別・run別・パターン別の詳細結果。 |
| `results/5_pattern_quality_without_low_information_judgment/evaluation5_summary.json` | 入力パス、状態属性、train/test期間、閾値、run情報、skipped methods、手法別集計。state-seriesの生成条件は本節のStep 3と実行コマンドで管理する。直前の修正前結果は `results/5_pattern_quality_low_information_gt_0_5/` に保持する。 |

FP-Growth系とtransition_probabilityの生成済みパターンはCSVキャッシュとして保存できる。同じ `state_series`、train期間、CLI設定で再実行した場合はこのCSVを読み込み、ベースライン生成時間を削減する。修正版の正式再集計では既存キャッシュを上書きしないよう `output/5_adl_correspondence_baselines_fixed/` を指定する。

## 結果の読み方

| 順序 | ファイル | 読み方 |
|---|---|---|
| 1 | `evaluation5_summary_by_method.csv` | 3指標に加え、`output_record_count`, `unique_sequence_count`, `num_evaluable_patterns`, `num_excluded_patterns`, `num_adl_grounded`, `num_contextless_useless`, `num_fragmented`, `num_useful_non_redundant`, `num_comparable_fragment_pairs`, `num_comparable_fragment_children`, `fragmentation_status`, `sequence_length_distribution_json` を確認する。複数run時のcount列は1 run当たりの平均である。`num_low_information` は互換列として空欄になる。 |
| 2 | `evaluation5_summary_by_method_by_run.csv` | 各runの整数countと率を確認する。Fragmentationは比較可能pair数と比較可能な子パターン数も併せて確認し、pair=0で率が0の場合を抑制成功と解釈しない。 |
| 3 | `evaluation5_pattern_details.csv` | detailsとして、`run`, `is_adl_grounded`, `is_structural_useless`, `is_adl_unsupported`, `is_contextless_useless`, `is_fragmented`, `comparable_fragment_parent_ids`, `fragment_parent_ids`, `is_useful_non_redundant`, `low_information_ratio`, `evaluation_status` を確認する。`is_low_information` は互換列として空欄になる。 |
| 4 | `evaluation5_summary.json` | 再現条件として、`train_period`, `test_period`, `thresholds`, `runs_completed`, `skipped_runs`, `skipped_methods`, FP-Growth設定を確認する。 |

FP-Growth系を見る場合は、supportやdurationなどのメタデータ列も確認できる。ただし評価5の集計指標として出力するのは上記3指標のみである。

## 実行手順

### 1. 🟨 **条件付き** 代表状態・状態遷移ネットワークを作成する

`state/aruba_15_0_154days.txt` や `picture/aruba_15_0_154days/state_transition_all.json` がなければ実行する。既に評価5条件の成果物がある場合はスキップしてよい。

```bash
uv run python scripts/run_build_network_from_labeled_casas.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --sensor-map configs/aruba_sensor_map.json \
  --days 154 \
  --n-states 15 \
  --hamming-threshold 0 \
  --smoothing-window-sec 5
```

### 2. 🟨 **条件付き** 提案手法LLM出力を生成する

`output/aruba_15_0_154days/llm_sequences_modes_15_0_154days_1.json` がなければ実行する。APIキーを使う重い処理である。

```bash
uv run python scripts/run_llm_extraction.py \
  --days 154 \
  --n-states 15 \
  --hamming-threshold 0
```

5回平均を出す場合は、提案手法LLM出力を5回分作成する。

```bash
uv run python scripts/run_llm_extraction.py \
  --days 154 \
  --n-states 15 \
  --hamming-threshold 0 \
  --runs 5
```

### 3. 🟨 **条件付き** 評価5用 `state_series.csv` を作成する

`output/5_adl_evaluation_15_0_154days_fixed/state_series_220days.csv` がなければ実行する。抽出時と同じ1秒粒度化、5秒の遅延OFF平滑化、代表状態写像、同一状態圧縮を適用した系列を保存する。event-driven系列を別実装で再構築したCSVは正式評価に使用しない。既存の修正前CSVは上書きしない。

`network-equivalent` は、最初のイベント日の00:00:00から1秒Sample-and-Holdを行い、抽出側と同じ `rolling(window=5).max()` に等価な遅延OFFを適用する。メモリ上に220日分の1秒行列を展開せず、状態変化点だけを処理する。代表状態は先頭154日で作成済みの `state/aruba_15_0_154days.txt` から読み込み、評価期間のデータから再抽出しない。`--state-series-days 220` により、先頭154日と後続66日を含む全期間を出力する。

```bash
uv run python scripts/evaluate_adl_labels.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --state-table state/aruba_15_0_154days.txt \
  --sensor-map configs/aruba_sensor_map.json \
  --hamming-threshold 0 \
  --state-series-preprocessing network-equivalent \
  --smoothing-window-sec 5 \
  --state-series-days 220 \
  --write-state-series output/5_adl_evaluation_15_0_154days_fixed/state_series_220days.csv \
  --state-series-only
```

### 4. 🟥 **必須** 評価5を実行する

手法別のパターン単位評価を作るために実行する。frequency / rule-filtered baselineは、指定した入力ファイルがない場合でも既定では `--state-series` から自動生成されるため、別Stepでは実行しない。

```bash
uv run python scripts/evaluate_adl_correspondence.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --state-series output/5_adl_evaluation_15_0_154days_fixed/state_series_220days.csv \
  --state-definition state/aruba_15_0_154days.txt \
  --patterns-frequency output/aruba_15_0_154days/state_sequence_counts_15_0_154days.json \
  --patterns-rule-light output/5_rule_filter/frequency_rule_light.csv \
  --patterns-rule-medium output/5_rule_filter/frequency_rule_medium.csv \
  --patterns-rule-strong output/5_rule_filter/frequency_rule_strong.csv \
  --patterns-proposed output/aruba_15_0_154days/llm_sequences_modes_15_0_154days_1.json \
  --output-dir results/5_pattern_quality_without_low_information_judgment \
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
  --baseline-cache-dir output/5_adl_correspondence_baselines_fixed \
  --use-baseline-cache \
  --fragmentation-containment-threshold 0.7 \
  --other-state-labels その他 Other Other_ADL unknown \
  --exclude-other-adl-from-any \
  --min-overlap-seconds 1
```

5回平均を出す場合は、Step 2で `_1.json` から `_5.json` までを作成したあと、評価5本体にも `--runs 5` を付ける。
このときfrequency / rule / FP-Growth / transition_probabilityはrunに依存しないため、最初に完了したrunで1回だけ評価する。2回目以降は提案手法だけを評価するため、以前より実行時間が短くなる。

```bash
uv run python scripts/evaluate_adl_correspondence.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --state-series output/5_adl_evaluation_15_0_154days_fixed/state_series_220days.csv \
  --state-definition state/aruba_15_0_154days.txt \
  --patterns-frequency output/aruba_15_0_154days/state_sequence_counts_15_0_154days.json \
  --patterns-rule-light output/5_rule_filter/frequency_rule_light.csv \
  --patterns-rule-medium output/5_rule_filter/frequency_rule_medium.csv \
  --patterns-rule-strong output/5_rule_filter/frequency_rule_strong.csv \
  --patterns-proposed output/aruba_15_0_154days/llm_sequences_modes_15_0_154days_1.json \
  --output-dir results/5_pattern_quality_without_low_information_judgment \
  --runs 5 \
  --train-ratio 0.7 \
  --enable-fp-growth-baseline \
  --enable-transition-baseline \
  --baseline-cache-dir output/5_adl_correspondence_baselines_fixed \
  --use-baseline-cache
```

一部のrunだけ存在する状態で平均を確認する場合は、次を追加する。

```bash
  --skip-missing-runs
```

標準命名以外のファイルを使う場合は、`{run}` を含むテンプレートを指定できる。

```bash
  --patterns-proposed-template output/aruba_15_0_154days/llm_sequences_modes_15_0_154days_{run}.json
```

### 5. 🟩 **スキップ可** FP-Growth系baselineなしで評価5を実行する

`fp_growth`, `fp_growth_filtered` を比較しない場合は、通常実行から `--enable-fp-growth-baseline` と各FP-Growth関連引数を外して実行する。

```bash
uv run python scripts/evaluate_adl_correspondence.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --state-series output/5_adl_evaluation_15_0_154days_fixed/state_series_220days.csv \
  --state-definition state/aruba_15_0_154days.txt \
  --patterns-frequency output/aruba_15_0_154days/state_sequence_counts_15_0_154days.json \
  --patterns-rule-light output/5_rule_filter/frequency_rule_light.csv \
  --patterns-rule-medium output/5_rule_filter/frequency_rule_medium.csv \
  --patterns-rule-strong output/5_rule_filter/frequency_rule_strong.csv \
  --patterns-proposed output/aruba_15_0_154days/llm_sequences_modes_15_0_154days_1.json \
  --output-dir results/5_pattern_quality_without_low_information_judgment \
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
2. 代表状態系列CSVを読み込み、代表状態定義またはネットワークのノード属性から、active sensorsが空の状態IDを解決して診断用 `low_information_ratio` を算出する。系列中の状態IDを解決できない場合はエラーで停止する。
3. ADL区間と代表状態系列を時系列順にtrain/testへ分割する。
4. 各手法のパターンを `method, pattern_id, pattern_name, sequence, count` に正規化する。
5. `--enable-fp-growth-baseline` 指定時は、train期間の状態系列から `fp_growth`, `fp_growth_filtered` を生成する。
6. train期間で各パターンを検索し、ADLカテゴリ別の重なり時間から `assigned_adl_set_train` を決める。`time_band` を持つレコードは、出現の半開区間全体が同じ時間帯に収まる場合だけ使う。
7. test期間で同じ時間帯条件によりパターンを検索し、trainで決めた `assigned_adl_set_train` を固定してADL-groundedを判定する。
8. 構造条件とADL支持だけからContextless uselessを判定し、ADL-grounded・非structural・非fragmentedからuseful non-redundantを判定する。率、分子・分母、比較可能pair数、系列長分布を集計する。
9. `--runs` が2以上の場合はrun別summaryを保存する。Fragmentation rateは比較可能対0件のrunを0として含め、全runから平均・標準偏差を計算する。

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
| `--state-definition` / `--state-network-json` | いずれか一方が必須 |
| 前段 `--state-series-preprocessing` | `network-equivalent` |
| 前段 `--smoothing-window-sec` | `5` |
| 前段 `--state-series-days` | `220` |
| 前段 `--state-series-only` | enabled |
| `--grounded-hit-threshold` | `0.3` |
| `--grounded-purity-threshold` | `0.3` |
| `--useless-hit-threshold` | `0.1` |
| `--useless-purity-threshold` | `0.1` |
| `--assigned-adl-purity-threshold` | `0.10` |
| `--assigned-adl-max-categories` | `3` |
| `--enable-fp-growth-baseline` | disabled。正式コマンドでは明示して有効化する。 |
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
| `--baseline-cache-dir` | `output/5_adl_correspondence_baselines_fixed` |
| `--use-baseline-cache` / `--no-use-baseline-cache` | enabled |
| `--fragmentation-containment-threshold` | `0.7` |
| `--low-information-threshold` | 非推奨。互換性のため受理するが無視する。 |
| `--runs` | `1` |
| `--patterns-proposed-template` | 任意 |
| `--skip-missing-runs` | disabled |
| `--other-state-labels` | `その他 Other Other_ADL unknown` |
| `--min-overlap-seconds` | `1` |

## 注意点

- test期間でpattern -> ADLを再割り当てしない。
- `time_band` を持つパターンは、半開区間 `[start,end)` 全体が同じ時間帯に収まる場合だけ照合する。
- 状態IDのactive sensors属性を解決できない場合は、診断用比率を推測せずエラーで停止する。
- `low_information_ratio` はUsefulおよびContextlessへ影響しない。高い比率を持つパターンがUsefulになり得るため、Usefulは「情報量が高い割合」ではない。
- 比較可能な短系列―長系列対が0件の場合も、Fragmentation rateは `0 / 評価可能パターン数 = 0` とする。ただし、比較機会がないため断片化抑制の証拠とはしない。
- `test_support=0` のパターンは、既定では主指標の分母から除外する。
- `Other_ADL` は既定で `any_adl_hit_rate` と `any_adl_purity` の意味あるADLから除外する。
- `frequency` とFP-Growth系は出現区間数が多く、フルデータでは実行に時間がかかる。
- 旧評価5のIoU/境界/hit系CSVが同じディレクトリに残っている場合でも、現在の主出力は `evaluation5_*` ファイルである。`evaluation5_summary_by_method_by_run.csv` は複数run時に出力される。
