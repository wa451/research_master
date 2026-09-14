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
| 最小継続時間設定 | `configs/adl_min_duration.json` | 推奨手順で明示指定するADLカテゴリ別の短時間予測除外設定。CLI既定はファイル未指定で、実装内既定値を使う。 |

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
| `results/4_adl_detect/state_series.csv` | `--write-state-series` 指定時に保存する代表状態系列CSV。下流で再利用する場合は、抽出側・下流側と前処理条件が一致するか確認する（[KI-06](../research/known_issues.md)）。 |

## 結果の読み方

| 順序 | ファイル | 読み方 |
|---|---|---|
| 1 | `evaluation_summary.json`, `adl_metrics_iou_0.3.csv`, `adl_interval_hit_metrics.csv` | summaryとして、macro/micro平均、ADL別F1、hit rate、後処理で予測数がどれだけ減ったかを見る。 |
| 2 | `pattern_occurrences.csv`, `pattern_adl_mapping.csv`, `filtered_predictions.csv`, `adl_interval_hit_details.csv` | detailsとして、どのパターンがいつ出現し、どのADLに割り当てられ、どの正解区間をmissしたかを見る。 |
| 3 | `evaluation_summary.json`, `configs/adl_min_duration.json`, `configs/aruba_sensor_map.json` | 再現条件として、入力パス、IoU閾値、マージ幅、最小継続時間、センサーマップを確認する。 |

## 実行手順

### 1. 🟨 **条件付き** 状態遷移ネットワークと代表状態テーブルを作成する

`state/aruba_15_1_154days.txt` がなければ実行する。ラベル付きCASASのみを入力に使い、`data/aruba.csv` は使わない。以下は文書中の互換条件を明示した再現例である。現論文条件 `h=0` との関係は未解決である（[KI-01](../research/known_issues.md)）。

```bash
uv run python scripts/run_build_network_from_labeled_casas.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --sensor-map configs/aruba_sensor_map.json \
  --days 154 \
  --n-states 15 \
  --hamming-threshold 1 \
  --smoothing-window-sec 5
```

### 2. 🟨 **条件付き** 状態遷移ネットワークからLLMパターンを抽出する

`output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json` がなければ実行する。既に同じ条件のLLM出力がある場合はスキップしてよい。前段と同じ条件を明示する。

```bash
uv run python scripts/run_llm_extraction.py \
  --days 154 \
  --runs 1 \
  --n-states 15 \
  --hamming-threshold 1
```

### 3. 🟥 **必須** 評価4を実行する

ADL区間評価を作るために実行する。`--write-state-series` により代表状態系列CSVを同時に保存する。以下は現在のCLI既定である `event-driven` を明示した互換手順であり、抽出側と同じ `network-equivalent` を正式条件にするかは未解決である（[KI-06](../research/known_issues.md)）。splitを指定しないため、同一期間で対応付けと評価を行うdescriptive evaluationになる（[KI-07](../research/known_issues.md)）。

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
  --max-skip-duration-minutes 1 \
  --hamming-threshold 1 \
  --state-series-preprocessing event-driven \
  --merge-gap-minutes 5 \
  --min-duration-config configs/adl_min_duration.json \
  --hit-tolerance-minutes 10 \
  --write-state-series results/4_adl_detect/state_series.csv
```

### 4. 🟩 **スキップ可** 代表状態系列CSVだけを再利用する

`results/4_adl_detect/state_series.csv` が既にあり、下流評価だけを実行したい場合は評価4の再実行を省いてよい。ただし、保存時の `event-driven` / `network-equivalent`、平滑化、期間、K/hが下流条件と一致する場合に限る（[KI-06](../research/known_issues.md)）。このStepの追加コマンドはない。

## 比較対象

| 対象 | 内容 |
|---|---|
| 評価対象パターン | `--patterns` で指定した1つの系列パターンファイル。 |
| 正解ADL区間 | `new_labeled_data/aruba.txt` のactivity `begin/end` から区間化したADL。 |
| 予測ADL区間 | パターン出現区間に `assigned_adl` を付与し、マージ・短時間除外した区間。 |

複数手法を横比較する場合は評価5を使う。

## 処理手順の内部仕様

1. CASAS activity `begin/end` を `start_time, end_time, raw_label, adl_category` に区間化する。
2. `--state-series` が指定されていればCSVを読み込む。指定がなければ `--labeled-casas`, `--state-table`, `--sensor-map` から、`--state-series-preprocessing` で選んだ方法により代表状態系列を再構築する。`event-driven` はラベル付きCASASの全イベント期間を使い、`network-equivalent` では `--state-series-days` によりカレンダー日数を制限できる。
3. LLMパターンを代表状態系列上で検索し、`pattern_occurrences.csv` を作る。
4. パターン出現区間とADL区間の重なり時間を集計し、最も重なりが大きいADLを `assigned_adl` とする。
5. 同じADLの近接予測を `--merge-gap-minutes` 以内でマージする。
6. ADLカテゴリ別の最小継続時間より短い予測を除外する。
7. 後処理後の予測区間でIoU評価、境界評価、ADL interval hit評価を行う。

## パラメータ

| パラメータ | CLI既定 | この文書の互換手順・用途 |
|---|---|---|
| `--labeled-casas` | `new_labeled_data/aruba.txt` | 同左。ADL区間と状態系列再構築の入力。 |
| `--state-series` | 未指定 | 既存CSVを再利用する場合だけ指定。指定時は再構築しない。 |
| `--event-log` | 未指定 | ラベルなしイベントログからevent-driven系列を再構築する場合だけ指定。 |
| `--state-table` | configのK/h/daysから組み立てる | `state/aruba_15_1_154days.txt`。 |
| `--sensor-map` | `configs/aruba_sensor_map.json` | 同左。 |
| `--patterns` | configのK/h/daysから組み立てたrun 1 JSON | `output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json`。 |
| `--output-dir` | `results/4_adl_detect` | 同左。 |
| `--iou-thresholds` | `0.3 0.5` | 同左。 |
| `--wake-window-minutes` | `30` | 同左。ただしADL分類規則は未解決（[KI-07](../research/known_issues.md)）。 |
| `--match-mode` | `exact` | 同左。`skip-other` も選択可能。 |
| `--max-skip-duration-minutes` | `1` | `skip-other` 使用時に無視できる1つの `その他` 区間の上限。 |
| `--hamming-threshold` | config値（現在 `1`） | 状態表・パターン抽出条件と一致させる。正式hは未解決（[KI-01](../research/known_issues.md)）。 |
| `--split-date` | 未指定 | 指定時はこの時刻より前で対応付けを学習し、後を評価する。 |
| `--train-ratio` | 未指定 | `--split-date` 未指定時の時間比率split。splitなしの位置付けは未解決（[KI-07](../research/known_issues.md)）。 |
| `--write-state-series` | 未指定 | 互換手順では `results/4_adl_detect/state_series.csv`。 |
| `--state-series-preprocessing` | `event-driven` | `network-equivalent` も選択可能。正式条件は未解決（[KI-06](../research/known_issues.md)）。 |
| `--smoothing-window-sec` | `5` | `network-equivalent` の遅延OFF窓。event-drivenでは使わない。 |
| `--state-series-days` | 未指定 | `network-equivalent` では未指定時にラベル付きデータの全カレンダー期間を使う。 |
| `--state-series-only` | 無効 | `--write-state-series` で系列だけを作り、パターン・ADL評価前に終了する場合に有効化。 |
| `--merge-gap-minutes` | `5` | 同左。 |
| `--min-duration-config` | 未指定 | 互換手順では `configs/adl_min_duration.json` を明示指定。未指定時は実装内既定値を使う。 |
| `--hit-tolerance-minutes` | `10` | overlap評価に加え、前後10分を許容するtolerance hit評価を出力する。 |

推奨手順で使う `configs/adl_min_duration.json` の値は、例として `Sleep=600`, `Relax=180`, `Meal=120`, `Wake-up=30` 秒である。CLIでファイルを省略した場合も現在は対応する実装内既定値を使うが、設定ファイルのパスはsummaryに記録されない。

## 注意点

- ラベル付きCASASデータに依存するため、ラベルなしの `data/aruba.txt` では実行しない。
- splitなしでは、パターンとADLの対応付けと評価を同じ全期間で行うため、descriptive evaluationとして扱う。検出性能評価としての期間・splitは未解決である（[KI-07](../research/known_issues.md)）。
- 評価4は既存の前処理、代表状態抽出、LLM抽出ロジックを変更せず、後段評価として実行する。
- マージ幅や最小継続時間の設定によりPrecision / Recall / F1は変わるため、報告時は後処理条件を併記する。
- ADL照合用状態系列のCLI既定は `event-driven` で、抽出側の1秒Sample-and-Hold・遅延OFFとは一致しない（[KI-06](../research/known_issues.md)）。
- `Bathroom`, `Personal_Hygiene`, `Bathing` を時間帯によらず `Wake-up` とする現在の分類規則は、正式仕様として未確定である（[KI-07](../research/known_issues.md)）。
