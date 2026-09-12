# 作業入口の索引

確認日: 2026-09-09。該当行から必要な参照だけ読む。詳細仕様はリンク先docsに置く。

| 作業 | 最初の参照・実装 | 最小テスト |
|---|---|---|
| 評価1〜9 | [評価番号別ルート](EVALUATION_ROUTES.md) の該当節 | 同じ節に記載 |
| 前処理・Sample-and-Hold・遅延OFF | [pipeline](../pipeline.md) → [state_vectors.py](../../src/behavior_pattern_mining/data/state_vectors.py) | [test_state_vector_and_transition_utils.py](../../tests/test_state_vector_and_transition_utils.py) |
| 代表状態・ハミング写像 | [state_mapping.py](../../src/behavior_pattern_mining/states/state_mapping.py)、代表状態の抽出は下行の統括クラス | [test_state_mapping.py](../../tests/test_state_mapping.py) |
| 遷移・network・図/JSON出力 | [transitions.py](../../src/behavior_pattern_mining/network/transitions.py)、統括 [state_transition_visualizer.py](../../src/behavior_pattern_mining/visualization/state_transition_visualizer.py) | [test_state_vector_and_transition_utils.py](../../tests/test_state_vector_and_transition_utils.py)、出力統括は [test_core_logic.py](../../tests/test_core_logic.py) |
| ラベル付きCASASからnetwork構築 | [run_build_network_from_labeled_casas.py](../../scripts/run_build_network_from_labeled_casas.py) | [test_run_build_network_from_labeled_casas.py](../../tests/test_run_build_network_from_labeled_casas.py) |
| baseline | [frequency.py](../../src/behavior_pattern_mining/baselines/frequency.py)、[transition_probability.py](../../src/behavior_pattern_mining/baselines/transition_probability.py)。FP-Growth系は [adl_correspondence.py](../../src/behavior_pattern_mining/evaluation/adl_correspondence.py)、direct-logは評価3 | [test_core_logic.py](../../tests/test_core_logic.py)、評価5は [test_adl_correspondence.py](../../tests/test_adl_correspondence.py) |
| LLM抽出・応答解析・prompt | [run_llm_extraction.py](../../scripts/run_llm_extraction.py) → [pattern_extractor.py](../../src/behavior_pattern_mining/llm/pattern_extractor.py)、共通解析 [client.py](../../src/behavior_pattern_mining/llm/client.py) の `parse_pattern_records`。編集前に [保全判断](DECISIONS.md) | [test_llm_response_parsing.py](../../tests/test_llm_response_parsing.py)、[test_llm_prompt_files_unchanged.py](../../tests/test_llm_prompt_files_unchanged.py) |
| Web・Streamlit | [dashboard文書](../evaluation_streamlit_dashboard.md) → [streamlit_app.py](../../app/streamlit_app.py) UI、[command_builder.py](../../app/command_builder.py) の `build_evaluationN_steps`、[utils.py](../../app/utils.py) 実行支援 | 評価ルートのテスト。UI一般の専用テストは未整備 |
| 設定・既定値 | [設定の注意](../code_inventory.md#共通設定の注意) → [default.yaml](../../configs/default.yaml) → [config.py](../../src/behavior_pattern_mining/config.py) → [experiment_config.py](../../experiment_config.py)。全CLIに伝播するとは限らない | [test_core_logic.py](../../tests/test_core_logic.py) |
| 成果物・再現手順 | [artifact_policy](../artifact_policy.md)、[experiment_reproduction](../experiment_reproduction.md)、[paper_parameters](../paper_parameters.md) | 対象producer/consumerのテスト |
| Hestia・合成データ接続 | 評価9ルート → 必要時 [hestia_dataset_integration](../hestia_dataset_integration.md)。`Hestia/` は親Git管理外の独立repo、通常探索に含めない | 評価9ルート |

## 流れと探索境界

- 通常CSV → [run_build_network.py](../../scripts/run_build_network.py) → `StateTransitionVisualizer.main` → 前処理 → 代表状態抽出・写像 → 遷移集計 → 状態表・時間帯別JSON → LLM / baseline → 評価。
- `data/`・`new_labeled_data/` は入力、`state/` は状態表、`picture/` は図とLLM入力の遷移JSON、`output/` は抽出・中間物、`results/` は後段評価。成果物を確認する時だけ対象runの必要なファイルを読む。
- `scripts/` は実行入口だが評価5〜8には入出力・集計も残る。`src/` だけ検索して調査完了としない。全体像が不足する場合のみ [code_inventory](../code_inventory.md)、全Python台帳が必要な時のみ [python_file_inventory](../python_file_inventory.md)。
- 旧入口 `run_build_network.py`、`run_baselines.py`、`run_all.py`、`run_llm_eval_batch.py` は引数を解析せず実処理へ進む。`--help` による安全確認は禁止。他の入口も委譲先・import時処理を確認してから実行する。

## 確認コマンド

- 対象テスト1件: `uv run python -m unittest discover -s tests -p 'test_adl_correspondence.py'`（ファイル名を対象に置換）。全体テストは必要時のみ `uv run python -m unittest discover -s tests`。
- メモ/skill参照の検査: `python3 .agents/skills/codex-memory-maintenance/scripts/check_context.py`。内容の正しさ・研究仕様・外部URLの到達性は検証しない。
