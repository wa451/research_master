from __future__ import annotations

import json
import csv
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from scripts.evaluate_adl_correspondence import aggregate_run_summaries, load_pattern_cache, write_pattern_cache
from src.behavior_pattern_mining.evaluation.adl import (
    ADLInterval,
    PredictionInterval,
    StateInterval,
    build_network_equivalent_state_series_from_labeled_casas,
)
from src.behavior_pattern_mining.evaluation.adl_correspondence import (
    detect_alternating_loop,
    detect_other_state_round_trip,
    compute_fragmentation_by_method,
    expand_adl_intervals_for_evaluation5,
    assign_mappings_by_method,
    build_fp_growth_baseline_patterns,
    build_transition_probability_baseline_patterns,
    build_predictions_by_method,
    clip_adl_intervals,
    clip_state_intervals,
    compute_time_split_periods,
    ensure_baseline_pattern_files,
    evaluate_pattern_groundedness,
    evaluate_methods,
    find_occurrences_by_method,
    is_low_information_sequence,
    load_state_low_information_map,
    load_method_patterns,
    MethodOccurrence,
    MethodPattern,
    occurrence_containment_rate,
    occurrence_is_within_time_band,
    parse_sequence,
    postprocess_predictions_by_method,
    train_pattern_adl_assignments,
    validate_state_attribute_coverage,
    write_pattern_groundedness_outputs,
)


def ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


class ADLCorrespondenceTests(unittest.TestCase):
    def test_parse_sequence_variants(self) -> None:
        self.assertEqual(parse_sequence("状態1 -> 状態5 -> 状態7"), ("状態1", "状態5", "状態7"))
        self.assertEqual(parse_sequence("状態1,状態5,状態7"), ("状態1", "状態5", "状態7"))
        self.assertEqual(parse_sequence('["状態1", "状態5"]'), ("状態1", "状態5"))
        self.assertEqual(parse_sequence(["状態1", "状態5"]), ("状態1", "状態5"))

    def test_state_definition_resolves_empty_active_sensors_as_low_information(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_definition = Path(tmpdir) / "states.tsv"
            state_definition.write_text(
                "状態\tKitchen\tBedroom\n"
                "状態1\t0\t0\n"
                "状態2\t1\t0\n"
                "その他\t-\t-\n",
                encoding="utf-8",
            )
            state_map = load_state_low_information_map(
                state_definition_path=state_definition,
                other_state_labels={"その他"},
            )

        self.assertTrue(state_map["状態1"])
        self.assertFalse(state_map["状態2"])
        self.assertTrue(state_map["その他"])
        validate_state_attribute_coverage(
            ["状態1", "状態2", "その他"],
            state_map,
            {"その他"},
        )
        with self.assertRaisesRegex(ValueError, "状態3"):
            validate_state_attribute_coverage(["状態3"], state_map, {"その他"})

    def test_state_network_resolves_active_sensors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            network = Path(tmpdir) / "network.json"
            network.write_text(
                json.dumps(
                    {
                        "nodes": [
                            {"state_id": "状態1", "active_sensors": []},
                            {"state_id": "状態2", "active_sensors": ["Kitchen"]},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            state_map = load_state_low_information_map(
                state_network_json_path=network,
            )

        self.assertEqual(state_map, {"状態1": True, "状態2": False})

    def test_low_information_threshold_is_strictly_greater_than_half(self) -> None:
        at_boundary, boundary_ratio = is_low_information_sequence(
            ("状態1", "状態2"),
            other_state_labels=set(),
            low_information_threshold=0.5,
            state_low_information_map={"状態1": True, "状態2": False},
        )
        above_boundary, above_ratio = is_low_information_sequence(
            ("状態1", "状態2", "状態3"),
            other_state_labels=set(),
            low_information_threshold=0.5,
            state_low_information_map={
                "状態1": True,
                "状態2": True,
                "状態3": False,
            },
        )

        self.assertEqual(boundary_ratio, 0.5)
        self.assertFalse(at_boundary)
        self.assertGreater(above_ratio, 0.5)
        self.assertTrue(above_boundary)

    def test_network_equivalent_state_series_applies_one_second_sampling_and_delayed_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            labeled = tmp / "labeled.txt"
            labeled.write_text(
                "2020-01-01 00:00:01.200000 M001 ON\n"
                "2020-01-01 00:00:03.000000 M001 OFF\n"
                "2020-01-01 00:00:10.000000 M001 ON\n"
                "2020-01-01 00:00:11.000000 M001 OFF\n",
                encoding="utf-8",
            )
            state_definition = tmp / "states.tsv"
            state_definition.write_text(
                "状態\tKitchen\n"
                "状態1\t0\n"
                "状態2\t1\n"
                "その他\t-\n",
                encoding="utf-8",
            )
            sensor_map = tmp / "sensor_map.json"
            sensor_map.write_text(
                json.dumps({"M001": "Kitchen"}),
                encoding="utf-8",
            )

            intervals = build_network_equivalent_state_series_from_labeled_casas(
                labeled_casas_path=labeled,
                state_table_path=state_definition,
                hamming_threshold=0,
                smoothing_window_sec=5,
                sensor_map_path=sensor_map,
                duration_days=1,
            )

        self.assertEqual(
            [
                (item.start_time, item.end_time, item.state_id)
                for item in intervals[:5]
            ],
            [
                (
                    ts("2020-01-01 00:00:00"),
                    ts("2020-01-01 00:00:02"),
                    "状態1",
                ),
                (
                    ts("2020-01-01 00:00:02"),
                    ts("2020-01-01 00:00:07"),
                    "状態2",
                ),
                (
                    ts("2020-01-01 00:00:07"),
                    ts("2020-01-01 00:00:10"),
                    "状態1",
                ),
                (
                    ts("2020-01-01 00:00:10"),
                    ts("2020-01-01 00:00:15"),
                    "状態2",
                ),
                (
                    ts("2020-01-01 00:00:15"),
                    ts("2020-01-02 00:00:00"),
                    "状態1",
                ),
            ],
        )

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

    def test_proposed_occurrence_search_respects_time_band(self) -> None:
        patterns = [
            MethodPattern(
                method="proposed",
                pattern_id="P001_Morning",
                pattern_name="morning",
                sequence=("状態1", "状態2"),
                time_band="Morning",
            )
        ]
        states = [
            StateInterval(ts("2020-01-01 06:00:00"), ts("2020-01-01 06:01:00"), "状態1"),
            StateInterval(ts("2020-01-01 06:01:00"), ts("2020-01-01 06:02:00"), "状態2"),
            StateInterval(ts("2020-01-01 18:00:00"), ts("2020-01-01 18:01:00"), "状態1"),
            StateInterval(ts("2020-01-01 18:01:00"), ts("2020-01-01 18:02:00"), "状態2"),
        ]

        occurrences = find_occurrences_by_method(
            {"proposed": patterns},
            states,
            "exact",
            2.0,
        )

        self.assertEqual(len(occurrences["proposed"]), 1)
        self.assertEqual(
            occurrences["proposed"][0].start_time,
            ts("2020-01-01 06:00:00"),
        )

    def test_time_band_half_open_interval_excludes_boundary_crossing(self) -> None:
        self.assertTrue(
            occurrence_is_within_time_band(
                ts("2020-01-01 09:59:00"),
                ts("2020-01-01 10:00:00"),
                "Morning",
            )
        )
        self.assertFalse(
            occurrence_is_within_time_band(
                ts("2020-01-01 09:59:00"),
                ts("2020-01-01 10:00:01"),
                "Morning",
            )
        )

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

    def test_transition_probability_baseline_builds_ranked_paths(self) -> None:
        states = [
            StateInterval(ts("2020-01-01 00:00:00"), ts("2020-01-01 00:01:00"), "状態1"),
            StateInterval(ts("2020-01-01 00:01:00"), ts("2020-01-01 00:02:00"), "状態2"),
            StateInterval(ts("2020-01-01 00:02:00"), ts("2020-01-01 00:03:00"), "状態3"),
            StateInterval(ts("2020-01-01 00:03:00"), ts("2020-01-01 00:04:00"), "状態1"),
            StateInterval(ts("2020-01-01 00:04:00"), ts("2020-01-01 00:05:00"), "状態2"),
            StateInterval(ts("2020-01-01 00:05:00"), ts("2020-01-01 00:06:00"), "状態3"),
            StateInterval(ts("2020-01-01 00:06:00"), ts("2020-01-01 00:07:00"), "状態4"),
        ]

        patterns, notes = build_transition_probability_baseline_patterns(
            states,
            top_k=5,
            min_prob=0.0,
            min_len=2,
            max_len=4,
        )

        sequences = {pattern.sequence: pattern for pattern in patterns}
        self.assertTrue(any("transition_probability: generated" in note for note in notes))
        self.assertIn(("状態1", "状態2"), sequences)
        self.assertEqual(sequences[("状態1", "状態2")].method, "transition_probability")
        self.assertEqual(sequences[("状態1", "状態2")].count, 2)
        self.assertGreaterEqual(sequences[("状態1", "状態2")].transition_joint_probability or 0.0, 0.0)

    def test_evaluation5_baseline_pattern_cache_round_trips_metadata(self) -> None:
        patterns = [
            MethodPattern(
                method="transition_probability",
                pattern_id="TP001",
                pattern_name="tp path",
                sequence=("状態1", "状態2", "状態3"),
                count=10,
                pattern_source="transition_probability",
                transition_joint_probability=0.42,
                transition_min_step_probability=0.6,
            ),
            MethodPattern(
                method="transition_probability",
                pattern_id="TP002",
                pattern_name="tp path 2",
                sequence=("状態4", "状態5"),
                train_occurrence_count=7,
                median_duration_seconds=12.5,
                p90_duration_seconds=20.0,
            ),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cache.csv"
            write_pattern_cache(path, patterns)
            loaded = load_pattern_cache(path, "transition_probability")

        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0].sequence, ("状態1", "状態2", "状態3"))
        self.assertEqual(loaded[0].transition_joint_probability, 0.42)
        self.assertEqual(loaded[1].train_occurrence_count, 7)
        self.assertEqual(loaded[1].median_duration_seconds, 12.5)

    def test_fragmentation_and_useful_non_redundant_metrics(self) -> None:
        patterns, _ = load_method_patterns_from_payload(
            [
                {"sequence": ["状態1", "状態2"], "count": 10},
                {"sequence": ["状態1", "状態2", "状態3"], "count": 4},
                {"sequence": ["その他", "unknown"], "count": 2},
            ],
            "frequency",
        )
        patterns_by_method = {"frequency": patterns}
        train_states = [
            StateInterval(ts("2020-01-01 00:00:00"), ts("2020-01-01 00:01:00"), "状態1"),
            StateInterval(ts("2020-01-01 00:01:00"), ts("2020-01-01 00:02:00"), "状態2"),
            StateInterval(ts("2020-01-01 00:02:00"), ts("2020-01-01 00:03:00"), "状態3"),
            StateInterval(ts("2020-01-01 00:03:00"), ts("2020-01-01 00:04:00"), "その他"),
            StateInterval(ts("2020-01-01 00:04:00"), ts("2020-01-01 00:05:00"), "unknown"),
        ]
        train_labels = [
            ADLInterval(ts("2020-01-01 00:00:00"), ts("2020-01-01 00:03:00"), "Relax", "Relax"),
            ADLInterval(ts("2020-01-01 00:03:00"), ts("2020-01-01 00:05:00"), "Unknown_Label", "Other_ADL"),
        ]
        test_states = [
            StateInterval(ts("2020-01-02 00:00:00"), ts("2020-01-02 00:01:00"), "状態1"),
            StateInterval(ts("2020-01-02 00:01:00"), ts("2020-01-02 00:02:00"), "状態2"),
            StateInterval(ts("2020-01-02 00:02:00"), ts("2020-01-02 00:03:00"), "状態3"),
            StateInterval(ts("2020-01-02 00:03:00"), ts("2020-01-02 00:04:00"), "その他"),
            StateInterval(ts("2020-01-02 00:04:00"), ts("2020-01-02 00:05:00"), "unknown"),
        ]
        test_labels = [
            ADLInterval(ts("2020-01-02 00:00:00"), ts("2020-01-02 00:03:00"), "Relax", "Relax")
        ]

        train_occurrences = find_occurrences_by_method(patterns_by_method, train_states, "exact", 2.0)
        test_occurrences = find_occurrences_by_method(patterns_by_method, test_states, "exact", 2.0)
        assignments = train_pattern_adl_assignments(patterns_by_method, train_occurrences, train_labels)
        fragmentation, fragmentation_summary = compute_fragmentation_by_method(
            patterns_by_method,
            test_occurrences,
            0.7,
        )
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
            other_state_labels={"その他", "unknown"},
        )

        by_pattern = {row["pattern_id"]: row for row in detail_rows}
        self.assertTrue(fragmentation["frequency"]["F001"]["is_fragmented"])
        self.assertEqual(
            fragmentation_summary["frequency"]["num_comparable_fragment_pairs"],
            1,
        )
        self.assertEqual(by_pattern["F001"]["is_fragmented"], 1)
        self.assertEqual(by_pattern["F001"]["is_useful_non_redundant"], 0)
        self.assertEqual(by_pattern["F002"]["is_useful_non_redundant"], 1)
        self.assertEqual(by_pattern["F003"]["is_low_information"], 1)
        self.assertEqual(by_pattern["F003"]["is_contextless_useless"], 1)
        summary = summary_rows[0]
        self.assertEqual(summary["output_record_count"], 3)
        self.assertEqual(summary["unique_sequence_count"], 3)
        self.assertEqual(summary["num_evaluable_patterns"], 3)
        self.assertEqual(summary["num_comparable_fragment_pairs"], 1)
        self.assertEqual(summary["fragmentation_status"], "evaluated")
        self.assertAlmostEqual(summary["fragmentation_rate"], 1 / 3)
        self.assertAlmostEqual(summary["useful_non_redundant_pattern_rate"], 1 / 3)
        self.assertAlmostEqual(summary["contextless_useless_rate"], 1 / 3)

    def test_fragmentation_uses_same_time_band_and_deduplicates_pairs(self) -> None:
        patterns = [
            MethodPattern(
                "proposed",
                "P_child_Morning",
                "child",
                ("状態1", "状態2"),
                time_band="Morning",
            ),
            MethodPattern(
                "proposed",
                "P_parent_Morning",
                "parent morning",
                ("状態1", "状態2", "状態3"),
                time_band="Morning",
            ),
            MethodPattern(
                "proposed",
                "P_parent_Night",
                "parent night",
                ("状態1", "状態2", "状態3"),
                time_band="Night",
            ),
        ]
        states = [
            StateInterval(ts("2020-01-01 06:00:00"), ts("2020-01-01 06:01:00"), "状態1"),
            StateInterval(ts("2020-01-01 06:01:00"), ts("2020-01-01 06:02:00"), "状態2"),
            StateInterval(ts("2020-01-01 06:02:00"), ts("2020-01-01 06:03:00"), "状態3"),
            StateInterval(ts("2020-01-01 18:00:00"), ts("2020-01-01 18:01:00"), "状態1"),
            StateInterval(ts("2020-01-01 18:01:00"), ts("2020-01-01 18:02:00"), "状態2"),
            StateInterval(ts("2020-01-01 18:02:00"), ts("2020-01-01 18:03:00"), "状態3"),
        ]
        patterns_by_method = {"proposed": patterns}
        occurrences = find_occurrences_by_method(
            patterns_by_method,
            states,
            "exact",
            2.0,
        )

        fragmentation, summary = compute_fragmentation_by_method(
            patterns_by_method,
            occurrences,
            0.7,
        )

        child = fragmentation["proposed"]["P_child_Morning"]
        self.assertTrue(child["is_fragmented"])
        self.assertEqual(
            child["comparable_fragment_parent_ids"],
            ["P_parent_Morning"],
        )
        self.assertEqual(summary["proposed"]["num_comparable_fragment_pairs"], 1)
        self.assertEqual(summary["proposed"]["num_comparable_fragment_children"], 1)

    def test_occurrence_containment_sweep_handles_overlapping_parents(self) -> None:
        def occurrence(
            occurrence_id: str,
            start: str,
            end: str,
        ) -> MethodOccurrence:
            return MethodOccurrence(
                method="proposed",
                pattern_id="P",
                pattern_name="p",
                sequence=("状態1", "状態2"),
                occurrence_id=occurrence_id,
                start_time=ts(start),
                end_time=ts(end),
            )

        children = [
            occurrence("C1", "2020-01-01 00:01:00", "2020-01-01 00:02:00"),
            occurrence("C2", "2020-01-01 00:07:00", "2020-01-01 00:08:00"),
            occurrence("C3", "2020-01-01 00:11:00", "2020-01-01 00:12:00"),
        ]
        parents = [
            occurrence("P1", "2020-01-01 00:00:00", "2020-01-01 00:10:00"),
            occurrence("P2", "2020-01-01 00:05:00", "2020-01-01 00:06:00"),
        ]

        self.assertAlmostEqual(
            occurrence_containment_rate(children, parents),
            2 / 3,
        )

    def test_fragmentation_rate_is_zero_when_no_comparable_pairs(self) -> None:
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
        self.assertAlmostEqual(summary["useful_non_redundant_pattern_rate"], 0.5)
        self.assertEqual(summary["fragmentation_rate"], 0.0)
        self.assertEqual(summary["fragmentation_status"], "evaluated")
        self.assertEqual(summary["num_comparable_fragment_pairs"], 0)
        self.assertEqual(summary["num_comparable_fragment_children"], 0)
        self.assertAlmostEqual(summary["contextless_useless_rate"], 0.5)

    def test_useful_flag_uses_state_attribute_low_information_result(self) -> None:
        patterns = [
            MethodPattern(
                "proposed",
                "P001",
                "pattern",
                ("状態1", "状態2"),
            )
        ]
        patterns_by_method = {"proposed": patterns}
        train_states = [
            StateInterval(ts("2020-01-01 00:00:00"), ts("2020-01-01 00:01:00"), "状態1"),
            StateInterval(ts("2020-01-01 00:01:00"), ts("2020-01-01 00:02:00"), "状態2"),
        ]
        test_states = [
            StateInterval(ts("2020-01-02 00:00:00"), ts("2020-01-02 00:01:00"), "状態1"),
            StateInterval(ts("2020-01-02 00:01:00"), ts("2020-01-02 00:02:00"), "状態2"),
        ]
        train_labels = [
            ADLInterval(ts("2020-01-01 00:00:00"), ts("2020-01-01 00:02:00"), "Relax", "Relax")
        ]
        test_labels = [
            ADLInterval(ts("2020-01-02 00:00:00"), ts("2020-01-02 00:02:00"), "Relax", "Relax")
        ]
        train_occurrences = find_occurrences_by_method(
            patterns_by_method,
            train_states,
            "exact",
            2.0,
        )
        test_occurrences = find_occurrences_by_method(
            patterns_by_method,
            test_states,
            "exact",
            2.0,
        )
        assignments = train_pattern_adl_assignments(
            patterns_by_method,
            train_occurrences,
            train_labels,
        )

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
            state_low_information_map={"状態1": True, "状態2": True},
        )

        self.assertEqual(detail_rows[0]["is_adl_grounded"], 1)
        self.assertEqual(detail_rows[0]["is_low_information"], 1)
        self.assertEqual(detail_rows[0]["is_contextless_useless"], 1)
        self.assertEqual(detail_rows[0]["is_useful_non_redundant"], 0)
        self.assertEqual(summary_rows[0]["fragmentation_rate"], 0.0)

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

    def test_evaluation5_multi_run_summary_outputs_average_and_by_run(self) -> None:
        by_run = [
            {
                "run": 1,
                "method": "proposed",
                "useful_non_redundant_pattern_rate": 0.2,
                "fragmentation_rate": 0.4,
                "contextless_useless_rate": 0.6,
            },
            {
                "run": 2,
                "method": "proposed",
                "useful_non_redundant_pattern_rate": 0.4,
                "fragmentation_rate": 0.2,
                "contextless_useless_rate": 0.8,
            },
        ]
        summary_rows, summary_by_method = aggregate_run_summaries(by_run)
        self.assertEqual(summary_rows[0]["num_runs"], 2)
        self.assertAlmostEqual(summary_rows[0]["useful_non_redundant_pattern_rate"], 0.3)
        self.assertAlmostEqual(summary_rows[0]["fragmentation_rate"], 0.3)
        self.assertAlmostEqual(summary_rows[0]["contextless_useless_rate"], 0.7)
        self.assertIn("useful_non_redundant_pattern_rate_std", summary_by_method["proposed"])

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            write_pattern_groundedness_outputs(
                output_dir=output_dir,
                pattern_detail_rows=[
                    {
                        "run": 1,
                        "method": "proposed",
                        "pattern_id": "P001",
                        "pattern_name": "p",
                        "sequence": "状態1 -> 状態2",
                        "is_contextless_useless": 0,
                        "is_fragmented": 0,
                        "is_useful_non_redundant": 1,
                    }
                ],
                summary_rows=summary_rows,
                summary_by_run_rows=by_run,
                summary={"summary_by_method": summary_by_method},
            )
            with (output_dir / "evaluation5_summary_by_method.csv").open(encoding="utf-8", newline="") as handle:
                header = next(csv.reader(handle))
            self.assertEqual(
                header,
                [
                    "method",
                    "num_runs",
                    "fragmentation_status",
                    "fragmentation_rate_num_valid_runs",
                    "fragmentation_rate_num_na_runs",
                    "useful_non_redundant_pattern_rate",
                    "useful_non_redundant_pattern_rate_std",
                    "fragmentation_rate",
                    "fragmentation_rate_std",
                    "contextless_useless_rate",
                    "contextless_useless_rate_std",
                ],
            )
            with (output_dir / "evaluation5_summary_by_method_by_run.csv").open(encoding="utf-8", newline="") as handle:
                by_run_header = next(csv.reader(handle))
            self.assertEqual(
                by_run_header,
                [
                    "run",
                    "method",
                    "useful_non_redundant_pattern_rate",
                    "fragmentation_rate",
                    "contextless_useless_rate",
                ],
            )

    def test_multi_run_fragmentation_aggregation_treats_legacy_na_as_zero(self) -> None:
        rows = [
            {
                "run": 1,
                "method": "proposed",
                "useful_non_redundant_pattern_rate": 0.8,
                "fragmentation_rate": None,
                "contextless_useless_rate": 0.2,
            },
            {
                "run": 2,
                "method": "proposed",
                "useful_non_redundant_pattern_rate": 0.6,
                "fragmentation_rate": 0.25,
                "contextless_useless_rate": 0.3,
            },
        ]

        summary_rows, _ = aggregate_run_summaries(rows)
        summary = summary_rows[0]

        self.assertEqual(summary["fragmentation_status"], "evaluated")
        self.assertEqual(summary["fragmentation_rate_num_valid_runs"], 2)
        self.assertEqual(summary["fragmentation_rate_num_na_runs"], 0)
        self.assertEqual(summary["fragmentation_rate"], 0.125)


def load_method_patterns_from_payload(payload: list[dict], method: str):
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "patterns.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return load_method_patterns(path, method)


if __name__ == "__main__":
    unittest.main()
