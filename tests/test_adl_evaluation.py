from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path

from src.behavior_pattern_mining.evaluation.adl import (
    ADLInterval,
    PatternRecord,
    PredictionInterval,
    StateInterval,
    find_pattern_occurrences,
    greedy_match_by_category,
    interval_overlap_seconds,
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


if __name__ == "__main__":
    unittest.main()
