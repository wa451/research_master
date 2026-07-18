"""Helpers for comparing recorded LLM API usage across evaluation methods."""

from __future__ import annotations

import csv
import math
import statistics
from pathlib import Path
from typing import Iterable, Sequence


RUN_USAGE_FIELDS = (
    "api_response_duration_sec",
    "prompt_tokens",
    "response_tokens",
    "total_tokens",
)

LLM_USAGE_COMPARISON_FIELDNAMES = [
    "method",
    "num_runs_evaluated",
    "num_runs_with_complete_metrics",
    "avg_recorded_api_calls_per_run",
    "avg_api_response_duration_sec_per_run",
    "std_api_response_duration_sec_per_run",
    "avg_prompt_tokens_per_run",
    "std_prompt_tokens_per_run",
    "avg_response_tokens_per_run",
    "std_response_tokens_per_run",
    "avg_total_tokens_per_run",
    "std_total_tokens_per_run",
]


def read_metrics_csv(path: Path) -> list[dict[str, str]]:
    """Read an extractor metrics CSV as dictionaries."""
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _parse_number(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = float(text)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _run_number(row: dict[str, str]) -> int | None:
    value = _parse_number(row.get("run"))
    if value is None or not value.is_integer():
        return None
    return int(value)


def aggregate_recorded_calls(
    method: str,
    run: int,
    rows: Sequence[dict[str, str]],
    source_path: Path,
    expected_recorded_calls: int,
) -> tuple[dict | None, str | None]:
    """Aggregate successful API-call rows into one run-level usage record.

    A run is considered complete only when every recorded call has all four
    duration/token fields. Partial values are never treated as zero.
    """
    if not rows:
        return None, "metrics_rows_missing"
    if len(rows) != expected_recorded_calls:
        return None, "unexpected_recorded_api_call_count"

    parsed_rows: list[dict[str, float]] = []
    for row in rows:
        parsed = {
            "api_response_duration_sec": _parse_number(row.get("duration_sec")),
            "prompt_tokens": _parse_number(row.get("prompt_tokens")),
            "response_tokens": _parse_number(row.get("response_tokens")),
            "total_tokens": _parse_number(row.get("total_tokens")),
        }
        if any(parsed[field] is None for field in RUN_USAGE_FIELDS):
            return None, "metrics_values_incomplete"
        parsed_rows.append({field: float(parsed[field]) for field in RUN_USAGE_FIELDS})

    return (
        {
            "method": method,
            "run": run,
            "recorded_api_calls": len(parsed_rows),
            **{
                field: sum(row[field] for row in parsed_rows)
                for field in RUN_USAGE_FIELDS
            },
            "source_path": str(source_path),
        },
        None,
    )


def load_proposed_run_usage(
    path: Path,
    run: int,
) -> tuple[dict | None, str | None]:
    """Load one proposed-method run, whose CSV contains one row per time band."""
    if not path.exists():
        return None, "metrics_file_missing"
    rows = read_metrics_csv(path)
    mismatched_runs = {
        parsed_run
        for row in rows
        if (parsed_run := _run_number(row)) is not None and parsed_run != run
    }
    if mismatched_runs:
        return None, "metrics_run_mismatch"
    return aggregate_recorded_calls(
        "proposed",
        run,
        rows,
        path,
        expected_recorded_calls=4,
    )


def load_direct_usage_by_run(
    path: Path,
    runs: Iterable[int],
) -> tuple[list[dict], list[dict]]:
    """Load direct-log metrics and return complete run rows plus missing details."""
    requested_runs = list(runs)
    if not path.exists():
        return [], [
            {
                "method": "direct_log_baseline",
                "run": run,
                "source_path": str(path),
                "reason": "metrics_file_missing",
            }
            for run in requested_runs
        ]

    rows_by_run: dict[int, list[dict[str, str]]] = {}
    for row in read_metrics_csv(path):
        run = _run_number(row)
        if run is not None:
            rows_by_run.setdefault(run, []).append(row)

    usage_rows: list[dict] = []
    missing_rows: list[dict] = []
    for run in requested_runs:
        usage, reason = aggregate_recorded_calls(
            "direct_log_baseline",
            run,
            rows_by_run.get(run, []),
            path,
            expected_recorded_calls=1,
        )
        if usage is not None:
            usage_rows.append(usage)
        else:
            missing_rows.append(
                {
                    "method": "direct_log_baseline",
                    "run": run,
                    "source_path": str(path),
                    "reason": reason,
                }
            )
    return usage_rows, missing_rows


def _mean(values: Sequence[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _std(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return statistics.stdev(values) if len(values) > 1 else 0.0


def summarize_usage(
    method: str,
    evaluated_runs: Sequence[int],
    run_usage_rows: Sequence[dict],
) -> dict:
    """Summarize complete run totals without substituting missing runs with zero."""
    rows = [row for row in run_usage_rows if row.get("method") == method]
    duration = [float(row["api_response_duration_sec"]) for row in rows]
    prompt_tokens = [float(row["prompt_tokens"]) for row in rows]
    response_tokens = [float(row["response_tokens"]) for row in rows]
    total_tokens = [float(row["total_tokens"]) for row in rows]
    recorded_calls = [float(row["recorded_api_calls"]) for row in rows]
    return {
        "method": method,
        "num_runs_evaluated": len(evaluated_runs),
        "num_runs_with_complete_metrics": len(rows),
        "avg_recorded_api_calls_per_run": _mean(recorded_calls),
        "avg_api_response_duration_sec_per_run": _mean(duration),
        "std_api_response_duration_sec_per_run": _std(duration),
        "avg_prompt_tokens_per_run": _mean(prompt_tokens),
        "std_prompt_tokens_per_run": _std(prompt_tokens),
        "avg_response_tokens_per_run": _mean(response_tokens),
        "std_response_tokens_per_run": _std(response_tokens),
        "avg_total_tokens_per_run": _mean(total_tokens),
        "std_total_tokens_per_run": _std(total_tokens),
    }
