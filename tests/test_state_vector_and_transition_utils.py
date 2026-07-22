from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.behavior_pattern_mining.data.state_vectors import (
    apply_delayed_off_smoothing,
    build_sample_and_hold_state_vectors,
    compress_consecutive_state_vectors,
)
from src.behavior_pattern_mining.network.transitions import (
    compress_consecutive_states,
    compute_state_durations,
    compute_transition_statistics,
)
from src.behavior_pattern_mining.visualization.state_transition_visualizer import (
    StateTransitionVisualizer,
)


class StateVectorUtilitiesTests(unittest.TestCase):
    def test_sample_and_hold_matches_event_order_and_second_boundaries(self) -> None:
        events = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(
                    [
                        "2019-12-31 23:59:59.500",
                        "2020-01-01 00:00:00.100",
                        "2020-01-01 00:00:00.900",
                        "2020-01-01 00:00:02.000",
                        "2020-01-01 00:00:02.000",
                    ]
                ),
                "sensor_id": ["Kitchen", "Bedroom", "Bedroom", "Kitchen", "Kitchen"],
                "binary_value": [1, 1, 0, 0, 1],
            }
        )
        time_range = pd.date_range("2020-01-01", periods=4, freq="1s")

        state_vectors = build_sample_and_hold_state_vectors(
            events,
            time_range=time_range,
            sensor_columns=["Kitchen", "Bedroom"],
        )

        expected = pd.DataFrame(
            {
                "Kitchen": [1, 1, 1, 1],
                "Bedroom": [0, 0, 0, 0],
            },
            index=time_range,
        )
        pd.testing.assert_frame_equal(state_vectors, expected)

    def test_sample_and_hold_matches_original_event_loop(self) -> None:
        events = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(
                    [
                        "2019-12-31 23:59:58.750",
                        "2020-01-01 00:00:00.000",
                        "2020-01-01 00:00:00.250",
                        "2020-01-01 00:00:00.750",
                        "2020-01-01 00:00:02.100",
                        "2020-01-01 00:00:04.000",
                    ]
                ),
                "sensor_id": ["Kitchen", "Bedroom", "Kitchen", "Kitchen", "Bedroom", "Kitchen"],
                "binary_value": [1, 1, 0, 1, 0, 0],
            }
        )
        time_range = pd.date_range("2020-01-01", periods=4, freq="1s")
        sensor_columns = ["Kitchen", "Bedroom"]

        # 変更前の実装と同じく、各サンプルまでのイベントを入力順で逐次反映する。
        sensor_states = {sensor: 0 for sensor in sensor_columns}
        event_records = events.to_dict("records")
        event_index = 0
        expected_rows = []
        for current_time in time_range:
            while (
                event_index < len(event_records)
                and event_records[event_index]["timestamp"] <= current_time
            ):
                event = event_records[event_index]
                sensor_states[event["sensor_id"]] = event["binary_value"]
                event_index += 1
            expected_rows.append(sensor_states.copy())
        expected = pd.DataFrame(
            expected_rows,
            index=time_range,
            columns=sensor_columns,
        )

        actual = build_sample_and_hold_state_vectors(
            events,
            time_range=time_range,
            sensor_columns=sensor_columns,
        )

        pd.testing.assert_frame_equal(actual, expected)

    def test_sample_and_hold_uses_actual_non_aligned_sampling_grid(self) -> None:
        events = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(
                    [
                        "2020-01-01 00:00:02.500",
                        "2020-01-01 00:00:09.500",
                        "2020-01-01 00:00:25.000",
                    ]
                ),
                "sensor_id": ["Kitchen", "Kitchen", "Kitchen"],
                "binary_value": [1, 0, 1],
            }
        )
        # 7秒刻みかつ絶対時刻の7秒境界と一致しない開始位置を使う。
        time_range = pd.date_range("2020-01-01 00:00:03", periods=3, freq="7s")

        actual = build_sample_and_hold_state_vectors(
            events,
            time_range=time_range,
            sensor_columns=["Kitchen"],
        )

        expected = pd.DataFrame(
            {"Kitchen": [1, 0, 0]},
            index=time_range,
        )
        pd.testing.assert_frame_equal(actual, expected)

    def test_sample_and_hold_empty_events_start_with_all_sensors_off(self) -> None:
        time_range = pd.date_range("2020-01-01", periods=3, freq="1s")
        events = pd.DataFrame(columns=["timestamp", "sensor_id", "binary_value"])

        state_vectors = build_sample_and_hold_state_vectors(
            events,
            time_range=time_range,
            sensor_columns=["Kitchen", "Bedroom"],
        )

        expected = pd.DataFrame(
            0,
            index=time_range,
            columns=["Kitchen", "Bedroom"],
            dtype=int,
        )
        pd.testing.assert_frame_equal(state_vectors, expected)

    def test_delayed_off_smoothing_matches_trailing_rolling_max(self) -> None:
        index = pd.date_range("2020-01-01", periods=7, freq="1s")
        state_vectors = pd.DataFrame(
            {
                "Kitchen": [0, 1, 0, 0, 0, 1, 0],
                "Bedroom": [0, 0, 0, 1, 0, 0, 0],
            },
            index=index,
        )

        smoothed = apply_delayed_off_smoothing(state_vectors, window_size=3)

        expected = pd.DataFrame(
            {
                "Kitchen": [0, 1, 1, 1, 0, 1, 1],
                "Bedroom": [0, 0, 0, 1, 1, 1, 0],
            },
            index=index,
        )
        pd.testing.assert_frame_equal(smoothed, expected)
        pd.testing.assert_frame_equal(
            state_vectors,
            pd.DataFrame(
                {
                    "Kitchen": [0, 1, 0, 0, 0, 1, 0],
                    "Bedroom": [0, 0, 0, 1, 0, 0, 0],
                },
                index=index,
            ),
        )

    def test_non_positive_smoothing_window_keeps_existing_dataframe(self) -> None:
        state_vectors = pd.DataFrame({"Kitchen": [0, 1, 0]})

        self.assertIs(apply_delayed_off_smoothing(state_vectors, 0), state_vectors)
        self.assertIs(apply_delayed_off_smoothing(state_vectors, -1), state_vectors)

    def test_vector_compression_keeps_first_row_of_each_consecutive_run(self) -> None:
        index = pd.date_range("2020-01-01", periods=6, freq="1s")
        state_vectors = pd.DataFrame(
            {
                "Kitchen": [0, 0, 1, 1, 0, 0],
                "Bedroom": [0, 0, 0, 1, 0, 0],
            },
            index=index,
        )

        compressed = compress_consecutive_state_vectors(state_vectors)

        expected = state_vectors.iloc[[0, 2, 3, 4]]
        pd.testing.assert_frame_equal(compressed, expected)


class TransitionUtilitiesTests(unittest.TestCase):
    def test_state_compression_removes_only_consecutive_duplicates(self) -> None:
        sequence = ["A", "A", "B", "B", "A", "C", "C"]

        self.assertEqual(
            compress_consecutive_states(sequence),
            ["A", "B", "A", "C"],
        )

    def test_transition_statistics_preserve_first_seen_dictionary_order(self) -> None:
        compressed_sequence = ["A", "B", "A", "C"]

        statistics = compute_transition_statistics(compressed_sequence)

        self.assertEqual(list(statistics.occurrences), ["A", "B", "C"])
        self.assertEqual(statistics.occurrences, {"A": 2, "B": 1, "C": 1})
        self.assertEqual(list(statistics.probabilities), ["A", "B"])
        self.assertEqual(list(statistics.probabilities["A"]), ["B", "C"])
        self.assertEqual(
            statistics.probabilities,
            {
                "A": {"B": 0.5, "C": 0.5},
                "B": {"A": 1.0},
            },
        )

    def test_single_state_has_an_occurrence_but_no_transition(self) -> None:
        statistics = compute_transition_statistics(["A"])

        self.assertEqual(statistics.occurrences, {"A": 1})
        self.assertEqual(statistics.probabilities, {})

    def test_state_durations_use_change_times_and_one_second_for_last_state(self) -> None:
        timestamps = pd.to_datetime(
            [
                "2020-01-01 00:00:00",
                "2020-01-01 00:00:02",
                "2020-01-01 00:00:07",
            ]
        )

        durations = compute_state_durations(
            state_sequence=["A", "B", "A"],
            timestamps=timestamps,
            known_states=["A", "B", "Other"],
        )

        self.assertEqual(durations, {"A": 3.0, "B": 5.0, "Other": 0.0})

    def test_transition_json_payload_keeps_schema_order_and_rounding(self) -> None:
        visualizer = StateTransitionVisualizer()
        representative_state = (1, 0)
        visualizer.sensor_list = ["Kitchen", "Bedroom"]
        visualizer.state_labels = {
            representative_state: "状態1",
            "Other": "その他",
        }

        payload = visualizer._build_transition_export_payload(
            states=[representative_state, "Other"],
            state_durations={representative_state: 120.0, "Other": 60.0},
            num_days=2,
            transition_matrix={
                representative_state: {"Other": 0.1236},
            },
        )

        self.assertEqual(list(payload), ["nodes", "edges"])
        self.assertEqual(
            payload,
            {
                "nodes": [
                    {
                        "state_id": "状態1",
                        "active_sensors": ["Kitchen"],
                        "avg_duration_minutes_per_day": 1.0,
                    },
                    {
                        "state_id": "その他",
                        "active_sensors": [],
                        "avg_duration_minutes_per_day": 0.5,
                    },
                ],
                "edges": [
                    {
                        "from": "状態1",
                        "to": "その他",
                        "probability": 0.124,
                    }
                ],
            },
        )

    def test_transition_json_writer_keeps_utf8_and_indentation(self) -> None:
        payload = {
            "nodes": [{"state_id": "状態1", "active_sensors": ["台所"]}],
            "edges": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "network.json"
            StateTransitionVisualizer._write_json(str(output_path), payload)
            serialized = output_path.read_text(encoding="utf-8")

        self.assertEqual(json.loads(serialized), payload)
        self.assertIn('"state_id": "状態1"', serialized)
        self.assertNotIn("\\u72b6", serialized)
        self.assertTrue(serialized.startswith("{\n  \"nodes\""))
        self.assertFalse(serialized.endswith("\n"))


if __name__ == "__main__":
    unittest.main()
