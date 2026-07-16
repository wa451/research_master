from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.command_builder import build_evaluation7_steps
from scripts import run_build_network_from_labeled_casas as build_network


class RunBuildNetworkFromLabeledCasasTests(unittest.TestCase):
    def test_smoothing_window_is_forwarded_to_visualizer(self) -> None:
        fixture_dir = Path(__file__).parent / "fixtures"
        with tempfile.TemporaryDirectory() as tmpdir:
            converted_csv = Path(tmpdir) / "converted.csv"
            argv = [
                "run_build_network_from_labeled_casas.py",
                "--labeled-casas",
                str(fixture_dir / "sample_labeled_casas.txt"),
                "--sensor-map",
                str(fixture_dir / "sample_sensor_map.json"),
                "--keep-converted-csv",
                str(converted_csv),
                "--smoothing-window-sec",
                "7",
            ]
            with (
                patch.object(sys, "argv", argv),
                patch.object(build_network, "StateTransitionVisualizer") as visualizer_class,
            ):
                build_network.main()

            visualizer_class.assert_called_once_with(
                data_duration_days=None,
                smoothing_window_sec=7,
            )
            visualizer_class.return_value.main.assert_called_once_with(
                str(converted_csv),
                mode_split=True,
            )

    def test_dashboard_forwards_smoothing_window_to_each_evaluation7_condition(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = {
                "runner": "python",
                "dataset": "aruba",
                "days": 30,
                "runs": 1,
                "staged_search": False,
                "n_states_list": [10, 15],
                "hamming_thresholds": [0],
                "smoothing_window_sec": 7,
                "labeled_casas": "new_labeled_data/aruba.txt",
                "sensor_map": "configs/aruba_sensor_map.json",
                "adl_intervals": "output/adl_label_intervals.csv",
                "patterns_template": "",
                "state_series_template": "",
                "output_dir": str(Path(tmpdir) / "results"),
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
            build_steps = [
                step
                for step in build_evaluation7_steps(settings)
                if step.step_id.endswith("_build_network")
            ]

        self.assertEqual(len(build_steps), 2)
        for build_step in build_steps:
            smoothing_index = build_step.command.index("--smoothing-window-sec")
            self.assertEqual(build_step.command[smoothing_index + 1], "7")


if __name__ == "__main__":
    unittest.main()
