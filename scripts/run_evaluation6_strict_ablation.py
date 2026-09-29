#!/usr/bin/env python3
"""Generate Evaluation 6 Strict Ablation LLM artifacts without touching full-pipeline outputs."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from experiment_config import (
    BEDROCK_ESTIMATED_OUTPUT_TOKENS,
    BEDROCK_MAX_TOKENS,
    BEDROCK_REGION,
    BEDROCK_MODEL_ID,
    DATASET_NAME,
    LLM_MODEL_NAME,
    LLM_PROVIDER,
    LLM_TEMPERATURE,
    SMOOTHING_WINDOW_SEC,
    TIME_MODES,
    current_model_identity,
    current_model_output_root,
    current_model_results_root,
)
from src.behavior_pattern_mining.data.sensor_representation import sensor_map_path
from src.behavior_pattern_mining.evaluation.strict_ablation import (
    ABLATION_FACTOR,
    COMPARISON_TYPE,
    OUTPUT_SCHEMA_VERSION,
    build_strict_prompt,
    load_strict_condition,
    normalize_strict_record,
    postprocess_strict_records,
    sha256_file,
    strict_ablation_paths,
    strict_prompt_path,
    validate_manifest_model,
)
from src.behavior_pattern_mining.llm import direct_log_extractor
from src.behavior_pattern_mining.llm.client import (
    call_llm,
    load_dotenv,
    parse_pattern_records,
    resolve_llm_runtime_config,
)
from src.behavior_pattern_mining.llm.result_paths import ensure_model_artifact_directory
from src.behavior_pattern_mining.visualization import state_transition_visualizer as stv


REPRESENTATION_DESCRIPTIONS = {
    "proposed": "入力は状態遷移ネットワークです。nodesとedgesに記録された情報だけを読み取ってください。",
    "llm_only": "入力は時刻順の代表状態列です。各行に記録された状態列だけを読み取ってください。",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--best-condition-manifest", required=True, type=Path)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true", help="Build and inspect inputs without any LLM API call or artifact write.")
    parser.add_argument("--inspect-time-band", choices=list(TIME_MODES), default="Morning")
    parser.add_argument("--n-states", type=int, default=None, help="Validation-only override; must match the manifest.")
    parser.add_argument("--hamming-threshold", type=int, default=None, help="Validation-only override; must match the manifest.")
    return parser.parse_args()


def _validate_overrides(args: argparse.Namespace, condition: Any) -> None:
    if args.runs < 1:
        raise ValueError("--runs must be >= 1")
    if args.n_states is not None and args.n_states != condition.n_states:
        raise ValueError("--n-states conflicts with --best-condition-manifest")
    if args.hamming_threshold is not None and args.hamming_threshold != condition.hamming_threshold:
        raise ValueError("--hamming-threshold conflicts with --best-condition-manifest")


def _load_direct_series(condition: Any, state_table: Path) -> dict[str, str]:
    """Build the same network-equivalent mapped series used by the current direct baseline."""
    source_log = direct_log_extractor.INPUT_LOG_PATH
    csv_path, tmpdir, _ = direct_log_extractor.prepare_input_csv(
        source_log,
        sensor_map_path(ROOT_DIR, condition.sensor_representation),
        f"{DATASET_NAME}_{condition.sensor_representation}",
    )
    try:
        visualizer = stv.StateTransitionVisualizer(
            n_representative_states=condition.n_states,
            hamming_threshold=condition.hamming_threshold,
            data_duration_days=condition.generation_days,
            smoothing_window_sec=SMOOTHING_WINDOW_SEC,
        )
        vectors = visualizer.create_state_vectors(visualizer.load_data(str(csv_path)))
        _, vector_to_label = direct_log_extractor.load_state_definition(state_table)
        labels, _ = direct_log_extractor.map_vectors_to_states(
            vectors, vector_to_label, condition.hamming_threshold
        )
        grouped = direct_log_extractor.split_state_labels_by_time_period(vectors.index, labels)
        return {
            band: "\n".join(
                direct_log_extractor.state_lines_for_time_period(
                    direct_log_extractor.compress_consecutive_state_labels(items)
                )
            )
            for band, items in grouped.items()
        }
    finally:
        if tmpdir is not None:
            tmpdir.cleanup()


def _stn_inputs(network_dir: Path) -> dict[str, str]:
    paths = {band: network_dir / f"state_transition_{band}.json" for band in TIME_MODES}
    missing = [str(path) for path in paths.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("Strict ablation STN inputs are missing:\n- " + "\n- ".join(missing))
    return {band: path.read_text(encoding="utf-8") for band, path in paths.items()}


def _provenance(
    *,
    condition: Any,
    identity: Any,
    prompt_path: Path,
    state_table: Path,
    source_log: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    generation_start = manifest.get("generation_start")
    generation_end = manifest.get("generation_end")
    if not generation_start or not generation_end:
        raise ValueError("strict ablation manifest must record generation_start and generation_end")
    generation_start_dt = datetime.fromisoformat(str(generation_start))
    test_start = generation_start_dt + timedelta(days=condition.test_start_day - 1)
    test_end = generation_start_dt + timedelta(days=condition.test_end_day)
    return {
        "comparison_type": COMPARISON_TYPE,
        "ablation_factor": ABLATION_FACTOR,
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "model": {"provider": identity.provider, "model_id": identity.model_id, "result_name": identity.result_name},
        "n_states": condition.n_states,
        "hamming_threshold": condition.hamming_threshold,
        "sensor_representation": condition.sensor_representation,
        "source_log": str(source_log),
        "source_log_sha256": sha256_file(source_log),
        "state_table": str(state_table),
        "state_table_sha256": sha256_file(state_table),
        "prompt_path": str(prompt_path),
        "prompt_sha256": sha256_file(prompt_path),
        "preprocessing": {
            "sampling_interval": "1s",
            "smoothing_window_sec": SMOOTHING_WINDOW_SEC,
            "state_mapping": "exact_then_nearest_hamming_with_state_table_tiebreak",
            "time_bands": TIME_MODES,
        },
        "generation_days": condition.generation_days,
        "generation_start": str(generation_start),
        "generation_end": str(generation_end),
        "validation_start_day": condition.validation_start_day,
        "validation_end_day": condition.validation_end_day,
        "test_start_day": condition.test_start_day,
        "test_end_day": condition.test_end_day,
        "test_start": test_start.isoformat(sep=" "),
        "test_end": test_end.isoformat(sep=" "),
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _generate_method(
    *,
    method: str,
    inputs: dict[str, str],
    prompt_template: str,
    state_table_text: str,
    method_dir: Path,
    provenance: dict[str, Any],
    llm_config: Any,
    run_id: int,
) -> None:
    raw_records: list[dict[str, Any]] = []
    processed_candidates: list[dict[str, Any]] = []
    time_band_metadata: list[dict[str, Any]] = []
    for time_band, representation_data in inputs.items():
        prompt = build_strict_prompt(
            prompt_template,
            state_table=state_table_text,
            time_band=time_band,
            representation_description=REPRESENTATION_DESCRIPTIONS[method],
            representation_data=representation_data,
        )
        entry: dict[str, Any] = {"time_band": time_band, "status": "failure"}
        try:
            response_text, backend, usage, duration_sec = call_llm(llm_config, prompt)
            parsed = parse_pattern_records(response_text)
            canonical = [
                record for item in parsed
                if (record := normalize_strict_record(item, time_band)) is not None
            ]
            raw_records.extend(canonical)
            processed_candidates.extend(canonical)
            entry.update({
                "status": "success", "backend": backend, "duration_sec": duration_sec,
                "prompt_tokens": usage.get("prompt_tokens"), "response_tokens": usage.get("response_tokens"),
                "total_tokens": usage.get("total_tokens"), "raw_record_count": len(canonical),
            })
        except Exception as exc:  # Preserve a failed run for paired-run selection.
            entry["error"] = str(exc)
        time_band_metadata.append(entry)

    status = "complete" if all(row["status"] == "success" for row in time_band_metadata) else "failed"
    metadata = {
        **provenance,
        "method": method,
        "run_id": run_id,
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "time_bands": time_band_metadata,
    }
    _write_json(method_dir / f"run_{run_id}_metadata.json", metadata)
    if status == "complete":
        _write_json(method_dir / "raw" / f"run_{run_id}.json", raw_records)
        _write_json(method_dir / f"run_{run_id}.json", postprocess_strict_records(processed_candidates))


def main() -> None:
    args = parse_args()
    condition = load_strict_condition(args.best_condition_manifest)
    _validate_overrides(args, condition)
    identity = current_model_identity()
    validate_manifest_model(
        args.best_condition_manifest, provider=identity.provider,
        model_id=identity.model_id, result_name=identity.result_name,
    )
    paths = strict_ablation_paths(
        project_root=ROOT_DIR, results_root=current_model_results_root(), output_root=current_model_output_root(),
        dataset=DATASET_NAME, condition=condition,
    )
    prompt_path = strict_prompt_path(ROOT_DIR)
    required = [prompt_path, paths.state_table, direct_log_extractor.INPUT_LOG_PATH]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Strict ablation inputs are missing:\n- " + "\n- ".join(missing))
    stn_inputs = _stn_inputs(paths.network_dir)
    direct_inputs = _load_direct_series(condition, paths.state_table)
    prompt_template = prompt_path.read_text(encoding="utf-8")
    state_table_text = paths.state_table.read_text(encoding="utf-8")
    provenance = _provenance(
        condition=condition, identity=identity, prompt_path=prompt_path,
        state_table=paths.state_table, source_log=direct_log_extractor.INPUT_LOG_PATH,
        manifest_path=args.best_condition_manifest,
    )

    if args.dry_run:
        band = args.inspect_time_band
        for method, inputs in (("proposed", stn_inputs), ("llm_only", direct_inputs)):
            message = build_strict_prompt(
                prompt_template, state_table=state_table_text, time_band=band,
                representation_description=REPRESENTATION_DESCRIPTIONS[method], representation_data=inputs[band],
            )
            print(f"{method}: time_band={band} input_characters={len(message)} approximate_tokens={len(message) // 4}")
        print("dry-run complete: no LLM API call and no artifact write")
        return

    load_dotenv(ROOT_DIR / ".env")
    llm_config = resolve_llm_runtime_config(
        default_provider=LLM_PROVIDER, gemini_model_name=LLM_MODEL_NAME, temperature=LLM_TEMPERATURE,
        bedrock_region=BEDROCK_REGION, bedrock_model_id=BEDROCK_MODEL_ID,
        bedrock_max_tokens=BEDROCK_MAX_TOKENS, bedrock_estimated_output_tokens=BEDROCK_ESTIMATED_OUTPUT_TOKENS,
    )
    if llm_config.model_name != identity.model_id:
        raise RuntimeError("active LLM runtime does not match the result namespace model")
    for method_dir in (paths.proposed_dir, paths.llm_only_dir):
        ensure_model_artifact_directory(
            method_dir, identity, temperature=llm_config.temperature, region=llm_config.region_name,
            max_tokens=llm_config.max_tokens,
            extra={"comparison_type": COMPARISON_TYPE, "output_schema_version": OUTPUT_SCHEMA_VERSION},
        )
    _write_json(paths.root / "manifest.json", {
        **provenance, "best_condition_manifest": str(args.best_condition_manifest),
        "runs_requested": args.runs, "strict_generation_contract": "Day 1-14 only; Day 155-220 is evaluation-only",
    })
    for run_id in range(1, args.runs + 1):
        for method, inputs, directory in (("proposed", stn_inputs, paths.proposed_dir), ("llm_only", direct_inputs, paths.llm_only_dir)):
            if (directory / f"run_{run_id}_metadata.json").exists():
                raise FileExistsError(f"strict ablation run already exists and will not be overwritten: {directory / f'run_{run_id}_metadata.json'}")
            _generate_method(method=method, inputs=inputs, prompt_template=prompt_template, state_table_text=state_table_text,
                             method_dir=directory, provenance=provenance, llm_config=llm_config, run_id=run_id)
    print(f"Strict ablation generation saved to: {paths.root}")


if __name__ == "__main__":
    main()
