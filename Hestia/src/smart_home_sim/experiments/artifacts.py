"""Generate immutable inputs and separate resident-aware ground truth."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from smart_home_sim.engine import SimulationEngine
from smart_home_sim.experiments.plan import ExperimentPlan, time_band_for_minute
from smart_home_sim.experiments.scenarios import TARGET_ACTIVITIES, build_scenario
from smart_home_sim.outputs import CasasPreset, export_aruba


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): file_hash(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def generation_sources() -> dict[str, str]:
    package = Path(__file__).resolve().parents[1]
    sources = [
        *package.glob("*.py"),
        *[Path(__file__).with_name(name) for name in ("artifacts.py", "plan.py", "scenarios.py")],
    ]
    return {path.relative_to(package).as_posix(): file_hash(path) for path in sorted(sources)}


def verify_files(root: Path, hashes: dict[str, str]) -> None:
    for name, digest in hashes.items():
        path = root / name
        if not path.is_file() or file_hash(path) != digest:
            raise ValueError(f"artifact changed or missing: {path}; use a new output directory")


def iso(value: datetime) -> str:
    return value.isoformat(timespec="microseconds")


def activity_truth(events: Path, end: datetime) -> list[dict[str, Any]]:
    active: dict[tuple[str, str], dict[str, Any]] = {}
    intervals: list[dict[str, Any]] = []
    with events.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["device_type"] != "ActivityBoundary":
                continue
            key = (row["resident_id"], row["activity_id"])
            if row["state"] == "START":
                if key in active:
                    raise ValueError(f"duplicate activity start: {key}")
                active[key] = {
                    "resident_id": key[0],
                    "activity_id": key[1],
                    "label": row["activity_label"],
                    "start": row["timestamp"],
                }
            elif row["state"] == "END":
                if key not in active:
                    raise ValueError(f"activity end without start: {key}")
                intervals.append({**active.pop(key), "end": row["timestamp"], "complete": True})
    intervals.extend({**item, "end": iso(end), "complete": False} for item in active.values())
    return sorted(
        intervals, key=lambda item: (item["start"], item["resident_id"], item["activity_id"])
    )


def _trace_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _actual_behavior_path(
    rows: list[dict[str, str]], episode: dict[str, Any]
) -> tuple[list[str], list[dict[str, Any]]]:
    left = datetime.fromisoformat(episode["start"])
    right = datetime.fromisoformat(episode["end"])
    selected_templates: list[str] = []
    starts: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    path: list[dict[str, Any]] = []
    for row in rows:
        if (
            row["resident_id"] != episode["resident_id"]
            or row["activity_id"] != episode["activity_id"]
        ):
            continue
        timestamp = datetime.fromisoformat(row["timestamp"])
        if not left <= timestamp <= right:
            continue
        if row["kind"] == "micro_template" and row["phase"] == "SELECTED":
            selected_templates.append(row["template_id"])
            continue
        if row["kind"] != "micro_action":
            continue
        key = row["template_id"], row["step_id"], row["occurrence"]
        if row["phase"] == "START":
            starts.setdefault(key, []).append(row)
        elif row["phase"] == "END" and starts.get(key):
            started = starts[key].pop(0)
            path.append(
                {
                    "template_id": row["template_id"],
                    "step_id": row["step_id"],
                    "occurrence": int(row["occurrence"]),
                    "start": started["timestamp"],
                    "end": row["timestamp"],
                    "room_id": started["room_id"],
                    "zone_id": None if started["zone_id"] == "-" else started["zone_id"],
                }
            )
    return sorted(set(selected_templates)), sorted(path, key=lambda item: item["start"])


def target_episode_truth(
    plan: ExperimentPlan,
    activities: list[dict[str, Any]],
    trace_path: Path,
) -> list[dict[str, Any]]:
    """Attach explicit target IDs and realized micro paths without changing sensor truth."""
    traces = _trace_rows(trace_path)
    if plan.targets is None:
        selected = [
            activity for activity in activities if activity["activity_id"] in TARGET_ACTIVITIES
        ]
        totals = Counter(
            (activity["resident_id"], activity["activity_id"]) for activity in selected
        )
        per_day = Counter(
            (
                activity["resident_id"],
                activity["activity_id"],
                (datetime.fromisoformat(activity["start"]) - plan.start_datetime).days,
            )
            for activity in selected
        )
        result = []
        day_order: Counter[tuple[str, int]] = Counter()
        target_occurrence: Counter[tuple[str, str, int]] = Counter()
        for index, activity in enumerate(selected, start=1):
            templates, path = _actual_behavior_path(traces, activity)
            key = activity["resident_id"], activity["activity_id"]
            day = (datetime.fromisoformat(activity["start"]) - plan.start_datetime).days
            day_order[activity["resident_id"], day] += 1
            target_occurrence[key[0], key[1], day] += 1
            result.append(
                {
                    **activity,
                    "target_id": f"{activity['resident_id']}_{activity['activity_id']}",
                    "target_episode_id": f"legacy_{index:05d}",
                    "generated": True,
                    "scheduled_start": None,
                    "configured_time_band": time_band_for_minute(
                        datetime.fromisoformat(activity["start"]).hour * 60
                        + datetime.fromisoformat(activity["start"]).minute
                    ),
                    "time_band": time_band_for_minute(
                        datetime.fromisoformat(activity["start"]).hour * 60
                        + datetime.fromisoformat(activity["start"]).minute
                    ),
                    "intended_repetitions_per_day": per_day[key[0], key[1], day],
                    "intended_repetitions_total": totals[key],
                    "intended_order_in_day": day_order[activity["resident_id"], day],
                    "intended_occurrence_index": target_occurrence[key[0], key[1], day],
                    "selected_template_ids": templates,
                    "actual_behavior_path": path,
                }
            )
        return result

    episodes: dict[tuple[int, str, str], list[dict[str, Any]]] = {}
    for activity in activities:
        day = (datetime.fromisoformat(activity["start"]) - plan.start_datetime).days
        episodes.setdefault((day, activity["resident_id"], activity["activity_id"]), []).append(
            activity
        )
    for values in episodes.values():
        values.sort(key=lambda item: item["start"])

    result = []
    for day in range(plan.days):
        order_by_slot: dict[tuple[str, float], int] = {}
        resident_order: Counter[str] = Counter()
        for minute, target_spec in sorted(
            (
                (minute, configured_target)
                for configured_target in plan.targets
                for minute in configured_target.scheduled_start_minutes
            ),
            key=lambda item: (item[1].resident_id, item[0], item[1].id),
        ):
            resident_order[target_spec.resident_id] += 1
            order_by_slot[target_spec.id, minute] = resident_order[target_spec.resident_id]
        by_activity: dict[tuple[str, str], list[tuple[float, Any, int]]] = {}
        for target in plan.targets:
            for occurrence, minute in enumerate(sorted(target.scheduled_start_minutes), start=1):
                by_activity.setdefault((target.resident_id, target.activity_id), []).append(
                    (minute, target, occurrence)
                )
        for (resident_id, activity_id), slots in sorted(by_activity.items()):
            slots.sort(key=lambda item: (item[0], item[1].id))
            actual = episodes.get((day, resident_id, activity_id), [])
            for position, (minute, target, occurrence) in enumerate(slots):
                scheduled = plan.start_datetime + timedelta(days=day, minutes=minute)
                episode = actual[position] if position < len(actual) else None
                common = {
                    "target_id": target.id,
                    "target_episode_id": f"{target.id}_day{day + 1}_{occurrence}",
                    "resident_id": resident_id,
                    "activity_id": activity_id,
                    "label": episode["label"] if episode else None,
                    "generated": episode is not None,
                    "scheduled_start": iso(scheduled),
                    "configured_time_band": target.time_band,
                    "intended_repetitions_per_day": len(target.scheduled_start_minutes),
                    "intended_repetitions_total": len(target.scheduled_start_minutes) * plan.days,
                    "intended_order_in_day": order_by_slot[target.id, minute],
                    "intended_occurrence_index": occurrence,
                }
                if episode is None:
                    result.append(
                        {
                            **common,
                            "start": None,
                            "end": None,
                            "complete": False,
                            "time_band": None,
                            "selected_template_ids": [],
                            "actual_behavior_path": [],
                        }
                    )
                    continue
                templates, path = _actual_behavior_path(traces, episode)
                started = datetime.fromisoformat(episode["start"])
                result.append(
                    {
                        **common,
                        "start": episode["start"],
                        "end": episode["end"],
                        "complete": episode["complete"],
                        "time_band": time_band_for_minute(started.hour * 60 + started.minute),
                        "selected_template_ids": templates,
                        "actual_behavior_path": path,
                    }
                )
    return sorted(
        result,
        key=lambda item: (item["scheduled_start"], item["resident_id"], item["target_id"]),
    )


def generate(plan: ExperimentPlan, output: Path) -> list[Path]:
    output = output.resolve()
    snapshot = output / "experiment.json"
    payload = plan.model_dump(mode="json")
    if snapshot.exists():
        if read_json(snapshot) != payload:
            raise ValueError("experiment plan differs from snapshot; use a new output directory")
    elif output.exists() and any(output.iterdir()):
        raise ValueError(f"output must be empty: {output}")
    else:
        write_json(snapshot, payload)
    runs = []
    source_hashes = generation_sources()
    for condition in sorted(plan.conditions, key=lambda item: item.id):
        scenario = build_scenario(condition, plan)
        if scenario.sensor_imperfections.enabled:
            raise ValueError("observation noise is forbidden in this experiment")
        for seed in sorted(plan.seeds):
            run = output / "runs" / condition.id / f"seed_{seed}"
            runs.append(run)
            marker = run / "generated.json"
            if marker.exists():
                if read_json(marker).get("generator_sources") != source_hashes:
                    raise ValueError("generator code changed; use a new experiment output")
                verify_files(run, read_json(marker)["files"])
                continue
            if run.exists() and any(run.iterdir()):
                raise ValueError(
                    f"incomplete generation at {run}; preserve it and use a new output"
                )
            write_json(run / "scenario.json", scenario.model_dump(mode="json"))
            write_json(
                run / "run.json",
                {"condition": condition.model_dump(mode="json"), "seed": seed, "plan": payload},
            )
            SimulationEngine(scenario, days=plan.days, seed=seed).run(run / "simulation")
            sensors = run / "input" / "sensors.txt"
            export_aruba(
                run / "simulation/events.csv",
                sensors,
                preset=CasasPreset.ALL_DEVICES,
                include_activity_boundaries=False,
            )
            split = plan.start_datetime + timedelta(days=plan.train_days)
            train_lines = []
            for line in sensors.read_text(encoding="utf-8").splitlines():
                parts = line.split()
                if len(parts) != 4:
                    raise ValueError("detector input must contain exactly four observable fields")
                timestamp = datetime.fromisoformat(f"{parts[0]}T{parts[1]}").replace(
                    tzinfo=plan.start_datetime.tzinfo
                )
                if timestamp < split:
                    train_lines.append(line)
            (run / "input/train.txt").write_text("\n".join(train_lines) + "\n", encoding="utf-8")
            # 部屋・機器の意味は与えるが、住人・活動・テンプレート名は与えない。
            write_json(
                run / "input/sensor_map.json",
                {
                    device.id: f"{room.id}_{device.type.value}_{device.id}"
                    for room in sorted(scenario.rooms, key=lambda item: item.id)
                    for device in sorted(room.devices, key=lambda item: item.id)
                },
            )
            activities = activity_truth(
                run / "simulation/events.csv", plan.start_datetime + timedelta(days=plan.days)
            )
            write_json(run / "truth/activities.json", activities)
            targets = target_episode_truth(plan, activities, run / "simulation/activity_trace.csv")
            write_json(run / "truth/target_episodes.json", targets)
            write_json(
                run / "truth/motifs.json",
                {
                    "targets": (
                        [target.model_dump(mode="json") for target in plan.targets]
                        if plan.targets is not None
                        else [
                            {
                                "target_id": f"{resident.id}_{activity_id}",
                                "activity_id": activity_id,
                                "resident_id": resident.id,
                                "schedule": "legacy condition routine",
                            }
                            for resident in sorted(scenario.residents, key=lambda item: item.id)
                            for activity_id in TARGET_ACTIVITIES
                        ]
                    ),
                    "canonical_rule": (
                        "maximum train target-episode support, then maximum length up to 4; "
                        "retain deterministic ties"
                    ),
                    "state_truth": "train-only realized target episodes projected to state table",
                    "split": iso(split),
                    "observation_noise": False,
                },
            )
            write_json(marker, {"files": tree_hashes(run), "generator_sources": source_hashes})
    return runs


def select_runs(output: Path, condition: str | None = None, seed: int | None = None) -> list[Path]:
    plan = ExperimentPlan.model_validate(read_json(output / "experiment.json"))
    runs = [
        output.resolve() / "runs" / item.id / f"seed_{number}"
        for item in sorted(plan.conditions, key=lambda value: value.id)
        for number in sorted(plan.seeds)
        if (condition is None or item.id == condition) and (seed is None or number == seed)
    ]
    if not runs:
        raise ValueError("no matching condition/seed")
    for run in runs:
        verify_files(run, read_json(run / "generated.json")["files"])
    return runs
