# Scripts

実験の実行入口です。実装本体は `src/behavior_pattern_mining/` にあり、ここにはCLIとして使う薄いスクリプトを置きます。

## 主な入口

- `run_all.py`: 提案手法の主要パイプラインを順番に実行。
- `run_build_network.py`: 前処理、代表状態抽出、状態遷移ネットワーク構築、図出力。
- `run_build_network_from_labeled_casas.py`: ラベル付きCASAS txtだけから前処理、代表状態抽出、状態遷移ネットワーク構築、図出力。評価6では `--days 14` を使い、条件変更時は `--n-states`、`--hamming-threshold`、`--smoothing-window-sec` を追加する。
- `run_baselines.py`: 遷移確率ベースラインと頻度ベースラインを実行。
- `run_llm_extraction.py`: 提案手法のLLM抽出のみ実行。評価6では `--days 14` を使い、条件変更時は `--n-states` と `--hamming-threshold`、5回分を作る場合は `--runs 5` を追加する。特定runだけを追加生成する場合は `--run-ids 2 3` を使う。
- `run_evaluation7_top_condition_repeats.py`: 評価7の初回summaryから上位条件を選び、初回run 1を含む合計run数まで不足するLLM出力だけを生成して条件manifestを保存する。
- `run_llm_eval_batch.py`: 提案手法を複数回実行し、評価をExcelに集計。
- `run_direct_log_baseline.py`: ラベル付きCASAS txtへ抽出側と同じ前処理・代表状態写像を適用し、同期間の代表状態系列をネットワーク化せず直接LLMへ入力するベースラインと評価を実行。評価6では `--log-days 14 --extract-only` を使い、条件変更時は `--n-states` と `--hamming-threshold`、5回分を作る場合は `--runs 5` を追加する。
- `run_evaluation.py`: 既存LLM出力に対するベースライン比較評価。
- `run_groundedness.py`: Groundedness評価。
- `evaluate_condition_metrics.py`: 条件ベース評価。
- `evaluate_adl_labels.py`: ラベル付きCASASデータによるADL評価。
- `evaluate_adl_correspondence.py`: 頻度、ルール、FP-Growth、遷移確率、提案手法をUseful non-redundant / Fragmentation / Contextless uselessで横比較する評価。low-information判定用に `--state-definition` または `--state-network-json` が必須で、比較可能な短系列―長系列対がないrunも評価可能パターン数を分母としてFragmentationを0にする。
- `evaluate_6_compare_adl_interpretation_set.py`: 評価6について、先頭14日を入力とする提案手法とLLM単独ベースラインを、14日条件の代表状態定義で写像した同じ全220日状態系列上で比較する。`--runs 5` でset一致指標に加え、1 run合計のトークン数・API応答時間の5回平均も出力する。

新しく実行する場合は、この `scripts/` 側を使ってください。
