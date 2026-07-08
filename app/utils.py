"""Utilities for command execution, logs, and result discovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Callable, Iterable

from app.command_builder import PROJECT_ROOT, command_preview, display_path


SECRET_RE = re.compile(r"(?i)(api[_-]?key|token|secret|password)(=|:)\s*([^\s]+)")


@dataclass
class CommandResult:
    returncode: int
    elapsed_seconds: float
    log_path: Path
    output: str


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def safe_run_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", name.strip())
    return cleaned.strip("_") or "run"


def redact_text(text: str) -> str:
    redacted = SECRET_RE.sub(r"\1\2 [REDACTED]", text)
    for key, value in os.environ.items():
        if not value or len(value) < 8:
            continue
        upper = key.upper()
        if any(marker in upper for marker in ["API_KEY", "TOKEN", "SECRET", "PASSWORD"]):
            redacted = redacted.replace(value, "[REDACTED]")
    return redacted


def ensure_log_dir(base_dir: Path, evaluation: str, run_name: str) -> Path:
    log_dir = base_dir / safe_run_name(evaluation) / f"{now_stamp()}_{safe_run_name(run_name)}"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def append_history(log_root: Path, record: dict) -> None:
    log_root.mkdir(parents=True, exist_ok=True)
    history_path = log_root / "command_history.jsonl"
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_command(
    command: list[str],
    *,
    cwd: Path = PROJECT_ROOT,
    log_path: Path,
    on_output: Callable[[str], None] | None = None,
) -> CommandResult:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    output_parts: list[str] = []
    with log_path.open("w", encoding="utf-8") as log_file:
        header = f"$ {command_preview(command)}\n\n"
        log_file.write(header)
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = redact_text(raw_line)
            output_parts.append(line)
            log_file.write(line)
            log_file.flush()
            if on_output is not None:
                on_output("".join(output_parts))
        returncode = process.wait()
    elapsed = time.monotonic() - started
    return CommandResult(
        returncode=returncode,
        elapsed_seconds=elapsed,
        log_path=log_path,
        output="".join(output_parts),
    )


def file_status_rows(paths: Iterable[Path]) -> list[dict[str, str]]:
    rows = []
    for path in paths:
        exists = path.exists()
        rows.append(
            {
                "path": display_path(path),
                "status": "exists" if exists else "missing",
                "size": str(path.stat().st_size) if exists and path.is_file() else "",
            }
        )
    return rows


def discover_result_files(base_dirs: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for base_dir in base_dirs:
        if not base_dir.exists():
            continue
        for pattern in ("*.csv", "*.json"):
            files.extend(base_dir.rglob(pattern))
    return sorted(set(files))


def discover_result_dirs() -> list[Path]:
    candidates = [
        PROJECT_ROOT / "results" / "4_adl_evaluation",
        PROJECT_ROOT / "results" / "5_adl_correspondence",
        PROJECT_ROOT / "results" / "6_adl_interpretation_set_comparison",
        PROJECT_ROOT / "results" / "7_parameter_sensitivity_adl_interpretation",
        PROJECT_ROOT / "output" / "6_adl_evaluation_30",
        PROJECT_ROOT / "output" / "6_adl_evaluation_30_1_30days",
    ]
    dirs: set[Path] = set()
    for candidate in candidates:
        if candidate.exists():
            dirs.add(candidate)
            for child in candidate.rglob("*"):
                if child.is_dir() and any(child.glob("*.csv")) or child.is_dir() and any(child.glob("*.json")):
                    dirs.add(child)
    return sorted(dirs)


def load_history(log_root: Path, limit: int = 200) -> list[dict]:
    history_path = log_root / "command_history.jsonl"
    if not history_path.exists():
        return []
    lines = history_path.read_text(encoding="utf-8").splitlines()
    records = []
    for line in lines[-limit:]:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def metric_columns(columns: Iterable[str]) -> list[str]:
    preferred = [
        "mean_multilabel_f1",
        "multilabel_f1",
        "f1",
        "macro_f1",
        "micro_f1",
        "adl_grounded_pattern_rate",
        "useless_pattern_rate",
        "mean_exact_set_match",
        "mean_accuracy",
        "mean_jaccard",
        "precision",
        "recall",
        "accuracy",
    ]
    available = list(columns)
    matched = [name for name in preferred if name in available]
    matched.extend([name for name in available if name not in matched and any(token in name.lower() for token in ["f1", "precision", "recall", "accuracy", "jaccard"])])
    return matched
