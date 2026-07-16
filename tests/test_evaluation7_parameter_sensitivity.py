from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def write_state_series(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["start_time", "end_time", "state_id"])
        writer.writeheader()
        writer.writerow(
            {
                "start_time": "2020-01-01 07:00:00",
                "end_time": "2020-01-01 07:05:00",
                "state_id": "状態1",
            }
        )
        writer.writerow(
            {
                "start_time": "2020-01-01 07:05:00",
                "end_time": "2020-01-01 07:10:00",
                "state_id": "状態2",
            }
        )


def write_patterns(path: Path, labels: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "pattern_id": "P001",
            "sequence": ["状態1", "状態2"],
            "time_band_interpretations": {
                "Morning": {
                    "パターン名": "morning pattern",
                    "ADL系列ラベル": labels,
                    "解釈の根拠": "test",
                }
            },
        }
    ]
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_adl_intervals(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["start_time", "end_time", "raw_label", "adl_category"])
        writer.writeheader()
        writer.writerow(
            {
                "start_time": "2020-01-01 07:00:00",
                "end_time": "2020-01-01 07:10:00",
                "raw_label": "Bed_to_Toilet",
                "adl_category": "Wake-up",
            }
        )


class Evaluation7ParameterSensitivityTests(unittest.TestCase):
    def test_cli_writes_condition_summary_and_best_condition(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            for n_states, labels in [(10, ["Wake-up", "Hygiene"]), (20, ["Meal"])]:
                suffix = f"{n_states}_1_30days"
                write_state_series(tmp / "output" / f"6_adl_evaluation_{suffix}" / "state_series.csv")
                write_patterns(
                    tmp / "output" / f"aruba_{suffix}" / f"llm_sequences_modes_{suffix}_1.json",
                    labels,
                )
            adl_path = tmp / "adl_intervals.csv"
            write_adl_intervals(adl_path)
            output_dir = tmp / "results"

            command = [
                sys.executable,
                "scripts/evaluate_7_parameter_sensitivity_adl_interpretation.py",
                "--n-states-list",
                "10,20",
                "--hamming-thresholds",
                "1",
                "--days",
                "30",
                "--runs",
                "1",
                "--patterns-template",
                str(tmp / "output" / "aruba_{suffix}" / "llm_sequences_modes_{suffix}_{run}.json"),
                "--state-series-template",
                str(tmp / "output" / "6_adl_evaluation_{suffix}" / "state_series.csv"),
                "--adl-intervals",
                str(adl_path),
                "--labeled-casas",
                str(tmp / "missing_labeled_casas.txt"),
                "--output-dir",
                str(output_dir),
            ]
            completed = subprocess.run(
                command,
                cwd=ROOT_DIR,
                check=True,
                text=True,
                capture_output=True,
            )

            self.assertIn("Best condition", completed.stdout)
            with (output_dir / "evaluation7_condition_summary.csv").open(encoding="utf-8", newline="") as handle:
                summary_rows = list(csv.DictReader(handle))
            self.assertEqual([row["condition_id"] for row in summary_rows], ["10_1_30days", "20_1_30days"])
            self.assertEqual(summary_rows[0]["rank"], "1")
            self.assertAlmostEqual(float(summary_rows[0]["mean_multilabel_f1"]), 1.0)
            self.assertAlmostEqual(float(summary_rows[1]["mean_multilabel_f1"]), 0.0)

            summary_payload = json.loads((output_dir / "evaluation7_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary_payload["best_condition"]["condition_id"], "10_1_30days")
            self.assertEqual(summary_payload["selection_metric"], "mean_multilabel_f1")
            self.assertTrue((output_dir / "evaluation7_by_pred_label.csv").exists())
            self.assertTrue((output_dir / "evaluation7_by_true_label.csv").exists())
            self.assertTrue((output_dir / "evaluation7_by_time_band.csv").exists())

    def test_cli_evaluates_exact_condition_pairs_and_explicit_run_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            selected = [(10, 0), (20, 1)]
            for n_states, hamming in selected:
                suffix = f"{n_states}_{hamming}_30days"
                write_state_series(tmp / "output" / f"6_adl_evaluation_{suffix}" / "state_series.csv")
                for run in (2, 3, 4):
                    labels = ["Wake-up"] if n_states == 10 else ["Meal"]
                    write_patterns(
                        tmp / "output" / f"aruba_{suffix}" / f"llm_sequences_modes_{suffix}_{run}.json",
                        labels,
                    )

            manifest = tmp / "top_conditions.csv"
            with manifest.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["rank", "n_states", "hamming_threshold", "days"],
                )
                writer.writeheader()
                for rank, (n_states, hamming) in enumerate(selected, start=1):
                    writer.writerow(
                        {
                            "rank": rank,
                            "n_states": n_states,
                            "hamming_threshold": hamming,
                            "days": 30,
                        }
                    )

            adl_path = tmp / "adl_intervals.csv"
            write_adl_intervals(adl_path)
            output_dir = tmp / "results"
            summary_copy = tmp / "evaluation7_top2_3runs_conditions.csv"
            command = [
                sys.executable,
                "scripts/evaluate_7_parameter_sensitivity_adl_interpretation.py",
                "--conditions-file",
                str(manifest),
                "--condition-summary-copy",
                str(summary_copy),
                "--run-ids",
                "2",
                "3",
                "4",
                "--days",
                "30",
                "--patterns-template",
                str(tmp / "output" / "aruba_{suffix}" / "llm_sequences_modes_{suffix}_{run}.json"),
                "--state-series-template",
                str(tmp / "output" / "6_adl_evaluation_{suffix}" / "state_series.csv"),
                "--adl-intervals",
                str(adl_path),
                "--labeled-casas",
                str(tmp / "missing_labeled_casas.txt"),
                "--output-dir",
                str(output_dir),
            ]
            subprocess.run(command, cwd=ROOT_DIR, check=True, text=True, capture_output=True)

            with (output_dir / "evaluation7_condition_summary.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                summary_rows = list(csv.DictReader(handle))
            self.assertEqual(len(summary_rows), 2)
            self.assertEqual({int(row["num_runs"]) for row in summary_rows}, {3})
            self.assertEqual(
                summary_copy.read_text(encoding="utf-8"),
                (output_dir / "evaluation7_condition_summary.csv").read_text(encoding="utf-8"),
            )

            with (output_dir / "evaluation7_condition_summary_by_run.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                run_rows = list(csv.DictReader(handle))
            self.assertEqual({int(row["run"]) for row in run_rows}, {2, 3, 4})
            payload = json.loads((output_dir / "evaluation7_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["run_ids_requested"], [2, 3, 4])
            self.assertEqual(payload["conditions_file"], str(manifest))
            self.assertEqual(payload["condition_summary_copy"], str(summary_copy))
            self.assertEqual(
                payload["condition_pairs"],
                [
                    {"n_states": 10, "hamming_threshold": 0},
                    {"n_states": 20, "hamming_threshold": 1},
                ],
            )


if __name__ == "__main__":
    unittest.main()
