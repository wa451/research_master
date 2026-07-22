# Code Inventory

この文書は、処理の責務と主要な実装・実行入口の対応を示す。個々のPythonファイルの台帳は [python_file_inventory.md](python_file_inventory.md)、処理のデータフローは [pipeline.md](pipeline.md) を参照する。

## 責務の配置

| 責務 | 主な実装 | 実行入口 |
|---|---|---|
| Sample-and-Hold、遅延OFF、連続状態圧縮 | `src/behavior_pattern_mining/data/state_vectors.py` | `scripts/run_build_network.py` |
| 代表状態抽出・写像 | `src/behavior_pattern_mining/states/state_mapping.py`, `src/behavior_pattern_mining/visualization/state_transition_visualizer.py` | `scripts/run_build_network.py`, `scripts/run_build_network_from_labeled_casas.py` |
| 状態遷移回数・確率・滞在時間 | `src/behavior_pattern_mining/network/transitions.py` | 上記network構築入口 |
| JSON・状態表・図の出力統括 | `src/behavior_pattern_mining/visualization/state_transition_visualizer.py` | 上記network構築入口 |
| 遷移確率baseline | `src/behavior_pattern_mining/baselines/transition_probability.py` | `scripts/run_baselines.py` |
| 頻度baseline | `src/behavior_pattern_mining/baselines/frequency.py` | `scripts/run_baselines.py` |
| 提案手法のLLM抽出 | `src/behavior_pattern_mining/llm/pattern_extractor.py` | `scripts/run_llm_extraction.py` |
| 複数run抽出・旧比較集計 | `src/behavior_pattern_mining/pipelines/llm_eval_batch.py` | `scripts/run_llm_eval_batch.py` |
| direct-log LLM baseline | `src/behavior_pattern_mining/llm/direct_log_extractor.py`, `src/behavior_pattern_mining/evaluation/direct_log.py` | `scripts/run_direct_log_baseline.py` |
| Precision/Recall/F1比較 | `src/behavior_pattern_mining/evaluation/metrics.py`, `src/behavior_pattern_mining/evaluation/compare_patterns.py` | `scripts/run_evaluation.py` |
| Groundedness | `src/behavior_pattern_mining/evaluation/groundedness.py`, `src/behavior_pattern_mining/evaluation/groundedness_check.py` | `scripts/run_groundedness.py` |
| 条件ベース評価 | `src/behavior_pattern_mining/evaluation/condition_metrics.py` | `scripts/evaluate_condition_metrics.py` |
| 評価4 | `src/behavior_pattern_mining/evaluation/adl.py` | `scripts/evaluate_adl_labels.py` |
| 評価5 | `src/behavior_pattern_mining/evaluation/adl_correspondence.py` | `scripts/evaluate_adl_correspondence.py` |
| 評価6 | `src/behavior_pattern_mining/evaluation/adl_interpretation_set.py`, `src/behavior_pattern_mining/evaluation/llm_usage.py` | `scripts/evaluate_6_compare_adl_interpretation_set.py` |
| 評価7 | `src/behavior_pattern_mining/evaluation/evaluation7_staged.py` | `scripts/evaluate_7_parameter_sensitivity_adl_interpretation.py`, `scripts/run_evaluation7_top_condition_repeats.py` |
| 評価8 | `src/behavior_pattern_mining/evaluation/adl_interpretation_set.py` と評価8スクリプト内の後段集計 | `scripts/evaluate_8_frequency_stratified_adl_consistency.py` |
| Streamlitラッパー | `app/streamlit_app.py`, `app/command_builder.py`, `app/utils.py` | `uv run streamlit run app/streamlit_app.py` |

`scripts/` は実行入口だが、すべてが薄いラッパーではない。特に後段評価スクリプトには入出力・集計処理が残るため、修正時は `src/` だけでなく対象scriptも確認する。

## ディレクトリの役割

| パス | 役割 |
|---|---|
| `configs/` | 共通既定値、センサー対応、ADL最小時間設定 |
| `data/`, `new_labeled_data/` | 生入力。Git管理・編集対象外 |
| `prompts/` | 実行時に読むLLMプロンプト |
| `scripts/` | 実験・評価の実行入口 |
| `src/behavior_pattern_mining/` | 再利用する研究ロジック |
| `app/` | 既存CLIを組み立てて実行するStreamlit UI |
| `tests/` | 回帰テスト |
| `state/` | 代表状態表 |
| `picture/` | 状態遷移JSON、遷移図、timeline図 |
| `output/` | LLM出力、baseline、中間成果物 |
| `results/` | 後段評価結果 |

## 文書の正本

| 確認内容 | 文書 |
|---|---|
| センサログから評価までの流れ | [pipeline.md](pipeline.md) |
| 評価全体の入口と順序 | [experiment_reproduction.md](experiment_reproduction.md) |
| 論文採用パラメータ | [paper_parameters.md](paper_parameters.md) |
| 評価固有のCLI・入出力・指標 | `evaluation_1_*.md` から `evaluation_8_*.md` |
| 成果物の扱い | [artifact_policy.md](artifact_policy.md) |
| 未確定の実装・文書差 | [known_issues.md](known_issues.md) |
| 段階的な構造整理の記録 | [refactoring_plan.md](refactoring_plan.md) |

## 共通設定の注意

`experiment_config.py` は `configs/default.yaml` を読み、既存モジュールへ定数を公開する互換レイヤーである。ただし、すべてのCLI引数や入出力パスを設定ファイルが支配するわけではない。共通既定の `K=15, h=1, 154日` と、論文採用条件の `K=15, h=0` を区別し、対象評価のCLIと [known_issues.md](known_issues.md) を確認する。
