from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.behavior_pattern_mining.evaluation.adl import (
    ADLInterval,
    PatternRecord,
    PredictionInterval,
    StateInterval,
    build_state_series_from_event_log,
    build_state_series_from_labeled_casas,
    compute_interval_hit_evaluation,
    filter_predictions_by_duration,
    find_pattern_occurrences,
    greedy_match_by_category,
    interval_overlap_seconds,
    merge_prediction_intervals,
    metrics_rows_from_counts,
    parse_labeled_casas_intervals,
    temporal_iou,
)


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


class ADLEvaluationTests(unittest.TestCase):
    def test_labeled_casas_intervals_and_wake_rule(self) -> None:
        intervals = parse_labeled_casas_intervals(
            FIXTURES_DIR / "sample_labeled_casas.txt",
            wake_window_minutes=30,
        )

        self.assertEqual(len(intervals), 3)
        self.assertEqual(intervals[0].raw_label, "Sleeping")
        self.assertEqual(intervals[0].adl_category, "Sleep")
        self.assertEqual(intervals[1].raw_label, "Bed_to_Toilet")
        self.assertEqual(intervals[1].adl_category, "Wake-up")
        self.assertEqual(intervals[2].adl_category, "Meal")

    def test_pattern_occurrence_exact_match(self) -> None:
        states = [
            StateInterval(ts("2020-01-01 00:00:00"), ts("2020-01-01 00:01:00"), "状態1"),
            StateInterval(ts("2020-01-01 00:01:00"), ts("2020-01-01 00:02:00"), "状態5"),
            StateInterval(ts("2020-01-01 00:02:00"), ts("2020-01-01 00:03:00"), "状態7"),
        ]
        patterns = [
            PatternRecord("P1", "wake", ("状態1", "状態5", "状態7")),
        ]

        occurrences = find_pattern_occurrences(patterns, states, match_mode="exact")

        self.assertEqual(len(occurrences), 1)
        self.assertEqual(occurrences[0].start_time, ts("2020-01-01 00:00:00"))
        self.assertEqual(occurrences[0].end_time, ts("2020-01-01 00:03:00"))

    def test_exact_match_counts_overlapping_start_positions_separately(self) -> None:
        states = [
            StateInterval(
                ts(f"2020-01-01 00:0{index}:00"),
                ts(f"2020-01-01 00:0{index + 1}:00"),
                state,
            )
            for index, state in enumerate(("A", "B", "A", "B", "A"))
        ]
        pattern = PatternRecord("P1", "overlap", ("A", "B", "A"))

        occurrences = find_pattern_occurrences(
            [pattern],
            states,
            match_mode="exact",
        )

        self.assertEqual(len(occurrences), 2)
        self.assertEqual(
            [item.start_time for item in occurrences],
            [ts("2020-01-01 00:00:00"), ts("2020-01-01 00:02:00")],
        )

    def test_exact_match_rejects_intervening_state_and_does_not_skip(self) -> None:
        states = [
            StateInterval(ts("2020-01-01 00:00:00"), ts("2020-01-01 00:01:00"), "A"),
            StateInterval(ts("2020-01-01 00:01:00"), ts("2020-01-01 00:02:00"), "X"),
            StateInterval(ts("2020-01-01 00:02:00"), ts("2020-01-01 00:03:00"), "B"),
            StateInterval(ts("2020-01-01 00:03:00"), ts("2020-01-01 00:04:00"), "C"),
        ]
        patterns = [
            PatternRecord("insert", "insert", ("A", "B", "C")),
            PatternRecord("substitute", "substitute", ("A", "Y", "B")),
            PatternRecord("delete", "delete", ("A", "X", "B", "C", "D")),
            PatternRecord("skip", "skip", ("A", "B")),
        ]

        occurrences = find_pattern_occurrences(
            patterns,
            states,
            match_mode="exact",
        )

        self.assertEqual(occurrences, [])

    def test_state_series_can_be_built_from_labeled_casas(self) -> None:
        intervals = build_state_series_from_labeled_casas(
            labeled_casas_path=FIXTURES_DIR / "sample_labeled_casas.txt",
            state_table_path=FIXTURES_DIR / "sample_state_table.tsv",
            hamming_threshold=0,
            sensor_map_path=FIXTURES_DIR / "sample_sensor_map.json",
        )

        self.assertGreaterEqual(len(intervals), 2)
        self.assertEqual(intervals[0].state_id, "状態2")
        self.assertEqual(intervals[0].start_time, ts("2020-01-01 00:00:00"))

    def test_event_log_and_labeled_casas_build_same_complete_intervals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            event_log_path = Path(tmpdir) / "events.csv"
            labeled_casas_path = Path(tmpdir) / "labeled.txt"
            event_log_path.write_text(
                "2020-01-01,00:00:00.000000,Kitchen,ON\n"
                "2020-01-01,00:00:01.000000,Bedroom,ON\n"
                "2020-01-01,00:00:01.250000,IgnoredSensor,ON\n"
                "2020-01-01,00:00:01.500000,Kitchen,MAYBE\n"
                "2020-01-01,00:00:02.000000,Kitchen,OFF\n"
                "2020-01-01,00:00:04.000000,Bedroom,OFF\n"
                "2020-01-01,00:00:05.000000,Kitchen,ON\n"
                "2020-01-01,00:00:06.000000,Kitchen,OFF\n",
                encoding="utf-8",
            )
            labeled_casas_path.write_text(
                "2020-01-01 00:00:00.000000 M001 ON\n"
                "2020-01-01 00:00:01.000000 M002 ON\n"
                "2020-01-01 00:00:01.250000 M999 ON\n"
                "2020-01-01 00:00:01.500000 M001 MAYBE\n"
                "2020-01-01 00:00:02.000000 M001 OFF\n"
                "2020-01-01 00:00:04.000000 M002 OFF\n"
                "2020-01-01 00:00:05.000000 M001 ON\n"
                "2020-01-01 00:00:06.000000 M001 OFF\n",
                encoding="utf-8",
            )

            event_log_intervals = build_state_series_from_event_log(
                event_log_path=event_log_path,
                state_table_path=FIXTURES_DIR / "sample_state_table.tsv",
                hamming_threshold=1,
            )
            labeled_casas_intervals = build_state_series_from_labeled_casas(
                labeled_casas_path=labeled_casas_path,
                state_table_path=FIXTURES_DIR / "sample_state_table.tsv",
                hamming_threshold=1,
                sensor_map_path=FIXTURES_DIR / "sample_sensor_map.json",
            )

        expected = [
            StateInterval(
                ts("2020-01-01 00:00:00"),
                ts("2020-01-01 00:00:02"),
                "状態2",
            ),
            StateInterval(
                ts("2020-01-01 00:00:02"),
                ts("2020-01-01 00:00:04"),
                "状態3",
            ),
            StateInterval(
                ts("2020-01-01 00:00:04"),
                ts("2020-01-01 00:00:05"),
                "状態1",
            ),
            StateInterval(
                ts("2020-01-01 00:00:05"),
                ts("2020-01-01 00:00:06"),
                "状態2",
            ),
        ]
        self.assertEqual(event_log_intervals, expected)
        self.assertEqual(labeled_casas_intervals, expected)

    def test_overlap_and_temporal_iou(self) -> None:
        overlap = interval_overlap_seconds(
            ts("2020-01-01 00:00:00"),
            ts("2020-01-01 00:10:00"),
            ts("2020-01-01 00:05:00"),
            ts("2020-01-01 00:15:00"),
        )
        iou = temporal_iou(
            ts("2020-01-01 00:00:00"),
            ts("2020-01-01 00:10:00"),
            ts("2020-01-01 00:05:00"),
            ts("2020-01-01 00:15:00"),
        )

        self.assertEqual(overlap, 5 * 60)
        self.assertAlmostEqual(iou, 5 / 15)

    def test_greedy_matching_does_not_reuse_truth_interval(self) -> None:
        truths = [
            ADLInterval(
                ts("2020-01-01 00:00:00"),
                ts("2020-01-01 00:10:00"),
                "Sleeping",
                "Sleep",
            )
        ]
        predictions = [
            PredictionInterval(
                "P1",
                "sleep A",
                ("状態1", "状態2"),
                ts("2020-01-01 00:00:00"),
                ts("2020-01-01 00:10:00"),
                "Sleep",
            ),
            PredictionInterval(
                "P2",
                "sleep B",
                ("状態3", "状態4"),
                ts("2020-01-01 00:01:00"),
                ts("2020-01-01 00:09:00"),
                "Sleep",
            ),
        ]

        matches, counts = greedy_match_by_category(predictions, truths, iou_threshold=0.3)
        rows = metrics_rows_from_counts(counts)
        sleep_row = next(row for row in rows if row["adl_category"] == "Sleep")

        self.assertEqual(len(matches), 1)
        self.assertEqual(sleep_row["tp"], 1)
        self.assertEqual(sleep_row["fp"], 1)
        self.assertEqual(sleep_row["fn"], 0)

    def test_merge_predictions_only_within_same_adl(self) -> None:
        predictions = [
            PredictionInterval("P1", "relax A", (), ts("2020-01-01 10:00:00"), ts("2020-01-01 10:00:20"), "Relax"),
            PredictionInterval("P2", "meal", (), ts("2020-01-01 10:00:30"), ts("2020-01-01 10:01:00"), "Meal"),
            PredictionInterval("P3", "relax B", (), ts("2020-01-01 10:01:00"), ts("2020-01-01 10:01:30"), "Relax"),
            PredictionInterval("P4", "relax C", (), ts("2020-01-01 10:03:00"), ts("2020-01-01 10:03:20"), "Relax"),
        ]

        merged = merge_prediction_intervals(predictions, merge_gap_minutes=5)

        self.assertEqual(len(merged), 2)
        relax = next(item for item in merged if item.assigned_adl == "Relax")
        meal = next(item for item in merged if item.assigned_adl == "Meal")
        self.assertEqual(relax.start_time, ts("2020-01-01 10:00:00"))
        self.assertEqual(relax.end_time, ts("2020-01-01 10:03:20"))
        self.assertEqual(relax.num_merged_occurrences, 3)
        self.assertEqual(meal.num_merged_occurrences, 1)

    def test_duration_filter_removes_short_predictions(self) -> None:
        predictions = merge_prediction_intervals(
            [
                PredictionInterval("P1", "short relax", (), ts("2020-01-01 10:00:00"), ts("2020-01-01 10:01:00"), "Relax"),
                PredictionInterval("P2", "long sleep", (), ts("2020-01-01 11:00:00"), ts("2020-01-01 11:20:00"), "Sleep"),
            ],
            merge_gap_minutes=0,
        )

        kept, removed = filter_predictions_by_duration(predictions, {"Relax": 180, "Sleep": 600, "Other_ADL": 0})

        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].assigned_adl, "Sleep")
        self.assertEqual(removed, {"Relax": 1})

    def test_interval_hit_overlap_and_tolerance(self) -> None:
        labels = [
            ADLInterval(
                ts("2020-01-01 07:00:00"),
                ts("2020-01-01 07:30:00"),
                "Meal_Preparation",
                "Meal",
            ),
            ADLInterval(
                ts("2020-01-01 08:00:00"),
                ts("2020-01-01 08:30:00"),
                "Relax",
                "Relax",
            ),
        ]
        predictions = merge_prediction_intervals(
            [
                PredictionInterval("P1", "meal", (), ts("2020-01-01 07:10:00"), ts("2020-01-01 07:11:00"), "Meal"),
                PredictionInterval("P2", "relax near", (), ts("2020-01-01 07:55:00"), ts("2020-01-01 07:56:00"), "Relax"),
            ],
            merge_gap_minutes=0,
        )

        rows, details = compute_interval_hit_evaluation(predictions, labels, hit_tolerance_minutes=10)
        overlap_relax = next(row for row in rows if row["hit_type"] == "overlap" and row["adl_category"] == "Relax")
        tolerance_relax = next(row for row in rows if row["hit_type"] == "tolerance" and row["adl_category"] == "Relax")
        overlap_meal = next(row for row in rows if row["hit_type"] == "overlap" and row["adl_category"] == "Meal")

        self.assertEqual(overlap_meal["hit_intervals"], 1)
        self.assertEqual(overlap_relax["hit_intervals"], 0)
        self.assertEqual(tolerance_relax["hit_intervals"], 1)
        self.assertTrue(any(row["hit_type"] == "tolerance" and row["true_adl"] == "Relax" and row["is_hit"] for row in details))


if __name__ == "__main__":
    unittest.main()
