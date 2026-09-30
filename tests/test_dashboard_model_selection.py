"""Regression tests for dashboard-only LLM model selection."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from app.command_builder import (
    PROJECT_ROOT,
    build_evaluation6_steps,
    build_evaluation6_strict_ablation_steps,
    build_evaluation7_steps,
    build_evaluation9_steps,
    default_direct_path,
    default_proposed_path,
)
from app.streamlit_app import (
    DEFAULT_HAMMING_THRESHOLD,
    DEFAULT_N_STATES,
    batch_target_steps,
    eval5_condition_widget_key,
)
from app.model_selection import (
    DASHBOARD_MODELS,
    DEFAULT_DASHBOARD_MODEL_ID,
    dashboard_model,
)
from app.utils import run_command
from src.behavior_pattern_mining.evaluation.evaluation6_manifest import (
    formal_artifact_paths,
    load_evaluation7_best_condition_manifest,
)


class DashboardModelSelectionTests(unittest.TestCase):
    def test_dashboard_uses_evaluation7_selected_defaults(self) -> None:
        self.assertEqual(DEFAULT_N_STATES, 10)
        self.assertEqual(DEFAULT_HAMMING_THRESHOLD, 2)

    def test_evaluation5_condition_path_widget_keys_change_with_condition(self) -> None:
        base = dict(
            field="state_table",
            model_id="us.openai.gpt-5.6-sol",
            dataset="aruba_individual",
            days=154,
        )
        default_key = eval5_condition_widget_key(
            **base,
            n_states=15,
            hamming_threshold=0,
        )
        selected_key = eval5_condition_widget_key(
            **base,
            n_states=10,
            hamming_threshold=2,
        )

        self.assertNotEqual(default_key, selected_key)
        self.assertIn("aruba_individual_10_2_154days", selected_key)

    def test_fable_is_default_and_all_model_roots_are_distinct(self) -> None:
        self.assertEqual(
            DEFAULT_DASHBOARD_MODEL_ID,
            "us.anthropic.claude-fable-5",
        )
        roots = {model.results_root(PROJECT_ROOT) for model in DASHBOARD_MODELS}
        output_roots = {model.output_root(PROJECT_ROOT) for model in DASHBOARD_MODELS}
        self.assertEqual(len(roots), len(DASHBOARD_MODELS))
        self.assertEqual(len(output_roots), len(DASHBOARD_MODELS))
        self.assertEqual(
            dashboard_model(DEFAULT_DASHBOARD_MODEL_ID).results_root(PROJECT_ROOT),
            PROJECT_ROOT / "results/claude-fable-5",
        )
        self.assertEqual(
            dashboard_model(DEFAULT_DASHBOARD_MODEL_ID).output_root(PROJECT_ROOT),
            PROJECT_ROOT / "output/claude-fable-5",
        )

    def test_selected_root_is_used_for_default_llm_artifacts(self) -> None:
        terra_root = dashboard_model("us.openai.gpt-5.6-terra").results_root(PROJECT_ROOT)
        self.assertEqual(
            default_proposed_path("aruba", 15, 0, 14, results_root=terra_root),
            terra_root / "aruba_15_0_14days/llm_sequences_modes_15_0_14days_1.json",
        )
        self.assertEqual(
            default_direct_path("aruba", 15, 0, 14, results_root=terra_root),
            terra_root / "llm_direct_15_0_14days_time_split/1.json",
        )
        self.assertEqual(
            default_direct_path(
                "aruba", 15, 0, 14, results_root=terra_root,
                llm_only_time_mode="legacy",
            ),
            terra_root / "llm_direct_15_0_14days/1.json",
        )

    def test_evaluation6_builder_passes_split_mode_to_generation_and_comparison(self) -> None:
        root = dashboard_model("us.openai.gpt-5.6-terra").results_root(PROJECT_ROOT)
        output_root = dashboard_model("us.openai.gpt-5.6-terra").output_root(PROJECT_ROOT)
        settings = {
            "runner": "python", "dataset": "aruba", "days": 14,
            "n_states": 15, "hamming_threshold": 0, "runs": 1,
            "labeled_casas": "new_labeled_data/aruba.txt",
            "sensor_map": "configs/aruba_sensor_map_individual.json",
            "state_table": "state/aruba_15_0_14days.txt",
            "patterns_proposed": root / "aruba_15_0_14days/llm_sequences_modes_15_0_14days_1.json",
            "patterns_direct": root / "llm_direct_15_0_14days_time_split/1.json",
            "state_series": output_root / "6_adl_evaluation_15_0_14days/state_series.csv",
            "intermediate_output_dir": output_root / "6_adl_evaluation_15_0_14days",
            "output_dir": root / "6_adl_match_holdout_test_direct_time_split",
            "model_results_root": root, "model_output_root": output_root, "sensor_representation": "individual",
            "min_overlap_ratio_for_true_label": 0.1, "wake_window_minutes": 30.0,
            "match_mode": "exact", "max_skip_duration_minutes": 1.0,
            "skip_missing_runs": False, "split_mode": "holdout",
            "generation_days": 14, "validation_start_day": 15,
            "validation_end_day": 154, "test_start_day": 155, "test_end_day": 220,
            "llm_only_time_mode": "split",
            "smoothing_window_sec": 7,
        }
        steps = build_evaluation6_steps(settings)
        commands = [" ".join(step.command) for step in steps]

        self.assertEqual(sum("--llm-only-time-mode split" in command for command in commands), 2)
        state_series_step = next(step for step in steps if step.step_id == "eval6_state_series")
        self.assertIn("--state-series-preprocessing", state_series_step.command)
        preprocessing_index = state_series_step.command.index("--state-series-preprocessing")
        self.assertEqual(state_series_step.command[preprocessing_index + 1], "network-equivalent")
        smoothing_index = state_series_step.command.index("--smoothing-window-sec")
        self.assertEqual(state_series_step.command[smoothing_index + 1], "7")
        self.assertNotIn("--state-series-days", state_series_step.command)
        build_step = next(step for step in steps if step.step_id == "eval6_build_network")
        direct_step = next(step for step in steps if step.step_id == "eval6_direct_baseline")
        for step in (build_step, direct_step):
            smoothing_index = step.command.index("--smoothing-window-sec")
            self.assertEqual(step.command[smoothing_index + 1], "7")

    def test_evaluation6_builder_uses_manifest_condition_artifact_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest_path = root / "evaluation7_best_condition_manifest.json"
            manifest_path.write_text(
                '{"K":20,"h":1,"sensor_representation":"individual",'
                '"generation_days":14,"split_mode":"holdout",'
                '"validation_start_day":15,"validation_end_day":154,'
                '"test_start_day":155,"test_end_day":220}',
                encoding="utf-8",
            )
            model_root = dashboard_model("us.openai.gpt-5.6-terra").results_root(PROJECT_ROOT)
            model_output = dashboard_model("us.openai.gpt-5.6-terra").output_root(PROJECT_ROOT)
            condition = load_evaluation7_best_condition_manifest(manifest_path)
            paths = formal_artifact_paths(
                project_root=PROJECT_ROOT,
                results_root=model_root,
                output_root=model_output,
                dataset="aruba",
                condition=condition,
                llm_only_time_mode="split",
            )
            settings = {
                "runner": "python", "dataset": "aruba", "days": 14,
                "n_states": 20, "hamming_threshold": 1, "runs": 1,
                "labeled_casas": "new_labeled_data/aruba.txt",
                "sensor_map": "configs/aruba_sensor_map_individual.json",
                "state_table": "state/aruba_individual_20_1_14days.txt",
                "patterns_proposed": paths["patterns_proposed"],
                "patterns_direct": paths["patterns_direct"],
                "state_series": paths["state_series"],
                "intermediate_output_dir": paths["state_series"].parent,
                "output_dir": paths["output_dir"],
                "model_results_root": model_root, "model_output_root": model_output, "sensor_representation": "individual",
                "min_overlap_ratio_for_true_label": 0.1, "wake_window_minutes": 30.0,
                "match_mode": "exact", "max_skip_duration_minutes": 1.0,
                "skip_missing_runs": False, "split_mode": "holdout",
                "generation_days": 14, "validation_start_day": 15,
                "validation_end_day": 154, "test_start_day": 155, "test_end_day": 220,
                "llm_only_time_mode": "split", "best_condition_manifest": manifest_path,
            }
            steps = build_evaluation6_steps(settings)

        compare = next(step for step in steps if step.step_id == "eval6_compare")
        self.assertIn(str(manifest_path), compare.command)
        self.assertIn(str(paths["patterns_proposed"]), compare.command)
        self.assertIn(str(paths["patterns_direct"]), compare.command)
        self.assertIn(str(paths["state_series"]), compare.command)

    def test_strict_evaluation6_can_use_sol_condition_manifest_for_fable_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest_path = root / "results/gpt-5.6-sol/7_param_search_14d_5runs_individual_holdout/evaluation7_best_condition_manifest.json"
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(
                '{"K":10,"h":2,"sensor_representation":"individual",'
                '"generation_days":14,"split_mode":"holdout",'
                '"validation_start_day":15,"validation_end_day":154,'
                '"test_start_day":155,"test_end_day":220}',
                encoding="utf-8",
            )
            fable = dashboard_model("us.anthropic.claude-fable-5")
            steps = build_evaluation6_strict_ablation_steps(
                {
                    "runner": "python",
                    "dataset": "aruba",
                    "runs": 5,
                    "labeled_casas": "new_labeled_data/aruba.txt",
                    "sensor_map": "configs/aruba_sensor_map_individual.json",
                    "smoothing_window_sec": 5,
                    "model_results_root": fable.results_root(PROJECT_ROOT),
                    "model_output_root": fable.output_root(PROJECT_ROOT),
                    "best_condition_manifest": manifest_path,
                }
            )

        self.assertEqual(
            [step.step_id for step in steps],
            [
                "eval6_strict_build_network",
                "eval6_strict_state_series",
                "eval6_strict_generate",
                "eval6_strict_evaluate",
            ],
        )
        state_series_step = steps[1]
        self.assertIn("--state-series-only", state_series_step.command)
        self.assertIn(str(fable.output_root(PROJECT_ROOT)), " ".join(state_series_step.command))
        for step in steps[2:]:
            self.assertIn(str(manifest_path), step.command)
        generated_paths = steps[2].expected_outputs
        self.assertEqual(
            [path.name for path in generated_paths[:5]],
            [f"run_{run_id}.json" for run_id in range(1, 6)],
        )
        self.assertEqual(
            [path.name for path in generated_paths[5:10]],
            [f"run_{run_id}.json" for run_id in range(1, 6)],
        )
        with patch("app.streamlit_app.missing_expected_outputs", return_value=[]):
            self.assertEqual(batch_target_steps(steps, "不足ファイル生成のみ"), [])
            self.assertEqual(
                [step.step_id for step in batch_target_steps(steps, "不足ファイル生成 + 評価本体")],
                ["eval6_strict_evaluate"],
            )

    def test_builders_use_the_selected_model_root_for_expected_outputs(self) -> None:
        terra_root = dashboard_model("us.openai.gpt-5.6-terra").results_root(PROJECT_ROOT)
        terra_output = dashboard_model("us.openai.gpt-5.6-terra").output_root(PROJECT_ROOT)
        evaluation7 = build_evaluation7_steps(
            {
                "runner": "python",
                "dataset": "aruba",
                "days": 14,
                "runs": 1,
                "staged_search": False,
                "n_states_list": [15],
                "hamming_thresholds": [0],
                "labeled_casas": "new_labeled_data/aruba.txt",
                "sensor_map": "configs/aruba_sensor_map_individual.json",
                "adl_intervals": terra_output / "adl_label_intervals.csv",
                "output_dir": terra_root / "7_param_search",
                "model_results_root": terra_root,
                "model_output_root": terra_output,
                "min_overlap_ratio_for_true_label": 0.1,
                "wake_window_minutes": 30.0,
                "match_mode": "exact",
                "max_skip_duration_minutes": 1.0,
                "selection_metric": "mean_multilabel_f1",
                "skip_missing_runs": False,
                "skip_missing_conditions": True,
                "show_preparation_steps": True,
            }
        )
        llm_step = next(step for step in evaluation7 if step.step_id.endswith("_llm"))
        self.assertEqual(
            llm_step.expected_outputs,
            [terra_root / "aruba_individual_15_0_14days/llm_sequences_modes_15_0_14days_1.json"],
        )

        evaluation9 = build_evaluation9_steps(
            {"runner": "python", "model_results_root": terra_root}
        )
        self.assertEqual(
            evaluation9[-1].expected_outputs[0],
            terra_root / "9_hestia/pilot/evaluation9_summary.csv",
        )

    def test_subprocess_receives_only_selected_model_override(self) -> None:
        sol = dashboard_model(DEFAULT_DASHBOARD_MODEL_ID)
        before = os.environ.get("BEDROCK_MODEL_ID")
        with tempfile.TemporaryDirectory() as directory:
            result = run_command(
                [
                    sys.executable,
                    "-c",
                    "import os; print(os.environ['LLM_PROVIDER']); print(os.environ['BEDROCK_MODEL_ID'])",
                ],
                log_path=Path(directory) / "command.log",
                environment_overrides=sol.environment_overrides(),
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.output.splitlines(),
            ["bedrock", "us.anthropic.claude-fable-5"],
        )
        self.assertEqual(os.environ.get("BEDROCK_MODEL_ID"), before)

    def test_missing_command_is_reported_instead_of_raising(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "command.log"
            result = run_command(
                ["definitely-not-a-dashboard-command"],
                log_path=log_path,
            )

            self.assertEqual(result.returncode, 127)
            self.assertIn("実行コマンドが見つかりません", result.output)
            self.assertIn("definitely-not-a-dashboard-command", result.output)
            self.assertEqual(log_path.read_text(encoding="utf-8").splitlines()[-1], "詳細: [Errno 2] No such file or directory: 'definitely-not-a-dashboard-command'")


if __name__ == "__main__":
    unittest.main()
