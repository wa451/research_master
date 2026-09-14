"""Evaluation 10: leakage-safe temporal holdout for private SwitchBot logs."""

from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Sequence
from zoneinfo import ZoneInfo
import csv
import json
import math

import pandas as pd

from experiment_config import TIME_MODES, UNKNOWN_STATE
from src.behavior_pattern_mining.baselines.frequency import count_sequences
from src.behavior_pattern_mining.data.state_vectors import (
    apply_delayed_off_smoothing,
    build_sample_and_hold_state_vectors,
)
from src.behavior_pattern_mining.llm import pattern_extractor
from src.behavior_pattern_mining.states.state_mapping import map_vector_to_state


ACTIVE_VALUES = frozenset({"ON", "OPEN", "PRESENT", "1", "TRUE"})
INACTIVE_VALUES = frozenset({"OFF", "CLOSE", "ABSENT", "0", "FALSE"})
STAGES = ("prepare", "extract", "evaluate", "run")
METHODS = ("frequency", "llm", "both")
DETAIL_COLUMNS = [
    "method",
    "pattern_id",
    "sequence_json",
    "time_bands_json",
    "train_occurrences",
    "test_occurrences",
    "train_days_present",
    "test_days_present",
    "train_eligible_days",
    "test_eligible_days",
    "train_day_recurrence",
    "test_day_recurrence",
    "train_occurrences_per_day",
    "test_occurrences_per_day",
    "test_to_train_rate_ratio",
    "supported_in_test",
]
SUMMARY_COLUMNS = [
    "method",
    "status",
    "pattern_count",
    "supported_pattern_count",
    "test_supported_pattern_fraction",
    "mean_test_day_recurrence",
    "train_occurrences_total",
    "test_occurrences_total",
    "test_transition_coverage",
]


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def _find_manifest_value(payload: Any, keys: set[str]) -> Any | None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).lower() in keys and value not in (None, ""):
                return value
        for value in payload.values():
            found = _find_manifest_value(value, keys)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _find_manifest_value(value, keys)
            if found is not None:
                return found
    return None


def manifest_timezone(payload: dict[str, Any]) -> str:
    value = _find_manifest_value(payload, {"timezone", "time_zone", "tz"})
    if value is None:
        raise ValueError("manifest.json must record timezone")
    return str(value)


def snapshot_period(snapshot_dir: Path) -> tuple[pd.Timestamp, pd.Timestamp]:
    parts = snapshot_dir.name.split("_")
    if len(parts) == 2:
        start = pd.to_datetime(parts[0], format="%Y-%m-%d", errors="coerce")
        end = pd.to_datetime(parts[1], format="%Y-%m-%d", errors="coerce")
        if not pd.isna(start) and not pd.isna(end):
            if end <= start:
                raise ValueError("snapshot directory period must have start < end")
            return pd.Timestamp(start), pd.Timestamp(end)
    raise ValueError("snapshot directory must be named YYYY-MM-DD_YYYY-MM-DD")


def _manifest_local_timestamp(value: Any, timezone: str, field: str) -> pd.Timestamp:
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        raise ValueError(f"manifest {field} must be an ISO 8601 timestamp")
    timestamp = pd.Timestamp(timestamp)
    if timestamp.tzinfo is None:
        raise ValueError(f"manifest {field} must include a timezone offset")
    try:
        return timestamp.tz_convert(ZoneInfo(timezone)).tz_localize(None)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"invalid manifest timezone: {timezone}") from exc


def validate_manifest_contract(
    manifest: dict[str, Any],
    *,
    row_count: int,
    period_start: pd.Timestamp,
    period_end: pd.Timestamp,
) -> str:
    if manifest.get("schema_version") != 1:
        raise ValueError("manifest schema_version must be 1")
    if manifest.get("format") != "casas_csv":
        raise ValueError("manifest format must be casas_csv")
    if manifest.get("columns") != ["date", "time", "sensor", "value"]:
        raise ValueError("manifest columns must be date,time,sensor,value")
    if manifest.get("header") is not False:
        raise ValueError("manifest header must be false")
    timezone = manifest_timezone(manifest)
    source = manifest.get("source")
    if not isinstance(source, dict) or source.get("system") != "switchbot_logger":
        raise ValueError("manifest source.system must be switchbot_logger")
    source_start = _manifest_local_timestamp(source.get("start"), timezone, "source.start")
    source_end = _manifest_local_timestamp(
        source.get("end_exclusive"), timezone, "source.end_exclusive"
    )
    if source_start != period_start or source_end != period_end:
        raise ValueError(
            "manifest source period must match the snapshot directory's complete-day period"
        )
    conversion = manifest.get("conversion_report")
    if not isinstance(conversion, dict):
        raise ValueError("manifest conversion_report must be an object")
    if conversion.get("output_events") != row_count:
        raise ValueError("manifest conversion_report.output_events must equal events.csv rows")
    return timezone


def load_snapshot(snapshot_dir: Path) -> tuple[pd.DataFrame, dict[str, Any], list[str]]:
    events_path = snapshot_dir / "events.csv"
    manifest_path = snapshot_dir / "manifest.json"
    if not events_path.is_file():
        raise FileNotFoundError(f"events.csv not found: {events_path}")
    manifest = read_json_object(manifest_path)

    raw = pd.read_csv(events_path, header=None, dtype=str, keep_default_na=False)
    if raw.shape[1] != 4:
        raise ValueError("events.csv must have exactly 4 columns: date,time,sensor,value")
    if raw.empty:
        raise ValueError("events.csv must contain at least one event")
    raw.columns = ["date", "time", "sensor", "value"]
    if (raw[["date", "time", "sensor", "value"]].apply(lambda c: c.str.strip()) == "").any().any():
        raise ValueError("events.csv contains an empty field")
    timestamps = pd.to_datetime(
        raw["date"].str.strip() + " " + raw["time"].str.strip(),
        errors="coerce",
    )
    if timestamps.isna().any():
        rows = [str(index + 1) for index in timestamps[timestamps.isna()].index[:5]]
        raise ValueError(f"events.csv contains invalid timestamp rows: {', '.join(rows)}")
    values = raw["value"].str.strip().str.upper()
    unsupported = sorted(set(values) - ACTIVE_VALUES - INACTIVE_VALUES)
    if unsupported:
        raise ValueError(f"unsupported sensor values: {unsupported}")

    events = pd.DataFrame(
        {
            "timestamp": timestamps,
            "sensor_id": raw["sensor"].str.strip(),
            "value": values,
            "binary_value": values.isin(ACTIVE_VALUES).astype(int),
            "source_order": range(len(raw)),
        }
    )
    duplicate_count = int(events.duplicated(subset=["timestamp", "sensor_id", "value"]).sum())
    if duplicate_count:
        raise ValueError(f"events.csv contains {duplicate_count} duplicate event rows")
    was_sorted = bool(events["timestamp"].is_monotonic_increasing)
    events = events.sort_values(["timestamp", "source_order"], kind="stable").reset_index(drop=True)
    start, end = snapshot_period(snapshot_dir)
    timezone = validate_manifest_contract(
        manifest,
        row_count=len(raw),
        period_start=start,
        period_end=end,
    )
    outside = events[(events["timestamp"] < start) | (events["timestamp"] >= end)]
    if not outside.empty:
        raise ValueError(
            f"{len(outside)} event(s) fall outside snapshot period [{start}, {end})"
        )
    warnings = [] if was_sorted else ["events.csv was not timestamp-sorted; stable sorting was applied"]
    events.attrs.update(
        {
            "period_start": start,
            "period_end": end,
            "timezone": timezone,
            "events_sha256": file_sha256(events_path),
            "manifest_sha256": file_sha256(manifest_path),
        }
    )
    return events, manifest, warnings


def choose_split(
    period_start: pd.Timestamp,
    period_end: pd.Timestamp,
    split_at: str | None,
    train_ratio: float,
) -> pd.Timestamp:
    total_days = int((period_end - period_start) / pd.Timedelta(days=1))
    if total_days < 2:
        raise ValueError("evaluation 10 requires at least two complete calendar days")
    if split_at:
        split = pd.to_datetime(split_at, errors="coerce")
        if pd.isna(split):
            raise ValueError(f"invalid --split-at: {split_at}")
        split = pd.Timestamp(split)
    else:
        if not 0 < train_ratio < 1:
            raise ValueError("--train-ratio must be between 0 and 1")
        train_days = max(1, min(total_days - 1, math.floor(total_days * train_ratio)))
        split = period_start + pd.Timedelta(days=train_days)
    if split != split.normalize():
        raise ValueError("split must be at local midnight to keep complete-day denominators")
    if not period_start < split < period_end:
        raise ValueError("split must be strictly inside the snapshot period")
    return split


def _time_band(timestamp: pd.Timestamp) -> str | None:
    minute = timestamp.hour * 60 + timestamp.minute
    for name, (start_text, end_text) in TIME_MODES.items():
        sh, sm = (int(part) for part in start_text.split(":"))
        eh, em = (int(part) for part in end_text.split(":"))
        start = sh * 60 + sm
        end = eh * 60 + em
        if (start <= minute < end) if start <= end else (minute >= start or minute < end):
            return name
    return None


def _compress(sequence: Sequence[str]) -> list[str]:
    return [value for index, value in enumerate(sequence) if index == 0 or value != sequence[index - 1]]


def _map_frame(
    frame: pd.DataFrame,
    mapping: dict[tuple[int, ...], str],
    hamming_threshold: int,
) -> pd.Series:
    cache: dict[tuple[int, ...], str] = {}
    mapped = []
    for row in frame.itertuples(index=False, name=None):
        vector = tuple(int(value) for value in row)
        if vector not in cache:
            cache[vector] = map_vector_to_state(
                vector, mapping, hamming_threshold, unknown_state=UNKNOWN_STATE
            )
        mapped.append(cache[vector])
    return pd.Series(mapped, index=frame.index, name="state")


def _segments(series: pd.Series) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[str]] = defaultdict(list)
    for timestamp, state in series.items():
        band = _time_band(pd.Timestamp(timestamp))
        if band is not None:
            buckets[(pd.Timestamp(timestamp).date().isoformat(), band)].append(str(state))
    return [
        {"date": date, "time_band": band, "sequence": _compress(sequence)}
        for (date, band), sequence in sorted(buckets.items())
    ]


def _transition_counts(segments: Iterable[dict[str, Any]]) -> Counter[tuple[str, str]]:
    counts: Counter[tuple[str, str]] = Counter()
    for segment in segments:
        sequence = segment["sequence"]
        counts.update(zip(sequence, sequence[1:]))
    return counts


def _network_payload(
    *,
    segments: list[dict[str, Any]],
    duration_counts: Counter[str],
    representative_vectors: list[tuple[int, ...]],
    sensor_columns: list[str],
    train_days: int,
    sampling_seconds: int,
) -> dict[str, Any]:
    labels = [f"状態{index}" for index in range(1, len(representative_vectors) + 1)]
    nodes = [
        {
            "state_id": label,
            "active_sensors": [
                sensor for sensor, value in zip(sensor_columns, vector) if value == 1
            ],
            "avg_duration_minutes_per_day": round(
                duration_counts.get(label, 0) * sampling_seconds / max(train_days, 1) / 60,
                3,
            ),
        }
        for label, vector in zip(labels, representative_vectors)
        if duration_counts.get(label, 0) > 0
    ]
    if duration_counts.get(UNKNOWN_STATE, 0):
        nodes.append(
            {
                "state_id": UNKNOWN_STATE,
                "active_sensors": [],
                "avg_duration_minutes_per_day": round(
                    duration_counts[UNKNOWN_STATE]
                    * sampling_seconds
                    / max(train_days, 1)
                    / 60,
                    3,
                ),
            }
        )
    pair_counts = _transition_counts(segments)
    outgoing: Counter[str] = Counter()
    for (source, _), count in pair_counts.items():
        outgoing[source] += count
    edges = [
        {"from": source, "to": target, "probability": round(count / outgoing[source], 3)}
        for (source, target), count in pair_counts.items()
    ]
    return {"nodes": nodes, "edges": edges}


def _write_state_table(
    path: Path, representative_vectors: list[tuple[int, ...]], sensor_columns: list[str]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["状態", *sensor_columns])
        for index, vector in enumerate(representative_vectors, start=1):
            writer.writerow([f"状態{index}", *vector])
        writer.writerow([UNKNOWN_STATE, *(["-"] * len(sensor_columns))])


def _count_sequence_in_segments(
    sequence: Sequence[str], segments: Sequence[dict[str, Any]], bands: set[str]
) -> tuple[int, set[str]]:
    total = 0
    dates: set[str] = set()
    length = len(sequence)
    for segment in segments:
        if segment["time_band"] not in bands:
            continue
        values = segment["sequence"]
        found = sum(
            1
            for index in range(len(values) - length + 1)
            if values[index : index + length] == list(sequence)
        )
        total += found
        if found:
            dates.add(segment["date"])
    return total, dates


def build_frequency_patterns(
    segments: list[dict[str, Any]],
    min_length: int,
    max_length: int,
    min_occurrences: int,
    top_k_per_mode: int,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], dict[str, Any]] = {}
    for band in TIME_MODES:
        band_segments = [segment for segment in segments if segment["time_band"] == band]
        counts: Counter[tuple[str, ...]] = Counter()
        for segment in band_segments:
            counts.update(count_sequences(segment["sequence"], min_length, max_length))
        candidates = [
            (sequence, count)
            for sequence, count in counts.most_common()
            if count >= min_occurrences and UNKNOWN_STATE not in sequence
        ][:top_k_per_mode]
        for sequence, count in candidates:
            record = grouped.setdefault(
                sequence,
                {"sequence": list(sequence), "time_bands": [], "train_occurrences": 0},
            )
            record["time_bands"].append(band)
            record["train_occurrences"] += count
    return [
        {"pattern_id": f"F{index:03d}", "method": "frequency", **record}
        for index, record in enumerate(grouped.values(), start=1)
    ]


def prepare(
    *,
    snapshot_dir: Path,
    output_dir: Path,
    split_at: str | None,
    train_ratio: float,
    n_states: int,
    hamming_threshold: int,
    smoothing_window_sec: int,
    sampling_seconds: int,
    min_sequence_length: int,
    max_sequence_length: int,
    min_train_occurrences: int,
    top_k_per_mode: int,
) -> dict[str, Any]:
    if n_states < 1 or hamming_threshold < 0 or smoothing_window_sec < 0:
        raise ValueError("K must be >= 1 and hamming/smoothing must be >= 0")
    if sampling_seconds < 1:
        raise ValueError("sampling seconds must be >= 1")
    if not 2 <= min_sequence_length <= max_sequence_length:
        raise ValueError("sequence lengths must satisfy 2 <= min <= max")
    if min_train_occurrences < 1 or top_k_per_mode < 1:
        raise ValueError("frequency thresholds must be >= 1")

    snapshot_dir = snapshot_dir.resolve()
    output_dir = output_dir.resolve()
    events, _manifest, warnings = load_snapshot(snapshot_dir)
    period_start = events.attrs["period_start"]
    period_end = events.attrs["period_end"]
    split = choose_split(period_start, period_end, split_at, train_ratio)
    train_events = events[events["timestamp"] < split]
    test_events = events[events["timestamp"] >= split]
    sensor_columns = sorted(train_events["sensor_id"].unique())
    if not sensor_columns:
        raise ValueError("training period contains no sensors")
    unseen_test_sensors = sorted(set(test_events["sensor_id"]) - set(sensor_columns))
    if unseen_test_sensors:
        warnings.append(
            "test-only sensors were ignored to prevent test data changing the training representation: "
            + ", ".join(unseen_test_sensors)
        )

    known_events = events[events["sensor_id"].isin(sensor_columns)]
    time_range = pd.date_range(
        start=period_start,
        end=period_end - pd.Timedelta(seconds=sampling_seconds),
        freq=f"{sampling_seconds}s",
    )
    vectors = build_sample_and_hold_state_vectors(known_events, time_range, sensor_columns)
    smoothing_rows = math.ceil(smoothing_window_sec / sampling_seconds)
    vectors = apply_delayed_off_smoothing(vectors, smoothing_rows)
    train_vectors = vectors[vectors.index < split]
    test_vectors = vectors[vectors.index >= split]

    changed = train_vectors.ne(train_vectors.shift()).any(axis=1)
    changed.iloc[0] = True
    compressed_train = train_vectors.loc[changed]
    state_counts = Counter(tuple(int(value) for value in row) for row in compressed_train.values)
    representative_vectors = [vector for vector, _ in state_counts.most_common(n_states)]
    mapping = {
        vector: f"状態{index}" for index, vector in enumerate(representative_vectors, start=1)
    }
    mapped_train = _map_frame(train_vectors, mapping, hamming_threshold)
    mapped_test = _map_frame(test_vectors, mapping, hamming_threshold)
    train_segments = _segments(mapped_train)
    test_segments = _segments(mapped_test)
    train_days = int((split - period_start) / pd.Timedelta(days=1))
    test_days = int((period_end - split) / pd.Timedelta(days=1))

    output_dir.mkdir(parents=True, exist_ok=True)
    network_dir = output_dir / "network"
    duration_all = Counter(mapped_train.tolist())
    write_json(
        network_dir / "state_transition_all.json",
        _network_payload(
            segments=train_segments,
            duration_counts=duration_all,
            representative_vectors=representative_vectors,
            sensor_columns=sensor_columns,
            train_days=train_days,
            sampling_seconds=sampling_seconds,
        ),
    )
    for band in TIME_MODES:
        band_segments = [segment for segment in train_segments if segment["time_band"] == band]
        mask = [_time_band(pd.Timestamp(timestamp)) == band for timestamp in mapped_train.index]
        duration_counts = Counter(mapped_train.loc[mask].tolist())
        write_json(
            network_dir / f"state_transition_{band}.json",
            _network_payload(
                segments=band_segments,
                duration_counts=duration_counts,
                representative_vectors=representative_vectors,
                sensor_columns=sensor_columns,
                train_days=train_days,
                sampling_seconds=sampling_seconds,
            ),
        )
    _write_state_table(output_dir / "state_table.tsv", representative_vectors, sensor_columns)
    write_json(output_dir / "train_state_segments.json", train_segments)
    write_json(output_dir / "test_state_segments.json", test_segments)
    frequency_patterns = build_frequency_patterns(
        train_segments,
        min_sequence_length,
        max_sequence_length,
        min_train_occurrences,
        top_k_per_mode,
    )
    write_json(output_dir / "frequency_patterns.json", frequency_patterns)

    preparation = {
        "evaluation": 10,
        "snapshot": {
            "directory": str(snapshot_dir),
            "events": str(snapshot_dir / "events.csv"),
            "manifest": str(snapshot_dir / "manifest.json"),
            "events_sha256": events.attrs["events_sha256"],
            "manifest_sha256": events.attrs["manifest_sha256"],
            "timezone": events.attrs["timezone"],
            "period_start": period_start.isoformat(),
            "period_end_exclusive": period_end.isoformat(),
        },
        "split": {
            "train_start": period_start.isoformat(),
            "train_end_exclusive": split.isoformat(),
            "test_start": split.isoformat(),
            "test_end_exclusive": period_end.isoformat(),
            "train_days": train_days,
            "test_days": test_days,
        },
        "parameters": {
            "n_states": n_states,
            "hamming_threshold": hamming_threshold,
            "smoothing_window_sec": smoothing_window_sec,
            "sampling_seconds": sampling_seconds,
            "min_sequence_length": min_sequence_length,
            "max_sequence_length": max_sequence_length,
            "min_train_occurrences": min_train_occurrences,
            "top_k_per_mode": top_k_per_mode,
            "unknown_state": UNKNOWN_STATE,
        },
        "counts": {
            "events": len(events),
            "train_events": len(train_events),
            "test_events": len(test_events),
            "training_sensors": len(sensor_columns),
            "test_only_sensors_ignored": len(unseen_test_sensors),
            "representative_states": len(representative_vectors),
            "frequency_patterns": len(frequency_patterns),
        },
        "warnings": warnings,
    }
    write_json(output_dir / "preparation.json", preparation)
    return preparation


def verify_preparation(output_dir: Path) -> dict[str, Any]:
    preparation = read_json_object(output_dir / "preparation.json")
    snapshot = preparation.get("snapshot", {})
    for key in ("events", "manifest"):
        path = Path(str(snapshot.get(key, "")))
        expected = snapshot.get(f"{key}_sha256")
        if not path.is_file() or file_sha256(path) != expected:
            raise ValueError(f"prepared input changed or is missing: {path}")
    for name in ("train_state_segments.json", "test_state_segments.json", "frequency_patterns.json"):
        if not (output_dir / name).is_file():
            raise FileNotFoundError(f"prepared artifact not found: {output_dir / name}")
    return preparation


def preparation_fingerprint(output_dir: Path, preparation: dict[str, Any]) -> str:
    digest = sha256()
    identity = {
        "snapshot": preparation["snapshot"],
        "split": preparation["split"],
        "parameters": preparation["parameters"],
    }
    digest.update(
        json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
    )
    for name in ["all", *TIME_MODES]:
        network_path = output_dir / "network" / f"state_transition_{name}.json"
        if not network_path.is_file():
            raise FileNotFoundError(f"prepared network not found: {network_path}")
        digest.update(network_path.name.encode("utf-8"))
        digest.update(network_path.read_bytes())
    return digest.hexdigest()[:16]


def llm_patterns_path(output_dir: Path, preparation: dict[str, Any]) -> Path:
    params = preparation["parameters"]
    train_days = preparation["split"]["train_days"]
    fingerprint = preparation_fingerprint(output_dir, preparation)
    return output_dir / "llm" / fingerprint / (
        f"llm_sequences_modes_{params['n_states']}_{params['hamming_threshold']}_{train_days}days_1.json"
    )


def extract(*, output_dir: Path, allow_api: bool) -> Path:
    preparation = verify_preparation(output_dir)
    if not allow_api:
        raise ValueError("LLM extraction requires explicit --allow-api")
    params = preparation["parameters"]
    llm_dir = output_dir / "llm" / preparation_fingerprint(output_dir, preparation)
    pattern_extractor.main(
        days=preparation["split"]["train_days"],
        input_modes_dir=output_dir / "network",
        output_dir=llm_dir,
        runs=1,
        n_states=params["n_states"],
        hamming_threshold=params["hamming_threshold"],
    )
    path = llm_patterns_path(output_dir, preparation)
    if not path.is_file():
        raise RuntimeError(f"LLM extractor did not produce expected output: {path}")
    return path


def _load_segments(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"segment array required: {path}")
    return payload


def _load_patterns(
    path: Path,
    method: str,
    min_sequence_length: int,
    max_sequence_length: int,
) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"pattern array required: {path}")
    patterns = []
    for index, record in enumerate(payload, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"invalid pattern at index {index}: {path}")
        sequence = record.get("sequence") or record.get("遷移のパターン") or record.get("遷移のシーケンス")
        if (
            not isinstance(sequence, list)
            or not min_sequence_length <= len(sequence) <= max_sequence_length
            or not all(isinstance(value, str) for value in sequence)
        ):
            raise ValueError(f"invalid pattern sequence at index {index}: {path}")
        bands = record.get("time_bands")
        interpretations = record.get("time_band_interpretations")
        if not bands and isinstance(interpretations, dict):
            bands = list(interpretations)
        if not bands:
            bands = list(TIME_MODES)
        bands = [str(band) for band in bands if str(band) in TIME_MODES]
        if not bands:
            raise ValueError(f"pattern has no recognized time band at index {index}: {path}")
        patterns.append(
            {
                "method": method,
                "pattern_id": record.get("pattern_id") or f"{'L' if method == 'llm' else 'F'}{index:03d}",
                "sequence": sequence,
                "time_bands": bands,
            }
        )
    return patterns


def _eligible_days(segments: Sequence[dict[str, Any]], bands: set[str]) -> set[str]:
    return {segment["date"] for segment in segments if segment["time_band"] in bands}


def _coverage(patterns: Sequence[dict[str, Any]], segments: Sequence[dict[str, Any]]) -> float:
    total_transitions = sum(max(len(segment["sequence"]) - 1, 0) for segment in segments)
    if total_transitions == 0:
        return 0.0
    covered = 0
    for segment in segments:
        sequence = segment["sequence"]
        positions: set[int] = set()
        for pattern in patterns:
            if segment["time_band"] not in pattern["time_bands"]:
                continue
            candidate = pattern["sequence"]
            for start in range(len(sequence) - len(candidate) + 1):
                if sequence[start : start + len(candidate)] == candidate:
                    positions.update(range(start, start + len(candidate) - 1))
        covered += len(positions)
    return covered / total_transitions


def _evaluate_method(
    method: str,
    patterns: list[dict[str, Any]],
    train_segments: list[dict[str, Any]],
    test_segments: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    for pattern in patterns:
        bands = set(pattern["time_bands"])
        train_count, train_dates = _count_sequence_in_segments(pattern["sequence"], train_segments, bands)
        test_count, test_dates = _count_sequence_in_segments(pattern["sequence"], test_segments, bands)
        train_eligible = _eligible_days(train_segments, bands)
        test_eligible = _eligible_days(test_segments, bands)
        train_rate = train_count / len(train_eligible) if train_eligible else 0.0
        test_rate = test_count / len(test_eligible) if test_eligible else 0.0
        rows.append(
            {
                "method": method,
                "pattern_id": pattern["pattern_id"],
                "sequence_json": json.dumps(pattern["sequence"], ensure_ascii=False),
                "time_bands_json": json.dumps(pattern["time_bands"], ensure_ascii=False),
                "train_occurrences": train_count,
                "test_occurrences": test_count,
                "train_days_present": len(train_dates),
                "test_days_present": len(test_dates),
                "train_eligible_days": len(train_eligible),
                "test_eligible_days": len(test_eligible),
                "train_day_recurrence": len(train_dates) / len(train_eligible) if train_eligible else 0.0,
                "test_day_recurrence": len(test_dates) / len(test_eligible) if test_eligible else 0.0,
                "train_occurrences_per_day": train_rate,
                "test_occurrences_per_day": test_rate,
                "test_to_train_rate_ratio": test_rate / train_rate if train_rate else None,
                "supported_in_test": bool(test_count),
            }
        )
    supported = sum(bool(row["supported_in_test"]) for row in rows)
    summary = {
        "method": method,
        "status": "complete",
        "pattern_count": len(rows),
        "supported_pattern_count": supported,
        "test_supported_pattern_fraction": supported / len(rows) if rows else None,
        "mean_test_day_recurrence": (
            sum(float(row["test_day_recurrence"]) for row in rows) / len(rows) if rows else None
        ),
        "train_occurrences_total": sum(int(row["train_occurrences"]) for row in rows),
        "test_occurrences_total": sum(int(row["test_occurrences"]) for row in rows),
        "test_transition_coverage": _coverage(patterns, test_segments),
    }
    return rows, summary


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def evaluate(
    *,
    output_dir: Path,
    results_dir: Path,
    method: str,
    llm_patterns: Path | None = None,
) -> dict[str, Any]:
    if method not in METHODS:
        raise ValueError(f"unknown method: {method}")
    preparation = verify_preparation(output_dir)
    train_segments = _load_segments(output_dir / "train_state_segments.json")
    test_segments = _load_segments(output_dir / "test_state_segments.json")
    methods = ("frequency", "llm") if method == "both" else (method,)
    detail_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    input_paths: dict[str, str | None] = {}
    for current in methods:
        path = (
            output_dir / "frequency_patterns.json"
            if current == "frequency"
            else (llm_patterns or llm_patterns_path(output_dir, preparation))
        )
        input_paths[current] = str(path)
        if current == "llm" and not path.is_file():
            summary_rows.append(
                {
                    "method": current,
                    "status": "missing",
                    "pattern_count": None,
                    "supported_pattern_count": None,
                    "test_supported_pattern_fraction": None,
                    "mean_test_day_recurrence": None,
                    "train_occurrences_total": None,
                    "test_occurrences_total": None,
                    "test_transition_coverage": None,
                }
            )
            continue
        patterns = _load_patterns(
            path,
            current,
            preparation["parameters"]["min_sequence_length"],
            preparation["parameters"]["max_sequence_length"],
        )
        rows, summary = _evaluate_method(current, patterns, train_segments, test_segments)
        detail_rows.extend(rows)
        summary_rows.append(summary)

    results_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(results_dir / "evaluation10_pattern_details.csv", detail_rows, DETAIL_COLUMNS)
    _write_csv(results_dir / "evaluation10_summary.csv", summary_rows, SUMMARY_COLUMNS)
    payload = {
        "evaluation": 10,
        "interpretation": (
            "Held-out recurrence diagnostics for unlabeled home logs; these are not ADL accuracy metrics."
        ),
        "preparation": preparation,
        "pattern_inputs": input_paths,
        "summary": summary_rows,
        "outputs": {
            "summary_csv": str(results_dir / "evaluation10_summary.csv"),
            "details_csv": str(results_dir / "evaluation10_pattern_details.csv"),
        },
    }
    write_json(results_dir / "evaluation10_summary.json", payload)
    return payload
