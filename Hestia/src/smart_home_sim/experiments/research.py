"""Isolate external dependencies, API execution, and resumable provenance."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from smart_home_sim.experiments.artifacts import (
    file_hash,
    read_json,
    tree_hashes,
    verify_files,
    write_json,
)
from smart_home_sim.experiments.metrics import parse_predictions


def _validate_llm_output(path: Path) -> None:
    """Reject syntactically valid JSON that cannot be scored by evaluation."""
    try:
        parse_predictions(read_json(path), require_labels=True)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid completed LLM output: {path} ({exc})") from exc


def _invalid_output_modes(payload: Any) -> set[str]:
    """Return modes that contributed an invalid record, or all modes if unclear."""
    all_modes = {"Midnight", "Morning", "Daytime", "Night"}
    if not isinstance(payload, list):
        return all_modes
    invalid_modes: set[str] = set()
    for record in payload:
        if not isinstance(record, dict):
            return all_modes
        sequence = record.get("sequence", record.get("遷移のパターン"))
        if (
            not isinstance(sequence, list)
            or not all(isinstance(item, str) for item in sequence)
            or not 2 <= len(sequence) <= 4
        ):
            interpretations = record.get("time_band_interpretations")
            if isinstance(interpretations, dict):
                invalid_modes.update(mode for mode in interpretations if mode in all_modes)
            else:
                mode = record.get("mode")
                if mode in all_modes:
                    invalid_modes.add(mode)
                else:
                    return all_modes
    return invalid_modes or all_modes


def _archive_invalid_llm_output(
    artifact_run: Path,
    index: int,
    output: Path,
) -> Path:
    """Preserve an unscorable response and clear only its affected mode checkpoints."""
    payload = read_json(output) if output.is_file() else None
    modes = _invalid_output_modes(payload)
    prediction_dir = artifact_run / "predictions/llm"
    attempts_root = prediction_dir / "invalid_completed"
    attempt = 1
    while (attempts_root / f"run_{index}_attempt_{attempt}").exists():
        attempt += 1
    archive = attempts_root / f"run_{index}_attempt_{attempt}"
    archive.mkdir(parents=True)

    paths = [output, prediction_dir / f"complete_{index}.json"]
    # The output/metric filename parameters live in the experiment plan, so move
    # the run-specific metrics file by glob instead of re-deriving its name here.
    paths.extend(prediction_dir.glob(f"llm_modes_metrics_*_run{index}.csv"))
    for mode in modes:
        paths.extend(
            [
                prediction_dir / f"llm_mode_records_run{index}" / f"state_transition_{mode}.json",
                prediction_dir / f"llm_mode_records_run{index}" / f"state_transition_{mode}_raw.txt",
                prediction_dir / f"llm_mode_records_run{index}" / f"state_transition_{mode}_metrics.json",
            ]
        )
    for path in paths:
        if path.is_file():
            destination = archive / path.relative_to(prediction_dir)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(destination))
    return archive


def research_provenance(root: Path) -> dict[str, Any]:
    python = root / ".venv/bin/python"
    if not python.is_file():
        raise ValueError(f"research runtime missing: {python}")
    paths = [
        root / "experiment_config.py",
        root / "uv.lock",
        root / "pyproject.toml",
        root / "prompts/pattern_extraction_prompt.md",
        root / "scripts/run_build_network_from_labeled_casas.py",
    ]
    paths.extend((root / "src").rglob("*.py"))
    paths.extend((root / "configs").glob("*.yaml"))
    version = subprocess.run([str(python), "--version"], check=True, capture_output=True, text=True)
    return {
        "python": version.stdout.strip(),
        "files": {
            path.relative_to(root).as_posix(): file_hash(path)
            for path in sorted(set(paths))
            if path.is_file()
        },
        "adapter_sha256": file_hash(Path(__file__).with_name("research_worker.py")),
    }


def _worker(
    action: str,
    run: Path,
    root: Path,
    run_id: int = 1,
    llm_output_dir: Path | None = None,
) -> None:
    environment = dict(os.environ)
    runtime_root = (
        llm_output_dir.parent.parent / "runtime"
        if action == "extract" and llm_output_dir is not None
        else run / "runtime"
    )
    environment["MPLBACKEND"] = "Agg"
    environment["MPLCONFIGDIR"] = str(runtime_root / "matplotlib")
    log = runtime_root / f"{action}_{run_id}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(root / ".venv/bin/python"),
        str(Path(__file__).with_name("research_worker.py")),
        action,
        "--research-root",
        str(root),
        "--run",
        str(run),
        "--run-id",
        str(run_id),
    ]
    if llm_output_dir is not None:
        command.extend(["--llm-output-dir", str(llm_output_dir)])
    with log.open("w", encoding="utf-8") as stream:
        result = subprocess.run(
            command, cwd=run, env=environment, stdout=stream, stderr=subprocess.STDOUT, check=False
        )
    if result.returncode:
        raise RuntimeError(f"research {action} failed ({result.returncode}); inspect {log}")


def prepare(run: Path, research_root: Path) -> None:
    root = research_root.resolve()
    run = run.resolve()
    verify_files(run, read_json(run / "generated.json")["files"])
    source = research_provenance(root)
    marker = run / "prepared.json"
    if marker.exists():
        previous = read_json(marker)
        if previous["research"] != source:
            raise ValueError("research code/settings changed; use a new experiment output")
        verify_files(run, previous["files"])
        return
    analysis = run / "analysis"
    if analysis.exists() and any(analysis.iterdir()):
        raise ValueError(f"incomplete preparation at {analysis}; use a new output directory")
    analysis.mkdir(parents=True, exist_ok=True)
    _worker("prepare", run, root)
    write_json(
        marker,
        {
            "research": source,
            "files": {f"analysis/{name}": digest for name, digest in tree_hashes(analysis).items()},
        },
    )


def extraction_budget(run: Path, artifact_run: Path | None = None) -> dict[str, Any]:
    verify_prepared(run)
    modes = len(
        [
            path
            for path in (run / "analysis/networks").glob("state_transition_*.json")
            if path.name != "state_transition_all.json"
        ]
    )
    repetitions = read_json(run / "run.json")["plan"]["llm_runs"]
    settings = read_json(run / "analysis/llm_settings.json")
    artifact_run = artifact_run or run
    pending = [
        index
        for index in range(1, repetitions + 1)
        if not (artifact_run / f"predictions/llm/complete_{index}.json").exists()
    ]
    return {
        "run": str(run),
        "modes": modes,
        "repetitions": repetitions,
        "pending_run_ids": pending,
        "fresh_mode_calls_upper_bound": modes * len(pending),
        "parse_attempts_upper_bound": modes * len(pending) * settings["max_parse_retries"],
        **settings,
    }


def verify_prepared(run: Path) -> None:
    verify_files(run, read_json(run / "generated.json")["files"])
    expected = read_json(run / "prepared.json")["files"]
    verify_files(run, expected)
    actual = {f"analysis/{name}": digest for name, digest in tree_hashes(run / "analysis").items()}
    if actual != expected:
        raise ValueError(
            "analysis artifacts changed (including unexpected files); use a new output"
        )


def llm_output(run: Path, index: int, artifact_run: Path | None = None) -> Path:
    plan = read_json(run / "run.json")["plan"]
    return (
        (artifact_run or run)
        / "predictions/llm"
        / (
            f"llm_sequences_modes_{plan['n_states']}_{plan['hamming_threshold']}_"
            f"{plan['train_days']}days_{index}.json"
        )
    )


def extract(
    run: Path,
    research_root: Path,
    artifact_run: Path | None = None,
    model_id: str | None = None,
) -> None:
    verify_prepared(run)
    root = research_root.resolve()
    if read_json(run / "prepared.json")["research"] != research_provenance(root):
        raise ValueError("research code/settings changed after preparation")
    artifact_run = artifact_run or run
    request = artifact_run / "predictions/llm/request.json"
    model_metadata_path = artifact_run / "predictions/llm/model_metadata.json"
    if model_metadata_path.is_file() and model_id:
        recorded_model = read_json(model_metadata_path).get("model_id")
        if recorded_model != model_id:
            raise ValueError(
                f"LLM artifacts belong to a different model: {recorded_model!r} != {model_id!r}"
            )
    fingerprint = {
        "prepared_sha256": file_hash(run / "prepared.json"),
        "model_id": model_id,
    }
    if request.exists():
        previous_request = read_json(request)
        legacy_gemini_request = {
            "prepared_sha256": fingerprint["prepared_sha256"],
        }
        if previous_request != fingerprint and not (
            previous_request == legacy_gemini_request
            and model_id == "gemini-2.5-pro"
            and model_metadata_path.is_file()
        ):
            raise ValueError("LLM checkpoints belong to different inputs/settings")
    elif request.parent.exists() and any(request.parent.iterdir()):
        raise ValueError("unbound LLM artifacts found; preserve them and use a new output")
    else:
        write_json(request, fingerprint)
    settings = read_json(run / "run.json")["plan"]
    for index in range(1, settings["llm_runs"] + 1):
        marker = artifact_run / f"predictions/llm/complete_{index}.json"
        output = llm_output(run, index, artifact_run)
        if marker.exists():
            verify_files(artifact_run, read_json(marker)["files"])
            try:
                _validate_llm_output(output)
            except ValueError:
                archive = _archive_invalid_llm_output(artifact_run, index, output)
                print(f"Archived invalid LLM output for run {index}: {archive}")
            else:
                continue
        _worker(
            "extract",
            run,
            root,
            index,
            artifact_run / "predictions/llm",
        )
        if not output.is_file():
            raise ValueError(f"missing or invalid completed LLM output: {output}")
        try:
            _validate_llm_output(output)
        except ValueError:
            _archive_invalid_llm_output(artifact_run, index, output)
            raise
        files = {output.relative_to(artifact_run).as_posix(): file_hash(output)}
        checkpoints = artifact_run / f"predictions/llm/llm_mode_records_run{index}"
        files.update(
            {
                path.relative_to(artifact_run).as_posix(): file_hash(path)
                for path in sorted(checkpoints.rglob("*"))
                if path.is_file()
            }
        )
        write_json(marker, {"files": files})
