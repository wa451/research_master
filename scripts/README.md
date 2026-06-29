# Scripts

実験の実行入口です。実装本体は `src/behavior_pattern_mining/` にあり、ここにはCLIとして使う薄いスクリプトを置きます。

## 主な入口

- `run_all.py`: 提案手法の主要パイプラインを順番に実行。
- `run_build_network.py`: 前処理、代表状態抽出、状態遷移ネットワーク構築、図出力。
- `run_baselines.py`: 遷移確率ベースラインと頻度ベースラインを実行。
- `run_llm_extraction.py`: 提案手法のLLM抽出のみ実行。
- `run_llm_eval_batch.py`: 提案手法を複数回実行し、評価をExcelに集計。
- `run_direct_log_baseline.py`: 直接ログLLMベースラインと評価を実行。
- `run_evaluation.py`: 既存LLM出力に対するベースライン比較評価。
- `run_groundedness.py`: Groundedness評価。
- `evaluate_condition_metrics.py`: 条件ベース評価。
- `evaluate_adl_labels.py`: ラベル付きCASASデータによるADL評価。

新しく実行する場合は、この `scripts/` 側を使ってください。
