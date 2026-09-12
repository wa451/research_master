"""Orchestrate Hestia's existing evaluation protocol in its own uv environment."""

from __future__ import annotations

from pathlib import Path
import os
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[3]
STAGES = ("generate", "prepare", "baseline", "budget", "extract", "evaluate", "run")


def resolve_path(path: Path) -> Path:
    path = path.expanduser()
    return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()


def build_commands(
    *,
    stage: str,
    hestia_root: Path,
    experiment: Path,
    plan: Path | None = None,
    output_dir: Path,
    method: str = "both",
    allow_api: bool = False,
) -> list[list[str]]:
    if stage not in STAGES:
        raise ValueError(f"unknown stage: {stage}")
    if method not in ("frequency", "llm", "both"):
        raise ValueError(f"unknown method: {method}")
    if allow_api and stage not in ("extract", "run"):
        raise ValueError("--allow-api is only valid for extract or run")
    root = resolve_path(hestia_root)
    experiment = resolve_path(experiment)
    output_dir = resolve_path(output_dir)
    # 生成先が空である契約を守り、生成途中に集計ファイルを混入させない。
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
    stages = (
        ("generate", "prepare", "baseline", "extract", "evaluate")
        if stage == "run"
        else (stage,)
    )
    commands = []
    for action in stages:
        if action == "generate":
            source = (
                resolve_path(plan)
                if plan is not None
                else root / "examples/experiments/noise_free_pilot.yaml"
            )
            command = [*prefix, "generate", str(source), "--output", str(experiment)]
        else:
            command = [
                *prefix,
                "extract" if action == "budget" else action,
                str(experiment),
            ]
            if action in ("prepare", "budget", "extract"):
                command.extend(["--research-root", str(PROJECT_ROOT)])
            if action == "extract" and allow_api:
                command.append("--allow-api")
            if action == "evaluate":
                command.extend(
                    [
                        "--method",
                        method,
                        "--summary",
                        str(output_dir / "evaluation9_summary"),
                    ]
                )
        commands.append(command)
    return commands


def execute(commands: list[list[str]], hestia_root: Path) -> None:
    root = resolve_path(hestia_root)
    if not (root / "src/smart_home_sim/experiments/cli.py").is_file():
        raise ValueError(f"Hestia experiment CLI is missing: {root}")
    environment = os.environ.copy()
    environment.pop("VIRTUAL_ENV", None)
    for command in commands:
        subprocess.run(command, cwd=PROJECT_ROOT, env=environment, check=True)
