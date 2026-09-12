"""Evaluation 9 routing, API opt-in and dashboard regression tests."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.command_builder import build_evaluation9_steps
from scripts.evaluate_9_hestia import main
from src.behavior_pattern_mining.evaluation.evaluation9_hestia import (
    build_commands,
    execute,
    PROJECT_ROOT,
)


class Evaluation9Tests(unittest.TestCase):
    def commands(self, **kwargs):
        settings = dict(
            stage="run",
            hestia_root=Path("Hestia"),
            experiment=Path("output/9_hestia/pilot"),
            output_dir=Path("results/9_hestia/pilot"),
        )
        return build_commands(**(settings | kwargs))

    def test_offline_default_and_order(self):
        commands = self.commands()
        self.assertEqual(
            [c[7] for c in commands],
            ["generate", "prepare", "baseline", "extract", "evaluate"],
        )
        self.assertTrue(all("--allow-api" not in c for c in commands))
        self.assertIn(str(PROJECT_ROOT / "Hestia"), commands[0])
        self.assertIn(str(PROJECT_ROOT), commands[1])
        self.assertIn(
            str(PROJECT_ROOT / "results/9_hestia/pilot/evaluation9_summary"),
            commands[-1],
        )

    def test_api_permission_only_on_extract(self):
        commands = self.commands(allow_api=True)
        self.assertEqual([c[7] for c in commands if "--allow-api" in c], ["extract"])
        with self.assertRaises(ValueError):
            self.commands(stage="budget", allow_api=True)

    def test_custom_paths_are_single_arguments(self):
        commands = self.commands(
            plan=Path("plans/a plan.yaml"), experiment=Path("output/a run")
        )
        self.assertIn(str(PROJECT_ROOT / "plans/a plan.yaml"), commands[0])
        self.assertIn(str(PROJECT_ROOT / "output/a run"), commands[0])

    def test_dry_run_does_not_execute_or_write(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("scripts.evaluate_9_hestia.execute") as run,
        ):
            target = Path(directory) / "untouched"
            self.assertEqual(main(["--dry-run", "--experiment", str(target)]), 0)
            run.assert_not_called()
            self.assertFalse(target.exists())

    def test_child_failure_stops_following_stages(self):
        import subprocess

        with patch(
            "src.behavior_pattern_mining.evaluation.evaluation9_hestia.subprocess.run",
            side_effect=subprocess.CalledProcessError(2, ["uv"]),
        ) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                execute(self.commands(), PROJECT_ROOT / "Hestia")
            self.assertEqual(run.call_count, 1)

    def test_dashboard_batch_revalidates_and_evaluates(self):
        from app.streamlit_app import batch_target_steps, default_result_dirs

        steps = build_evaluation9_steps({"runner": "uv run python"})
        self.assertEqual(len(steps), 5)
        self.assertTrue(all(step.verify_on_batch for step in steps))
        with patch("app.streamlit_app.missing_expected_outputs", return_value=[]):
            self.assertEqual(
                len(batch_target_steps(steps, "不足ファイル生成 + 評価本体")), 5
            )
            self.assertEqual(len(batch_target_steps(steps, "不足ファイル生成のみ")), 4)
        self.assertEqual(steps[3].step_id, "eval9_budget")
        self.assertNotIn("--allow-api", steps[3].command)
        enabled = build_evaluation9_steps({"runner": "python", "allow_api": True})
        self.assertIn("--allow-api", enabled[3].command)
        self.assertEqual(
            default_result_dirs(
                {"evaluation": "評価9", "output_dir": "results/9_hestia/pilot"}
            ),
            [PROJECT_ROOT / "results/9_hestia/pilot"],
        )

    def test_result_discovery_and_guide(self):
        from app.streamlit_app import infer_evaluation_for_results, result_file_rank

        path = Path("results/9_hestia/pilot/evaluation9_summary.csv")
        self.assertEqual(
            infer_evaluation_for_results(path.parent, [path], "評価8"), "評価9"
        )
        self.assertEqual(result_file_rank("評価9", path)[0], 0)


if __name__ == "__main__":
    unittest.main()
