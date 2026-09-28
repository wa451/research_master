"""Formal Evaluation 6 condition and artifact resolution from Evaluation 7."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.behavior_pattern_mining.data.sensor_representation import (
    artifact_dataset_name,
    validate_sensor_representation,
)


@dataclass(frozen=True)
class Evaluation6ManifestCondition:
    n_states: int
    hamming_threshold: int
    sensor_representation: str
    generation_days: int | None
    split_mode: str | None
    validation_start_day: int | None
    validation_end_day: int | None
    test_start_day: int | None
    test_end_day: int | None


def load_evaluation7_best_condition_manifest(path: Path) -> Evaluation6ManifestCondition:
    """Read current and pre-schema-version Evaluation 7 best-condition files."""
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid best-condition manifest JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"best-condition manifest must be a JSON object: {path}")

    try:
        n_states = int(payload["n_states"] if "n_states" in payload else payload["K"])
        hamming_threshold = int(
            payload["hamming_threshold"] if "hamming_threshold" in payload else payload["h"]
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("best-condition manifest must contain K/n_states and h/hamming_threshold") from exc
    if n_states < 1 or hamming_threshold < 0:
        raise ValueError("best-condition manifest contains an invalid K or h")
    representation = validate_sensor_representation(payload.get("sensor_representation", "individual"))

    def optional_int(field: str) -> int | None:
        value = payload.get(field)
        return None if value is None else int(value)

    return Evaluation6ManifestCondition(
        n_states=n_states,
        hamming_threshold=hamming_threshold,
        sensor_representation=representation,
        generation_days=optional_int("generation_days"),
        split_mode=payload.get("split_mode"),
        validation_start_day=optional_int("validation_start_day"),
        validation_end_day=optional_int("validation_end_day"),
        test_start_day=optional_int("test_start_day"),
        test_end_day=optional_int("test_end_day"),
    )


def complete_holdout_condition(
    condition: Evaluation6ManifestCondition,
    *,
    default_generation_days: int,
) -> Evaluation6ManifestCondition:
    """Supply the established holdout fields absent from older manifests."""
    return Evaluation6ManifestCondition(
        n_states=condition.n_states,
        hamming_threshold=condition.hamming_threshold,
        sensor_representation=condition.sensor_representation,
        generation_days=condition.generation_days or default_generation_days,
        split_mode=condition.split_mode or "holdout",
        validation_start_day=condition.validation_start_day or 15,
        validation_end_day=condition.validation_end_day or 154,
        test_start_day=condition.test_start_day or 155,
        test_end_day=condition.test_end_day or 220,
    )


def formal_artifact_paths(
    *,
    project_root: Path,
    results_root: Path,
    output_root: Path | None = None,
    dataset: str,
    condition: Evaluation6ManifestCondition,
    llm_only_time_mode: str,
) -> dict[str, Path]:
    """Return the canonical run-1 paths for one formal Evaluation 6 condition."""
    if condition.generation_days is None:
        raise ValueError("best-condition manifest must record generation_days for formal holdout evaluation")
    artifact_dataset = artifact_dataset_name(dataset, condition.sensor_representation)
    suffix = f"{condition.n_states}_{condition.hamming_threshold}_{condition.generation_days}days"
    proposed_dir = results_root / f"{artifact_dataset}_{suffix}"
    direct_dir = f"llm_direct_{artifact_dataset}_{suffix}"
    if llm_only_time_mode == "split":
        direct_dir += "_time_split"
    state_dir = f"6_adl_evaluation_{artifact_dataset}_{suffix}"
    output_dir = results_root / f"6_adl_match_{condition.sensor_representation}_holdout_test"
    if llm_only_time_mode == "split":
        output_dir = output_dir.with_name(f"{output_dir.name}_direct_time_split")
    return {
        "patterns_proposed": proposed_dir / f"llm_sequences_modes_{suffix}_1.json",
        "patterns_direct": results_root / direct_dir / "1.json",
        # ``output_root`` is supplied by current callers so generated state
        # series share the selected LLM's namespace.  Keep the old root as a
        # read-compatible default for third-party callers during migration.
        "state_series": (output_root or project_root / "output") / state_dir / "state_series.csv",
        "proposed_metrics": proposed_dir / f"llm_modes_metrics_{suffix}_run1.csv",
        "direct_metrics": results_root / direct_dir / f"llm_direct_metrics_{condition.generation_days}days.csv",
        "output_dir": output_dir / suffix,
    }


def same_path(left: Path, right: Path) -> bool:
    """Compare CLI and canonical paths without requiring that either already exists."""
    return left.expanduser().resolve() == right.expanduser().resolve()
