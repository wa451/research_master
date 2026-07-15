# Code Inventory

この文書は、現在のパッケージ化後のリポジトリ構造と処理内容をまとめた台帳です。Pythonファイル単位の詳細は `docs/python_file_inventory.md` を参照してください。

## 現在の実装配置

主要な実装本体は `src/behavior_pattern_mining/` にあります。実験の実行入口は `scripts/` に集約しています。

| 責務 | 実装本体 | 実行入口 |
|---|---|---|
| 前処理・代表状態・遷移ネットワーク・可視化 | `src/behavior_pattern_mining/visualization/state_transition_visualizer.py` | `scripts/run_build_network.py` |
| ラベル付きCASASからのネットワーク構築 | `src/behavior_pattern_mining/visualization/state_transition_visualizer.py` | `scripts/run_build_network_from_labeled_casas.py` |
| 遷移確率ベースライン | `src/behavior_pattern_mining/baselines/transition_probability.py` | `scripts/run_baselines.py` |
| 頻度ベースライン | `src/behavior_pattern_mining/baselines/frequency.py` | `scripts/run_baselines.py` |
| 提案手法LLM抽出 | `src/behavior_pattern_mining/llm/pattern_extractor.py` | `scripts/run_llm_extraction.py` |
| LLM複数回実行評価 | `src/behavior_pattern_mining/pipelines/llm_eval_batch.py` | `scripts/run_llm_eval_batch.py` |
| direct log baseline | `src/behavior_pattern_mining/llm/direct_log_extractor.py`, `src/behavior_pattern_mining/evaluation/direct_log.py` | `scripts/run_direct_log_baseline.py` |
| Precision/Recall/F1評価 | `src/behavior_pattern_mining/evaluation/compare_patterns.py`, `src/behavior_pattern_mining/evaluation/metrics.py` | `scripts/run_evaluation.py` |
| Groundedness | `src/behavior_pattern_mining/evaluation/groundedness.py`, `src/behavior_pattern_mining/evaluation/groundedness_check.py` | `scripts/run_groundedness.py` |
| 条件ベース評価 | `src/behavior_pattern_mining/evaluation/condition_metrics.py` | `scripts/evaluate_condition_metrics.py` |
| ADL評価 | `src/behavior_pattern_mining/evaluation/adl.py` | `scripts/evaluate_adl_labels.py` |
| 評価5: パターン単位ADL-grounded/Useless評価 | `src/behavior_pattern_mining/evaluation/adl_correspondence.py` | `scripts/evaluate_adl_correspondence.py` |
| 評価6: ADL解釈ラベルset比較評価 | `src/behavior_pattern_mining/evaluation/adl_interpretation_set.py` | `scripts/evaluate_6_compare_adl_interpretation_set.py` |

## フォルダの役割

| パス | 役割 |
|---|---|
| `configs/` | 実験設定。現在は `configs/default.yaml` が中心。 |
| `data/` | 入力データ置き場。Git管理外。 |
| `new_labeled_data/` | ラベル付きCASASデータ置き場。 |
| `docs/` | パイプライン、評価手順、再現手順、ファイル台帳などの文書。 |
| `prompts/` | LLMプロンプト。 |
| `scripts/` | 実験・評価のCLI入口。 |
| `src/behavior_pattern_mining/` | 研究ロジックの実装本体。 |
| `state/` | 代表状態テーブル出力。 |
| `picture/` | 状態遷移ネットワークJSON、図、タイムライン出力。 |
| `output/` | LLM出力、ベースライン出力、中間生成物。 |
| `results/` | ADL評価などの後段評価出力。 |
| `support/` | 補助調査スクリプト。 |
| `tests/` | `unittest` ベースの回帰テスト。 |

## 推奨実行順序

```bash
uv run python scripts/run_build_network.py
uv run python scripts/run_baselines.py
uv run python scripts/run_llm_eval_batch.py
uv run python scripts/run_groundedness.py
uv run python scripts/evaluate_condition_metrics.py
```

まとめて実行する場合:

```bash
uv run python scripts/run_all.py
```

ADL評価:

```bash
uv run python scripts/run_build_network_from_labeled_casas.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --sensor-map configs/aruba_sensor_map.json

uv run python scripts/run_llm_extraction.py

uv run python scripts/evaluate_adl_labels.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --state-table state/aruba_15_1_154days.txt \
  --sensor-map configs/aruba_sensor_map.json \
  --patterns output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json \
  --output-dir results/4_adl_detect
```

評価5: パターン単位ADL-grounded/Useless評価:

```bash
uv run python scripts/evaluate_adl_correspondence.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --state-series results/4_adl_detect/state_series.csv \
  --patterns-frequency output/aruba_15_1_154days/state_sequence_counts_15_1_154days.json \
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
  --other-state-labels その他 Other Other_ADL unknown \
  --exclude-other-adl-from-any \
  --min-overlap-seconds 1
```

評価6: LLM解釈ラベルとADL重なりラベルのset一致比較:

```bash
uv run python scripts/run_build_network_from_labeled_casas.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --sensor-map configs/aruba_sensor_map.json \
  --days 30

uv run python scripts/run_llm_extraction.py --days 30

uv run python scripts/evaluate_adl_labels.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --state-table state/aruba_15_1_30days.txt \
  --sensor-map configs/aruba_sensor_map.json \
  --patterns output/aruba_15_1_30days/llm_sequences_modes_15_1_30days_1.json \
  --output-dir output/6_adl_evaluation_30 \
  --write-state-series output/6_adl_evaluation_30/state_series.csv

uv run python scripts/run_direct_log_baseline.py \
  --log-days 30 \
  --extract-only

uv run python scripts/evaluate_6_compare_adl_interpretation_set.py \
  --patterns-proposed output/aruba_15_1_30days/llm_sequences_modes_15_1_30days_1.json \
  --patterns-direct output/llm_direct_15_1_30days/1.json \
  --state-series output/6_adl_evaluation_30/state_series.csv \
  --labeled-casas new_labeled_data/aruba.txt \
  --output-dir results/6_adl_match \
  --min-overlap-ratio-for-true-label 0.10
```

## 設定

| 項目 | 現在値 | 定義箇所 |
|---|---:|---|
| データセット名 | `aruba` | `configs/default.yaml` |
| 代表状態数 K | `15` | `configs/default.yaml` |
| ハミング距離閾値 | `1` | `configs/default.yaml` |
| 分析日数 | `154` | `configs/default.yaml` |
| サンプリング間隔 | `1s` | `configs/default.yaml` |
| 遅延OFF窓幅 | `5`秒 | `configs/default.yaml` |
| 可視化の最小遷移確率 | `0.1` | `configs/default.yaml` |
| ベースライン遷移確率閾値 | `0.2` | `configs/default.yaml` |
| パターン長 | `2-4` | `configs/default.yaml` |
| LLMモデル | `gemini-2.5-pro` | `configs/default.yaml` |
| Temperature | `0.2` | `configs/default.yaml` |
| ADL予測最小継続時間 | ADLカテゴリ別 | `configs/adl_min_duration.json` |
| Arubaラベル付きCASASセンサーID対応 | `M001` などを部屋名へ変換 | `configs/aruba_sensor_map.json` |

`experiment_config.py` は `configs/default.yaml` を読み込み、既存モジュール向けに定数を公開する互換レイヤーです。現時点では削除しないでください。
