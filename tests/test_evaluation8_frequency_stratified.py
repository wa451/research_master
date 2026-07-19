from __future__ import annotations

import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.command_builder import build_evaluation8_steps
from app.streamlit_app import evaluation8_scope_config


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_8_frequency_stratified_adl_consistency.py"
SPEC = importlib.util.spec_from_file_location("evaluation8", SCRIPT_PATH)
assert SPEC and SPEC.loader
evaluation8 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluation8)


def row(pattern_id: str, occurrences: int, precision: float) -> dict[str, object]:
    return {
        "method": "proposed",
        "eval_pattern_id": pattern_id,
        "sequence": "状態1->状態2",
        "time_band": "All",
        "num_occurrences": occurrences,
        "exact_set_match": 0,
        "jaccard": precision / 2,
        "multilabel_precision": precision,
        "multilabel_recall": precision / 2,
        "multilabel_f1": precision / 3,
    }


class Evaluation8FrequencyStratifiedTests(unittest.TestCase):
    def test_default_output_directories_follow_analysis_scope(self) -> None:
        self.assertEqual(
            evaluation8.default_output_dir("comparison_14days").name,
            "8_vs_llm_own_id_fixed",
        )
        self.assertEqual(
            evaluation8.default_output_dir("comparison_30days").name,
            "8_vs_llm_own_id_fixed",
        )
        self.assertEqual(
            evaluation8.default_output_dir("proposed_154days").name,
            "8_proposed_own_id_fixed",
        )

    def test_default_scope_is_14_day_comparison(self) -> None:
        with patch.object(sys, "argv", [str(SCRIPT_PATH)]):
            args = evaluation8.parse_args()

        self.assertEqual(args.analysis_scope, "comparison_14days")

    def test_dashboard_scope_mapping_keeps_previous_30_day_comparison_out_of_proposed_branch(self) -> None:
        self.assertEqual(
            evaluation8_scope_config("30日: 提案手法 vs LLM単独ベースライン"),
            ("comparison_30days", 30),
        )
        self.assertEqual(
            evaluation8_scope_config("14日: 提案手法 vs LLM単独ベースライン"),
            ("comparison_14days", 14),
        )

    def test_dashboard_comparison_command_passes_state_series_and_tracks_new_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            details = root / "evaluation6_details.csv"
            state_series = root / "state_series.csv"
            output_dir = root / "evaluation8"
            step = build_evaluation8_steps(
                {
                    "runner": "python",
                    "analysis_scope": "comparison_14days",
                    "n_states": 15,
                    "hamming_threshold": 0,
                    "days": 14,
                    "output_dir": output_dir,
                    "frequency_band_mode": "both",
                    "fixed_frequency_bin_edges": "0,1,10,100",
                    "evaluation6_details": details,
                    "state_series": state_series,
                }
            )[0]

        self.assertIn("--state-series", step.command)
        self.assertIn(str(state_series), step.command)
        self.assertIn(state_series, step.required_inputs)
        self.assertIn(
            output_dir / "tertile" / "evaluation8_by_frequency_band_by_run.csv",
            step.expected_outputs,
        )

    def test_tertiles_are_stable_and_near_equal(self) -> None:
        rows = [
            row("P3", 1, 0.3),
            row("P1", 1, 0.1),
            row("P2", 1, 0.2),
            row("P4", 4, 0.4),
            row("P5", 5, 0.5),
        ]

        evaluation8.assign_frequency_bands(rows)

        by_id = {item["eval_pattern_id"]: item["frequency_band"] for item in rows}
        self.assertEqual(by_id["P1"], "Low")
        self.assertEqual(by_id["P2"], "Low")
        self.assertEqual(by_id["P3"], "Middle")
        self.assertEqual(by_id["P4"], "Middle")
        self.assertEqual(by_id["P5"], "High")

    def test_summary_uses_occurrence_weighting(self) -> None:
        rows = [row("P1", 1, 0.0), row("P2", 9, 1.0)]
        for item in rows:
            item["frequency_band"] = "Low"

        summary = evaluation8.summarize_rows(rows, "Low")

        self.assertEqual(summary["num_patterns"], 2)
        self.assertAlmostEqual(summary["mean_multilabel_precision"], 0.5)
        self.assertAlmostEqual(summary["weighted_multilabel_precision"], 0.9)

    def test_truth_undefined_band_has_no_weighted_metric(self) -> None:
        truth_undefined = {
            **row("P1", 6, 0.0),
            "occurrence_status": "matched",
            "truth_status": "no_adl_overlap",
            "prediction_status": "valid",
            "is_metric_evaluable": 0,
            "is_end_to_end_evaluable": 0,
        }

        summary = evaluation8.summarize_rows([truth_undefined], "1-9")

        self.assertEqual(summary["num_conditional_evaluable_patterns"], 0)
        self.assertEqual(summary["num_end_to_end_evaluable_patterns"], 0)
        self.assertIsNone(summary["weighted_multilabel_f1"])

    def test_own_pattern_id_reconstruction_excludes_same_sequence_other_ids(self) -> None:
        rows = [
            {**row("P1", 2, 0.1), "run": 1},
            {**row("P2", 2, 0.2), "run": 1},
        ]
        for item in rows:
            item["num_occurrences_before_fix"] = item["num_occurrences"]
        with tempfile.TemporaryDirectory() as tmpdir:
            state_series = Path(tmpdir) / "state_series.csv"
            state_series.write_text(
                "start_time,end_time,state_id\n"
                "2020-01-01 07:00:00,2020-01-01 07:01:00,状態1\n"
                "2020-01-01 07:01:00,2020-01-01 07:02:00,状態2\n",
                encoding="utf-8",
            )
            intervals = evaluation8.load_state_series_csv(state_series)
            evaluation8.attach_own_id_occurrences(rows, intervals, "exact", 1.0)

        by_id = {item["eval_pattern_id"]: item for item in rows}
        self.assertEqual(by_id["P1"]["num_occurrences_corrected"], 1)
        self.assertEqual(by_id["P1"]["num_occurrences_difference"], -1)
        self.assertEqual(by_id["P1"]["duplicate_occurrences_removed"], 1)
        self.assertEqual(by_id["P1"]["cross_id_occurrences_removed"], 0)
        self.assertEqual(by_id["P2"]["num_occurrences_corrected"], 0)
        self.assertEqual(by_id["P2"]["num_occurrences_difference"], -2)
        self.assertEqual(by_id["P2"]["duplicate_occurrences_removed"], 2)
        self.assertEqual(by_id["P2"]["cross_id_occurrences_removed"], 1)
        for item in rows:
            self.assertEqual(item["num_occurrences_before_fix"], 2)
            self.assertEqual(item["fallback_used"], 0)
            self.assertEqual(item["own_id_duplicate_occurrences_removed"], 0)
            self.assertEqual(item["cross_id_shared_physical_occurrences"], 1)

        audit = evaluation8.occurrence_weight_validation(rows)
        self.assertTrue(audit["all_passed"])
        self.assertEqual(audit["by_method_run"][0]["occurrence_weight_sum"], 1)
        self.assertEqual(
            audit["by_method_run"][0]["unique_physical_occurrence_total"],
            1,
        )
        evaluation8.assign_frequency_bands(rows)
        self.assertEqual(by_id["P2"]["frequency_band"], "Low")
        self.assertEqual(by_id["P1"]["frequency_band"], "Middle")

    def test_own_pattern_id_reconstruction_rejects_missing_eval_pattern_id(self) -> None:
        rows = [
            {
                **row("P1", 1, 0.1),
                "run": 1,
                "eval_pattern_id": "",
                "pattern_id": "legacy-id",
            }
        ]

        with self.assertRaisesRegex(ValueError, "has no eval_pattern_id"):
            evaluation8.attach_own_id_occurrences(rows, [], "exact", 1.0)

    def test_physical_occurrence_deduplication_uses_run_band_times_and_sequence(self) -> None:
        occurrence = SimpleNamespace(
            sequence=("状態1", "状態2"),
            start_time=datetime.fromisoformat("2020-01-01 07:00:00"),
            end_time=datetime.fromisoformat("2020-01-01 07:02:00"),
        )

        unique, removed = evaluation8.deduplicate_physical_occurrences(
            [occurrence, occurrence],
            run=1,
        )

        self.assertEqual(len(unique), 1)
        self.assertEqual(removed, 1)
        self.assertNotEqual(
            evaluation8.occurrence_physical_key(occurrence, 1),
            evaluation8.occurrence_physical_key(occurrence, 2),
        )

    def test_fixed_frequency_bands_use_configured_numeric_ranges(self) -> None:
        rows = [
            row("P0", 0, 0.1),
            row("P1", 1, 0.2),
            row("P9", 9, 0.3),
            row("P10", 10, 0.4),
            row("P99", 99, 0.5),
            row("P100", 100, 0.6),
            row("P1000", 1000, 0.7),
        ]
        edges = evaluation8.parse_fixed_frequency_bin_edges("0,1,10,100,1000")

        evaluation8.assign_frequency_bands(rows, "fixed", edges)

        by_id = {item["eval_pattern_id"]: item["frequency_band"] for item in rows}
        self.assertEqual(by_id["P0"], "0")
        self.assertEqual(by_id["P1"], "1-9")
        self.assertEqual(by_id["P9"], "1-9")
        self.assertEqual(by_id["P10"], "10-99")
        self.assertEqual(by_id["P99"], "10-99")
        self.assertEqual(by_id["P100"], "100-999")
        self.assertEqual(by_id["P1000"], "1000+")

    def test_method_summary_averages_per_run_after_run_specific_tertiles(self) -> None:
        rows = [
            {**row("P1", 1, 0.0), "run": 1},
            {**row("P2", 2, 0.5), "run": 1},
            {**row("P3", 3, 1.0), "run": 1},
            {**row("P1", 1, 0.6), "run": 2},
            {**row("P2", 2, 0.7), "run": 2},
            {**row("P3", 3, 0.8), "run": 2},
        ]

        evaluation8.assign_frequency_bands(rows)
        summaries = evaluation8.summaries_by_method_and_frequency_band(rows)

        low = next(item for item in summaries if item["frequency_band"] == "Low")
        self.assertEqual(low["num_runs"], 2)
        self.assertAlmostEqual(low["mean_multilabel_precision"], 0.3)
        self.assertGreater(low["std_multilabel_precision"], 0.0)

        by_run = evaluation8.run_summaries_by_frequency_band(rows)
        self.assertEqual(len(by_run), 6)
        self.assertTrue(all(item["num_evaluable_patterns"] == 1 for item in by_run))

    def test_fixed_band_aggregation_includes_empty_runs_in_count_columns(self) -> None:
        rows = [
            {**row("P1", 1, 0.2), "run": 1},
            {**row("P2", 10, 0.8), "run": 2},
        ]
        edges = evaluation8.parse_fixed_frequency_bin_edges("0,1,10,100")
        bands = evaluation8.frequency_bands_for_mode("fixed", edges)
        evaluation8.assign_frequency_bands(rows, "fixed", edges)

        summaries = evaluation8.summaries_by_frequency_band(rows, bands)
        one_to_nine = next(
            item for item in summaries if item["frequency_band"] == "1-9"
        )
        self.assertEqual(one_to_nine["num_runs"], 2)
        self.assertEqual(one_to_nine["num_runs_with_patterns"], 1)
        self.assertEqual(one_to_nine["num_patterns"], 0.5)
        self.assertAlmostEqual(one_to_nine["mean_multilabel_precision"], 0.2)

        by_run = evaluation8.run_summaries_by_frequency_band(rows, bands)
        self.assertEqual(len(by_run), 8)
        empty = next(
            item
            for item in by_run
            if item["run"] == 2 and item["frequency_band"] == "1-9"
        )
        self.assertEqual(empty["evaluation_status"], "empty_band")
        self.assertEqual(empty["num_patterns"], 0)
        self.assertIsNone(empty["mean_multilabel_f1"])

    def test_weight_sum_validation_uses_corrected_counts(self) -> None:
        rows = [
            {
                **row("P1", 2, 0.2),
                "run": 1,
                "num_occurrences_before_fix": 5,
                "num_occurrences_corrected": 2,
                "duplicate_occurrences_removed": 3,
                "own_id_duplicate_occurrences_removed": 0,
                "fallback_used": 0,
            },
            {
                **row("P2", 3, 0.3),
                "run": 1,
                "num_occurrences_before_fix": 6,
                "num_occurrences_corrected": 3,
                "duplicate_occurrences_removed": 3,
                "own_id_duplicate_occurrences_removed": 0,
                "fallback_used": 0,
            },
        ]

        audit = evaluation8.occurrence_weight_validation(rows)

        self.assertTrue(audit["all_passed"])
        self.assertEqual(audit["by_method_run"][0]["num_occurrences_corrected"], 5)
        self.assertEqual(audit["by_method_run"][0]["occurrence_weight_sum"], 5)

    def test_missing_count_is_reconstructed_per_time_band(self) -> None:
        source_rows = [row("P1_Morning", 1, 0.1)]
        source_rows[0].pop("num_occurrences")
        source_rows[0]["time_band"] = "Morning"
        source_rows[0]["sequence"] = "状態1->状態2"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            details = root / "evaluation6.csv"
            with details.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(source_rows[0]))
                writer.writeheader()
                writer.writerows(source_rows)
            state_series = root / "state_series.csv"
            state_series.write_text(
                "start_time,end_time,state_id\n"
                "2020-01-01 07:00:00,2020-01-01 07:01:00,状態1\n"
                "2020-01-01 07:01:00,2020-01-01 07:02:00,状態2\n"
                "2020-01-01 01:00:00,2020-01-01 01:01:00,状態1\n"
                "2020-01-01 01:01:00,2020-01-01 01:02:00,状態2\n",
                encoding="utf-8",
            )
            args = type(
                "Args", (),
                {"state_series": state_series, "match_mode": None, "max_skip_duration_minutes": None},
            )()

            loaded_rows, source = evaluation8.load_details(details, args)

        self.assertEqual(loaded_rows[0]["num_occurrences"], 1)
        self.assertIn("strict_own_pattern_id_from_state_series", source)

    def test_time_band_assignment_excludes_boundary_crossing_occurrence(self) -> None:
        rows = [
            {
                **row("P1_Morning", 1, 0.1),
                "run": 1,
                "time_band": "Morning",
                "num_occurrences_before_fix": 1,
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            state_series = Path(tmpdir) / "state_series.csv"
            state_series.write_text(
                "start_time,end_time,state_id\n"
                "2020-01-01 09:59:00,2020-01-01 10:00:00,状態1\n"
                "2020-01-01 10:00:00,2020-01-01 10:01:00,状態2\n",
                encoding="utf-8",
            )
            intervals = evaluation8.load_state_series_csv(state_series)
            evaluation8.attach_own_id_occurrences(rows, intervals, "exact", 1.0)

        self.assertEqual(rows[0]["num_occurrences_corrected"], 0)
        self.assertEqual(rows[0]["num_boundary_crossing_occurrences"], 1)
        self.assertEqual(rows[0]["num_boundary_crossing_occurrences_excluded"], 1)

    def test_main_writes_required_output_schema(self) -> None:
        source_rows = [
            row("P1", 1, 0.1),
            row("P2", 2, 0.2),
            row("P3", 3, 0.3),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            details = root / "evaluation6.csv"
            with details.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(source_rows[0]))
                writer.writeheader()
                writer.writerows(source_rows)
            state_series = root / "state_series.csv"
            state_series.write_text(
                "start_time,end_time,state_id\n"
                "2020-01-01 07:00:00,2020-01-01 07:01:00,状態1\n"
                "2020-01-01 07:01:00,2020-01-01 07:02:00,状態2\n",
                encoding="utf-8",
            )
            output_dir = root / "evaluation8"

            original_parse_args = evaluation8.parse_args
            evaluation8.parse_args = lambda: type(
                "Args", (),
                {
                    "analysis_scope": "comparison_30days",
                    "evaluation6_details": details,
                    "output_dir": output_dir,
                    "frequency_band_mode": "tertile",
                    "state_series": state_series,
                    "match_mode": None,
                    "max_skip_duration_minutes": None,
                },
            )()
            try:
                evaluation8.main()
            finally:
                evaluation8.parse_args = original_parse_args

            with (output_dir / "evaluation8_by_frequency_band_by_method.csv").open(encoding="utf-8", newline="") as f:
                headers = csv.DictReader(f).fieldnames
            self.assertEqual(headers, evaluation8.METHOD_SUMMARY_FIELDNAMES)
            self.assertTrue((output_dir / "evaluation8_by_frequency_band_by_run.csv").exists())
            payload = json.loads((output_dir / "evaluation8_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["frequency_band_mode"], "tertile_by_num_occurrences")
            self.assertTrue(payload["occurrence_weight_validation"]["all_passed"])

    def test_main_writes_fixed_range_summary_without_method_csv_for_proposed_scope(self) -> None:
        source_rows = [row("P1", 1, 0.1), row("P2", 10, 0.2), row("P3", 100, 0.3)]
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_dir = root / "evaluation8"
            original_parse_args = evaluation8.parse_args
            original_evaluate = evaluation8.evaluate_proposed_154days
            evaluation8.parse_args = lambda: type(
                "Args", (),
                {
                    "analysis_scope": "proposed_154days",
                    "evaluation6_details": None,
                    "output_dir": output_dir,
                    "frequency_band_mode": "fixed",
                    "fixed_frequency_bin_edges": "0,1,10,100",
                    "write_distribution_plots": False,
                },
            )()
            evaluation8.evaluate_proposed_154days = lambda args: (
                [{**item, "run": 1} for item in source_rows],
                "test",
                {},
            )
            try:
                evaluation8.main()
            finally:
                evaluation8.parse_args = original_parse_args
                evaluation8.evaluate_proposed_154days = original_evaluate

            self.assertFalse((output_dir / "evaluation8_by_frequency_band_by_method.csv").exists())
            payload = json.loads((output_dir / "evaluation8_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["frequency_band_mode"], "fixed_ranges_by_num_occurrences")
            self.assertEqual(payload["frequency_bands"], ["0", "1-9", "10-99", "100+"])

    def test_main_both_mode_evaluates_input_once_and_writes_two_subdirectories(self) -> None:
        source_rows = [row("P1", 1, 0.1), row("P2", 10, 0.2), row("P3", 100, 0.3)]
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "evaluation8"
            original_parse_args = evaluation8.parse_args
            original_evaluate = evaluation8.evaluate_proposed_154days
            calls = 0

            def fake_evaluate(args):
                nonlocal calls
                calls += 1
                return [{**item, "run": 1} for item in source_rows], "test", {}

            evaluation8.parse_args = lambda: type(
                "Args", (),
                {
                    "analysis_scope": "proposed_154days",
                    "evaluation6_details": None,
                    "output_dir": output_dir,
                    "frequency_band_mode": "both",
                    "fixed_frequency_bin_edges": "0,1,10,100",
                    "write_distribution_plots": False,
                },
            )()
            evaluation8.evaluate_proposed_154days = fake_evaluate
            try:
                evaluation8.main()
            finally:
                evaluation8.parse_args = original_parse_args
                evaluation8.evaluate_proposed_154days = original_evaluate

            self.assertEqual(calls, 1)
            tertile_summary = json.loads(
                (output_dir / "tertile" / "evaluation8_summary.json").read_text(encoding="utf-8")
            )
            fixed_summary = json.loads(
                (output_dir / "fixed" / "evaluation8_summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual(tertile_summary["frequency_band_mode"], "tertile_by_num_occurrences")
            self.assertEqual(fixed_summary["frequency_band_mode"], "fixed_ranges_by_num_occurrences")
            self.assertFalse(
                (output_dir / "tertile" / "evaluation8_by_frequency_band_by_method.csv").exists()
            )
            self.assertFalse(
                (output_dir / "fixed" / "evaluation8_by_frequency_band_by_method.csv").exists()
            )

    def test_proposed_154day_scope_evaluates_proposed_patterns_directly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            patterns = root / "patterns.json"
            patterns.write_text(
                json.dumps(
                    [
                        {
                            "pattern_id": "P1",
                            "パターン名": "meal pattern",
                            "遷移のパターン": ["状態1", "状態2"],
                            "ADL系列ラベル": ["Meal"],
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            state_series = root / "state_series.csv"
            state_series.write_text(
                "start_time,end_time,state_id\n"
                "2020-01-01 07:00:00,2020-01-01 07:01:00,状態1\n"
                "2020-01-01 07:01:00,2020-01-01 07:02:00,状態2\n",
                encoding="utf-8",
            )
            adl_intervals = root / "adl_intervals.csv"
            adl_intervals.write_text(
                "start_time,end_time,adl_category\n"
                "2020-01-01 07:00:00,2020-01-01 07:02:00,Meal\n",
                encoding="utf-8",
            )
            args = type(
                "Args", (),
                {
                    "patterns_proposed": patterns,
                    "patterns_proposed_template": None,
                    "runs": 1,
                    "state_series": state_series,
                    "labeled_casas": None,
                    "adl_intervals": adl_intervals,
                    "wake_window_minutes": 30.0,
                    "missing_pred_label": "Ambiguous",
                    "unknown_pred_label": "Other",
                    "match_mode": "exact",
                    "max_skip_duration_minutes": 1.0,
                    "min_overlap_ratio_for_true_label": 0.1,
                    "no_overlap_label": "Ambiguous",
                },
            )()

            rows, source, inputs = evaluation8.evaluate_proposed_154days(args)

        self.assertEqual(source, "strict_own_pattern_id_from_proposed_154day_state_series")
        self.assertEqual(rows[0]["method"], "proposed")
        self.assertEqual(rows[0]["num_occurrences"], 1)
        self.assertEqual(inputs["evaluation6_summaries_by_run"][0]["num_patterns"], 1)

    def test_proposed_scope_clips_state_and_adl_intervals_to_requested_days(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            patterns = root / "patterns.json"
            patterns.write_text(
                json.dumps(
                    [
                        {
                            "pattern_id": "P1",
                            "パターン名": "meal pattern",
                            "遷移のパターン": ["状態1", "状態2"],
                            "ADL系列ラベル": ["Meal"],
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            state_series = root / "state_series.csv"
            state_series.write_text(
                "start_time,end_time,state_id\n"
                "2020-01-01 07:00:00,2020-01-01 07:01:00,状態1\n"
                "2020-01-01 07:01:00,2020-01-01 07:02:00,状態2\n"
                "2020-01-02 07:00:00,2020-01-02 07:01:00,状態1\n"
                "2020-01-02 07:01:00,2020-01-02 07:02:00,状態2\n",
                encoding="utf-8",
            )
            adl_intervals = root / "adl_intervals.csv"
            adl_intervals.write_text(
                "start_time,end_time,adl_category\n"
                "2020-01-01 07:00:00,2020-01-01 07:02:00,Meal\n"
                "2020-01-02 07:00:00,2020-01-02 07:02:00,Meal\n",
                encoding="utf-8",
            )
            args = type(
                "Args",
                (),
                {
                    "patterns_proposed": patterns,
                    "patterns_proposed_template": None,
                    "runs": 1,
                    "days": 1,
                    "state_series": state_series,
                    "labeled_casas": None,
                    "adl_intervals": adl_intervals,
                    "wake_window_minutes": 30.0,
                    "missing_pred_label": "Ambiguous",
                    "unknown_pred_label": "Other",
                    "match_mode": "exact",
                    "max_skip_duration_minutes": 1.0,
                    "min_overlap_ratio_for_true_label": 0.1,
                    "no_overlap_label": "Ambiguous",
                },
            )()

            rows, _, inputs = evaluation8.evaluate_proposed_154days(args)

        self.assertEqual(rows[0]["num_occurrences_corrected"], 1)
        self.assertEqual(inputs["source_state_interval_count"], 4)
        self.assertEqual(inputs["effective_state_interval_count"], 2)
        self.assertEqual(inputs["source_adl_interval_count"], 2)
        self.assertEqual(inputs["effective_adl_interval_count"], 1)
        self.assertEqual(inputs["effective_period_start"], "2020-01-01 00:00:00")
        self.assertEqual(inputs["effective_period_end_exclusive"], "2020-01-02 00:00:00")


if __name__ == "__main__":
    unittest.main()
