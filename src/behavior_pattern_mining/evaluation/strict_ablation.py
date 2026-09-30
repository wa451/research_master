"""Shared contracts for Evaluation 6 strict-ablation generation and scoring."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from src.behavior_pattern_mining.evaluation.adl_interpretation_set import (
    ALLOWED_LABEL_SET,
    normalize_prediction_labels,
)
from src.behavior_pattern_mining.evaluation.evaluation6_manifest import (
    Evaluation6ManifestCondition,
    complete_holdout_condition,
    load_evaluation7_best_condition_manifest,
)
from src.behavior_pattern_mining.data.sensor_representation import artifact_dataset_name


COMPARISON_TYPE = "strict_ablation"
ABLATION_FACTOR = "state_transition_network_representation"
OUTPUT_SCHEMA_VERSION = "evaluation6_strict_ablation_v1"
PROMPT_FILENAME = "evaluation6_strict_ablation_prompt.md"


@dataclass(frozen=True)
class StrictAblationPaths:
    root: Path
    proposed_dir: Path
    llm_only_dir: Path
    state_table: Path
    network_dir: Path
    state_series: Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_strict_condition(manifest_path: Path) -> Evaluation6ManifestCondition:
    condition = complete_holdout_condition(
        load_evaluation7_best_condition_manifest(manifest_path),
        default_generation_days=14,
    )
    if condition.split_mode != "holdout":
        raise ValueError("strict ablation requires a holdout Evaluation 7 manifest")
    if (
        condition.generation_days != 14
        or condition.validation_start_day != 15
        or condition.validation_end_day != 154
        or condition.test_start_day != 155
        or condition.test_end_day != 220
    ):
        raise ValueError(
            "strict ablation requires Day 1-14 generation, Day 15-154 validation, "
            "and Day 155-220 test periods"
        )
    return condition


def selection_manifest_provenance(manifest_path: Path) -> dict[str, Any]:
    """Record the fixed Evaluation 7 condition source independently of the LLM under test."""
    payload: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"best-condition manifest must be a JSON object: {manifest_path}")
    model = payload.get("model")
    return {
        "path": str(manifest_path),
        "sha256": sha256_file(manifest_path),
        "model": model if isinstance(model, dict) else None,
        # Legacy Evaluation 7 manifests do not embed model metadata. Keep their
        # result namespace as provenance rather than treating it as the active LLM.
        "result_namespace": manifest_path.parent.parent.name,
    }


def strict_ablation_paths(
    *,
    project_root: Path,
    results_root: Path,
    output_root: Path,
    dataset: str,
    condition: Evaluation6ManifestCondition,
) -> StrictAblationPaths:
    artifact_dataset = artifact_dataset_name(dataset, condition.sensor_representation)
    suffix = f"{condition.n_states}_{condition.hamming_threshold}_{condition.generation_days}days"
    root = results_root / "6_strict_ablation" / f"{artifact_dataset}_{suffix}_holdout_test"
    return StrictAblationPaths(
        root=root,
        proposed_dir=root / "proposed",
        llm_only_dir=root / "llm_only",
        state_table=project_root / "state" / f"{artifact_dataset}_{suffix}.txt",
        network_dir=project_root / "picture" / f"{artifact_dataset}_{suffix}",
        state_series=output_root / f"6_adl_evaluation_{artifact_dataset}_{suffix}" / "state_series.csv",
    )


def strict_prompt_path(project_root: Path) -> Path:
    return project_root / "prompts" / PROMPT_FILENAME


def build_strict_prompt(
    prompt_template: str,
    *,
    state_table: str,
    time_band: str,
    representation_description: str,
    representation_data: str,
) -> str:
    return (
        prompt_template.replace("{STATE_TABLE}", state_table.strip())
        .replace("{TIME_BAND}", time_band)
        .replace("{REPRESENTATION_DESCRIPTION}", representation_description)
        .replace("{REPRESENTATION_DATA}", representation_data.strip())
    )


def _record_value(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in record and record[key] is not None:
            return record[key]
    return None


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def normalize_strict_record(record: dict[str, Any], time_band: str) -> dict[str, Any] | None:
    """Convert a parsed model record into the strict, method-independent schema."""
    sequence = _as_string_list(
        _record_value(record, "state_sequence", "遷移のパターン", "sequence", "states")
    )
    if not 2 <= len(sequence) <= 4:
        return None
    labels = normalize_prediction_labels(
        _record_value(record, "adl_sequence", "ADL系列ラベル", "adl_sequence_labels", "adl_labels")
    )
    if labels.status != "valid" or not labels.normalized_labels:
        return None
    if any(label not in ALLOWED_LABEL_SET for label in labels.normalized_labels):
        return None
    name = str(_record_value(record, "pattern_name", "パターン名", "name") or "").strip()
    rationale = str(_record_value(record, "rationale", "解釈の根拠", "reason") or "").strip()
    if not name or not rationale:
        return None
    return {
        "time_band": time_band,
        "pattern_name": name,
        "adl_sequence": list(labels.normalized_labels),
        "rationale": rationale,
        "state_sequence": sequence,
    }


def postprocess_strict_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply one normalized sequence-times-band deduplication rule to both methods."""
    deduplicated: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}
    for record in records:
        time_band = str(record.get("time_band") or "").strip()
        normalized = normalize_strict_record(record, time_band)
        if normalized is None:
            continue
        key = (time_band, tuple(normalized["state_sequence"]))
        deduplicated.setdefault(key, normalized)
    return list(deduplicated.values())


def completed_run_ids(method_dir: Path, requested_runs: Iterable[int]) -> list[int]:
    """Return only runs whose metadata records successful calls for every time band."""
    completed: list[int] = []
    for run_id in requested_runs:
        metadata_path = method_dir / f"run_{run_id}_metadata.json"
        output_path = method_dir / f"run_{run_id}.json"
        if not metadata_path.exists() or not output_path.exists():
            continue
        try:
            import json

            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if metadata.get("status") == "complete":
            completed.append(run_id)
    return completed
