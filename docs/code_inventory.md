# Code Inventory

この文書は、現在のパッケージ化後のリポジトリ構造と処理内容をまとめた台帳です。Pythonファイル単位の詳細は `docs/python_file_inventory.md` を参照してください。

## 現在の実装配置

主要な実装本体は `src/behavior_pattern_mining/` にあります。実験の実行入口は `scripts/` に集約しています。

| 責務 | 実装本体 | 実行入口 |
|---|---|---|
| 前処理・代表状態・遷移ネットワーク・可視化 | `src/behavior_pattern_mining/visualization/state_transition_visualizer.py` | `scripts/run_build_network.py` |
| 遷移確率ベースライン | `src/behavior_pattern_mining/baselines/transition_probability.py` | `scripts/run_baselines.py` |
| 頻度ベースライン | `src/behavior_pattern_mining/baselines/frequency.py` | `scripts/run_baselines.py` |
| 提案手法LLM抽出 | `src/behavior_pattern_mining/llm/pattern_extractor.py` | `scripts/run_llm_extraction.py` |
| LLM複数回実行評価 | `src/behavior_pattern_mining/pipelines/llm_eval_batch.py` | `scripts/run_llm_eval_batch.py` |
| direct log baseline | `src/behavior_pattern_mining/llm/direct_log_extractor.py`, `src/behavior_pattern_mining/evaluation/direct_log.py` | `scripts/run_direct_log_baseline.py` |
| Precision/Recall/F1評価 | `src/behavior_pattern_mining/evaluation/compare_patterns.py`, `src/behavior_pattern_mining/evaluation/metrics.py` | `scripts/run_evaluation.py` |
| Groundedness | `src/behavior_pattern_mining/evaluation/groundedness.py`, `src/behavior_pattern_mining/evaluation/groundedness_check.py` | `scripts/run_groundedness.py` |
| 条件ベース評価 | `src/behavior_pattern_mining/evaluation/condition_metrics.py` | `scripts/evaluate_condition_metrics.py` |
| ADL評価 | `src/behavior_pattern_mining/evaluation/adl.py` | `scripts/evaluate_adl_labels.py` |

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
| `output/` | LLM出力、ベースライン出力、評価レポート。 |
| `outputs/` | 将来の統合出力先。 |
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
uv run python scripts/evaluate_adl_labels.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --event-log data/aruba.csv \
  --state-table state/aruba_15_1_154days.txt \
  --patterns output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json \
  --output-dir results/adl_evaluation
```

## 設定

| 項目 | 現在値 | 定義箇所 |
|---|---:|---|
| データセット名 | `aruba` | `configs/default.yaml` |
| 代表状態数 K | `15` | `configs/default.yaml` |
| ハミング距離閾値 | `1` | `configs/default.yaml` |
| 分析日数 | `154` | `configs/default.yaml` |
| サンプリング間隔 | `1s` | `configs/default.yaml` |
| 遅延OFF窓幅 | `180`秒 | `configs/default.yaml` |
| 可視化の最小遷移確率 | `0.1` | `configs/default.yaml` |
| ベースライン遷移確率閾値 | `0.2` | `configs/default.yaml` |
| パターン長 | `2-4` | `configs/default.yaml` |
| LLMモデル | `gemini-2.5-pro` | `configs/default.yaml` |
| Temperature | `0.2` | `configs/default.yaml` |

`experiment_config.py` は `configs/default.yaml` を読み込み、既存モジュール向けに定数を公開する互換レイヤーです。現時点では削除しないでください。
