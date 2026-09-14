# 評価番号別の最短ルート

確認日: 2026-09-12。各節の「文書→入口/実装→テスト」を使う。評価変更前は [既知の不一致](../research/known_issues.md) の該当IDも確認。テストは関連候補であり評価全体の保証ではない。
該当節のみ取得: `rg -n -A 6 '^## eval6 ' docs/codex_memory/EVALUATION_ROUTES.md`（番号を置換）。実行条件は仕様docsと実際のCLIで確認する。

## eval1 旧K/h感度分析

- 文書: [評価1](../evaluations/evaluation_1_parameter_sensitivity.md)。現行論文の感度評価はeval7。
- 入口/実装: [run_all.py](../../scripts/run_all.py) → [pipelines/run_all.py](../../src/behavior_pattern_mining/pipelines/run_all.py)。前処理・baselineは [CODEBASE_MAP](CODEBASE_MAP.md)。
- テスト: [test_core_logic.py](../../tests/test_core_logic.py)（部品のみ、旧一括実行の専用テストなし）。
- 注意: KI-01/14。`run_all.py --help` は実処理を起動し得る。

## eval2 提案手法5 run・旧系列一致

- 文書: [評価2](../evaluations/evaluation_2_proposed_method_5runs.md)。
- 入口/実装: [run_llm_eval_batch.py](../../scripts/run_llm_eval_batch.py) → [pipelines/llm_eval_batch.py](../../src/behavior_pattern_mining/pipelines/llm_eval_batch.py)、指標 [metrics.py](../../src/behavior_pattern_mining/evaluation/metrics.py)。
- テスト: [test_core_logic.py](../../tests/test_core_logic.py)（部品のみ、run独立性の専用テストなし）。
- 注意: KI-02/03。batchは非argparse。run1 checkpoint再利用の疑いを解決済みと扱わない。

## eval3 direct-log比較

- 文書: [評価3](../evaluations/evaluation_3_direct_log_baseline_comparison.md)。
- 入口/実装: [run_direct_log_baseline.py](../../scripts/run_direct_log_baseline.py) → [direct_log_extractor.py](../../src/behavior_pattern_mining/llm/direct_log_extractor.py)、[evaluation/direct_log.py](../../src/behavior_pattern_mining/evaluation/direct_log.py)。
- テスト: [test_llm_response_parsing.py](../../tests/test_llm_response_parsing.py)、[test_llm_prompt_files_unchanged.py](../../tests/test_llm_prompt_files_unchanged.py)（抽出保全、比較全体の専用テストなし）。
- 注意: KI-04/05。最終写像の完全一致、固定K/hパス。抽出ファイル編集前に [DECISIONS](DECISIONS.md)。

## eval4 ADL区間・検出指標

- 文書: [評価4](../evaluations/evaluation_4_labeled_casas_adl.md)。
- 入口/実装: [evaluate_adl_labels.py](../../scripts/evaluate_adl_labels.py) → [adl.py](../../src/behavior_pattern_mining/evaluation/adl.py)。
- テスト: [test_adl_evaluation.py](../../tests/test_adl_evaluation.py)。
- 注意: KI-06/07。状態系列生成は後続評価も利用する。

## eval5 有用性・断片化・無文脈

- 文書: [評価5](../evaluations/evaluation_5_adl_correspondence.md)。
- 入口/実装: [evaluate_adl_correspondence.py](../../scripts/evaluate_adl_correspondence.py)（cache・run集計も保持） → [adl_correspondence.py](../../src/behavior_pattern_mining/evaluation/adl_correspondence.py)（FP-Growth/遷移baseline生成も保持）。
- テスト: [test_adl_correspondence.py](../../tests/test_adl_correspondence.py)。
- 注意: low-informationは診断専用。旧引数・空列互換とpair=0の解釈は [DECISIONS](DECISIONS.md)。

## eval6 ADL解釈ラベル集合・LLM使用量

- 文書: [評価6](../evaluations/evaluation_6_adl_interpretation_set.md)。
- 入口/実装: [evaluate_6_compare_adl_interpretation_set.py](../../scripts/evaluate_6_compare_adl_interpretation_set.py)（run集計も保持） → [adl_interpretation_set.py](../../src/behavior_pattern_mining/evaluation/adl_interpretation_set.py)、[llm_usage.py](../../src/behavior_pattern_mining/evaluation/llm_usage.py)。
- テスト: [test_evaluation6_adl_interpretation_set.py](../../tests/test_evaluation6_adl_interpretation_set.py)、[test_evaluation6_default_days.py](../../tests/test_evaluation6_default_days.py)。
- 注意: KI-06/08/09。ラベル集合指標はeval7/8も利用し、details CSVはeval8の入力。

## eval7 K/h探索・上位条件の追加run

- 文書: [評価7](../evaluations/evaluation_7_parameter_sensitivity_adl_interpretation.md)。
- 入口/実装: [evaluate_7_parameter_sensitivity_adl_interpretation.py](../../scripts/evaluate_7_parameter_sensitivity_adl_interpretation.py)、[run_evaluation7_top_condition_repeats.py](../../scripts/run_evaluation7_top_condition_repeats.py) → [evaluation7_staged.py](../../src/behavior_pattern_mining/evaluation/evaluation7_staged.py)、eval6の集合指標。
- テスト: [test_evaluation7_parameter_sensitivity.py](../../tests/test_evaluation7_parameter_sensitivity.py)、[test_evaluation7_staged_workflow.py](../../tests/test_evaluation7_staged_workflow.py)（Web配線も含む）。
- 注意: KI-06。初回探索→選抜→追加run→最終集計の順序とmanifestを保持。

## eval8 頻度層別ADL整合性

- 文書: [評価8](../evaluations/evaluation_8_frequency_stratified_adl_consistency.md)。
- 入口/実装: [evaluate_8_frequency_stratified_adl_consistency.py](../../scripts/evaluate_8_frequency_stratified_adl_consistency.py) 内に集計本体。`attach_own_id_occurrences` / `occurrence_weight_validation`、eval6の集合指標。
- テスト: [test_evaluation8_frequency_stratified.py](../../tests/test_evaluation8_frequency_stratified.py)（Web配線も含む）。
- 注意: KI-10。own-ID→物理区間一意化→ID間所有権の対策は [KNOWN_ISSUES](KNOWN_ISSUES.md)。系列fallbackを復活させない。

## eval9 Hestia合成ログ

- 文書: [評価9](../evaluations/evaluation_9_hestia.md)。
- 入口/実装: [evaluate_9_hestia.py](../../scripts/evaluate_9_hestia.py) → [evaluation9_hestia.py](../../src/behavior_pattern_mining/evaluation/evaluation9_hestia.py) → 独立repo `Hestia/` のexperiment CLI（別uv環境）。指標を親側に再実装しない。
- テスト: [test_evaluation9_hestia.py](../../tests/test_evaluation9_hestia.py)（CLI・Web配線、外部repoの全実験は保証しない）。
- 注意: Webの `build_evaluation9_steps` / `render_eval9_settings`、`verify_on_batch` で既存出力もCLIへhash検証を委譲。APIはopt-in。

## eval10 SwitchBot実宅ログ

- 文書: [評価10](../evaluations/evaluation_10_switchbot_holdout.md)、入力連携は [SwitchBot Logger](../integrations/switchbot_logger.md)。
- 入口/実装: [evaluate_10_switchbot.py](../../scripts/evaluate_10_switchbot.py) → [evaluation10_switchbot.py](../../src/behavior_pattern_mining/evaluation/evaluation10_switchbot.py)。trainだけで代表状態・候補を作り、固定写像したtestの再出現を採点する。
- テスト: [test_evaluation10_switchbot.py](../../tests/test_evaluation10_switchbot.py)（入力hash、test-onlyセンサー、CSV/JSON契約、CLI・Web配線）。
- 注意: 正解ADLなし。再出現診断をPrecision/Recallと呼ばない。入力・中間・結果はGit管理外で、LLM APIはopt-in。
