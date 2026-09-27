from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from scripts import evaluate_6_compare_adl_interpretation_set as evaluation6
from scripts import evaluate_7_parameter_sensitivity_adl_interpretation as evaluation7
from src.behavior_pattern_mining.evaluation.adl import ADLInterval, StateInterval
from src.behavior_pattern_mining.evaluation.period_splits import clip_intervals, resolve_split


START = datetime(2020, 1, 1)


def write_state_series(path: Path) -> None:
    rows = [
        (START, START + timedelta(minutes=1), "anchor"),
        (START + timedelta(days=14, hours=7), START + timedelta(days=14, hours=7, minutes=5), "状態1"),
        (START + timedelta(days=14, hours=7, minutes=5), START + timedelta(days=14, hours=7, minutes=10), "状態2"),
        (START + timedelta(days=154, hours=7), START + timedelta(days=154, hours=7, minutes=5), "状態1"),
        (START + timedelta(days=154, hours=7, minutes=5), START + timedelta(days=154, hours=7, minutes=10), "状態2"),
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["start_time", "end_time", "state_id"])
        writer.writeheader()
        for start, end, state_id in rows:
            writer.writerow({"start_time": start, "end_time": end, "state_id": state_id})


def write_adl_intervals(path: Path, test_label: str = "Meal", validation_label: str = "Wake-up") -> None:
    rows = [
        (START, START + timedelta(minutes=1), "Housekeeping", "Housework"),
        (START + timedelta(days=14, hours=7), START + timedelta(days=14, hours=7, minutes=10), "Bed_to_Toilet", validation_label),
        (START + timedelta(days=154, hours=7), START + timedelta(days=154, hours=7, minutes=10), "Eating", test_label),
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["start_time", "end_time", "raw_label", "adl_category"])
        writer.writeheader()
        for start, end, raw_label, category in rows:
            writer.writerow({"start_time": start, "end_time": end, "raw_label": raw_label, "adl_category": category})


def write_patterns(path: Path, labels: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            [{
                "pattern_id": "P001",
                "sequence": ["状態1", "状態2"],
                "time_band_interpretations": {
                    "Morning": {
                        "パターン名": "test pattern",
                        "ADL系列ラベル": labels,
                        "解釈の根拠": "test",
                    }
                },
            }],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


class EvaluationHoldoutPeriodTests(unittest.TestCase):
    def test_holdout_clips_a_boundary_interval_without_double_counting(self) -> None:
        boundary = START + timedelta(days=154)
        source = [
            StateInterval(START, START + timedelta(days=220), "state"),
            ADLInterval(boundary - timedelta(minutes=1), boundary + timedelta(minutes=1), "Eating", "Meal"),
        ]
        split = resolve_split(
            source,
            split_mode="holdout",
            generation_days=14,
            validation_start_day=15,
            validation_end_day=154,
            test_start_day=155,
            test_end_day=220,
        )
        validation_start, validation_end = split.scoring_period("validation")
        test_start, test_end = split.scoring_period("test")

        self.assertEqual(split.generation_start, START)
        self.assertEqual(split.generation_end, START + timedelta(days=14))
        self.assertEqual(validation_start, START + timedelta(days=14))
        self.assertEqual(validation_end, boundary)
        self.assertEqual(test_start, boundary)
        self.assertEqual(test_end, START + timedelta(days=220))
        validation = clip_intervals(source, validation_start, validation_end)
        test = clip_intervals(source, test_start, test_end)
        validation_adl = [item for item in validation if isinstance(item, ADLInterval)]
        test_adl = [item for item in test if isinstance(item, ADLInterval)]
        self.assertEqual(validation_adl[0].end_time, boundary)
        self.assertEqual(test_adl[0].start_time, boundary)
        self.assertEqual(
            (validation_adl[0].end_time - validation_adl[0].start_time)
            + (test_adl[0].end_time - test_adl[0].start_time),
            timedelta(minutes=2),
        )

    def test_legacy_scores_the_full_available_period(self) -> None:
        source = [StateInterval(START, START + timedelta(days=220), "state")]
        split = resolve_split(
            source,
            split_mode="legacy",
            generation_days=14,
            validation_start_day=15,
            validation_end_day=154,
            test_start_day=155,
            test_end_day=220,
        )
        self.assertEqual(split.scoring_period("validation"), (START, START + timedelta(days=220)))
        self.assertEqual(split.scoring_period("test"), (START, START + timedelta(days=220)))

    def test_evaluation7_uses_validation_only_and_writes_reusable_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state_series = root / "state_series.csv"
            adl_intervals = root / "adl.csv"
            write_state_series(state_series)
            write_adl_intervals(adl_intervals, test_label="Meal")
            for n_states, label in ((10, "Wake-up"), (20, "Meal")):
                write_patterns(root / f"patterns_{n_states}_1_1.json", [label])

            argv = [
                "evaluation7", "--n-states-list", "10,20", "--hamming-thresholds", "1",
                "--runs", "1", "--patterns-template", str(root / "patterns_{n_states}_{hamming}_{run}.json"),
                "--state-series-template", str(state_series), "--adl-intervals", str(adl_intervals),
                "--labeled-casas", str(root / "missing.txt"), "--output-dir", str(root / "first"),
            ]
            with patch.object(sys, "argv", argv):
                args = evaluation7.parse_args()
            first = evaluation7.evaluate_conditions(args)
            evaluation7.write_outputs(args, first)

            # Only Day 155 is changed.  A correct validation split keeps the
            # selected condition and validation metric unchanged.
            write_adl_intervals(adl_intervals, test_label="Relax")
            argv[-1] = str(root / "second")
            with patch.object(sys, "argv", argv):
                changed_args = evaluation7.parse_args()
            changed = evaluation7.evaluate_conditions(changed_args)

            self.assertEqual(first["best_condition"]["n_states"], 10)
            self.assertEqual(changed["best_condition"]["n_states"], 10)
            self.assertEqual(
                first["best_condition"]["selection_metric_value"],
                changed["best_condition"]["selection_metric_value"],
            )
            manifest = json.loads(
                (args.output_dir / "evaluation7_best_condition_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual((manifest["K"], manifest["h"]), (10, 1))
            self.assertEqual(manifest["sensor_representation"], "individual")
            self.assertEqual(manifest["evaluation_role"], "validation")

    def test_evaluation6_uses_test_only_and_accepts_matching_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state_series = root / "state_series.csv"
            adl_intervals = root / "adl.csv"
            proposed = root / "proposed.json"
            direct = root / "direct.json"
            write_state_series(state_series)
            write_adl_intervals(adl_intervals, validation_label="Wake-up")
            write_patterns(proposed, ["Meal"])
            write_patterns(direct, ["Meal"])

            def run(output_dir: Path) -> float:
                argv = [
                    "evaluation6", "--patterns-proposed", str(proposed), "--patterns-direct", str(direct),
                    "--state-series", str(state_series), "--adl-intervals", str(adl_intervals),
                    "--output-dir", str(output_dir), "--sensor-representation", "individual",
                    "--n-states", "10", "--hamming-threshold", "1",
                ]
                with patch.object(sys, "argv", argv):
                    evaluation6.main()
                payload = json.loads((output_dir / "evaluation6_comparison_summary.json").read_text(encoding="utf-8"))
                return payload["methods"]["proposed"]["mean_multilabel_f1"]

            first_f1 = run(root / "first")
            write_adl_intervals(adl_intervals, validation_label="Relax")
            second_f1 = run(root / "second")
            self.assertEqual(first_f1, 1.0)
            self.assertEqual(second_f1, 1.0)

            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps({"n_states": 10, "hamming_threshold": 1, "sensor_representation": "individual", "split_mode": "holdout"}),
                encoding="utf-8",
            )
            with patch.object(sys, "argv", ["evaluation6", "--best-condition-manifest", str(manifest)]):
                parsed = evaluation6.parse_args()
            self.assertEqual((parsed.n_states, parsed.hamming_threshold), (10, 1))

            manifest.write_text(
                json.dumps({"n_states": 10, "hamming_threshold": 1, "sensor_representation": "room", "split_mode": "holdout"}),
                encoding="utf-8",
            )
            with patch.object(sys, "argv", [
                "evaluation6", "--best-condition-manifest", str(manifest),
                "--sensor-representation", "individual",
            ]):
                with self.assertRaisesRegex(ValueError, "sensor-representation"):
                    evaluation6.parse_args()

    def test_evaluation6_manifest_resolves_the_complete_formal_condition_and_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = Path(tmpdir) / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "K": 20,
                        "h": 1,
                        "sensor_representation": "individual",
                        "generation_days": 14,
                        "split_mode": "holdout",
                        "validation_start_day": 15,
                        "validation_end_day": 154,
                        "test_start_day": 155,
                        "test_end_day": 220,
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(sys, "argv", ["evaluation6", "--best-condition-manifest", str(manifest)]):
                args = evaluation6.parse_args()

        self.assertEqual((args.n_states, args.hamming_threshold), (20, 1))
        self.assertEqual(args.sensor_representation, "individual")
        self.assertEqual(args.generation_days, 14)
        self.assertIn("aruba_individual_20_1_14days", str(args.patterns_proposed))
        self.assertIn("llm_direct_aruba_individual_20_1_14days_time_split", str(args.patterns_direct))
        self.assertIn("6_adl_evaluation_aruba_individual_20_1_14days", str(args.state_series))
        self.assertIn("6_adl_match_individual_holdout_test_direct_time_split", str(args.output_dir))

    def test_evaluation6_manifest_rejects_condition_and_artifact_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "n_states": 20,
                        "hamming_threshold": 1,
                        "sensor_representation": "individual",
                        "generation_days": 14,
                        "split_mode": "holdout",
                    }
                ),
                encoding="utf-8",
            )
            conflict_cases = [
                (["--days", "10"], "days"),
                (["--n-states", "15"], "n-states"),
                (["--hamming-threshold", "0"], "hamming-threshold"),
                (["--sensor-representation", "room"], "sensor-representation"),
                (["--test-start-day", "100"], "test-start-day"),
                (["--patterns-proposed", str(root / "aruba_individual_15_0_14days" / "wrong.json")], "artifact path"),
            ]
            for extra, message in conflict_cases:
                with patch.object(sys, "argv", ["evaluation6", "--best-condition-manifest", str(manifest), *extra]):
                    with self.assertRaisesRegex(ValueError, message):
                        evaluation6.parse_args()

            with patch.object(sys, "argv", ["evaluation6", "--best-condition-manifest", str(manifest)]):
                expected = evaluation6.parse_args().patterns_proposed
            with patch.object(sys, "argv", [
                "evaluation6", "--best-condition-manifest", str(manifest),
                "--patterns-proposed", str(expected),
            ]):
                self.assertEqual(evaluation6.parse_args().patterns_proposed, expected)

    def test_evaluation6_manifest_reports_all_missing_required_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = Path(tmpdir) / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "K": 999,
                        "h": 9,
                        "sensor_representation": "individual",
                        "generation_days": 14,
                        "split_mode": "holdout",
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(sys, "argv", ["evaluation6", "--best-condition-manifest", str(manifest)]):
                with self.assertRaisesRegex(FileNotFoundError, "(?s)state_series.*proposed run 1.*direct run 1"):
                    evaluation6.main()


if __name__ == "__main__":
    unittest.main()
