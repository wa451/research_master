from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from experiment_config import CONFIG, DATASET_NAME, LLM_MODEL_NAME
from src.behavior_pattern_mining.states.state_mapping import load_event_log, map_vector_to_state
from src.behavior_pattern_mining.evaluation.groundedness_check import check_sequence
from src.behavior_pattern_mining.llm import pattern_extractor as llm_extractor_modes
from src.behavior_pattern_mining.baselines.transition_probability import (
    Edge,
    build_adjacency,
    discover_sequences,
)
from src.behavior_pattern_mining.visualization.state_transition_visualizer import StateTransitionVisualizer
from src.behavior_pattern_mining.evaluation.groundedness import load_markov_edges
from src.behavior_pattern_mining.evaluation.metrics import compute_metrics


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class CoreLogicTests(unittest.TestCase):
    def test_rendered_state_labels_are_english_without_changing_state_ids(self) -> None:
        visualizer = StateTransitionVisualizer()
        representative_state = (1, 0)
        visualizer.state_labels = {
            representative_state: "状態1",
            "Other": "その他",
        }

        self.assertEqual(visualizer._state_to_label(representative_state), "状態1")
        self.assertEqual(visualizer._state_to_display_label(representative_state), "State 1")
        self.assertEqual(visualizer._state_to_display_label("Other"), "Other")

    def test_main_exports_all_json_without_rendering_all_figures(self) -> None:
        visualizer = StateTransitionVisualizer()
        with (
            patch.object(visualizer, "load_data", return_value=pd.DataFrame()),
            patch.object(visualizer, "create_state_vectors"),
            patch.object(visualizer, "extract_representative_states"),
            patch.object(visualizer, "map_to_representative_states"),
            patch.object(visualizer, "compute_transition_matrix"),
            patch.object(
                visualizer,
                "_generate_save_folder",
                return_value=("picture/test", None, "state/test.txt"),
            ),
            patch.object(visualizer, "export_to_json") as export_json,
            patch.object(visualizer, "save_state_table"),
            patch.object(visualizer, "visualize_transition_graph") as transition_graph,
            patch.object(visualizer, "visualize_mode_timeline") as timeline,
        ):
            visualizer.main("data/test.csv", mode_split=False)

        export_json.assert_called_once_with("picture/test/state_transition_all.json")
        transition_graph.assert_not_called()
        timeline.assert_not_called()

    def test_config_loads_from_default_yaml(self) -> None:
        self.assertEqual(DATASET_NAME, "aruba")
        self.assertEqual(LLM_MODEL_NAME, "gemini-2.5-pro")
        self.assertIn("dataset", CONFIG)

    def test_sensor_log_loads_event_format(self) -> None:
        df = load_event_log(FIXTURES_DIR / "sample_sensor_log.csv")

        self.assertEqual(list(df.columns), ["timestamp", "sensor", "value"])
        self.assertEqual(len(df), 4)
        self.assertEqual(df.iloc[0]["sensor"], "Kitchen")

    def test_preprocess_outputs_state_vector_dataframe(self) -> None:
        visualizer = StateTransitionVisualizer(
            n_representative_states=2,
            hamming_threshold=0,
            data_duration_days=1,
            smoothing_window_sec=0,
        )
        events = visualizer.load_data(str(FIXTURES_DIR / "sample_sensor_log.csv"))
        vectors = visualizer.create_state_vectors(events)

        self.assertIsInstance(vectors, pd.DataFrame)
        self.assertIn("Kitchen", vectors.columns)
        self.assertIn("Bedroom", vectors.columns)
        self.assertGreaterEqual(len(vectors), 2)

    def test_representative_state_mapping_uses_hamming_threshold(self) -> None:
        state_mapping = {
            (1, 0): "状態1",
            (0, 1): "状態2",
        }

        self.assertEqual(map_vector_to_state((1, 1), state_mapping, hamming_threshold=1), "状態1")
        self.assertEqual(map_vector_to_state((1, 1), state_mapping, hamming_threshold=0), "その他")

    def test_transition_probabilities_sum_to_one_and_self_loops_are_removed(self) -> None:
        visualizer = StateTransitionVisualizer()
        visualizer.state_sequence = ["A", "A", "B", "B", "A"]

        matrix = visualizer.compute_transition_matrix()

        for transitions in matrix.values():
            self.assertAlmostEqual(sum(transitions.values()), 1.0)
        self.assertNotIn("A", matrix.get("A", {}))
        self.assertNotIn("B", matrix.get("B", {}))

    def test_pattern_length_limit_is_respected(self) -> None:
        edges = [
            Edge("A", "B", 0.9),
            Edge("B", "C", 0.8),
            Edge("C", "D", 0.7),
            Edge("D", "E", 0.6),
        ]
        sequences = discover_sequences(
            build_adjacency(edges),
            min_length=2,
            max_length=4,
            allow_revisit=False,
        )

        self.assertTrue(sequences)
        self.assertTrue(all(2 <= len(seq.states) <= 4 for seq in sequences))

    def test_groundedness_check(self) -> None:
        edge_probs = load_markov_edges(FIXTURES_DIR / "sample_transition_graph.json")

        ok, details = check_sequence(["状態1", "状態2", "状態3"], edge_probs)

        self.assertTrue(ok)
        self.assertTrue(details["length_ok"])
        self.assertEqual(details["missing_edges"], [])

    def test_precision_recall_f1(self) -> None:
        baseline = [["A", "B"], ["B", "C"]]
        llm = [["A", "B"], ["C", "D"]]

        result = compute_metrics(
            baseline,
            llm,
            allow_base_contains_llm=False,
            allow_llm_contains_base=False,
        )

        self.assertEqual(result.tp, 1)
        self.assertEqual(result.fp, 1)
        self.assertEqual(result.fn, 1)
        self.assertAlmostEqual(result.precision, 0.5)
        self.assertAlmostEqual(result.recall, 0.5)
        self.assertAlmostEqual(result.f1, 0.5)

    def test_llm_output_path_can_be_forced_by_batch_runner(self) -> None:
        original_output_path = llm_extractor_modes.OUTPUT_FILE_PATH
        original_runs = llm_extractor_modes.RUNS
        try:
            forced = Path("output/sample/llm_sequences_modes_15_1_154days_3.json")
            llm_extractor_modes.OUTPUT_FILE_PATH = forced
            llm_extractor_modes.RUNS = 1

            actual = llm_extractor_modes.output_path_for_run(Path("output/sample"), run_idx=1)

            self.assertEqual(actual, forced)
        finally:
            llm_extractor_modes.OUTPUT_FILE_PATH = original_output_path
            llm_extractor_modes.RUNS = original_runs


if __name__ == "__main__":
    unittest.main()
