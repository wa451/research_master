"""Evaluation 10 input, split, output-contract, and dashboard tests."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

from app.command_builder import build_evaluation10_steps
from scripts.evaluate_10_switchbot import main
from src.behavior_pattern_mining.evaluation.evaluation10_switchbot import (
    DETAIL_COLUMNS,
    SUMMARY_COLUMNS,
    evaluate,
    file_sha256,
    llm_patterns_path,
    prepare,
)


class Evaluation10SwitchBotTests(unittest.TestCase):
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
            self.assertGreater(rows["frequency"]["pattern_count"], 0)
            self.assertGreater(rows["frequency"]["test_supported_pattern_fraction"], 0)
            self.assertEqual(rows["llm"]["status"], "missing")
            with (results / "evaluation10_summary.csv").open(encoding="utf-8") as handle:
                self.assertEqual(next(csv.reader(handle)), SUMMARY_COLUMNS)
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

    def test_dashboard_commands_keep_api_opt_in(self):
        settings = {
            "runner": "uv run python",
            "snapshot": "data/switchbot/2026-09-01_2026-09-08",
            "output_dir": "output/10_switchbot/2026-09-01_2026-09-08",
            "results_dir": "results/10_switchbot/2026-09-01_2026-09-08",
            "split_at": "",
            "train_ratio": 0.7,
            "n_states": 15,
            "hamming_threshold": 0,
            "smoothing_window_sec": 5,
            "sampling_seconds": 1,
            "min_sequence_length": 2,
            "max_sequence_length": 4,
            "min_train_occurrences": 2,
            "top_k_per_mode": 20,
            "method": "both",
            "allow_api": False,
        }
        steps = build_evaluation10_steps(settings)
        self.assertEqual([step.step_id for step in steps], ["eval10_prepare", "eval10_evaluate"])
        self.assertTrue(all("--allow-api" not in step.command for step in steps))
        enabled = build_evaluation10_steps({**settings, "allow_api": True})
        self.assertEqual([step.step_id for step in enabled], ["eval10_prepare", "eval10_extract", "eval10_evaluate"])
        self.assertIn("--allow-api", enabled[1].command)


if __name__ == "__main__":
    unittest.main()
