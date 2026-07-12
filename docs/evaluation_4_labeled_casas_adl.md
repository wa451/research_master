# 評価4: ラベル付きCASASデータによる単一手法ADL評価

## 評価の要約

1つの系列パターンファイルをラベル付きCASASデータのADLラベルと照合し、各パターンがどのADLカテゴリに対応するか、ADLカテゴリごとの検出性能、開始・終了境界の一致度を確認する。主な対象は提案手法のLLM出力である。

## RQ

| RQ | 内容 |
|---|---|
| RQ4-1 | 抽出された系列パターンは、どのADLカテゴリに対応するか。 |
| RQ4-2 | `Sleep`, `Wake-up`, `Meal`, `Outing`, `Relax` などのADLをどの程度検出できるか。 |
| RQ4-3 | 予測区間の開始・終了境界は、正解ADL区間とどの程度一致するか。 |
| RQ4-4 | 近接予測のマージと短時間除外により、短いパターン出現の過剰予測を抑えられるか。 |

## 評価指標

| 指標 | 定義・確認内容 |
|---|---|
| ADLカテゴリ別Precision / Recall / F1 | IoU閾値以上で一致した予測区間をTPとして計算する。 |
| Temporal IoU | `overlap_duration / union_duration`。既定閾値は `0.3`, `0.5`。 |
| 境界誤差 | TPペアについて、開始・終了時刻の誤差を分単位で集計する。 |
| ADL interval hit rate | 正解ADL区間に同じADL予測が1回以上出たかを見る。 |
| prediction hit precision | 予測区間のうち、正解ADL区間に重なった割合を見る。 |
| pattern-to-ADL confidence | パターン出現時間のうち、割当ADLと重なった時間割合。 |

## 入力と出力

### 入力

| 入力 | 既定パス | 役割 |
|---|---|---|
| ラベル付きCASAS | `new_labeled_data/aruba.txt` | ADL begin/endラベルとセンサーイベントを含む正解データ。 |
| 代表状態テーブル | `state/aruba_15_1_154days.txt` | センサー状態を代表状態IDに対応付ける。 |
| センサーマップ | `configs/aruba_sensor_map.json` | `M003` などを代表状態テーブルの列名へ対応付ける。 |
| LLM抽出パターン | `output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json` | 評価対象の系列パターン。 |
| 最小継続時間設定 | `configs/adl_min_duration.json` | ADLカテゴリ別の短時間予測除外設定。 |

評価4では、ADL正解ラベルと代表状態系列の再構築に `new_labeled_data/aruba.txt` を使う。`data/aruba.csv` は使わない。

### 出力

| 出力 | 内容 |
|---|---|
| `results/4_adl_detect/pattern_occurrences.csv` | パターン出現区間。 |
| `results/4_adl_detect/pattern_adl_mapping.csv` | パターンごとのADL割当。 |
| `results/4_adl_detect/merged_predictions.csv` | 同じADLの近接予測をマージした区間。 |
| `results/4_adl_detect/filtered_predictions.csv` | 最小継続時間フィルタ後の予測区間。 |
| `results/4_adl_detect/adl_metrics_iou_0.3.csv` | IoU `0.3` のADLカテゴリ別Precision / Recall / F1。 |
| `results/4_adl_detect/adl_metrics_iou_0.5.csv` | IoU `0.5` のADLカテゴリ別Precision / Recall / F1。 |
| `results/4_adl_detect/boundary_metrics_iou_0.3.csv` | IoU `0.3` の境界誤差。 |
| `results/4_adl_detect/boundary_metrics_iou_0.5.csv` | IoU `0.5` の境界誤差。 |
| `results/4_adl_detect/adl_interval_hit_metrics.csv` | ADL区間内hit評価。 |
| `results/4_adl_detect/adl_interval_hit_details.csv` | 各正解区間のhit/miss詳細。 |
| `results/4_adl_detect/evaluation_summary.json` | 入力パス、閾値、後処理件数、平均指標。 |
| `results/4_adl_detect/state_series.csv` | 評価5などで再利用する代表状態系列CSV。`--write-state-series` 指定時に保存。 |

## 結果の読み方

| 順序 | ファイル | 読み方 |
|---|---|---|
| 1 | `evaluation_summary.json`, `adl_metrics_iou_0.3.csv`, `adl_interval_hit_metrics.csv` | summaryとして、macro/micro平均、ADL別F1、hit rate、後処理で予測数がどれだけ減ったかを見る。 |
| 2 | `pattern_occurrences.csv`, `pattern_adl_mapping.csv`, `filtered_predictions.csv`, `adl_interval_hit_details.csv` | detailsとして、どのパターンがいつ出現し、どのADLに割り当てられ、どの正解区間をmissしたかを見る。 |
| 3 | `evaluation_summary.json`, `configs/adl_min_duration.json`, `configs/aruba_sensor_map.json` | 再現条件として、入力パス、IoU閾値、マージ幅、最小継続時間、センサーマップを確認する。 |

## 実行手順

### 1. 🟨 **条件付き** 状態遷移ネットワークと代表状態テーブルを作成する

`state/aruba_15_1_154days.txt` がなければ実行する。ラベル付きCASASのみを入力に使い、`data/aruba.csv` は使わない。

```bash
uv run python scripts/run_build_network_from_labeled_casas.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --sensor-map configs/aruba_sensor_map.json
```

### 2. 🟨 **条件付き** 状態遷移ネットワークからLLMパターンを抽出する

`output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json` がなければ実行する。既に同じ条件のLLM出力がある場合はスキップしてよい。

```bash
uv run python scripts/run_llm_extraction.py
```

### 3. 🟥 **必須** 評価4を実行する

ADL区間評価を作るために実行する。`--write-state-series` により、評価5や評価6でも使える代表状態系列CSVを同時に保存する。

```bash
uv run python scripts/evaluate_adl_labels.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --state-table state/aruba_15_1_154days.txt \
  --sensor-map configs/aruba_sensor_map.json \
  --patterns output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json \
  --output-dir results/4_adl_detect \
  --iou-thresholds 0.3 0.5 \
  --wake-window-minutes 30 \
  --match-mode exact \
  --merge-gap-minutes 5 \
  --min-duration-config configs/adl_min_duration.json \
  --hit-tolerance-minutes 10 \
  --write-state-series results/4_adl_detect/state_series.csv
```

### 4. 🟩 **スキップ可** 代表状態系列CSVだけを再利用する

`results/4_adl_detect/state_series.csv` が既にあり、評価5だけを実行したい場合は評価4の再実行を省いてよい。このStepの追加コマンドはない。

## 比較対象

| 対象 | 内容 |
|---|---|
| 評価対象パターン | `--patterns` で指定した1つの系列パターンファイル。 |
| 正解ADL区間 | `new_labeled_data/aruba.txt` のactivity `begin/end` から区間化したADL。 |
| 予測ADL区間 | パターン出現区間に `assigned_adl` を付与し、マージ・短時間除外した区間。 |

複数手法を横比較する場合は評価5を使う。

## 処理手順の内部仕様

1. CASAS activity `begin/end` を `start_time, end_time, raw_label, adl_category` に区間化する。
2. `--state-series` が指定されていればCSVを読み込む。指定がなければ `--labeled-casas`, `--state-table`, `--sensor-map` から代表状態系列を再構築する。
3. LLMパターンを代表状態系列上で検索し、`pattern_occurrences.csv` を作る。
4. パターン出現区間とADL区間の重なり時間を集計し、最も重なりが大きいADLを `assigned_adl` とする。
5. 同じADLの近接予測を `--merge-gap-minutes` 以内でマージする。
6. ADLカテゴリ別の最小継続時間より短い予測を除外する。
7. 後処理後の予測区間でIoU評価、境界評価、ADL interval hit評価を行う。

## パラメータ

| パラメータ | 既定値・例 |
|---|---|
| `--labeled-casas` | `new_labeled_data/aruba.txt` |
| `--state-table` | `state/aruba_15_1_154days.txt` |
| `--sensor-map` | `configs/aruba_sensor_map.json` |
| `--patterns` | `output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json` |
| `--output-dir` | `results/4_adl_detect` |
| `--iou-thresholds` | `0.3 0.5` |
| `--wake-window-minutes` | `30` |
| `--match-mode` | `exact` |
| `--merge-gap-minutes` | `5` |
| `--min-duration-config` | `configs/adl_min_duration.json` |
| `--hit-tolerance-minutes` | `10` |

最小継続時間の既定値は `configs/adl_min_duration.json` に保存する。例: `Sleep=600`, `Relax=180`, `Meal=120`, `Wake-up=30` 秒。

## 注意点

- ラベル付きCASASデータに依存するため、ラベルなしの `data/aruba.txt` では実行しない。
- パターンとADLの対応付けを同じ期間で行う場合はdescriptive evaluationとして扱う。
- 評価4は既存の前処理、代表状態抽出、LLM抽出ロジックを変更せず、後段評価として実行する。
- マージ幅や最小継続時間の設定によりPrecision / Recall / F1は変わるため、報告時は後処理条件を併記する。
