from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.behavior_pattern_mining.evaluation.adl import ADLInterval, PredictionInterval, StateInterval
from src.behavior_pattern_mining.evaluation.adl_correspondence import (
    detect_alternating_loop,
    detect_other_state_round_trip,
    expand_adl_intervals_for_evaluation5,
    assign_mappings_by_method,
    build_fp_growth_baseline_patterns,
    build_predictions_by_method,
    clip_adl_intervals,
    clip_state_intervals,
    compute_time_split_periods,
    ensure_baseline_pattern_files,
    evaluate_pattern_groundedness,
    evaluate_methods,
    find_occurrences_by_method,
    load_method_patterns,
    parse_sequence,
    postprocess_predictions_by_method,
    train_pattern_adl_assignments,
)


def ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


class ADLCorrespondenceTests(unittest.TestCase):
    def test_parse_sequence_variants(self) -> None:
        self.assertEqual(parse_sequence("状態1 -> 状態5 -> 状態7"), ("状態1", "状態5", "状態7"))
        self.assertEqual(parse_sequence("状態1,状態5,状態7"), ("状態1", "状態5", "状態7"))
        self.assertEqual(parse_sequence('["状態1", "状態5"]'), ("状態1", "状態5"))
        self.assertEqual(parse_sequence(["状態1", "状態5"]), ("状態1", "状態5"))

    def test_load_method_patterns_from_json_and_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            json_path = tmp / "frequency.json"
            json_path.write_text(
                json.dumps(
                    [
                        {"rank": 1, "sequence": ["状態1", "状態2"], "count": 12},
                        {"rank": 2, "sequence": ["状態3"], "count": 2},
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            csv_path = tmp / "proposed.csv"
            csv_path.write_text(
                "pattern_name,sequence,count\n"
                "wake,状態1 -> 状態5 -> 状態7,\n",
                encoding="utf-8",
            )

            frequency, frequency_notes = load_method_patterns(json_path, "frequency")
            proposed, proposed_notes = load_method_patterns(csv_path, "proposed")

        self.assertEqual(len(frequency), 1)
        self.assertEqual(frequency[0].pattern_id, "F001")
        self.assertEqual(frequency[0].count, 12)
        self.assertEqual(len(frequency_notes), 1)
        self.assertEqual(len(proposed), 1)
        self.assertEqual(proposed[0].sequence, ("状態1", "状態5", "状態7"))
        self.assertEqual(proposed_notes, [])

    def test_method_metrics_do_not_share_truth_intervals(self) -> None:
        labels = [
            ADLInterval(
                ts("2020-01-01 00:00:00"),
                ts("2020-01-01 00:10:00"),
                "Sleeping",
                "Sleep",
            )
        ]
        states = [
            StateInterval(ts("2020-01-01 00:00:00"), ts("2020-01-01 00:05:00"), "状態1"),
            StateInterval(ts("2020-01-01 00:05:00"), ts("2020-01-01 00:10:00"), "状態2"),
            StateInterval(ts("2020-01-01 00:10:00"), ts("2020-01-01 00:15:00"), "状態1"),
            StateInterval(ts("2020-01-01 00:15:00"), ts("2020-01-01 00:20:00"), "状態2"),
        ]
        patterns, _ = load_method_patterns_from_payload(
            [
                {"sequence": ["状態1", "状態2"], "count": 2},
            ],
            "frequency",
        )
        patterns_by_method = {"frequency": patterns}

        occurrences = find_occurrences_by_method(patterns_by_method, states, "exact", 2.0)
        mappings = assign_mappings_by_method(patterns_by_method, occurrences, labels)
        predictions = build_predictions_by_method(occurrences, mappings)
        metrics_by_threshold, _, comparison_rows, _ = evaluate_methods(predictions, labels, [0.3])

        sleep_row = next(
            row for row in metrics_by_threshold[0.3]
            if row["method"] == "frequency" and row["adl_category"] == "Sleep"
        )
        comparison = comparison_rows[0]
        self.assertEqual(sleep_row["tp"], 1)
        self.assertEqual(sleep_row["fp"], 1)
        self.assertEqual(sleep_row["fn"], 0)
        self.assertAlmostEqual(sleep_row["precision"], 0.5)
        self.assertAlmostEqual(sleep_row["recall"], 1.0)
        self.assertAlmostEqual(sleep_row["f1"], 2 / 3)
        self.assertAlmostEqual(comparison["Sleep_F1"], 2 / 3)

    def test_method_postprocess_merges_filters_and_computes_hits(self) -> None:
        labels = [
            ADLInterval(
                ts("2020-01-01 10:00:00"),
                ts("2020-01-01 10:05:00"),
                "Relax",
                "Relax",
            ),
            ADLInterval(
                ts("2020-01-01 11:00:00"),
                ts("2020-01-01 11:10:00"),
                "Meal_Preparation",
                "Meal",
            ),
        ]
        predictions_by_method = {
            "frequency": [
                PredictionInterval("F001", "relax A", (), ts("2020-01-01 10:00:00"), ts("2020-01-01 10:00:20"), "Relax"),
                PredictionInterval("F002", "relax B", (), ts("2020-01-01 10:01:00"), ts("2020-01-01 10:01:30"), "Relax"),
                PredictionInterval("F003", "relax C", (), ts("2020-01-01 10:03:00"), ts("2020-01-01 10:03:20"), "Relax"),
                PredictionInterval("F004", "meal short", (), ts("2020-01-01 11:00:00"), ts("2020-01-01 11:01:00"), "Meal"),
            ]
        }

        merged, filtered, postprocessed, removed, hit_rows, _ = postprocess_predictions_by_method(
            predictions_by_method=predictions_by_method,
            labels=labels,
            merge_gap_minutes=5,
            min_duration_by_adl={"Relax": 180, "Meal": 120, "Other_ADL": 0},
            hit_tolerance_minutes=10,
        )

        self.assertEqual(len(merged["frequency"]), 2)
        self.assertEqual(len(filtered["frequency"]), 1)
        self.assertEqual(len(postprocessed["frequency"]), 1)
        self.assertEqual(removed["frequency"], {"Meal": 1})
        relax_overlap = next(
            row for row in hit_rows
            if row["method"] == "frequency" and row["hit_type"] == "overlap" and row["adl_category"] == "Relax"
        )
        self.assertEqual(relax_overlap["hit_intervals"], 1)
        self.assertEqual(relax_overlap["prediction_intervals"], 1)

    def test_missing_baselines_are_generated_from_state_series(self) -> None:
        states = [
            StateInterval(ts("2020-01-01 00:00:00"), ts("2020-01-01 00:01:00"), "状態1"),
            StateInterval(ts("2020-01-01 00:01:00"), ts("2020-01-01 00:02:00"), "状態2"),
            StateInterval(ts("2020-01-01 00:02:00"), ts("2020-01-01 00:03:00"), "状態3"),
            StateInterval(ts("2020-01-01 00:03:00"), ts("2020-01-01 00:04:00"), "状態1"),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            method_paths = {
                "frequency": tmp / "state_sequence_counts.json",
                "rule_light": tmp / "frequency_rule_light.csv",
                "rule_medium": tmp / "frequency_rule_medium.csv",
                "rule_strong": tmp / "frequency_rule_strong.csv",
                "proposed": tmp / "proposed.json",
            }

            notes = ensure_baseline_pattern_files(
                method_paths=method_paths,
                state_intervals=states,
                min_length=2,
                max_length=3,
                top_k=10,
            )

            self.assertTrue(method_paths["frequency"].exists())
            self.assertTrue(method_paths["rule_light"].exists())
            self.assertTrue(method_paths["rule_medium"].exists())
            self.assertTrue(method_paths["rule_strong"].exists())
            self.assertTrue(any("frequency: generated" in note for note in notes))
            frequency_patterns, _ = load_method_patterns(method_paths["frequency"], "frequency")
            rule_patterns, _ = load_method_patterns(method_paths["rule_light"], "rule_light")
            self.assertTrue(frequency_patterns)
            self.assertTrue(rule_patterns)

    def test_time_split_clips_intervals_at_boundary(self) -> None:
        labels = [
            ADLInterval(ts("2020-01-01 00:00:00"), ts("2020-01-01 00:10:00"), "Relax", "Relax")
        ]
        states = [
            StateInterval(ts("2020-01-01 00:00:00"), ts("2020-01-01 00:10:00"), "状態1")
        ]

        train_period, test_period = compute_time_split_periods(labels, states, train_ratio=0.5)
        train_labels = clip_adl_intervals(labels, *train_period)
        test_labels = clip_adl_intervals(labels, *test_period)
        train_states = clip_state_intervals(states, *train_period)
        test_states = clip_state_intervals(states, *test_period)

        self.assertEqual(train_period[1], ts("2020-01-01 00:05:00"))
        self.assertEqual(test_period[0], ts("2020-01-01 00:05:00"))
        self.assertEqual(train_labels[0].end_time, ts("2020-01-01 00:05:00"))
        self.assertEqual(test_labels[0].start_time, ts("2020-01-01 00:05:00"))
        self.assertEqual(train_states[0].end_time, ts("2020-01-01 00:05:00"))
        self.assertEqual(test_states[0].start_time, ts("2020-01-01 00:05:00"))

    def test_evaluation5_expands_raw_labels_to_multiple_adl_categories(self) -> None:
        labels = [
            ADLInterval(
                ts("2020-01-01 00:00:00"),
                ts("2020-01-01 00:01:00"),
                "Bed_to_Toilet",
                "Wake-up",
            ),
            ADLInterval(
                ts("2020-01-01 00:01:00"),
                ts("2020-01-01 00:02:00"),
                "Meal_Preparation",
                "Wake-up",
            ),
        ]

        expanded = expand_adl_intervals_for_evaluation5(labels)
        categories_by_raw = {}
        for item in expanded:
            categories_by_raw.setdefault(item.raw_label, set()).add(item.adl_category)

        self.assertEqual(categories_by_raw["Bed_to_Toilet"], {"Wake-up", "Toileting"})
        self.assertEqual(categories_by_raw["Meal_Preparation"], {"Meal", "Wake-up"})

    def test_useless_b_and_c_sequence_detectors(self) -> None:
        is_useless_b, reason_b = detect_other_state_round_trip(
            ("状態1", "その他", "状態1"),
            {"その他", "Other"},
        )
        is_useless_c, reason_c = detect_alternating_loop(("状態1", "状態2", "状態1", "状態2"))

        self.assertTrue(is_useless_b)
        self.assertIn("other_round_trip", reason_b)
        self.assertTrue(is_useless_c)
        self.assertIn("alternating_loop", reason_c)

    def test_fp_growth_baseline_builds_and_filters_patterns(self) -> None:
        states = [
            StateInterval(ts("2020-01-01 06:00:00"), ts("2020-01-01 06:01:00"), "状態1"),
            StateInterval(ts("2020-01-01 06:01:00"), ts("2020-01-01 06:02:00"), "状態2"),
            StateInterval(ts("2020-01-01 06:02:00"), ts("2020-01-01 06:03:00"), "状態1"),
            StateInterval(ts("2020-01-01 06:03:00"), ts("2020-01-01 06:04:00"), "状態2"),
            StateInterval(ts("2020-01-02 06:00:00"), ts("2020-01-02 06:01:00"), "状態1"),
            StateInterval(ts("2020-01-02 06:01:00"), ts("2020-01-02 06:02:00"), "その他"),
            StateInterval(ts("2020-01-02 06:02:00"), ts("2020-01-02 06:03:00"), "状態1"),
            StateInterval(ts("2020-01-03 06:00:00"), ts("2020-01-03 06:01:00"), "状態3"),
            StateInterval(ts("2020-01-03 06:01:00"), ts("2020-01-03 06:02:00"), "状態4"),
            StateInterval(ts("2020-01-04 06:00:00"), ts("2020-01-04 07:00:00"), "状態5"),
            StateInterval(ts("2020-01-04 07:00:00"), ts("2020-01-04 08:00:00"), "状態6"),
        ]

        patterns_by_method, notes = build_fp_growth_baseline_patterns(
            state_intervals=states,
            min_support=0.01,
            top_k=50,
            min_len=2,
            max_len=4,
            other_state_labels={"その他", "Other"},
            max_median_duration_seconds=1800,
            max_p90_duration_seconds=3600,
        )

        fp_sequences = {pattern.sequence: pattern for pattern in patterns_by_method["fp_growth"]}
        filtered_sequences = {pattern.sequence for pattern in patterns_by_method["fp_growth_filtered"]}

        self.assertTrue(any("fp_growth: generated" in note for note in notes))
        self.assertIn(("状態1", "状態2", "状態1", "状態2"), fp_sequences)
        self.assertIn(("状態1", "その他", "状態1"), fp_sequences)
        self.assertIn(("状態5", "状態6"), fp_sequences)
        self.assertNotIn(("状態1", "状態2", "状態1", "状態2"), filtered_sequences)
        self.assertNotIn(("状態1", "その他", "状態1"), filtered_sequences)
        self.assertNotIn(("状態5", "状態6"), filtered_sequences)
        self.assertIn("alternating_loop", fp_sequences[("状態1", "状態2", "状態1", "状態2")].fp_filter_reason)
        self.assertIn("other_round_trip", fp_sequences[("状態1", "その他", "状態1")].fp_filter_reason)
        self.assertIn("median_duration", fp_sequences[("状態5", "状態6")].fp_filter_reason)

    def test_pattern_groundedness_and_useless_a_are_pattern_level(self) -> None:
        patterns, _ = load_method_patterns_from_payload(
            [
                {"sequence": ["状態1", "状態2"], "count": 10},
                {"sequence": ["状態3", "状態4"], "count": 5},
                {"sequence": ["状態5", "状態6"], "count": 3},
            ],
            "frequency",
        )
        patterns_by_method = {"frequency": patterns}
        train_states = [
            StateInterval(ts("2020-01-01 00:00:00"), ts("2020-01-01 00:01:00"), "状態1"),
            StateInterval(ts("2020-01-01 00:01:00"), ts("2020-01-01 00:02:00"), "状態2"),
            StateInterval(ts("2020-01-01 00:02:00"), ts("2020-01-01 00:03:00"), "状態3"),
            StateInterval(ts("2020-01-01 00:03:00"), ts("2020-01-01 00:04:00"), "状態4"),
        ]
        train_labels = [
            ADLInterval(ts("2020-01-01 00:00:00"), ts("2020-01-01 00:02:00"), "Relax", "Relax")
        ]
        test_states = [
            StateInterval(ts("2020-01-02 00:00:00"), ts("2020-01-02 00:01:00"), "状態1"),
            StateInterval(ts("2020-01-02 00:01:00"), ts("2020-01-02 00:02:00"), "状態2"),
            StateInterval(ts("2020-01-02 00:02:00"), ts("2020-01-02 00:03:00"), "状態3"),
            StateInterval(ts("2020-01-02 00:03:00"), ts("2020-01-02 00:04:00"), "状態4"),
        ]
        test_labels = [
            ADLInterval(ts("2020-01-02 00:00:00"), ts("2020-01-02 00:02:00"), "Relax", "Relax")
        ]

        train_occurrences = find_occurrences_by_method(patterns_by_method, train_states, "exact", 2.0)
        test_occurrences = find_occurrences_by_method(patterns_by_method, test_states, "exact", 2.0)
        assignments = train_pattern_adl_assignments(patterns_by_method, train_occurrences, train_labels)
        detail_rows, summary_rows, _ = evaluate_pattern_groundedness(
            patterns_by_method=patterns_by_method,
            train_assignments=assignments,
            test_occurrences_by_method=test_occurrences,
            test_labels=test_labels,
            min_overlap_seconds=1,
            grounded_hit_threshold=0.3,
            grounded_purity_threshold=0.3,
            useless_hit_threshold=0.1,
            useless_purity_threshold=0.1,
        )

        by_pattern = {row["pattern_id"]: row for row in detail_rows}
        self.assertEqual(by_pattern["F001"]["evaluation_status"], "evaluated")
        self.assertEqual(by_pattern["F001"]["is_adl_grounded"], 1)
        self.assertEqual(by_pattern["F001"]["is_useless_a"], 0)
        self.assertEqual(by_pattern["F002"]["evaluation_status"], "no_assigned_adl")
        self.assertEqual(by_pattern["F002"]["is_adl_grounded"], 0)
        self.assertEqual(by_pattern["F002"]["is_useless_a"], 1)
        self.assertEqual(by_pattern["F003"]["evaluation_status"], "no_train_support")

        summary = summary_rows[0]
        self.assertEqual(summary["num_patterns"], 3)
        self.assertEqual(summary["num_evaluable_patterns"], 2)
        self.assertEqual(summary["num_adl_grounded"], 1)
        self.assertEqual(summary["num_useless_a"], 1)
        self.assertEqual(summary["num_useless"], 1)
        self.assertAlmostEqual(summary["adl_grounded_pattern_rate"], 0.5)
        self.assertAlmostEqual(summary["useless_a_pattern_rate"], 0.5)
        self.assertAlmostEqual(summary["useless_pattern_rate"], 0.5)

    def test_evaluation5_multi_label_assigned_set_and_other_adl_exclusion(self) -> None:
        patterns, _ = load_method_patterns_from_payload(
            [
                {"sequence": ["状態1", "状態2"], "count": 10},
                {"sequence": ["状態7", "状態8"], "count": 4},
            ],
            "frequency",
        )
        patterns_by_method = {"frequency": patterns}
        train_states = [
            StateInterval(ts("2020-01-01 00:00:00"), ts("2020-01-01 00:01:00"), "状態1"),
            StateInterval(ts("2020-01-01 00:01:00"), ts("2020-01-01 00:02:00"), "状態2"),
            StateInterval(ts("2020-01-01 00:02:00"), ts("2020-01-01 00:03:00"), "状態7"),
            StateInterval(ts("2020-01-01 00:03:00"), ts("2020-01-01 00:04:00"), "状態8"),
        ]
        train_labels = [
            ADLInterval(ts("2020-01-01 00:00:00"), ts("2020-01-01 00:02:00"), "Bed_to_Toilet", "Wake-up"),
            ADLInterval(ts("2020-01-01 00:00:00"), ts("2020-01-01 00:02:00"), "Bed_to_Toilet", "Toileting"),
            ADLInterval(ts("2020-01-01 00:02:00"), ts("2020-01-01 00:04:00"), "Unknown_Label", "Other_ADL"),
        ]
        test_states = [
            StateInterval(ts("2020-01-02 00:00:00"), ts("2020-01-02 00:01:00"), "状態1"),
            StateInterval(ts("2020-01-02 00:01:00"), ts("2020-01-02 00:02:00"), "状態2"),
            StateInterval(ts("2020-01-02 00:02:00"), ts("2020-01-02 00:03:00"), "状態7"),
            StateInterval(ts("2020-01-02 00:03:00"), ts("2020-01-02 00:04:00"), "状態8"),
        ]
        test_labels = [
            ADLInterval(ts("2020-01-02 00:00:00"), ts("2020-01-02 00:02:00"), "Bed_to_Toilet", "Toileting"),
            ADLInterval(ts("2020-01-02 00:02:00"), ts("2020-01-02 00:04:00"), "Unknown_Label", "Other_ADL"),
        ]

        train_occurrences = find_occurrences_by_method(patterns_by_method, train_states, "exact", 2.0)
        test_occurrences = find_occurrences_by_method(patterns_by_method, test_states, "exact", 2.0)
        assignments = train_pattern_adl_assignments(patterns_by_method, train_occurrences, train_labels)
        detail_rows, _, _ = evaluate_pattern_groundedness(
            patterns_by_method=patterns_by_method,
            train_assignments=assignments,
            test_occurrences_by_method=test_occurrences,
            test_labels=test_labels,
            min_overlap_seconds=1,
            grounded_hit_threshold=0.3,
            grounded_purity_threshold=0.3,
            useless_hit_threshold=0.1,
            useless_purity_threshold=0.1,
            exclude_other_adl_from_any=True,
        )

        by_pattern = {row["pattern_id"]: row for row in detail_rows}
        self.assertEqual(by_pattern["F001"]["assigned_adl_set_train"], "Toileting|Wake-up")
        self.assertEqual(by_pattern["F001"]["is_adl_grounded"], 1)
        self.assertEqual(by_pattern["F002"]["any_adl_hit_rate_test"], "0.000000")
        self.assertEqual(by_pattern["F002"]["is_useless_a"], 1)

    def test_train_assignment_uses_purity_threshold_top3_and_other_policy(self) -> None:
        patterns, _ = load_method_patterns_from_payload(
            [
                {"sequence": ["状態1", "状態2"], "count": 10},
                {"sequence": ["状態3", "状態4"], "count": 5},
            ],
            "frequency",
        )
        patterns_by_method = {"frequency": patterns}
        train_states = [
            StateInterval(ts("2020-01-01 00:00:00"), ts("2020-01-01 00:01:00"), "状態1"),
            StateInterval(ts("2020-01-01 00:01:00"), ts("2020-01-01 00:02:00"), "状態2"),
            StateInterval(ts("2020-01-01 00:02:00"), ts("2020-01-01 00:03:00"), "状態3"),
            StateInterval(ts("2020-01-01 00:03:00"), ts("2020-01-01 00:04:00"), "状態4"),
        ]
        train_labels = [
            ADLInterval(ts("2020-01-01 00:00:00"), ts("2020-01-01 00:01:00"), "Meal", "Meal"),
            ADLInterval(ts("2020-01-01 00:00:00"), ts("2020-01-01 00:00:40"), "Relax", "Relax"),
            ADLInterval(ts("2020-01-01 00:00:00"), ts("2020-01-01 00:00:30"), "Outing", "Outing"),
            ADLInterval(ts("2020-01-01 00:00:00"), ts("2020-01-01 00:00:20"), "Housekeeping", "Housework"),
            ADLInterval(ts("2020-01-01 00:00:00"), ts("2020-01-01 00:02:00"), "Unknown_Label", "Other_ADL"),
            ADLInterval(ts("2020-01-01 00:02:00"), ts("2020-01-01 00:04:00"), "Unknown_Label", "Other_ADL"),
        ]

        train_occurrences = find_occurrences_by_method(patterns_by_method, train_states, "exact", 2.0)
        assignments = train_pattern_adl_assignments(
            patterns_by_method,
            train_occurrences,
            train_labels,
            assigned_adl_purity_threshold=0.10,
            assigned_adl_max_categories=3,
        )

        assigned = assignments["frequency"]["F001"]["assigned_adl_set_train"]
        self.assertEqual(assigned, ["Meal", "Relax", "Outing"])
        self.assertNotIn("Housework", assigned)
        self.assertNotIn("Other_ADL", assigned)
        self.assertEqual(assignments["frequency"]["F002"]["assigned_adl_set_train"], ["Other_ADL"])


def load_method_patterns_from_payload(payload: list[dict], method: str):
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "patterns.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return load_method_patterns(path, method)


if __name__ == "__main__":
    unittest.main()
