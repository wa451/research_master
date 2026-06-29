# 評価4: ラベル付きCASASデータによるADL評価

この評価では、提案手法で抽出された系列パターンを、ラベル付きCASASデータのADLラベルと照合する。パターンがどのADLカテゴリに対応するか、各ADLカテゴリをどの程度検出できるか、開始・終了境界がどの程度一致するかを評価する。

## 目的

- 抽出された系列パターンをADLカテゴリに対応付ける。
- `Sleep`, `Wake-up`, `Meal`, `Outing`, `Relax` などの行動単位でPrecision, Recall, F1を計算する。
- ラベル境界とパターン出現区間の開始・終了時刻のずれを測る。

## 入力

| 入力 | 既定パス | 役割 |
|---|---|---|
| ラベル付きCASAS | `new_labeled_data/aruba.txt` | ADL begin/endラベルを含む正解データ |
| センサログ | `data/aruba.csv` | 代表状態系列を再構築する元ログ |
| 代表状態テーブル | `state/aruba_15_1_154days.txt` | センサ状態を代表状態IDに対応付ける |
| LLM抽出パターン | `output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json` | 評価対象の系列パターン |

`data/aruba.txt` はラベルなしデータなので、この評価では使わない。

## ADLカテゴリマッピング

既定では次のようにCASASラベルを上位カテゴリに変換する。

```python
ADL_CATEGORY_MAP = {
    "Sleeping": "Sleep",
    "Bed_to_Toilet": "Wake-up",
    "Personal_Hygiene": "Wake-up",
    "Bathing": "Wake-up",
    "Toileting": "Wake-up",
    "Meal_Preparation": "Meal",
    "Eating": "Meal",
    "Wash_Dishes": "Meal",
    "Leave_Home": "Outing",
    "Enter_Home": "Outing",
    "Relax": "Relax",
    "Housekeeping": "Housework",
}
```

`Wake-up` はCASASに直接存在しない場合がある。そのため、`Sleeping` 終了後30分以内に発生した `Bed_to_Toilet`, `Bathroom`, `Personal_Hygiene`, `Meal_Preparation` などは `Wake-up` として扱う。時間幅は `--wake-window-minutes` で変更できる。

## 実行前の準備

評価2を少なくとも1回実行し、LLMパターンを生成しておく。

```bash
uv run python scripts/run_all.py
```

必要なファイルがあることを確認する。

```text
new_labeled_data/aruba.txt
data/aruba.csv
state/aruba_15_1_154days.txt
output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json
```

## 実行コマンド

```bash
uv run python scripts/evaluate_adl_labels.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --event-log data/aruba.csv \
  --state-table state/aruba_15_1_154days.txt \
  --patterns output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json \
  --output-dir results/adl_evaluation \
  --iou-thresholds 0.3 0.5 \
  --wake-window-minutes 30 \
  --match-mode exact
```

## 処理手順

### 1. ラベル付きCASASの区間化

`new_labeled_data/aruba.txt` のactivity begin/endを対応付け、次の形式の区間に変換する。

```text
start_time, end_time, raw_label, adl_category
```

### 2. LLMパターンの時刻付き出現区間への展開

LLMが出力した状態系列を代表状態系列上で検索する。既定の `--match-mode exact` では、状態系列が連続して完全一致した場合のみ出現とする。

出力例:

```text
pattern_id, pattern_name, sequence, start_time, end_time
```

### 3. パターンとADLカテゴリの対応付け

各パターン出現区間とADLラベル区間の重なり時間を計算する。

```text
overlap = max(0, min(pred_end, label_end) - max(pred_start, label_start))
```

パターンごとに重なり時間が最大のADLカテゴリを割り当てる。

```text
confidence = assigned_adl_overlap_time / total_pattern_occurrence_time
```

### 4. ADLごとのPrecision, Recall, F1

割り当て済みパターン出現区間を予測区間として扱う。同じADLカテゴリ内でTemporal IoUが閾値以上ならTPとする。

```text
IoU = overlap_duration / union_duration
```

評価閾値:

```text
IoU >= 0.3
IoU >= 0.5
```

マッチングは同じADLカテゴリ内でIoUが最大のペアから貪欲に行う。1つの正解区間または予測区間を複数回使わない。

### 5. 境界一致度

TPになったペアについて次を計算する。

```text
start_error_minutes = predicted_start - true_start
end_error_minutes = predicted_end - true_end
abs_start_error_minutes
abs_end_error_minutes
temporal_iou
```

ADLカテゴリごとに平均値と中央値を出力する。

## 出力

```text
results/adl_evaluation/pattern_occurrences.csv
results/adl_evaluation/pattern_adl_mapping.csv
results/adl_evaluation/adl_metrics_iou_0.3.csv
results/adl_evaluation/adl_metrics_iou_0.5.csv
results/adl_evaluation/boundary_metrics_iou_0.3.csv
results/adl_evaluation/boundary_metrics_iou_0.5.csv
results/adl_evaluation/evaluation_summary.json
```

`evaluation_summary.json` には次が保存される。

- 使用したデータパス
- 評価対象期間
- IoU閾値
- ADLマッピング
- パターン数
- 出現区間数
- 予測区間数
- macro平均
- micro平均

## オプション

### 代表状態系列CSVを直接使う

既に `start_time,end_time,state_id` 形式のCSVがある場合:

```bash
uv run python scripts/evaluate_adl_labels.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --state-series results/state_series.csv \
  --patterns output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json \
  --output-dir results/adl_evaluation
```

### 代表状態系列CSVを書き出す

```bash
uv run python scripts/evaluate_adl_labels.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --event-log data/aruba.csv \
  --state-table state/aruba_15_1_154days.txt \
  --patterns output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json \
  --write-state-series results/adl_evaluation/state_series.csv
```

### train/test splitを使う

同じデータで対応付けと評価を行うと過大評価になる可能性がある。分割する場合は次のどちらかを指定する。

```bash
uv run python scripts/evaluate_adl_labels.py \
  --split-date "2010-12-01 00:00:00"
```

または:

```bash
uv run python scripts/evaluate_adl_labels.py \
  --train-ratio 0.7
```

分割時は、前半でpattern to ADL対応を学習し、後半で評価する。

### skip-other一致

短時間の「その他」状態を1個まで無視したい場合:

```bash
uv run python scripts/evaluate_adl_labels.py \
  --match-mode skip-other \
  --max-skip-duration-minutes 1
```

まずは `exact` の結果を基準として報告する。

## テスト

ADL評価モジュールの単体テスト:

```bash
uv run python -m unittest discover -s tests
```

確認している内容:

- CASASラベルを区間化できる。
- 状態系列からパターン出現区間を検出できる。
- overlapとTemporal IoUを計算できる。
- TP, FP, FNを数えられる。
- 同じ正解区間に複数の予測が重複マッチしない。

## 注意点

- この評価はラベル付きCASASデータに依存するため、ラベルなしの `data/aruba.txt` では実行できない。
- パターンとADLの対応付けを同じ期間で行う場合はdescriptive evaluationとして扱う。
- 評価4は既存の前処理、代表状態抽出、LLM抽出ロジックを変更せず、後段評価として実行する。
