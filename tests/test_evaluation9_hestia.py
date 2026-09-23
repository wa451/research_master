"""Evaluation 9 routing, API opt-in and dashboard regression tests."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.command_builder import build_evaluation9_steps
from app.evaluation9_plan import (
    DURATION_TRAIN_DAYS,
    archive_evaluation9_outputs,
    build_effective_plan,
    estimate_scale,
    experiment_snapshot_matches,
    load_preset_plan,
    parse_seed_list,
    save_effective_plan,
)
from app.hestia_house_diagrams import house_rooms, house_topology_dot
from scripts.evaluate_9_hestia import main
from scripts.evaluate_9_duration import main as duration_main
from src.behavior_pattern_mining.evaluation.evaluation9_duration import (
    build_duration_commands,
)
from src.behavior_pattern_mining.evaluation.evaluation9_hestia import (
    PROJECT_ROOT,
    build_commands,
    execute,
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

    def test_dashboard_preset_scale_estimates(self):
        hestia = PROJECT_ROOT / "Hestia"
        pilot_path, pilot = load_preset_plan(hestia, "Pilot")
        smoke_path, smoke = load_preset_plan(hestia, "本実験・小規模確認")
        full_path, full = load_preset_plan(hestia, "本実験")
        duration_path, duration = load_preset_plan(hestia, "期間感度評価")

        self.assertEqual(pilot_path.name, "noise_free_pilot.yaml")
        self.assertEqual(len(pilot.conditions), 4)
        self.assertEqual(pilot.seeds, [11])
        self.assertEqual(pilot.llm_runs, 1)
        self.assertEqual(estimate_scale(pilot).fresh_api_calls, 16)

        self.assertEqual(smoke_path.name, "noise_free.yaml")
        self.assertEqual(
            [condition.id for condition in smoke.conditions],
            [
                "compact_base",
                "compact_variable",
                "corridor_base",
                "corridor_variable",
                "branched_base",
                "branched_variable",
            ],
        )
        self.assertEqual(smoke.train_days, 7)
        self.assertEqual(smoke.test_days, 7)
        self.assertEqual(smoke.seeds, [11])
        self.assertEqual(smoke.llm_runs, 1)
        self.assertEqual(estimate_scale(smoke).fresh_api_calls, 24)

        self.assertEqual(full_path.name, "noise_free.yaml")
        self.assertEqual(len(full.conditions), 6)
        self.assertEqual(full.seeds, [11, 22, 33])
        self.assertEqual(full.llm_runs, 3)
        self.assertEqual(estimate_scale(full).fresh_api_calls, 216)

        self.assertEqual(duration_path.name, "noise_free_duration.yaml")
        self.assertEqual(duration.train_days, 28)
        self.assertEqual(duration.test_days, 7)
        duration_scale = estimate_scale(
            duration, duration_train_days=DURATION_TRAIN_DAYS
        )
        self.assertEqual(duration_scale.hestia_run_count, 18)
        self.assertEqual(duration_scale.fresh_api_calls, 864)
        self.assertEqual(duration_scale.parse_attempts_upper_bound, 2592)

        expected_smoke = full.model_dump(mode="json")
        expected_smoke.update({"seeds": [11], "llm_runs": 1})
        self.assertEqual(smoke.model_dump(mode="json"), expected_smoke)

    def test_full_smoke_effective_plan_is_reloadable_and_used_by_builder(self):
        from smart_home_sim.experiments.plan import load_plan

        _, smoke = load_preset_plan(PROJECT_ROOT / "Hestia", "本実験・小規模確認")
        with tempfile.TemporaryDirectory() as directory:
            effective = save_effective_plan(smoke, Path(directory))
            self.assertEqual(load_plan(effective), smoke)
            steps = build_evaluation9_steps(
                {
                    "runner": "python",
                    "effective_plan": effective,
                    "experiment": "output/9_hestia/full_smoke",
                    "output_dir": "results/9_hestia/full_smoke",
                    "allow_api": False,
                }
            )
        self.assertIn(str(effective), steps[0].command)
        self.assertTrue(all("--allow-api" not in step.command for step in steps))

    def test_duration_cli_and_dashboard_share_raw_generation(self):
        commands = build_duration_commands(
            stage="run",
            hestia_root=Path("Hestia"),
            plan=Path("Hestia/examples/experiments/noise_free_duration.yaml"),
            experiment=Path("output/9_hestia/duration"),
            output_dir=Path("results/9_hestia/duration"),
            train_days=list(DURATION_TRAIN_DAYS),
        )
        self.assertEqual(sum("duration-generate" in command for command in commands), 1)
        self.assertEqual(sum(command[7] == "prepare" for command in commands), 4)
        self.assertEqual(sum(command[7] == "baseline" for command in commands), 4)
        self.assertEqual(sum(command[7] == "extract" for command in commands), 4)
        self.assertEqual(sum("duration-evaluate" in command for command in commands), 1)
        self.assertTrue(all("--allow-api" not in command for command in commands))

        steps = build_evaluation9_steps(
            {
                "runner": "python",
                "duration": True,
                "duration_train_days": list(DURATION_TRAIN_DAYS),
                "plan": "Hestia/examples/experiments/noise_free_duration.yaml",
                "experiment": "output/9_hestia/duration",
                "output_dir": "results/9_hestia/duration",
            }
        )
        self.assertTrue(
            all("scripts/evaluate_9_duration.py" in step.command for step in steps)
        )
        self.assertIn("--train-days", steps[0].command)
        self.assertNotIn("--allow-api", steps[3].command)
        self.assertIn(
            "evaluation9_duration_summary.csv", str(steps[-1].expected_outputs[0])
        )

        enabled = build_duration_commands(
            stage="extract",
            hestia_root=Path("Hestia"),
            plan=Path("Hestia/examples/experiments/noise_free_duration.yaml"),
            experiment=Path("output/9_hestia/duration"),
            output_dir=Path("results/9_hestia/duration"),
            train_days=list(DURATION_TRAIN_DAYS),
            allow_api=True,
        )
        self.assertEqual(len(enabled), 4)
        self.assertTrue(all(command[-1] == "--allow-api" for command in enabled))

        with patch("scripts.evaluate_9_duration.execute") as execute:
            self.assertEqual(duration_main(["--dry-run"]), 0)
            execute.assert_not_called()

    def test_dashboard_overrides_change_only_requested_plan_fields(self):
        _, pilot = load_preset_plan(PROJECT_ROOT / "Hestia", "Pilot")
        two_runs = build_effective_plan(pilot, seeds=[11], llm_runs=2)
        two_seeds = build_effective_plan(pilot, seeds=[11, 22], llm_runs=1)

        self.assertEqual(estimate_scale(two_runs).fresh_api_calls, 32)
        self.assertEqual(estimate_scale(two_seeds).seed_count, 2)
        self.assertEqual(estimate_scale(two_seeds).fresh_api_calls, 32)
        expected = pilot.model_dump(mode="json")
        expected.update({"llm_runs": 2})
        self.assertEqual(two_runs.model_dump(mode="json"), expected)

    def test_dashboard_prefers_existing_extraction_budget(self):
        _, pilot = load_preset_plan(PROJECT_ROOT / "Hestia", "Pilot")
        with patch("app.evaluation9_plan._existing_budget", return_value=(5, 15)):
            scale = estimate_scale(pilot, experiment=Path("existing"))
        self.assertTrue(scale.uses_existing_budget)
        self.assertEqual(scale.fresh_api_calls, 5)
        self.assertEqual(scale.parse_attempts_upper_bound, 15)
        self.assertEqual(scale.full_fresh_api_calls, 16)

    def test_dashboard_seed_input_uses_experiment_plan_validation(self):
        _, pilot = load_preset_plan(PROJECT_ROOT / "Hestia", "Pilot")
        self.assertEqual(parse_seed_list("11, 22, 33"), [11, 22, 33])
        for invalid in ("", "11,", "eleven"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                parse_seed_list(invalid)
        with self.assertRaises(ValueError):
            build_effective_plan(pilot, seeds=[11, 11], llm_runs=1)

    def test_effective_plan_is_content_addressed_reloadable_and_preserves_sources(self):
        hestia = PROJECT_ROOT / "Hestia"
        source_paths = [
            hestia / "examples/experiments/noise_free_pilot.yaml",
            hestia / "examples/experiments/noise_free.yaml",
            hestia / "examples/experiments/noise_free_duration.yaml",
        ]
        before = {path: path.read_bytes() for path in source_paths}
        _, pilot = load_preset_plan(hestia, "Pilot")
        effective = build_effective_plan(pilot, seeds=[11, 22], llm_runs=2)

        with tempfile.TemporaryDirectory() as directory:
            target = save_effective_plan(effective, Path(directory))
            duplicate = save_effective_plan(effective, Path(directory))
            from smart_home_sim.experiments.plan import load_plan

            self.assertEqual(target, duplicate)
            self.assertEqual(load_plan(target), effective)
            self.assertEqual(len(list(Path(directory).glob("*.yaml"))), 1)

        self.assertEqual({path: path.read_bytes() for path in source_paths}, before)

    def test_different_effective_plan_is_rejected_for_existing_experiment(self):
        _, pilot = load_preset_plan(PROJECT_ROOT / "Hestia", "Pilot")
        changed = build_effective_plan(pilot, seeds=[11, 22], llm_runs=1)
        with tempfile.TemporaryDirectory() as directory:
            experiment = Path(directory)
            (experiment / "experiment.json").write_text(
                pilot.model_dump_json(), encoding="utf-8"
            )
            self.assertTrue(experiment_snapshot_matches(pilot, experiment))
            self.assertFalse(experiment_snapshot_matches(changed, experiment))

            legacy_payload = pilot.model_dump(mode="json")
            legacy_payload.pop("fragmentation_containment_threshold")
            (experiment / "experiment.json").write_text(
                json.dumps(legacy_payload), encoding="utf-8"
            )
            self.assertFalse(experiment_snapshot_matches(pilot, experiment))

    def test_dashboard_builder_prefers_effective_plan_and_keeps_api_opt_in(self):
        effective = Path(
            "output/logs/evaluation_dashboard/evaluation9_plans/custom.yaml"
        )
        steps = build_evaluation9_steps(
            {
                "runner": "python",
                "plan": "Hestia/examples/experiments/noise_free_pilot.yaml",
                "effective_plan": effective,
                "allow_api": False,
            }
        )
        expected = str(PROJECT_ROOT / effective)
        self.assertIn(expected, steps[0].command)
        self.assertNotIn(
            str(PROJECT_ROOT / "Hestia/examples/experiments/noise_free_pilot.yaml"),
            steps[0].command,
        )
        self.assertTrue(all("--allow-api" not in step.command for step in steps))

    def test_existing_outputs_can_be_archived_before_reusing_same_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            experiment = root / "output/9_hestia/pilot"
            results = root / "results/9_hestia/pilot"
            experiment.mkdir(parents=True)
            results.mkdir(parents=True)
            (experiment / "experiment.json").write_text("{}", encoding="utf-8")
            (results / "summary.csv").write_text("metric\n", encoding="utf-8")

            archived = archive_evaluation9_outputs(
                experiment=experiment,
                output_dir=results,
                project_root=root,
                archive_root=root / "backups",
                timestamp="20260916_130000",
            )

            archive = Path(archived["archive_directory"])
            self.assertFalse(experiment.exists())
            self.assertFalse(results.exists())
            self.assertTrue((archive / "experiment/experiment.json").is_file())
            self.assertTrue((archive / "results/summary.csv").is_file())
            self.assertTrue((archive / "manifest.json").is_file())

    def test_output_archive_refuses_broad_or_unmanaged_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            managed_root = root / "output/9_hestia"
            managed_root.mkdir(parents=True)
            with self.assertRaises(ValueError):
                archive_evaluation9_outputs(
                    experiment=managed_root,
                    output_dir=root / "results/9_hestia/pilot",
                    project_root=root,
                    archive_root=root / "backups",
                )

    def test_result_discovery_and_guide(self):
        from app.streamlit_app import infer_evaluation_for_results, result_file_rank

        path = Path("results/9_hestia/pilot/evaluation9_summary.csv")
        self.assertEqual(
            infer_evaluation_for_results(path.parent, [path], "評価8"), "評価9"
        )
        self.assertEqual(result_file_rank("評価9", path)[0], 0)

    def test_house_diagrams_match_hestia_topologies(self):
        expected_rooms = {
            "compact": {"bathroom", "bedroom", "kitchen", "living", "outside"},
            "corridor": {
                "bathroom",
                "bedroom",
                "hallway",
                "kitchen",
                "living",
                "outside",
            },
            "branched": {
                "bathroom",
                "bedroom",
                "hallway",
                "kitchen",
                "living",
                "outside",
                "study",
            },
        }
        expected_edges = {
            "compact": {
                '"living" -- "bathroom" [label="D_bathroom / 10秒"]',
                '"living" -- "bedroom" [label="D_bedroom / 10秒"]',
                '"living" -- "kitchen" [label="D_kitchen / 10秒"]',
                '"living" -- "outside" [label="D_outside / 10秒"]',
            },
            "corridor": {
                '"hallway" -- "bathroom" [label="D_bathroom / 10秒"]',
                '"hallway" -- "bedroom" [label="D_bedroom / 10秒"]',
                '"hallway" -- "kitchen" [label="D_kitchen / 10秒"]',
                '"hallway" -- "living" [label="D_living / 10秒"]',
                '"hallway" -- "outside" [label="D_outside / 10秒"]',
            },
            "branched": {
                '"hallway" -- "bathroom" [label="D_bathroom / 10秒"]',
                '"hallway" -- "bedroom" [label="D_bedroom / 10秒"]',
                '"hallway" -- "kitchen" [label="D_kitchen / 10秒"]',
                '"hallway" -- "living" [label="D_living / 10秒"]',
                '"hallway" -- "outside" [label="D_outside / 10秒"]',
                '"living" -- "study" [label="D_study / 15秒"]',
            },
        }
        for house, rooms in expected_rooms.items():
            self.assertEqual(set(house_rooms(house)), rooms)
            dot = house_topology_dot(house)
            for edge in expected_edges[house]:
                self.assertIn(edge, dot)


if __name__ == "__main__":
    unittest.main()
