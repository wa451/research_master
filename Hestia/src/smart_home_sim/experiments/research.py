"""Isolate external dependencies, API execution, and resumable provenance."""

from __future__ import annotations

import os
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


def _worker(action: str, run: Path, root: Path, run_id: int = 1) -> None:
    environment = dict(os.environ)
    environment["MPLBACKEND"] = "Agg"
    environment["MPLCONFIGDIR"] = str(run / "runtime/matplotlib")
    log = run / "runtime" / f"{action}_{run_id}.log"
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


def extraction_budget(run: Path) -> dict[str, Any]:
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
    pending = [
        index
        for index in range(1, repetitions + 1)
        if not (run / f"predictions/llm/complete_{index}.json").exists()
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


def llm_output(run: Path, index: int) -> Path:
    plan = read_json(run / "run.json")["plan"]
    return (
        run
        / "predictions/llm"
        / (
            f"llm_sequences_modes_{plan['n_states']}_{plan['hamming_threshold']}_"
            f"{plan['train_days']}days_{index}.json"
        )
    )


def extract(run: Path, research_root: Path) -> None:
    verify_prepared(run)
    root = research_root.resolve()
    if read_json(run / "prepared.json")["research"] != research_provenance(root):
        raise ValueError("research code/settings changed after preparation")
    request = run / "predictions/llm/request.json"
    fingerprint = {"prepared_sha256": file_hash(run / "prepared.json")}
    if request.exists():
        if read_json(request) != fingerprint:
            raise ValueError("LLM checkpoints belong to different inputs/settings")
    elif request.parent.exists() and any(request.parent.iterdir()):
        raise ValueError("unbound LLM artifacts found; preserve them and use a new output")
    else:
        write_json(request, fingerprint)
    settings = read_json(run / "run.json")["plan"]
    for index in range(1, settings["llm_runs"] + 1):
        marker = run / f"predictions/llm/complete_{index}.json"
        if marker.exists():
            verify_files(run, read_json(marker)["files"])
            continue
        _worker("extract", run, root, index)
        output = llm_output(run, index)
        if not output.is_file() or not isinstance(read_json(output), list):
            raise ValueError(f"missing or invalid completed LLM output: {output}")
        files = {output.relative_to(run).as_posix(): file_hash(output)}
        checkpoints = run / f"predictions/llm/llm_mode_records_run{index}"
        files.update(
            {
                path.relative_to(run).as_posix(): file_hash(path)
                for path in sorted(checkpoints.rglob("*"))
                if path.is_file()
            }
        )
        write_json(marker, {"files": files})
