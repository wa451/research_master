# Hestia生成データの統合手順

Webアプリからの生成・提案手法の実行・正解ログによる採点は [評価9](../evaluations/evaluation_9_hestia.md) を参照する。本書は単体CASASログを従来の研究前処理へ渡す手順を扱う。

## 位置づけ

`/Users/wataru/Desktop/master-research/Hestia`はHESTIA論文に着想を得た独立実装である。生成ログは既知scenarioとseedから再現可能なため、本研究パイプラインの機能試験、パラメータ感度確認、ADL対応関係のsanity checkに使える。一方、実Arubaのイベント点過程を統計的に代替するデータではない。

## 推奨入力

```bash
cd /Users/wataru/Desktop/master-research/Hestia
uv sync --frozen
uv run smart-home-sim simulate examples/aruba_single_resident.yaml \
  --days 7 --seed 42 --output outputs/hestia_aruba_7d_seed42
```

研究側へ渡すファイルは次の2つ。

- `outputs/hestia_aruba_7d_seed42/casas_motion_door.txt`
- `outputs/hestia_aruba_7d_seed42/casas_sensor_map.json`

`aruba.txt`は旧5フィールド形式を維持する後方互換出力なので、ADL評価入力には使わない。`casas_motion_door.txt`では通常センサー行が4フィールド、活動境界が6フィールドである。

```text
2025-01-06 07:02:21.000000 M001 OFF
2025-01-06 07:02:25.000000 activity::resident_1 START Personal_Hygiene begin
2025-01-06 07:31:00.000000 activity::resident_1 END Personal_Hygiene end
```

## 代表状態・遷移ネットワーク

研究リポジトリ直下で実CLIを使う。

```bash
cd /Users/wataru/Desktop/master-research
uv run python scripts/run_build_network_from_labeled_casas.py \
  --labeled-casas /Users/wataru/Desktop/master-research/Hestia/outputs/hestia_aruba_7d_seed42/casas_motion_door.txt \
  --sensor-map /Users/wataru/Desktop/master-research/Hestia/outputs/hestia_aruba_7d_seed42/casas_sensor_map.json \
  --keep-converted-csv /tmp/hestia_aruba_7d.csv \
  --days 7 --n-states 15 --hamming-threshold 0 --smoothing-window-sec 5
```

上記は次の既存条件を通る。

1. CASASテキストからON/OFF/OPEN/CLOSEを4列CSVへ変換。
2. 1秒Sample-and-Hold。
3. 5秒遅延OFFによるchattering除去。
4. 連続同一ベクトル圧縮。
5. 上位K=15代表状態。
6. h=0の完全一致写像、非一致は`Other/その他`。
7. 自己連続遷移圧縮、遷移回数・確率。
8. Morning/Daytime/Night/Midnight分割。

入力CSV名が`hestia_aruba_7d.csv`の場合、成果物は概ね次になる。

- `state/hestia_aruba_7d_15_0_7days.txt`
- `picture/hestia_aruba_7d_15_0_7days/state_transition_all.json`
- 同フォルダの時間帯別JSON/PNG/EPS/timeline

既存`aruba_*`成果物を上書きしないよう、変換CSVのstemを必ず`hestia_*`にする。

## ADL状態系列

ネットワークと同じ1秒/5秒条件を評価側でも使う。

```bash
uv run python scripts/evaluate_adl_labels.py \
  --labeled-casas /Users/wataru/Desktop/master-research/Hestia/outputs/hestia_aruba_7d_seed42/casas_motion_door.txt \
  --state-table state/hestia_aruba_7d_15_0_7days.txt \
  --sensor-map /Users/wataru/Desktop/master-research/Hestia/outputs/hestia_aruba_7d_seed42/casas_sensor_map.json \
  --state-series-preprocessing network-equivalent \
  --smoothing-window-sec 5 --hamming-threshold 0 --state-series-days 7 \
  --write-state-series /tmp/hestia_aruba_7d_state_series.csv \
  --state-series-only
```

2026-08-01の統合監査では、Hestia seed 42について次を確認した。

| days | CASAS sensor events | compressed state intervals | ADL intervals |
|---:|---:|---:|---:|
| 1 | 87 | 29 | 11 |
| 7 | 551 | 213 | 76 |

7日では4時間帯すべての遷移JSONが生成された。1日ではNight/Midnightの有効遷移が不足し、一部mode JSONが生成されない場合がある。

## LLM段階

`picture/.../state_transition_<Mode>.json`は既存`pattern_extractor.py`が列挙する入力形式である。監査では`find_mode_json_files`、`mode_label_from_path`、`build_user_message`まで実行し、4時間帯のAPI入力文字列を構築した。外部Gemini APIは呼び出していない。

LLMを呼ぶ実験は、APIキー、費用、モデル版、run数を実験計画で明示した別runとして行うこと。単なる統合確認では呼び出さない。

## 評価上の注意

- Hestiaの1人scenarioをADL教師区間用途の標準とする。研究parserは同名ADLが複数住人で重なる場合にresident IDを区別しない。
- Hestiaの`Personal_Hygiene`は既存`ADL_CATEGORY_MAP`で`Wake-up`へ正規化される一方、`Bed_Toilet_Transition`は同マップに存在しないため`Other_ADL`になる。複数ラベル評価では`Personal_Hygiene`が`Wake-up`と`Hygiene`の両方へ対応する点も含め、評価対象カテゴリを実験前に確認する。
- K=15、h=0では生成7日の`Other`滞在比率が72.7%だった。実Aruba先頭7日の2.1%とは大きく異なる。
- 生成側は約79 sensor events/day、実Aruba先頭7日は約6,924 events/dayだった。実データの反復モーション発火・ノイズ・欠測を生成しない。
- したがってHestia結果を実Aruba結果と混ぜて集計せず、dataset列とscenario/seedを必ず成果物に記録する。
- Hestiaを使った診断評価を提案手法の正式性能値として報告しない。

詳細な意味論・統計・再現性監査はHestia側の次を参照する。

- `reports/semantic_audit.md`
- `reports/pipeline_integration_report.md`
- `reports/data_quality_report.md`
- `reports/data_quality_metrics.csv`
- `reports/reproducibility_report.md`
