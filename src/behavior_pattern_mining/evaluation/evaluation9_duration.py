"""Orchestrate Evaluation 9 train-duration sensitivity in Hestia's environment."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from itertools import groupby
import os
from pathlib import Path
import subprocess

from src.behavior_pattern_mining.evaluation.evaluation9_hestia import (
    PROJECT_ROOT,
    execute,
    resolve_path,
)

STAGES = ("generate", "prepare", "baseline", "budget", "extract", "evaluate", "run")
DEFAULT_TRAIN_DAYS = (3, 7, 14, 28)


def parse_train_days(value: str) -> list[int]:
    try:
        days = [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise ValueError("--train-days must contain comma-separated integers") from exc
    if not days or any(day < 1 for day in days) or len(days) != len(set(days)):
        raise ValueError("--train-days must contain unique positive integers")
    return sorted(days)


def build_duration_commands(
    *,
    stage: str,
    hestia_root: Path,
    experiment: Path,
    plan: Path,
    output_dir: Path,
    train_days: list[int],
    method: str = "both",
    allow_api: bool = False,
    llm_results_root: Path | None = None,
    model_id: str | None = None,
) -> list[list[str]]:
    if stage not in STAGES:
        raise ValueError(f"unknown stage: {stage}")
    if method not in ("frequency", "llm", "both"):
        raise ValueError(f"unknown method: {method}")
    if allow_api and stage not in ("extract", "run"):
        raise ValueError("--allow-api is only valid for extract or run")
    root = resolve_path(hestia_root)
    experiment = resolve_path(experiment)
    plan = resolve_path(plan)
    output_dir = resolve_path(output_dir)
    llm_results_root = resolve_path(llm_results_root or output_dir / "artifacts")
    if output_dir == experiment or output_dir in experiment.parents:
        raise ValueError(
            "output directory must not equal or contain the experiment directory"
        )
    prefix = [
        "uv",
        "run",
        "--project",
        str(root),
        "--frozen",
        "smart-home-sim",
        "experiment",
    ]
    actions = (
        ("generate", "prepare", "baseline", "extract", "evaluate")
        if stage == "run"
        else (stage,)
    )
    commands: list[list[str]] = []
    for action in actions:
        if action == "generate":
            commands.append(
                [
                    *prefix,
                    "duration-generate",
                    str(plan),
                    "--output",
                    str(experiment),
                    "--train-days",
                    ",".join(str(day) for day in train_days),
                ]
            )
            continue
        if action == "evaluate":
            commands.append(
                [
                    *prefix,
                    "duration-evaluate",
                    str(experiment),
                    "--output-dir",
                    str(output_dir),
                    "--method",
                    method,
                    "--llm-results-root",
                    str(llm_results_root),
                ]
            )
            continue
        command_name = "extract" if action == "budget" else action
        for days in train_days:
            window = experiment / "windows" / f"train_{days}d"
            window_llm_root = llm_results_root / "windows" / f"train_{days}d"
            command = [*prefix, command_name, str(window)]
            if action in ("prepare", "budget", "extract"):
                command.extend(["--research-root", str(PROJECT_ROOT)])
            if action in ("budget", "extract"):
                command.extend(["--llm-results-root", str(window_llm_root)])
                if model_id:
                    command.extend(["--model-id", model_id])
            if action == "extract" and allow_api:
                command.append("--allow-api")
            commands.append(command)
    return commands


def execute_duration_commands(
    commands: list[list[str]],
    hestia_root: Path,
    *,
    duration_workers: int = 4,
) -> None:
    """Run independent duration windows concurrently without crossing stages.

    Generation and final aggregation remain serial.  For each intervening stage,
    every train-duration window uses a distinct directory, so its command can run
    alongside the other duration windows.  The next stage starts only after all
    commands in the preceding stage have completed.
    """
    if duration_workers < 1:
        raise ValueError("--duration-workers must be at least 1")
    if duration_workers == 1:
        execute(commands, hestia_root)
        return

    root = resolve_path(hestia_root)
    if not (root / "src/smart_home_sim/experiments/cli.py").is_file():
        raise ValueError(f"Hestia experiment CLI is missing: {root}")
    environment = os.environ.copy()
    environment.pop("VIRTUAL_ENV", None)

    def command_stage(command: list[str]) -> str:
        try:
            return command[7]
        except IndexError as exc:
            raise ValueError(f"invalid Hestia experiment command: {command!r}") from exc

    for stage, grouped_commands in groupby(commands, key=command_stage):
        stage_commands = list(grouped_commands)
        workers = min(duration_workers, len(stage_commands))
        if workers == 1:
            subprocess.run(
                stage_commands[0], cwd=PROJECT_ROOT, env=environment, check=True
            )
            continue

        print(
            f"Running {stage} for {len(stage_commands)} train durations "
            f"with {workers} workers.",
            flush=True,
        )
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(
                    subprocess.run,
                    command,
                    cwd=PROJECT_ROOT,
                    env=environment,
                    check=True,
                )
                for command in stage_commands
            ]
            # Await every already-started window before failing, then do not
            # advance to the next stage. This keeps later dependencies intact.
            first_error: BaseException | None = None
            for future in futures:
                try:
                    future.result()
                except BaseException as exc:  # Preserve CalledProcessError details.
                    if first_error is None:
                        first_error = exc
            if first_error is not None:
                raise first_error
