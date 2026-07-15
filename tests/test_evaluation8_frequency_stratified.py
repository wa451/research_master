from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_8_frequency_stratified_adl_consistency.py"
SPEC = importlib.util.spec_from_file_location("evaluation8", SCRIPT_PATH)
assert SPEC and SPEC.loader
evaluation8 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluation8)


def row(pattern_id: str, occurrences: int, precision: float) -> dict[str, object]:
    return {
        "method": "proposed",
        "eval_pattern_id": pattern_id,
        "num_occurrences": occurrences,
        "exact_set_match": 0,
        "jaccard": precision / 2,
        "multilabel_precision": precision,
        "multilabel_recall": precision / 2,
        "multilabel_f1": precision / 3,
    }


class Evaluation8FrequencyStratifiedTests(unittest.TestCase):
    def test_default_output_directories_follow_analysis_scope(self) -> None:
        self.assertEqual(evaluation8.default_output_dir("comparison_30days").name, "8_vs_llm")
        self.assertEqual(evaluation8.default_output_dir("proposed_154days").name, "8_proposed")

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
        self.assertIn("reconstructed_from_state_series", source)

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
            output_dir = root / "evaluation8"

            original_parse_args = evaluation8.parse_args
            evaluation8.parse_args = lambda: type(
                "Args", (),
                {
                    "analysis_scope": "comparison_30days",
                    "evaluation6_details": details,
                    "output_dir": output_dir,
                    "frequency_band_mode": "tertile",
                },
            )()
            try:
                evaluation8.main()
            finally:
                evaluation8.parse_args = original_parse_args

            with (output_dir / "evaluation8_by_frequency_band_by_method.csv").open(encoding="utf-8", newline="") as f:
                headers = csv.DictReader(f).fieldnames
            self.assertEqual(headers, evaluation8.METHOD_SUMMARY_FIELDNAMES)
            payload = json.loads((output_dir / "evaluation8_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["frequency_band_mode"], "tertile_by_num_occurrences")

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

        self.assertEqual(source, "computed_from_proposed_154day_inputs")
        self.assertEqual(rows[0]["method"], "proposed")
        self.assertEqual(rows[0]["num_occurrences"], 1)
        self.assertEqual(inputs["evaluation6_summaries_by_run"][0]["num_patterns"], 1)


if __name__ == "__main__":
    unittest.main()
