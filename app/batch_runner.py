"""Detached, observable batch execution for the Streamlit dashboard.

The worker receives a fully resolved command plan from the dashboard.  It never
constructs evaluation commands, so the dashboard remains the single UI-to-CLI
adapter and the evaluation implementations stay unchanged.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping

from app.command_builder import PROJECT_ROOT, command_preview, display_path
from app.utils import append_history, redact_text, run_command


BATCH_SCHEMA_VERSION = 1
ACTIVE_BATCH_STATUSES = frozenset({"queued", "running"})


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Atomically replace a dashboard control file so readers never see partial JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def initial_status(plan: Mapping[str, Any]) -> dict[str, Any]:
    steps = list(plan.get("steps", []))
    return {
        "schema_version": BATCH_SCHEMA_VERSION,
        "evaluation": plan["evaluation"],
        "model_label": plan["model_label"],
        "batch_mode": plan["batch_mode"],
        "dry_run": bool(plan["dry_run"]),
        "status": "queued",
        "created_at": timestamp(),
        "started_at": None,
        "finished_at": None,
        "updated_at": timestamp(),
        "worker_pid": None,
        "total_steps": len(steps),
        "completed_steps": 0,
        "current_step_index": None,
        "current_step_id": None,
        "current_step_title": None,
        "current_log_path": None,
        "declared_output_paths": list(plan.get("declared_output_paths", [])),
        "steps": [
            {
                "index": step["index"],
                "step_id": step["step_id"],
                "title": step["title"],
                "status": "pending",
                "log_path": step["log_path"],
            }
            for step in steps
        ],
    }


def create_batch_artifacts(plan_path: Path, plan: dict[str, Any]) -> Path:
    """Persist the immutable command plan and its initial observable status."""
    status_path = plan_path.with_name("batch_status.json")
    plan = {**plan, "schema_version": BATCH_SCHEMA_VERSION, "status_path": str(status_path)}
    write_json(plan_path, plan)
    write_json(status_path, initial_status(plan))
    return status_path


def launch_batch_worker(plan_path: Path, worker_log_path: Path) -> subprocess.Popen:
    """Start a detached worker that survives Streamlit reruns and page changes."""
    worker_log_path.parent.mkdir(parents=True, exist_ok=True)
    with worker_log_path.open("w", encoding="utf-8") as worker_log:
        process = subprocess.Popen(
            [sys.executable, "-m", "app.batch_runner", "--plan", str(plan_path)],
            cwd=str(PROJECT_ROOT),
            stdin=subprocess.DEVNULL,
            stdout=worker_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    return process


def discover_batch_statuses(output_root: Path) -> list[tuple[Path, dict[str, Any]]]:
    """Read every model-scoped dashboard batch status without trusting malformed files."""
    statuses: list[tuple[Path, dict[str, Any]]] = []
    for path in output_root.glob("*/logs/evaluation_dashboard/*/*/batch_status.json"):
        status = read_json(path)
        if status is not None and status.get("schema_version") == BATCH_SCHEMA_VERSION:
            statuses.append((path, status))
    return sorted(statuses, key=lambda item: str(item[1].get("created_at", "")), reverse=True)


def _update_status(status_path: Path, state: dict[str, Any], **changes: Any) -> None:
    state.update(changes)
    state["updated_at"] = timestamp()
    write_json(status_path, state)


def _step_status(status: dict[str, Any], index: int) -> dict[str, Any]:
    return status["steps"][index - 1]


def run_batch_plan(plan_path: Path) -> dict[str, Any]:
    """Run resolved steps serially in a detached worker and update status after each step."""
    plan = read_json(plan_path)
    if plan is None:
        raise ValueError(f"Invalid batch plan: {plan_path}")
    status_path = Path(plan["status_path"])
    status = read_json(status_path) or initial_status(plan)
    _update_status(
        status_path,
        status,
        status="running",
        started_at=timestamp(),
        worker_pid=os.getpid(),
    )

    log_root = Path(plan["log_root"])
    project_root = Path(plan["project_root"])
    environment = {str(key): str(value) for key, value in dict(plan.get("model_environment", {})).items()}
    completed = 0
    try:
        for raw_step in plan["steps"]:
            index = int(raw_step["index"])
            step_status = _step_status(status, index)
            log_path = Path(raw_step["log_path"])
            _update_status(
                status_path,
                status,
                current_step_index=index,
                current_step_id=raw_step["step_id"],
                current_step_title=raw_step["title"],
                current_log_path=str(log_path),
            )
            step_status["status"] = "running"
            step_status["started_at"] = timestamp()
            write_json(status_path, status)

            record = {
                "evaluation": plan["evaluation"],
                "step_id": raw_step["step_id"],
                "title": raw_step["title"],
                "dry_run": bool(plan["dry_run"]),
                "batch": True,
                "batch_mode": plan["batch_mode"],
                "command": raw_step["command"],
                "command_preview": command_preview(raw_step["command"]),
                "model_id": plan["model_id"],
                "model_label": plan["model_label"],
                "model_environment": environment,
                "log_path": display_path(log_path),
            }
            environment_preview = " ".join(f"{key}={value}" for key, value in sorted(environment.items()))
            command_header = f"$ {command_preview(raw_step['command'])}\n"
            if environment_preview:
                command_header += f"# subprocess environment: {environment_preview}\n"
            missing_inputs = [Path(path) for path in raw_step["required_inputs"] if not Path(path).exists()]
            if missing_inputs and not plan["dry_run"]:
                missing_text = "\n".join(f"- {display_path(path)}" for path in missing_inputs)
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text(
                    f"{command_header}\nSTOPPED: missing required inputs.\n{missing_text}\n",
                    encoding="utf-8",
                )
                append_history(log_root, {**record, "status": "blocked_missing_inputs"})
                step_status.update({"status": "blocked_missing_inputs", "finished_at": timestamp()})
                _update_status(
                    status_path,
                    status,
                    status="blocked_missing_inputs",
                    finished_at=timestamp(),
                )
                return status

            append_history(log_root, record)
            if plan["dry_run"]:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text(command_header, encoding="utf-8")
                result_status = "dry_run"
                elapsed_seconds = 0.0
                returncode = 0
            else:
                result = run_command(
                    raw_step["command"],
                    cwd=project_root,
                    log_path=log_path,
                    environment_overrides=environment,
                )
                result_status = "succeeded" if result.returncode == 0 else "failed"
                elapsed_seconds = result.elapsed_seconds
                returncode = result.returncode

            step_status.update(
                {
                    "status": result_status,
                    "returncode": returncode,
                    "elapsed_seconds": elapsed_seconds,
                    "finished_at": timestamp(),
                }
            )
            if returncode != 0:
                _update_status(status_path, status, status="failed", finished_at=timestamp())
                return status

            completed += 1
            _update_status(status_path, status, completed_steps=completed)

        _update_status(
            status_path,
            status,
            status="succeeded",
            current_step_index=None,
            current_step_id=None,
            current_step_title=None,
            current_log_path=None,
            finished_at=timestamp(),
        )
    except Exception as exc:  # pragma: no cover - defensive worker boundary
        _update_status(
            status_path,
            status,
            status="failed",
            error=redact_text(f"{type(exc).__name__}: {exc}"),
            finished_at=timestamp(),
        )
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a dashboard batch plan in the background.")
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    status = run_batch_plan(args.plan)
    return 0 if status.get("status") == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
