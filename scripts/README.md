# Scripts

実験の実行入口です。再利用する実装は主に `src/behavior_pattern_mining/` にありますが、後段評価の入出力・集計処理は一部のscriptにも残っています。

## 主な入口

- `run_all.py`: 提案手法の主要パイプラインを順番に実行。
- `run_build_network.py`: 前処理、代表状態抽出、状態遷移ネットワーク構築、図出力。
- `run_build_network_from_labeled_casas.py`: ラベル付きCASAS txtだけから前処理、代表状態抽出、状態遷移ネットワーク構築、図出力。評価6では `--days 14` を使い、条件変更時は `--n-states`、`--hamming-threshold`、`--smoothing-window-sec` を追加する。
- `run_baselines.py`: 遷移確率ベースラインと頻度ベースラインを実行。
- `run_llm_extraction.py`: 提案手法のLLM抽出のみ実行。評価6では `--days 14` を使い、条件変更時は `--n-states` と `--hamming-threshold`、5回分を作る場合は `--runs 5` を追加する。特定runだけを追加生成する場合は `--run-ids 2 3` を使う。
- `run_evaluation7_top_condition_repeats.py`: 評価7の初回summaryから上位条件を選び、初回run 1を含む合計run数まで不足するLLM出力だけを生成して条件manifestを保存する。
- `run_llm_eval_batch.py`: 提案手法を複数回実行し、評価をExcelに集計。
- `run_direct_log_baseline.py`: ラベル付きCASAS txt由来の代表状態系列を、ネットワーク化せず直接LLMへ入力するベースラインと評価を実行。代表状態の最終写像には未解決の条件差があるため `docs/known_issues.md` のKI-04を参照する。評価6では `--log-days 14 --extract-only` を使い、条件変更時は `--n-states` と `--hamming-threshold`、5回分を作る場合は `--runs 5` を追加する。
- `run_evaluation.py`: 既存LLM出力に対するベースライン比較評価。
- `run_groundedness.py`: Groundedness評価。
- `evaluate_condition_metrics.py`: 条件ベース評価。
- `evaluate_adl_labels.py`: ラベル付きCASASデータによるADL評価。
- `evaluate_adl_correspondence.py`: 頻度、ルール、FP-Growth、遷移確率、提案手法をUseful non-redundant / Fragmentation / Contextless uselessで横比較する評価。low-information ratioは診断値に限定し、UsefulとContextlessには使用しない。比較可能な短系列―長系列対がないrunも評価可能パターン数を分母としてFragmentationを0にする。
- `evaluate_6_compare_adl_interpretation_set.py`: 評価6について、先頭14日を入力とする提案手法とLLM単独ベースラインを、14日条件の代表状態定義で写像した同じ全220日状態系列上で比較する。`--runs 5` でset一致指標に加え、1 run合計のトークン数・API応答時間の5回平均も出力する。
- `evaluate_7_parameter_sensitivity_adl_interpretation.py`: 評価7について、K・ハミング距離の条件別にADL解釈ラベルset指標を集計する。
- `evaluate_8_frequency_stratified_adl_consistency.py`: 評価8について、own-IDの一意な物理出現数から頻度帯を再構築し、ADL整合性を後段集計する。

新しく実行する場合は、この `scripts/` 側を使ってください。
CLI引数、正式評価条件、出力先は対応する `docs/evaluation_*.md` を参照し、共通既定値と論文採用値の差は `docs/known_issues.md` で確認してください。
