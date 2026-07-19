from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.command_builder import build_evaluation7_steps
from scripts import run_evaluation7_top_condition_repeats as repeat_runner
from src.behavior_pattern_mining.evaluation.evaluation7_staged import (
    condition_pairs_from_file,
    select_top_condition_rows,
)


def staged_settings(output_dir: Path) -> dict:
    return {
        "runner": "python",
        "dataset": "aruba",
        "days": 30,
        "runs": 1,
        "staged_search": True,
        "top_n": 10,
        "total_runs": 3,
        "n_states_list": [10, 15, 20, 25, 30],
        "hamming_thresholds": [0, 1],
        "labeled_casas": "new_labeled_data/aruba.txt",
        "sensor_map": "configs/aruba_sensor_map.json",
        "adl_intervals": "output/adl_label_intervals.csv",
        "patterns_template": "",
        "state_series_template": "",
        "output_dir": str(output_dir),
        "min_overlap_ratio_for_true_label": 0.1,
        "no_overlap_label": "Ambiguous",
        "missing_pred_label": "Ambiguous",
        "unknown_pred_label": "Other",
        "wake_window_minutes": 30.0,
        "match_mode": "exact",
        "max_skip_duration_minutes": 1.0,
        "selection_metric": "mean_multilabel_f1",
        "skip_missing_runs": False,
        "skip_missing_conditions": True,
        "show_preparation_steps": True,
    }


class Evaluation7StagedWorkflowTests(unittest.TestCase):
    def test_repeat_runner_defaults_to_five_total_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            argv = [
                "run_evaluation7_top_condition_repeats.py",
                "--screening-summary",
                str(root / "screening.csv"),
                "--manifest",
                str(root / "manifest.csv"),
            ]
            with patch.object(sys, "argv", argv):
                args = repeat_runner.parse_args()

        self.assertEqual(args.total_runs, 5)

    def test_top_condition_selection_uses_screening_rank(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = Path(tmpdir) / "summary.csv"
            with summary.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "rank",
                        "condition_id",
                        "n_states",
                        "hamming_threshold",
                        "days",
                        "selection_metric_value",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "rank": 2,
                        "condition_id": "20_1_30days",
                        "n_states": 20,
                        "hamming_threshold": 1,
                        "days": 30,
                        "selection_metric_value": 0.7,
                    }
                )
                writer.writerow(
                    {
                        "rank": 1,
                        "condition_id": "15_0_30days",
                        "n_states": 15,
                        "hamming_threshold": 0,
                        "days": 30,
                        "selection_metric_value": 0.75,
                    }
                )

            selected = select_top_condition_rows(summary, 2)
            self.assertEqual(
                [(int(row["n_states"]), int(row["hamming_threshold"])) for row in selected],
                [(15, 0), (20, 1)],
            )
            self.assertEqual(
                condition_pairs_from_file(summary, expected_days=30),
                [(20, 1), (15, 0)],
            )

    def test_repeat_runner_generates_only_missing_run_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            summary = tmp / "screening.csv"
            with summary.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "rank",
                        "condition_id",
                        "n_states",
                        "hamming_threshold",
                        "days",
                        "num_runs",
                        "mean_multilabel_f1",
                        "selection_metric",
                        "selection_metric_value",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "rank": 1,
                        "condition_id": "15_0_30days",
                        "n_states": 15,
                        "hamming_threshold": 0,
                        "days": 30,
                        "num_runs": 1,
                        "mean_multilabel_f1": 0.75,
                        "selection_metric": "mean_multilabel_f1",
                        "selection_metric_value": 0.75,
                    }
                )
            (tmp / "run2.json").write_text("[]\n", encoding="utf-8")
            manifest = tmp / "manifest.csv"

            def fake_extract(**kwargs) -> None:
                self.assertEqual(kwargs["run_ids"], [3])
                (tmp / "run3.json").write_text("[]\n", encoding="utf-8")

            argv = [
                "run_evaluation7_top_condition_repeats.py",
                "--screening-summary",
                str(summary),
                "--manifest",
                str(manifest),
                "--top-n",
                "1",
                "--total-runs",
                "3",
            ]
            with (
                patch.object(sys, "argv", argv),
                patch.object(
                    repeat_runner,
                    "expected_pattern_path",
                    side_effect=lambda _dataset, _k, _h, _days, run_id: tmp / f"run{run_id}.json",
                ),
                patch.object(repeat_runner.pattern_extractor, "main", side_effect=fake_extract) as extract,
            ):
                repeat_runner.main()
                extract.assert_called_once()
                extract.reset_mock()
                repeat_runner.main()
                extract.assert_not_called()

            with manifest.open(encoding="utf-8", newline="") as handle:
                manifest_rows = list(csv.DictReader(handle))
            self.assertEqual(manifest_rows[0]["mean_multilabel_f1"], "0.75")

    def test_dashboard_builds_screening_repeats_and_final_average(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            steps = build_evaluation7_steps(staged_settings(Path(tmpdir) / "results"))
            step_ids = [step.step_id for step in steps]
            self.assertIn("eval7_screening", step_ids)
            self.assertIn("eval7_top_repeats", step_ids)
            self.assertEqual(step_ids[-1], "eval7_evaluate")

            repeat_step = next(step for step in steps if step.step_id == "eval7_top_repeats")
            self.assertIn("--top-n", repeat_step.command)
            self.assertIn("10", repeat_step.command)
            self.assertIn("--total-runs", repeat_step.command)
            self.assertIn("3", repeat_step.command)

            final_step = steps[-1]
            run_ids_index = final_step.command.index("--run-ids")
            self.assertEqual(final_step.command[run_ids_index + 1 : run_ids_index + 4], ["1", "2", "3"])
            self.assertIn("--conditions-file", final_step.command)
            conditions_index = final_step.command.index("--conditions-file")
            copy_index = final_step.command.index("--condition-summary-copy")
            self.assertEqual(
                final_step.command[conditions_index + 1],
                final_step.command[copy_index + 1],
            )
            self.assertNotIn("--skip-missing-runs", final_step.command)
            self.assertNotIn("--skip-missing-conditions", final_step.command)

    def test_dashboard_skips_screening_steps_when_summary_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "results"
            output_dir.mkdir(parents=True)
            (output_dir / "evaluation7_condition_summary.csv").write_text(
                "rank,n_states,hamming_threshold\n1,15,0\n",
                encoding="utf-8",
            )
            steps = build_evaluation7_steps(staged_settings(output_dir))
            step_ids = [step.step_id for step in steps]
            self.assertNotIn("eval7_screening", step_ids)
            self.assertFalse(any(step_id.endswith("_build_network") for step_id in step_ids))
            self.assertEqual(step_ids, ["eval7_top_repeats", "eval7_evaluate"])

    def test_dashboard_tracks_each_top_condition_repeat_as_expected_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "results"
            output_dir.mkdir(parents=True)
            summary = output_dir / "evaluation7_condition_summary.csv"
            with summary.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["rank", "n_states", "hamming_threshold", "days"],
                )
                writer.writeheader()
                for rank, n_states in enumerate(range(10, 20), start=1):
                    writer.writerow(
                        {
                            "rank": rank,
                            "n_states": n_states,
                            "hamming_threshold": 0,
                            "days": 30,
                        }
                    )

            settings = staged_settings(output_dir)
            settings["dataset"] = "testdataset"
            repeat_step = next(
                step
                for step in build_evaluation7_steps(settings)
                if step.step_id == "eval7_top_repeats"
            )
            self.assertEqual(len(repeat_step.expected_outputs), 21)
            expected_names = {path.name for path in repeat_step.expected_outputs}
            self.assertIn("llm_sequences_modes_10_0_30days_2.json", expected_names)
            self.assertIn("llm_sequences_modes_19_0_30days_3.json", expected_names)


if __name__ == "__main__":
    unittest.main()
