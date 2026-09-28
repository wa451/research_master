"""Evaluation 9 dashboard helpers for validated, reproducible effective plans."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.behavior_pattern_mining.llm.result_paths import MODEL_RESULT_NAMES

import yaml
from smart_home_sim.experiments.plan import ExperimentPlan, load_plan
from smart_home_sim.experiments.research import extraction_budget

from experiment_config import TIME_MODES
from src.behavior_pattern_mining.llm.pattern_extractor import MAX_PARSE_RETRIES

PRESET_PLAN_FILENAMES = {
    "Pilot": "noise_free_pilot.yaml",
    "本実験・小規模確認": "noise_free.yaml",
    "本実験": "noise_free.yaml",
    "期間感度評価": "noise_free_duration.yaml",
}
PRESET_PLAN_OVERRIDES = {
    "本実験・小規模確認": {"seeds": [11], "llm_runs": 1},
}
PRESET_DIRECTORY_NAMES = {
    "Pilot": "pilot",
    "本実験・小規模確認": "full_smoke",
    "本実験": "full",
    "期間感度評価": "duration",
}
DURATION_PRESET = "期間感度評価"
DURATION_TRAIN_DAYS = (3, 7, 14, 28)


@dataclass(frozen=True)
class Evaluation9Scale:
    condition_count: int
    seed_count: int
    llm_runs: int
    time_band_count: int
    hestia_run_count: int
    fresh_api_calls: int
    parse_attempts_upper_bound: int
    full_fresh_api_calls: int
    uses_existing_budget: bool = False


def preset_plan_path(hestia_root: Path, preset: str) -> Path:
    """Return the canonical source plan path for a dashboard preset."""
    try:
        filename = PRESET_PLAN_FILENAMES[preset]
    except KeyError as exc:
        raise ValueError(f"unknown Evaluation 9 preset: {preset}") from exc
    return hestia_root / "examples" / "experiments" / filename


def load_preset_plan(hestia_root: Path, preset: str) -> tuple[Path, ExperimentPlan]:
    path = preset_plan_path(hestia_root, preset)
    plan = load_plan(path)
    overrides = PRESET_PLAN_OVERRIDES.get(preset)
    if overrides is not None:
        plan = build_effective_plan(
            plan,
            seeds=list(overrides["seeds"]),
            llm_runs=int(overrides["llm_runs"]),
        )
    return path, plan


def preset_directory_name(preset: str) -> str:
    try:
        return PRESET_DIRECTORY_NAMES[preset]
    except KeyError as exc:
        raise ValueError(f"unknown Evaluation 9 preset: {preset}") from exc


def parse_seed_list(text: str) -> list[int]:
    """Parse a comma-separated seed list without inventing seed values."""
    parts = [part.strip() for part in text.split(",")]
    if not parts or any(not part for part in parts):
        raise ValueError("seedは1個以上の整数をカンマ区切りで入力してください")
    try:
        return [int(part) for part in parts]
    except ValueError as exc:
        raise ValueError("seedには整数だけを入力してください") from exc


def build_effective_plan(
    base_plan: ExperimentPlan, *, seeds: list[int], llm_runs: int
) -> ExperimentPlan:
    """Apply dashboard overrides and run the canonical ExperimentPlan validation."""
    payload = base_plan.model_dump(mode="json")
    payload.update({"seeds": seeds, "llm_runs": llm_runs})
    return ExperimentPlan.model_validate(payload)


def _canonical_plan_bytes(plan: ExperimentPlan) -> bytes:
    return json.dumps(
        plan.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def save_effective_plan(plan: ExperimentPlan, directory: Path) -> Path:
    """Persist a content-addressed YAML plan, reusing an identical existing file."""
    digest = hashlib.sha256(_canonical_plan_bytes(plan)).hexdigest()[:16]
    path = directory / f"evaluation9_{digest}.yaml"
    if path.exists():
        if load_plan(path) != plan:
            raise ValueError(f"effective plan hash collision: {path}")
        return path

    directory.mkdir(parents=True, exist_ok=True)
    payload = yaml.safe_dump(
        plan.model_dump(mode="json"),
        allow_unicode=True,
        sort_keys=False,
    )
    temporary = path.with_suffix(".yaml.tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)
    return path


def experiment_snapshot_matches(
    plan: ExperimentPlan,
    experiment: Path,
    *,
    duration_train_days: tuple[int, ...] | None = None,
) -> bool | None:
    """Mirror Hestia's raw snapshot equality check, or return None if absent."""
    snapshot = experiment / (
        "raw/experiment.json" if duration_train_days else "experiment.json"
    )
    if not snapshot.is_file():
        return None
    try:
        payload = json.loads(snapshot.read_text(encoding="utf-8"))
        if payload != plan.model_dump(mode="json"):
            return False
        if duration_train_days:
            manifest = json.loads(
                (experiment / "duration.json").read_text(encoding="utf-8")
            )
            return manifest.get("train_days") == list(duration_train_days)
        return True
    except (json.JSONDecodeError, OSError):
        return False


def _managed_evaluation9_results(path: Path, project_root: Path) -> Path:
    results_root = (project_root / "results").resolve()
    resolved = path.expanduser().resolve()
    if not resolved.is_relative_to(results_root) or resolved == results_root:
        raise ValueError(f"results directory must be a managed Evaluation 9 child: {resolved}")
    relative = resolved.relative_to(results_root)
    valid_prefixes = {("9_hestia",)} | {
        (name, "9_hestia") for name in set(MODEL_RESULT_NAMES.values())
    }
    if not any(
        relative.parts[: len(prefix)] == prefix and len(relative.parts) > len(prefix)
        for prefix in valid_prefixes
    ):
        raise ValueError(f"results directory must be under an Evaluation 9 root: {resolved}")
    if path.is_symlink():
        raise ValueError(f"results directory must not be a symbolic link: {path}")
    return resolved


def _managed_evaluation9_experiment(path: Path, project_root: Path) -> Path:
    """Accept legacy or model-namespaced Evaluation 9 generation roots."""
    output_root = (project_root / "output").resolve()
    resolved = path.expanduser().resolve()
    if not resolved.is_relative_to(output_root) or resolved == output_root:
        raise ValueError(f"experiment directory must be under output: {resolved}")
    relative = resolved.relative_to(output_root)
    valid_prefixes = {("9_hestia",)} | {
        (name, "9_hestia") for name in set(MODEL_RESULT_NAMES.values())
    }
    if not any(
        relative.parts[: len(prefix)] == prefix and len(relative.parts) > len(prefix)
        for prefix in valid_prefixes
    ):
        raise ValueError(f"experiment directory must be under an Evaluation 9 root: {resolved}")
    if path.is_symlink():
        raise ValueError(f"experiment directory must not be a symbolic link: {path}")
    return resolved


def archive_evaluation9_outputs(
    *,
    experiment: Path,
    output_dir: Path,
    project_root: Path,
    archive_root: Path,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Move managed Evaluation 9 outputs into a recoverable archive."""
    experiment = _managed_evaluation9_experiment(experiment, project_root)
    output_dir = _managed_evaluation9_results(output_dir, project_root)
    if not experiment.exists():
        raise ValueError(f"experiment directory does not exist: {experiment}")
    if not experiment.is_dir():
        raise ValueError(f"experiment path is not a directory: {experiment}")
    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError(f"results path is not a directory: {output_dir}")

    stamp = timestamp or datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    archive_root = archive_root.expanduser().resolve()
    if archive_root.is_relative_to(experiment) or archive_root.is_relative_to(
        output_dir
    ):
        raise ValueError("archive directory must be outside the outputs being archived")
    base = archive_root / f"{stamp}_{experiment.name}"
    destination = base
    counter = 2
    while destination.exists():
        destination = base.with_name(f"{base.name}_{counter}")
        counter += 1
    destination.mkdir(parents=True)

    archived: dict[str, str] = {}
    moved: list[tuple[Path, Path]] = []
    try:
        for name, source in (("experiment", experiment), ("results", output_dir)):
            if source.exists():
                target = destination / name
                shutil.move(str(source), str(target))
                moved.append((source, target))
                archived[name] = str(target)
        manifest: dict[str, Any] = {
            "archived_at": stamp,
            "original_experiment": str(experiment),
            "original_results": str(output_dir),
            "archived": archived,
        }
        (destination / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except Exception:
        for source, target in reversed(moved):
            if target.exists() and not source.exists():
                shutil.move(str(target), str(source))
        if destination.exists() and not any(destination.iterdir()):
            destination.rmdir()
        raise
    return {**manifest, "archive_directory": str(destination)}


def _existing_budget(
    plan: ExperimentPlan,
    experiment: Path,
    duration_train_days: tuple[int, ...] | None = None,
) -> tuple[int, int] | None:
    snapshot = experiment / (
        "raw/experiment.json" if duration_train_days else "experiment.json"
    )
    if not snapshot.is_file():
        return None
    try:
        if (
            experiment_snapshot_matches(
                plan, experiment, duration_train_days=duration_train_days
            )
            is not True
        ):
            return None
        experiments = (
            [experiment / "windows" / f"train_{days}d" for days in duration_train_days]
            if duration_train_days
            else [experiment]
        )
        runs = [
            selected / "runs" / condition.id / f"seed_{seed}"
            for selected in experiments
            for condition in sorted(plan.conditions, key=lambda item: item.id)
            for seed in sorted(plan.seeds)
        ]
        if not runs or any(not (run / "prepared.json").is_file() for run in runs):
            return None
        budgets = [extraction_budget(run) for run in runs]
    except (KeyError, OSError, TypeError, ValueError):
        return None
    return (
        sum(int(item["fresh_mode_calls_upper_bound"]) for item in budgets),
        sum(int(item["parse_attempts_upper_bound"]) for item in budgets),
    )


def estimate_scale(
    plan: ExperimentPlan,
    *,
    experiment: Path | None = None,
    duration_train_days: tuple[int, ...] | None = None,
) -> Evaluation9Scale:
    """Estimate generation and API scale, preferring resumable artifact budgets."""
    condition_count = len(plan.conditions)
    seed_count = len(plan.seeds)
    time_band_count = len(TIME_MODES)
    hestia_run_count = condition_count * seed_count
    duration_count = len(duration_train_days) if duration_train_days else 1
    full_fresh_api_calls = (
        hestia_run_count * plan.llm_runs * time_band_count * duration_count
    )
    fresh_api_calls = full_fresh_api_calls
    parse_upper = full_fresh_api_calls * MAX_PARSE_RETRIES
    uses_existing_budget = False
    if experiment is not None:
        existing = _existing_budget(plan, experiment, duration_train_days)
        if existing is not None:
            fresh_api_calls, parse_upper = existing
            uses_existing_budget = True
    return Evaluation9Scale(
        condition_count=condition_count,
        seed_count=seed_count,
        llm_runs=plan.llm_runs,
        time_band_count=time_band_count,
        hestia_run_count=hestia_run_count,
        fresh_api_calls=fresh_api_calls,
        parse_attempts_upper_bound=parse_upper,
        full_fresh_api_calls=full_fresh_api_calls,
        uses_existing_budget=uses_existing_budget,
    )
