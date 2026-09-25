from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.command_builder import build_evaluation7_steps

from src.behavior_pattern_mining.data.sensor_representation import (
    artifact_dataset_name,
    sensor_map_path,
)
from src.behavior_pattern_mining.evaluation.adl import (
    DEFAULT_ARUBA_SENSOR_ID_MAP,
    default_aruba_individual_sensor_id_map,
)


class SensorRepresentationTests(unittest.TestCase):
    def test_individual_map_keeps_all_physical_sensors_distinct(self) -> None:
        individual = default_aruba_individual_sensor_id_map()

        self.assertEqual(set(individual), set(DEFAULT_ARUBA_SENSOR_ID_MAP))
        self.assertEqual(len(set(individual.values())), len(individual))
        self.assertEqual(individual["M001"], "Bedroom_M001")
        self.assertEqual(individual["D001"], "OutsideDoor_D001")

    def test_checked_in_individual_map_matches_runtime_default(self) -> None:
        root = Path(__file__).resolve().parents[1]
        path = sensor_map_path(root, "individual")
        payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload, default_aruba_individual_sensor_id_map())

    def test_room_artifacts_remain_compatible_and_individual_are_namespaced(self) -> None:
        self.assertEqual(artifact_dataset_name("aruba", "room"), "aruba")
        self.assertEqual(artifact_dataset_name("aruba", "individual"), "aruba_individual")

    def test_evaluation7_defaults_to_individual_and_can_select_room(self) -> None:
        base_settings = {
            "runner": "python",
            "dataset": "aruba",
            "days": 14,
            "runs": 1,
            "staged_search": False,
            "n_states_list": [15],
            "hamming_thresholds": [0],
            "labeled_casas": "new_labeled_data/aruba.txt",
            "sensor_map": "configs/aruba_sensor_map_individual.json",
            "adl_intervals": "output/adl_label_intervals.csv",
            "output_dir": "results/test-sensor-representation",
            "min_overlap_ratio_for_true_label": 0.1,
            "wake_window_minutes": 30.0,
            "match_mode": "exact",
            "max_skip_duration_minutes": 1.0,
            "selection_metric": "mean_multilabel_f1",
            "skip_missing_runs": False,
            "skip_missing_conditions": True,
            "show_preparation_steps": True,
        }
        individual_steps = build_evaluation7_steps(base_settings)
        individual_build = next(
            step for step in individual_steps if step.step_id.endswith("_build_network")
        )
        self.assertIn("aruba_individual_15_0_14days.txt", str(individual_build.expected_outputs))
        self.assertIn("individual", individual_build.command)

        room_steps = build_evaluation7_steps(
            {
                **base_settings,
                "sensor_representation": "room",
                "sensor_map": "configs/aruba_sensor_map.json",
            }
        )
        room_build = next(
            step for step in room_steps if step.step_id.endswith("_build_network")
        )
        self.assertIn("aruba_15_0_14days.txt", str(room_build.expected_outputs))
        self.assertNotIn("aruba_individual", str(room_build.expected_outputs))
        self.assertIn("room", room_build.command)


if __name__ == "__main__":
    unittest.main()
