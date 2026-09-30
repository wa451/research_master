"""Focused contract tests for detached dashboard batch execution."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

from app.batch_runner import (
    ACTIVE_BATCH_STATUSES,
    create_batch_artifacts,
    discover_batch_statuses,
    launch_batch_worker,
    read_json,
    run_batch_plan,
)


class DashboardBackgroundBatchTests(unittest.TestCase):
    def make_plan(self, root: Path, *, required_inputs: list[Path] | None = None) -> tuple[Path, Path]:
        log_dir = root / "output" / "test-model" / "logs" / "evaluation_dashboard" / "評価4" / "batch"
        plan_path = log_dir / "batch_plan.json"
        plan = {
            "evaluation": "評価4",
            "model_id": "test-model",
            "model_label": "Test model",
            "batch_mode": "全ステップを再実行",
            "dry_run": False,
            "project_root": str(root),
            "log_root": str(log_dir.parent.parent),
            "model_environment": {"TEST_DASHBOARD_BATCH": "1"},
            "declared_output_paths": [str(root / "results" / "summary.json")],
            "steps": [
                {
                    "index": 1,
                    "step_id": "test_step",
                    "title": "Test step",
                    "command": [sys.executable, "-c", "print('background batch')"],
                    "required_inputs": [str(path) for path in (required_inputs or [])],
                    "log_path": str(log_dir / "01_test_step.log"),
                }
            ],
        }
        return plan_path, create_batch_artifacts(plan_path, plan)

    def test_worker_persists_successful_status_and_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path, status_path = self.make_plan(root)
            worker = launch_batch_worker(plan_path, plan_path.parent / "batch_worker.log")

            self.assertEqual(worker.wait(timeout=10), 0)
            status = read_json(status_path)
            assert status is not None
            self.assertEqual(status["status"], "succeeded")
            self.assertEqual(status["completed_steps"], 1)
            self.assertEqual(status["steps"][0]["status"], "succeeded")
            self.assertIn("background batch", (plan_path.parent / "01_test_step.log").read_text(encoding="utf-8"))
            discovered = discover_batch_statuses(root / "output")
            self.assertEqual(discovered[0][1]["status"], "succeeded")
            self.assertNotIn(status["status"], ACTIVE_BATCH_STATUSES)

    def test_missing_input_blocks_without_running_the_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = root / "missing.csv"
            plan_path, status_path = self.make_plan(root, required_inputs=[missing])

            status = run_batch_plan(plan_path)

            self.assertEqual(status["status"], "blocked_missing_inputs")
            self.assertEqual(status["completed_steps"], 0)
            self.assertEqual(status["steps"][0]["status"], "blocked_missing_inputs")
            self.assertIn("missing.csv", (plan_path.parent / "01_test_step.log").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
