from __future__ import annotations

import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_6_compare_adl_interpretation_set.py"
SPEC = importlib.util.spec_from_file_location("evaluation6", SCRIPT_PATH)
assert SPEC and SPEC.loader
evaluation6 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluation6)


class Evaluation6DefaultDaysTests(unittest.TestCase):
    def test_default_condition_uses_14_days(self) -> None:
        with patch.object(sys, "argv", [str(SCRIPT_PATH)]):
            args = evaluation6.parse_args()

        self.assertEqual(args.days, 14)
        self.assertIn("15_1_14days", str(args.patterns_proposed))
        self.assertIn("llm_direct_15_1_14days", str(args.patterns_direct))
        self.assertIn("6_adl_evaluation_14", str(args.state_series))

    def test_five_run_cli_writes_llm_usage_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            proposed_dir = root / "proposed"
            direct_dir = root / "direct"
            proposed_dir.mkdir()
            direct_dir.mkdir()
            pattern = [
                {
                    "パターン名": "食事",
                    "ADL系列ラベル": ["Meal"],
                    "解釈の根拠": "test",
                    "遷移のパターン": ["状態1", "状態2"],
                }
            ]
            for run in range(1, 6):
                (proposed_dir / f"llm_sequences_modes_15_1_14days_{run}.json").write_text(
                    json.dumps(pattern, ensure_ascii=False),
                    encoding="utf-8",
                )
                (direct_dir / f"{run}.json").write_text(
                    json.dumps(pattern, ensure_ascii=False),
                    encoding="utf-8",
                )
                proposed_metrics = root / f"proposed_metrics_run{run}.csv"
                with proposed_metrics.open("w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(
                        f,
                        fieldnames=[
                            "run",
                            "duration_sec",
                            "prompt_tokens",
                            "response_tokens",
                            "total_tokens",
                        ],
                    )
                    writer.writeheader()
                    for _ in range(4):
                        writer.writerow(
                            {
                                "run": run,
                                "duration_sec": 1,
                                "prompt_tokens": 10,
                                "response_tokens": 2,
                                "total_tokens": 12,
                            }
                        )

            direct_metrics = direct_dir / "llm_direct_metrics_14days.csv"
            with direct_metrics.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "run",
                        "duration_sec",
                        "prompt_tokens",
                        "response_tokens",
                        "total_tokens",
                    ],
                )
                writer.writeheader()
                for run in range(1, 6):
                    writer.writerow(
                        {
                            "run": run,
                            "duration_sec": 3,
                            "prompt_tokens": 100,
                            "response_tokens": 10,
                            "total_tokens": 110,
                        }
                    )

            state_series = root / "state_series.csv"
            state_series.write_text(
                "\n".join(
                    [
                        "start_time,end_time,state_id",
                        "2020-01-01 00:00:00,2020-01-01 00:01:00,状態1",
                        "2020-01-01 00:01:00,2020-01-01 00:02:00,状態2",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            labeled_casas = root / "labeled.txt"
            labeled_casas.write_text(
                "\n".join(
                    [
                        "2020-01-01 00:00:00 M001 ON Meal_Preparation begin",
                        "2020-01-01 00:02:00 M001 OFF Meal_Preparation end",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            output_dir = root / "results"

            argv = [
                str(SCRIPT_PATH),
                "--patterns-proposed",
                str(proposed_dir / "llm_sequences_modes_15_1_14days_1.json"),
                "--patterns-direct",
                str(direct_dir / "1.json"),
                "--proposed-metrics-template",
                str(root / "proposed_metrics_run{run}.csv"),
                "--direct-metrics",
                str(direct_metrics),
                "--state-series",
                str(state_series),
                "--labeled-casas",
                str(labeled_casas),
                "--output-dir",
                str(output_dir),
                "--runs",
                "5",
            ]
            with patch.object(sys, "argv", argv):
                evaluation6.main()

            comparison_path = output_dir / "evaluation6_llm_usage_comparison.csv"
            with comparison_path.open(encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            summary = json.loads(
                (output_dir / "evaluation6_comparison_summary.json").read_text(
                    encoding="utf-8"
                )
            )

        by_method = {row["method"]: row for row in rows}
        self.assertEqual(by_method["proposed"]["num_runs_with_complete_metrics"], "5")
        self.assertEqual(by_method["proposed"]["avg_total_tokens_per_run"], "48.0")
        self.assertEqual(
            by_method["direct_log_baseline"]["avg_api_response_duration_sec_per_run"],
            "3.0",
        )
        self.assertEqual(
            summary["llm_usage_comparison"]["missing_metrics"],
            [],
        )


if __name__ == "__main__":
    unittest.main()
