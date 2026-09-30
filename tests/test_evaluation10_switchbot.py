"""Evaluation 10 input, split, output-contract, and dashboard tests."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from app.command_builder import build_evaluation10_steps
from app.streamlit_app import batch_target_steps
from scripts.evaluate_10_switchbot import build_parser, main, resume_extract
from src.behavior_pattern_mining.evaluation.evaluation10_switchbot import (
    DETAIL_COLUMNS,
    FORMAL_EVALUATION7_BEST_CONDITION_MANIFEST,
    RUN_SUMMARY_COLUMNS,
    SUMMARY_COLUMNS,
    build_frequency_patterns,
    choose_split,
    evaluate,
    file_sha256,
    llm_patterns_path,
    prepare,
)


class Evaluation10SwitchBotTests(unittest.TestCase):
    def test_cli_default_uses_fixed_formal_evaluation7_manifest(self):
        args = build_parser().parse_args(["--snapshot", "data/switchbot/example"])
        self.assertEqual(
            args.eval7_best_condition_manifest,
            FORMAL_EVALUATION7_BEST_CONDITION_MANIFEST,
        )

    def make_eval7_manifest(self, root: Path, *, n_states: int = 8, hamming: int = 0) -> Path:
        path = root / "evaluation7_best_condition_manifest.json"
        path.write_text(
            json.dumps(
                {
                    "n_states": n_states,
                    "hamming_threshold": hamming,
                    "sensor_representation": "individual",
                    "generation_days": 14,
                    "split_mode": "holdout",
                }
            ),
            encoding="utf-8",
        )
        return path

    def make_snapshot(self, root: Path, *, test_variant: bool = False) -> Path:
        snapshot = root / "2026-09-01_2026-09-05"
        snapshot.mkdir(parents=True)
        rows = []
        for day in range(1, 5):
            date = f"2026-09-{day:02d}"
            rows.extend(
                [
                    [date, "08:00:00.000000", "M001", "ON"],
                    [date, "08:10:00.000000", "D001", "OPEN"],
                    [date, "08:20:00.000000", "M001", "OFF"],
                    [date, "08:30:00.000000", "D001", "CLOSE"],
                ]
            )
        if test_variant:
            rows.extend(
                [
                    ["2026-09-04", "09:00:00.000000", "X999", "ON"],
                    ["2026-09-04", "09:01:00.000000", "X999", "OFF"],
                ]
            )
        rows.sort(key=lambda row: (row[0], row[1]))
        with (snapshot / "events.csv").open("w", encoding="utf-8", newline="") as handle:
            csv.writer(handle).writerows(rows)
        (snapshot / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "format": "casas_csv",
                    "columns": ["date", "time", "sensor", "value"],
                    "header": False,
                    "timezone": "Asia/Tokyo",
                    "source": {
                        "system": "switchbot_logger",
                        "firestore_project_id": "test-project",
                        "raw_collection": "raw_events",
                        "control_collection": "control_events",
                        "start": "2026-09-01T00:00:00+09:00",
                        "end_exclusive": "2026-09-05T00:00:00+09:00",
                    },
                    "conversion_report": {
                        "output_events": len(rows),
                        "duplicate_events_removed": 0,
                    },
                }
            ),
            encoding="utf-8",
        )
        return snapshot

    def prepare_snapshot(self, snapshot: Path, output: Path) -> dict:
        return prepare(
            snapshot_dir=snapshot,
            output_dir=output,
            split_at=None,
            train_ratio=0.5,
            n_states=8,
            hamming_threshold=0,
            smoothing_window_sec=0,
            sampling_seconds=60,
            min_sequence_length=2,
            max_sequence_length=4,
            min_train_occurrences=2,
            top_k_per_mode=20,
        )

    def test_prepare_uses_train_only_and_evaluate_writes_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = self.make_snapshot(root, test_variant=True)
            output = root / "intermediate"
            results = root / "results"
            preparation = self.prepare_snapshot(snapshot, output)

            self.assertEqual(preparation["split"]["train_days"], 2)
            self.assertEqual(preparation["split"]["test_days"], 2)
            self.assertEqual(preparation["counts"]["test_only_sensors_ignored"], 1)
            self.assertNotIn("X999", (output / "state_table.tsv").read_text(encoding="utf-8"))
            self.assertTrue((output / "network/state_transition_Morning.json").is_file())
            self.assertTrue((output / "frequency_patterns.json").is_file())

            payload = evaluate(
                output_dir=output,
                results_dir=results,
                method="both",
            )
            rows = {row["method"]: row for row in payload["summary"]}
            self.assertEqual(rows["frequency"]["status"], "complete")
            self.assertGreater(rows["frequency"]["pattern_count_mean"], 0)
            self.assertGreater(rows["frequency"]["test_supported_pattern_fraction_mean"], 0)
            self.assertEqual(rows["llm"]["status"], "incomplete")
            with (results / "evaluation10_summary.csv").open(encoding="utf-8") as handle:
                self.assertEqual(next(csv.reader(handle)), SUMMARY_COLUMNS)
            with (results / "evaluation10_summary_by_run.csv").open(encoding="utf-8") as handle:
                self.assertEqual(next(csv.reader(handle)), RUN_SUMMARY_COLUMNS)
            with (results / "evaluation10_pattern_details.csv").open(encoding="utf-8") as handle:
                self.assertEqual(next(csv.reader(handle)), DETAIL_COLUMNS)

    def test_test_only_changes_do_not_change_training_state_table(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self.make_snapshot(root / "base")
            changed = self.make_snapshot(root / "changed", test_variant=True)
            output_base = root / "output_base"
            output_changed = root / "output_changed"
            self.prepare_snapshot(base, output_base)
            self.prepare_snapshot(changed, output_changed)
            self.assertEqual(
                (output_base / "state_table.tsv").read_text(encoding="utf-8"),
                (output_changed / "state_table.tsv").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                file_sha256(output_base / "frequency_patterns.json"),
                file_sha256(output_changed / "frequency_patterns.json"),
            )

    def test_changed_input_is_rejected_after_prepare(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = self.make_snapshot(root)
            output = root / "output"
            self.prepare_snapshot(snapshot, output)
            with (snapshot / "events.csv").open("a", encoding="utf-8") as handle:
                handle.write("2026-09-04,10:00:00.000000,M001,ON\n")
            with self.assertRaisesRegex(ValueError, "prepared input changed"):
                evaluate(output_dir=output, results_dir=root / "results", method="frequency")

    def test_manifest_row_count_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = self.make_snapshot(root)
            manifest_path = snapshot / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["conversion_report"]["output_events"] += 1
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "output_events"):
                self.prepare_snapshot(snapshot, root / "output")

    def test_llm_cache_path_changes_with_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = self.make_snapshot(root)
            output = root / "output"
            preparation = self.prepare_snapshot(snapshot, output)
            first = llm_patterns_path(output, preparation)
            network = output / "network/state_transition_Morning.json"
            payload = json.loads(network.read_text(encoding="utf-8"))
            payload["fingerprint_test"] = True
            network.write_text(json.dumps(payload), encoding="utf-8")
            second = llm_patterns_path(output, preparation)
            self.assertNotEqual(first.parent, second.parent)

    def test_cli_dry_run_and_api_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = self.make_snapshot(root)
            output = root / "untouched"
            self.assertEqual(
                main(["--snapshot", str(snapshot), "--output-dir", str(output), "--dry-run"]),
                0,
            )
            self.assertFalse(output.exists())
            self.assertEqual(
                main(["--snapshot", str(snapshot), "--stage", "extract"]),
                2,
            )

    def test_cli_runs_frequency_pipeline_end_to_end(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = self.make_snapshot(root)
            output = root / "output"
            results = root / "results"
            eval7_manifest = self.make_eval7_manifest(root)
            return_code = main(
                [
                    "--snapshot",
                    str(snapshot),
                    "--output-dir",
                    str(output),
                    "--results-dir",
                    str(results),
                    "--method",
                    "frequency",
                    "--eval7-best-condition-manifest",
                    str(eval7_manifest),
                    "--train-ratio",
                    "0.5",
                    "--sampling-seconds",
                    "60",
                    "--smoothing-window-sec",
                    "0",
                    "--n-states",
                    "8",
                ]
            )
            self.assertEqual(return_code, 0)
            self.assertTrue((output / "preparation.json").is_file())
            self.assertTrue((results / "evaluation10_summary.json").is_file())
            self.assertTrue((results / "evaluation10_manifest.json").is_file())

    def test_dashboard_commands_keep_api_opt_in(self):
        settings = {
            "runner": "uv run python",
            "snapshot": "data/switchbot/2026-09-01_2026-09-08",
            "output_dir": "output/10_switchbot/2026-09-01_2026-09-08",
            "results_dir": "results/10_switchbot/2026-09-01_2026-09-08",
            "eval7_best_condition_manifest": "results/gpt-5.6-sol/7_param_search_14d_5runs_individual_holdout/evaluation7_best_condition_manifest.json",
            "split_at": "",
            "train_ratio": 0.7,
            "smoothing_window_sec": 5,
            "sampling_seconds": 1,
            "min_sequence_length": 2,
            "max_sequence_length": 4,
            "min_train_occurrences": 2,
            "top_k_per_mode": 20,
            "method": "both",
            "runs": 5,
            "allow_api": False,
        }
        steps = build_evaluation10_steps(settings)
        self.assertEqual([step.step_id for step in steps], ["eval10_prepare", "eval10_evaluate"])
        self.assertTrue(all("--allow-api" not in step.command for step in steps))
        enabled = build_evaluation10_steps({**settings, "allow_api": True})
        self.assertEqual([step.step_id for step in enabled], ["eval10_prepare", "eval10_extract", "eval10_evaluate"])
        self.assertIn("--allow-api", enabled[1].command)

    def test_dashboard_batch_skips_completed_preparation_before_resuming_extract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = {
                "runner": "uv run python",
                "snapshot": root / "snapshot",
                "output_dir": root / "output",
                "results_dir": root / "results",
                "eval7_best_condition_manifest": root / "evaluation7.json",
                "split_at": "",
                "train_ratio": 0.7,
                "smoothing_window_sec": 5,
                "sampling_seconds": 1,
                "min_sequence_length": 2,
                "max_sequence_length": 4,
                "min_train_occurrences": 2,
                "top_k_per_mode": 20,
                "method": "llm",
                "runs": 5,
                "allow_api": True,
            }
            steps = build_evaluation10_steps(settings)
            for path in steps[0].expected_outputs:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            targets = batch_target_steps(steps, "不足ファイル生成 + 評価本体")
            self.assertEqual(
                [step.step_id for step in targets],
                ["eval10_extract", "eval10_evaluate"],
            )

    def test_cli_rejects_k_or_h_conflicting_with_eval7_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = self.make_snapshot(root)
            manifest = self.make_eval7_manifest(root)
            self.assertEqual(
                main([
                    "--snapshot", str(snapshot),
                    "--eval7-best-condition-manifest", str(manifest),
                    "--n-states", "9", "--dry-run",
                ]),
                2,
            )
            self.assertEqual(
                main([
                    "--snapshot", str(snapshot),
                    "--eval7-best-condition-manifest", str(manifest),
                    "--hamming-threshold", "1", "--dry-run",
                ]),
                2,
            )

    def test_frequency_patterns_keep_time_band_as_candidate_identity(self):
        patterns = build_frequency_patterns(
            [
                {"date": "2026-09-01", "time_band": "Morning", "sequence": ["状態1", "状態2", "状態1"]},
                {"date": "2026-09-01", "time_band": "Daytime", "sequence": ["状態1", "状態2", "状態1"]},
            ],
            min_length=2,
            max_length=2,
            min_occurrences=1,
            top_k_per_mode=20,
        )
        same_sequence = [item for item in patterns if item["sequence"] == ["状態1", "状態2"]]
        self.assertEqual(len(same_sequence), 2)
        self.assertEqual({item["time_bands"][0] for item in same_sequence}, {"Morning", "Daytime"})

    def test_choose_split_is_chronological_and_at_midnight(self):
        split = choose_split(
            pd.Timestamp("2026-09-01"), pd.Timestamp("2026-09-11"), None, 0.7
        )
        self.assertEqual(split, pd.Timestamp("2026-09-08T00:00:00"))

    def test_llm_paths_are_run_specific(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preparation = self.prepare_snapshot(self.make_snapshot(root), root / "output")
            paths = [llm_patterns_path(root / "output", preparation, root / "results", run) for run in range(1, 6)]
            self.assertEqual(len(set(paths)), 5)
            self.assertTrue(all(path.name.endswith(f"_{run}.json") for run, path in enumerate(paths, start=1)))

    def test_cli_resume_extract_only_generates_missing_runs_without_overwriting_complete_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            preparation = self.prepare_snapshot(self.make_snapshot(root), output)
            results = root / "results"
            completed = [
                llm_patterns_path(output, preparation, results, run)
                for run in (1, 2)
            ]
            for run, path in enumerate(completed, start=1):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"completed run {run}", encoding="utf-8")

            def write_missing_runs(**kwargs):
                self.assertEqual(kwargs["run_ids"], [3, 4, 5])
                for run in kwargs["run_ids"]:
                    path = llm_patterns_path(output, preparation, results, run)
                    path.write_text(f"new run {run}", encoding="utf-8")

            with patch(
                "scripts.evaluate_10_switchbot.pattern_extractor.main",
                side_effect=write_missing_runs,
            ) as extractor:
                paths = resume_extract(
                    output_dir=output,
                    results_dir=results,
                    runs=5,
                )

            self.assertEqual([path.name for path in paths], [
                "llm_sequences_modes_8_0_2days_1.json",
                "llm_sequences_modes_8_0_2days_2.json",
                "llm_sequences_modes_8_0_2days_3.json",
                "llm_sequences_modes_8_0_2days_4.json",
                "llm_sequences_modes_8_0_2days_5.json",
            ])
            self.assertEqual(completed[0].read_text(encoding="utf-8"), "completed run 1")
            self.assertEqual(completed[1].read_text(encoding="utf-8"), "completed run 2")
            self.assertEqual(extractor.call_count, 1)

    def test_llm_run_summary_uses_mean_and_sample_sd(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = self.make_snapshot(root)
            output = root / "output"
            preparation = self.prepare_snapshot(snapshot, output)
            results = root / "results"
            for run in range(1, 6):
                path = llm_patterns_path(output, preparation, results, run)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps([{
                    "pattern_id": f"L{run}", "sequence": ["状態1", "状態2"], "time_bands": ["Morning"]
                }]), encoding="utf-8")
            payload = evaluate(output_dir=output, results_dir=results, method="llm", runs=5)
            row = payload["summary"][0]
            self.assertEqual(row["complete_runs"], 5)
            self.assertEqual(row["requested_runs"], 5)
            self.assertIsNotNone(row["test_supported_pattern_fraction_mean"])
            self.assertIsNotNone(row["test_supported_pattern_fraction_sd"])

    def test_evaluate_does_not_overwrite_existing_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            self.prepare_snapshot(self.make_snapshot(root), output)
            results = root / "results"
            evaluate(output_dir=output, results_dir=results, method="frequency")
            with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
                evaluate(output_dir=output, results_dir=results, method="frequency")

    def test_prepare_does_not_overwrite_existing_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = self.make_snapshot(root)
            output = root / "output"
            self.prepare_snapshot(snapshot, output)
            with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
                self.prepare_snapshot(snapshot, output)

    def test_preparation_records_and_locks_evaluation7_condition(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = self.make_snapshot(root)
            condition = self.make_eval7_manifest(root)
            output = root / "output"
            preparation = prepare(
                snapshot_dir=snapshot,
                output_dir=output,
                split_at=None,
                train_ratio=0.5,
                n_states=8,
                hamming_threshold=0,
                smoothing_window_sec=0,
                sampling_seconds=60,
                min_sequence_length=2,
                max_sequence_length=4,
                min_train_occurrences=2,
                top_k_per_mode=20,
                evaluation7_manifest=condition,
            )
            self.assertEqual(preparation["evaluation7_condition"]["sha256"], file_sha256(condition))
            condition.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Evaluation 7 condition changed"):
                evaluate(output_dir=output, results_dir=root / "results", method="frequency")

    def test_llm_patterns_are_scored_once_per_declared_time_band(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            self.prepare_snapshot(self.make_snapshot(root), output)
            patterns = root / "patterns.json"
            patterns.write_text(json.dumps([{
                "pattern_id": "L001",
                "sequence": ["状態1", "状態2"],
                "time_bands": ["Morning", "Daytime"],
            }]), encoding="utf-8")
            evaluate(
                output_dir=output,
                results_dir=root / "results",
                method="llm",
                llm_patterns=patterns,
            )
            with (root / "results/evaluation10_pattern_details.csv").open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual({row["time_band"] for row in rows}, {"Morning", "Daytime"})

    def test_duplicate_patterns_do_not_double_count_recurrence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            self.prepare_snapshot(self.make_snapshot(root), output)
            patterns = root / "patterns.json"
            patterns.write_text(json.dumps([
                {"pattern_id": "L001", "sequence": ["状態1", "状態2"], "time_bands": ["Morning"]},
                {"pattern_id": "L002", "sequence": ["状態1", "状態2"], "time_bands": ["Morning"]},
            ]), encoding="utf-8")
            payload = evaluate(
                output_dir=output,
                results_dir=root / "results",
                method="llm",
                llm_patterns=patterns,
            )
            self.assertEqual(payload["run_summary"][0]["pattern_count"], 1)

    def test_breakdown_files_include_time_band_and_pattern_length(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            self.prepare_snapshot(self.make_snapshot(root), output)
            results = root / "results"
            evaluate(output_dir=output, results_dir=results, method="frequency")
            for name in ("evaluation10_by_time_band.csv", "evaluation10_by_pattern_length.csv"):
                with (results / name).open(encoding="utf-8") as handle:
                    header = next(csv.reader(handle))
                self.assertIn("future_recurrence_rate", header)
                self.assertIn("mean_test_support_count", header)


if __name__ == "__main__":
    unittest.main()
