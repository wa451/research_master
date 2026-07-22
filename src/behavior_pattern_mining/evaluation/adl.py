"""ADL evaluation against labeled CASAS intervals.

This module is intentionally independent from the existing LLM extraction and
network-building pipeline. It consumes existing outputs and computes a
post-hoc evaluation against labeled CASAS activity intervals.
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Sequence

from src.behavior_pattern_mining.states.state_mapping import (
    DEFAULT_ACTIVE_VALUES,
    DEFAULT_INACTIVE_VALUES,
    load_event_log,
    load_state_mapping,
    map_vector_to_state,
)


ADL_CATEGORY_MAP = {
    "Sleeping": "Sleep",
    "Bed_to_Toilet": "Wake-up",
    "Bathroom": "Wake-up",
    "Personal_Hygiene": "Wake-up",
    "Bathing": "Wake-up",
    "Toileting": "Toileting",
    "Meal_Preparation": "Meal",
    "Eating": "Meal",
    "Wash_Dishes": "Meal",
    "Leave_Home": "Outing",
    "Enter_Home": "Outing",
    "Relax": "Relax",
    "Housekeeping": "Housework",
    "Work": "Work",
}

ADL_CATEGORY_SET_MAP = {
    "Sleeping": ("Sleep",),
    # Bed_to_Toilet is both a wake-up marker and an explicit toileting activity.
    "Bed_to_Toilet": ("Wake-up", "Toileting"),
    "Bathroom": ("Wake-up", "Hygiene"),
    "Personal_Hygiene": ("Wake-up", "Hygiene"),
    "Bathing": ("Hygiene",),
    "Toileting": ("Toileting",),
    # Meal_Preparation can become Wake-up through apply_wake_up_rule when it occurs right after sleep.
    "Meal_Preparation": ("Meal",),
    "Eating": ("Meal",),
    "Wash_Dishes": ("Meal", "Housework"),
    "Leave_Home": ("Outing",),
    "Enter_Home": ("Outing",),
    "Relax": ("Relax",),
    "Housekeeping": ("Housework",),
    "Work": ("Work",),
}

DEFAULT_MIN_DURATION_BY_ADL = {
    "Sleep": 10 * 60,
    "Relax": 3 * 60,
    "Meal": 2 * 60,
    "Wake-up": 30,
    "Outing": 60,
    "Housework": 60,
    "Work": 60,
    "Other": 0,
    "Other_ADL": 0,
}

DEFAULT_ARUBA_SENSOR_ID_MAP = {
    "M001": "Bedroom",
    "M002": "Bedroom",
    "M003": "Bedroom",
    "M004": "Bathroom",
    "M005": "Bedroom",
    "M006": "Bedroom",
    "M007": "Bedroom",
    "M008": "OtherRoom",
    "M009": "LoungeChair",
    "M010": "LoungeChair",
    "M011": "OutsideDoor",
    "M012": "LivingRoom",
    "M013": "LivingRoom",
    "M014": "DiningRoom",
    "M015": "Kitchen",
    "M016": "Kitchen",
    "M017": "Kitchen",
    "M018": "Kitchen",
    "M019": "Kitchen",
    "M020": "LivingRoom",
    "M021": "GuestRoom",
    "M022": "GuestRoom",
    "M023": "GuestRoom",
    "M024": "Bathroom",
    "M025": "WorkArea",
    "M026": "WorkArea",
    "M027": "WorkArea",
    "M028": "WorkArea",
    "M029": "Bathroom",
    "M030": "OutsideDoor",
    "M031": "OtherRoom",
    "D001": "OutsideDoor",
    "D002": "OutsideDoor",
    "D004": "OutsideDoor",
}

WAKE_UP_CANDIDATE_LABELS = {
    "Bed_to_Toilet",
    "Bathroom",
    "Personal_Hygiene",
    "Bathing",
    "Toileting",
    "Meal_Preparation",
}


@dataclass(frozen=True)
class ADLInterval:
    start_time: datetime
    end_time: datetime
    raw_label: str
    adl_category: str


@dataclass(frozen=True)
class StateInterval:
    start_time: datetime
    end_time: datetime
    state_id: str


@dataclass(frozen=True)
class PatternRecord:
    pattern_id: str
    pattern_name: str
    sequence: tuple[str, ...]


@dataclass(frozen=True)
class PatternOccurrence:
    pattern_id: str
    pattern_name: str
    sequence: tuple[str, ...]
    start_time: datetime
    end_time: datetime


@dataclass(frozen=True)
class PatternADLMapping:
    pattern_id: str
    pattern_name: str
    sequence: tuple[str, ...]
    support: int
    assigned_adl: str
    confidence: float
    total_duration_seconds: float


@dataclass(frozen=True)
class PredictionInterval:
    pattern_id: str
    pattern_name: str
    sequence: tuple[str, ...]
    start_time: datetime
    end_time: datetime
    assigned_adl: str


@dataclass(frozen=True)
class MergedPredictionInterval:
    prediction_id: str
    start_time: datetime
    end_time: datetime
    assigned_adl: str
    num_merged_occurrences: int
    source_pattern_ids: tuple[str, ...]
    source_pattern_names: tuple[str, ...]


@dataclass(frozen=True)
class MatchRecord:
    category: str
    prediction_index: int
    truth_index: int
    temporal_iou: float
    start_error_minutes: float
    end_error_minutes: float
    abs_start_error_minutes: float
    abs_end_error_minutes: float


def parse_timestamp(date_text: str, time_text: str | None = None) -> datetime:
    """Parse timestamps used by CASAS text files and generated CSV files."""
    if time_text is None:
        text = date_text.strip()
    else:
        text = f"{date_text.strip()} {time_text.strip()}"
    return datetime.fromisoformat(text)


def normalize_label(label: str) -> str:
    return label.strip().replace(" ", "_")


def adl_category_for_label(raw_label: str) -> str:
    return ADL_CATEGORY_MAP.get(normalize_label(raw_label), "Other_ADL")


def lookup_adl_category_set(raw_label: str) -> tuple[str, ...] | None:
    normalized = normalize_label(raw_label)
    if normalized in ADL_CATEGORY_SET_MAP:
        return ADL_CATEGORY_SET_MAP[normalized]
    normalized_lower = normalized.lower()
    for key, labels in ADL_CATEGORY_SET_MAP.items():
        if key.lower() == normalized_lower:
            return labels
    return None


def adl_category_set_for_label(
    raw_label: str,
    primary_category: str | None = None,
) -> tuple[str, ...]:
    """Return one or more ADL labels for set-based interpretation evaluation."""
    labels = list(lookup_adl_category_set(raw_label) or ())
    if primary_category and primary_category not in {"Other_ADL", "Other"}:
        labels.append(primary_category)
    if not labels:
        labels.append("Other")

    seen = set()
    unique = []
    for label in labels:
        if label in seen:
            continue
        seen.add(label)
        unique.append(label)
    return tuple(unique)


def parse_labeled_casas_intervals(
    path: Path,
    wake_window_minutes: float = 30.0,
) -> list[ADLInterval]:
    """Read a labeled CASAS file and convert begin/end annotations to intervals."""
    active_by_label: dict[str, list[datetime]] = defaultdict(list)
    intervals: list[ADLInterval] = []

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 6:
            continue

        marker = parts[-1].lower()
        if marker not in {"begin", "end"}:
            continue

        timestamp = parse_timestamp(parts[0], parts[1])
        label = normalize_label(" ".join(parts[4:-1]))
        if not label:
            continue

        if marker == "begin":
            active_by_label[label].append(timestamp)
            continue

        if not active_by_label[label]:
            print(
                f"[WARN] {path}:{line_number}: activity end without begin: {label}",
                file=sys.stderr,
            )
            continue
        start_time = active_by_label[label].pop()
        if timestamp <= start_time:
            print(
                f"[WARN] {path}:{line_number}: activity end is not after begin: {label}",
                file=sys.stderr,
            )
            continue
        intervals.append(
            ADLInterval(
                start_time=start_time,
                end_time=timestamp,
                raw_label=label,
                adl_category=adl_category_for_label(label),
            )
        )

    for label, starts in sorted(active_by_label.items()):
        for start_time in starts:
            print(
                f"[WARN] {path}: activity begin without end: {label} at {start_time.isoformat(sep=' ')}",
                file=sys.stderr,
            )

    intervals.sort(key=lambda item: (item.start_time, item.end_time, item.raw_label))
    return apply_wake_up_rule(intervals, wake_window_minutes=wake_window_minutes)


def apply_wake_up_rule(
    intervals: Sequence[ADLInterval],
    wake_window_minutes: float,
) -> list[ADLInterval]:
    """Re-label selected post-sleep activities as Wake-up within a time window."""
    wake_window = timedelta(minutes=wake_window_minutes)
    sleep_end_times = [item.end_time for item in intervals if item.raw_label == "Sleeping"]
    adjusted: list[ADLInterval] = []

    for interval in intervals:
        category = interval.adl_category
        if interval.raw_label in WAKE_UP_CANDIDATE_LABELS:
            nearest_sleep_end = max(
                (end for end in sleep_end_times if end <= interval.start_time),
                default=None,
            )
            if nearest_sleep_end is not None and interval.start_time - nearest_sleep_end <= wake_window:
                category = "Wake-up"
        adjusted.append(
            ADLInterval(
                start_time=interval.start_time,
                end_time=interval.end_time,
                raw_label=interval.raw_label,
                adl_category=category,
            )
        )
    return adjusted


def load_state_series_csv(path: Path) -> list[StateInterval]:
    """Load state intervals from CSV.

    Supported columns:
    - start_time,end_time,state_id
    - start,end,state_id
    - timestamp,state_id (converted to adjacent intervals)
    """
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return []

    columns = set(rows[0].keys())
    state_col = "state_id" if "state_id" in columns else "state"

    if {"start_time", "end_time", state_col}.issubset(columns):
        start_col, end_col = "start_time", "end_time"
    elif {"start", "end", state_col}.issubset(columns):
        start_col, end_col = "start", "end"
    elif {"timestamp", state_col}.issubset(columns):
        parsed = [
            (parse_timestamp(row["timestamp"]), row[state_col])
            for row in rows
            if row.get("timestamp") and row.get(state_col)
        ]
        parsed.sort(key=lambda item: item[0])
        return [
            StateInterval(start_time=ts, end_time=parsed[index + 1][0], state_id=state_id)
            for index, (ts, state_id) in enumerate(parsed[:-1])
            if parsed[index + 1][0] > ts
        ]
    else:
        raise ValueError(
            f"Unsupported state series CSV columns: {sorted(columns)}. "
            "Expected start_time/end_time/state_id or timestamp/state_id."
        )

    intervals = []
    for row in rows:
        if not row.get(start_col) or not row.get(end_col) or not row.get(state_col):
            continue
        start_time = parse_timestamp(row[start_col])
        end_time = parse_timestamp(row[end_col])
        if end_time <= start_time:
            continue
        intervals.append(
            StateInterval(
                start_time=start_time,
                end_time=end_time,
                state_id=row[state_col].strip(),
            )
        )
    intervals.sort(key=lambda item: (item.start_time, item.end_time))
    return intervals


_OrderedSensorEvent = tuple[datetime, str, str]


def _build_state_intervals_from_ordered_sensor_events(
    events: Iterable[_OrderedSensorEvent],
    sensor_columns: Sequence[str],
    state_mapping: dict[tuple[int, ...], str],
    hamming_threshold: int,
) -> list[StateInterval]:
    """入力順のセンサーイベントを代表状態の連続区間へ変換する。

    ``events`` は ``(timestamp, sensor, value)`` の順序付き系列であり、この
    関数内では並べ替えない。未知のセンサーとON/OFFに解釈できない値は状態更新にも
    最終時刻にも含めず、受理したイベントだけを代表状態へ写像する。

    最終区間の終了は、event-driven前処理の既存仕様に合わせて最後に受理した
    イベントの時刻とする。このため、最後のイベントで始まる長さ0の区間は出力しない。
    """
    current_sensor_state = {sensor: 0 for sensor in sensor_columns}
    intervals: list[StateInterval] = []
    current_label: str | None = None
    current_start: datetime | None = None
    last_timestamp: datetime | None = None

    # 評価結果の再現性を保つため、同一時刻を含め呼び出し側から渡された順序を維持する。
    for timestamp, raw_sensor, raw_value in events:
        sensor = raw_sensor.strip()
        value = raw_value.strip().upper()
        if sensor not in current_sensor_state:
            continue

        if value in DEFAULT_ACTIVE_VALUES:
            current_sensor_state[sensor] = 1
        elif value in DEFAULT_INACTIVE_VALUES:
            current_sensor_state[sensor] = 0
        else:
            continue

        vector = tuple(
            current_sensor_state[sensor_name] for sensor_name in sensor_columns
        )
        state_id = map_vector_to_state(
            vector,
            state_mapping,
            hamming_threshold=hamming_threshold,
        )

        if current_label is None:
            current_label = state_id
            current_start = timestamp
        elif state_id != current_label:
            if current_start is not None and timestamp > current_start:
                intervals.append(
                    StateInterval(
                        start_time=current_start,
                        end_time=timestamp,
                        state_id=current_label,
                    )
                )
            current_label = state_id
            current_start = timestamp

        last_timestamp = timestamp

    if (
        current_label is not None
        and current_start is not None
        and last_timestamp is not None
    ):
        if last_timestamp > current_start:
            intervals.append(
                StateInterval(
                    start_time=current_start,
                    end_time=last_timestamp,
                    state_id=current_label,
                )
            )

    return intervals


def build_state_series_from_event_log(
    event_log_path: Path,
    state_table_path: Path,
    hamming_threshold: int,
) -> list[StateInterval]:
    """イベントログを代表状態の時刻区間へ変換する。"""
    events = load_event_log(event_log_path)
    sensor_cols, state_mapping = load_state_mapping(state_table_path)
    ordered_events = (
        (
            row["timestamp"].to_pydatetime(),
            str(row["sensor"]),
            str(row["value"]),
        )
        for _, row in events.iterrows()
    )
    return _build_state_intervals_from_ordered_sensor_events(
        ordered_events,
        sensor_columns=sensor_cols,
        state_mapping=state_mapping,
        hamming_threshold=hamming_threshold,
    )


def load_sensor_id_map(path: Path | None) -> dict[str, str]:
    if path is None:
        return dict(DEFAULT_ARUBA_SENSOR_ID_MAP)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Sensor map must be a JSON object: {path}")
    return {str(key).strip(): str(value).strip() for key, value in payload.items()}


def _ceil_to_second(timestamp: datetime) -> datetime:
    rounded = timestamp.replace(microsecond=0)
    if timestamp.microsecond:
        rounded += timedelta(seconds=1)
    return rounded


_MappedBinaryEvent = tuple[datetime, int, str, int]
_SensorOnIntervals = dict[str, list[tuple[datetime, datetime]]]


def _load_mapped_binary_events(
    labeled_casas_path: Path,
    sensor_id_map: dict[str, str],
    sensor_columns: Sequence[str],
) -> list[_MappedBinaryEvent]:
    """CASASログから代表状態表に対応する二値イベントを読み込む。

    ON/OFFとして解釈できない値は除外し、代表状態表に存在しないセンサーは
    まとめて既存の例外にする。イベントは時刻、同時刻では元の行番号の順に並べ、
    同秒内の更新順を再現できる形で返す。
    """
    sensor_set = set(sensor_columns)
    events: list[_MappedBinaryEvent] = []
    unexpected_sensors: set[str] = set()

    with labeled_casas_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            parts = raw_line.strip().split()
            if len(parts) < 4:
                continue
            value = parts[3].strip().upper()
            if value in DEFAULT_ACTIVE_VALUES:
                binary_value = 1
            elif value in DEFAULT_INACTIVE_VALUES:
                binary_value = 0
            else:
                continue

            sensor = sensor_id_map.get(parts[2].strip(), parts[2].strip())
            if sensor not in sensor_set:
                unexpected_sensors.add(sensor)
                continue
            events.append(
                (
                    parse_timestamp(parts[0], parts[1]),
                    line_number,
                    sensor,
                    binary_value,
                )
            )

    if unexpected_sensors:
        preview = ", ".join(sorted(unexpected_sensors)[:20])
        raise ValueError(
            "ON/OFF sensors are missing from the representative-state definition: "
            f"{preview}"
        )
    if not events:
        raise ValueError(
            f"No mapped ON/OFF events were loaded from: {labeled_casas_path}"
        )

    events.sort(key=lambda item: (item[0], item[1]))
    return events


def _build_one_second_sensor_updates(
    events: Sequence[_MappedBinaryEvent],
    duration_days: int | None,
) -> tuple[datetime, datetime, dict[datetime, dict[str, int]]]:
    """分析期間と1秒境界のセンサー更新を構築する。

    期間は最初のイベント日の00:00を始端とする半開区間である。イベント時刻は
    1秒境界へ切り上げ、同じ秒・同じセンサーの更新は入力順で最後の値を採用する。
    """
    first_timestamp = events[0][0]
    last_timestamp = events[-1][0]
    period_start = datetime.combine(first_timestamp.date(), datetime.min.time())
    if duration_days is None:
        period_end = datetime.combine(
            (last_timestamp + timedelta(days=1)).date(),
            datetime.min.time(),
        )
    else:
        period_end = period_start + timedelta(days=duration_days)

    updates_by_time: dict[datetime, dict[str, int]] = defaultdict(dict)
    for timestamp, _, sensor, binary_value in events:
        sample_time = _ceil_to_second(timestamp)
        if period_start <= sample_time < period_end:
            # 半開区間を維持し、同秒の同一センサーは後のイベントで上書きする。
            updates_by_time[sample_time][sensor] = binary_value

    return period_start, period_end, updates_by_time


def _build_delayed_off_intervals_by_sensor(
    sensor_columns: Sequence[str],
    updates_by_time: dict[datetime, dict[str, int]],
    period_start: datetime,
    period_end: datetime,
    smoothing_window_sec: int,
) -> _SensorOnIntervals:
    """センサー別に遅延OFF適用後のON半開区間を生成する。

    1秒サンプリングのtrailing rolling maxと一致させるため、OFF端を
    ``window - 1`` 秒だけ延長する。重なる区間と端点で接する区間は、従来どおり
    1区間へ統合する。
    """
    smoothed_intervals_by_sensor: _SensorOnIntervals = {
        sensor: [] for sensor in sensor_columns
    }
    sorted_update_times = sorted(updates_by_time)
    delayed_off_extension = timedelta(seconds=max(smoothing_window_sec - 1, 0))

    for sensor in sensor_columns:
        raw_state = 0
        on_start: datetime | None = None
        raw_on_intervals: list[tuple[datetime, datetime]] = []
        for sample_time in sorted_update_times:
            if sensor not in updates_by_time[sample_time]:
                continue
            next_state = updates_by_time[sample_time][sensor]
            if next_state == raw_state:
                continue
            raw_state = next_state
            if raw_state:
                on_start = sample_time
            elif on_start is not None:
                raw_on_intervals.append(
                    (on_start, min(sample_time + delayed_off_extension, period_end))
                )
                on_start = None
        if raw_state and on_start is not None:
            raw_on_intervals.append((on_start, period_end))

        merged: list[tuple[datetime, datetime]] = []
        for start_time, end_time in raw_on_intervals:
            if end_time <= period_start or start_time >= period_end:
                continue
            start_time = max(start_time, period_start)
            end_time = min(end_time, period_end)
            if end_time <= start_time:
                continue
            if merged and start_time <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end_time))
            else:
                merged.append((start_time, end_time))
        smoothed_intervals_by_sensor[sensor] = merged

    return smoothed_intervals_by_sensor


def _build_state_intervals_from_sensor_boundaries(
    smoothed_intervals_by_sensor: _SensorOnIntervals,
    sensor_columns: Sequence[str],
    state_mapping: dict[tuple[int, ...], str],
    hamming_threshold: int,
    period_start: datetime,
    period_end: datetime,
) -> list[StateInterval]:
    """ON区間の境界から圧縮済み代表状態区間を構築する。

    代表状態は呼び出し側から渡された固定表だけで写像する。同じ代表状態が境界を
    またいで連続する場合は、端点が一致する区間だけを連結して既存出力を保つ。
    """
    boundary_updates: dict[datetime, dict[str, int]] = defaultdict(dict)
    for sensor, intervals in smoothed_intervals_by_sensor.items():
        for start_time, end_time in intervals:
            boundary_updates[start_time][sensor] = 1
            if end_time < period_end:
                boundary_updates[end_time][sensor] = 0

    current_sensor_state = {sensor: 0 for sensor in sensor_columns}
    output: list[StateInterval] = []

    def mapped_state_id() -> str:
        vector = tuple(current_sensor_state[sensor] for sensor in sensor_columns)
        return map_vector_to_state(
            vector,
            state_mapping,
            hamming_threshold=hamming_threshold,
        )

    def append_interval(start_time: datetime, end_time: datetime, state_id: str) -> None:
        if end_time <= start_time:
            return
        if (
            output
            and output[-1].state_id == state_id
            and output[-1].end_time == start_time
        ):
            previous = output[-1]
            output[-1] = StateInterval(
                start_time=previous.start_time,
                end_time=end_time,
                state_id=state_id,
            )
        else:
            output.append(
                StateInterval(
                    start_time=start_time,
                    end_time=end_time,
                    state_id=state_id,
                )
            )

    current_time = period_start
    for boundary_time in sorted(boundary_updates):
        if boundary_time > current_time:
            append_interval(current_time, boundary_time, mapped_state_id())
            current_time = boundary_time
        for sensor, value in boundary_updates[boundary_time].items():
            current_sensor_state[sensor] = value
    if current_time < period_end:
        append_interval(current_time, period_end, mapped_state_id())
    return output


def build_network_equivalent_state_series_from_labeled_casas(
    labeled_casas_path: Path,
    state_table_path: Path,
    hamming_threshold: int,
    smoothing_window_sec: int = 5,
    sensor_map_path: Path | None = None,
    duration_days: int | None = None,
) -> list[StateInterval]:
    """状態遷移ネットワークと等価な圧縮代表状態系列を構築する。

    1秒Sample-and-Holdと ``rolling(window).max()`` の遅延OFFを変化点だけで
    再現し、評価5の長期間データで1秒行列を展開しない。代表状態は
    ``state_table_path`` の固定表を使い、評価データから再抽出しない。
    """
    if smoothing_window_sec < 0:
        raise ValueError("smoothing_window_sec must be non-negative")
    if duration_days is not None and duration_days < 1:
        raise ValueError("duration_days must be >= 1")

    sensor_id_map = load_sensor_id_map(sensor_map_path)
    sensor_columns, state_mapping = load_state_mapping(state_table_path)
    events = _load_mapped_binary_events(
        labeled_casas_path,
        sensor_id_map,
        sensor_columns,
    )
    period_start, period_end, updates_by_time = _build_one_second_sensor_updates(
        events,
        duration_days,
    )
    smoothed_intervals_by_sensor = _build_delayed_off_intervals_by_sensor(
        sensor_columns,
        updates_by_time,
        period_start,
        period_end,
        smoothing_window_sec,
    )
    return _build_state_intervals_from_sensor_boundaries(
        smoothed_intervals_by_sensor,
        sensor_columns,
        state_mapping,
        hamming_threshold,
        period_start,
        period_end,
    )


def build_state_series_from_labeled_casas(
    labeled_casas_path: Path,
    state_table_path: Path,
    hamming_threshold: int,
    sensor_map_path: Path | None = None,
) -> list[StateInterval]:
    """ラベル付きCASASテキストから代表状態の時刻区間を構築する。"""
    sensor_id_map = load_sensor_id_map(sensor_map_path)
    sensor_cols, state_mapping = load_state_mapping(state_table_path)
    sensor_set = set(sensor_cols)

    def ordered_events() -> Iterable[_OrderedSensorEvent]:
        for raw_line in labeled_casas_path.read_text(encoding="utf-8").splitlines():
            parts = raw_line.strip().split()
            if len(parts) < 4:
                continue

            sensor = sensor_id_map.get(parts[2].strip(), parts[2].strip())
            if sensor not in sensor_set:
                # 未知センサーは従来どおり、時刻や値を解釈する前に除外する。
                continue
            yield parse_timestamp(parts[0], parts[1]), sensor, parts[3]

    return _build_state_intervals_from_ordered_sensor_events(
        ordered_events(),
        sensor_columns=sensor_cols,
        state_mapping=state_mapping,
        hamming_threshold=hamming_threshold,
    )


def write_state_series_csv(intervals: Sequence[StateInterval], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["start_time", "end_time", "state_id"])
        writer.writeheader()
        for interval in intervals:
            writer.writerow(
                {
                    "start_time": interval.start_time.isoformat(sep=" "),
                    "end_time": interval.end_time.isoformat(sep=" "),
                    "state_id": interval.state_id,
                }
            )


def load_patterns(path: Path) -> list[PatternRecord]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Pattern JSON must be a list: {path}")

    patterns: list[PatternRecord] = []
    for index, item in enumerate(payload, start=1):
        if isinstance(item, dict):
            sequence = item.get("遷移のパターン") or item.get("遷移のシーケンス") or item.get("sequence")
            pattern_name = item.get("パターン名") or item.get("pattern_name") or f"P{index}"
        elif isinstance(item, list):
            sequence = item
            pattern_name = f"P{index}"
        else:
            continue

        if not isinstance(sequence, list) or not all(isinstance(state, str) for state in sequence):
            continue
        if len(sequence) < 2:
            continue
        patterns.append(
            PatternRecord(
                pattern_id=f"P{len(patterns) + 1}",
                pattern_name=str(pattern_name),
                sequence=tuple(sequence),
            )
        )
    return patterns


def duration_seconds(start_time: datetime, end_time: datetime) -> float:
    return max(0.0, (end_time - start_time).total_seconds())


def interval_overlap_seconds(
    start_a: datetime,
    end_a: datetime,
    start_b: datetime,
    end_b: datetime,
) -> float:
    return duration_seconds(max(start_a, start_b), min(end_a, end_b))


def temporal_iou(
    pred_start: datetime,
    pred_end: datetime,
    true_start: datetime,
    true_end: datetime,
) -> float:
    overlap = interval_overlap_seconds(pred_start, pred_end, true_start, true_end)
    union = duration_seconds(min(pred_start, true_start), max(pred_end, true_end))
    return overlap / union if union > 0 else 0.0


def find_pattern_occurrences(
    patterns: Sequence[PatternRecord],
    state_intervals: Sequence[StateInterval],
    match_mode: str = "exact",
    max_skip_duration_minutes: float = 1.0,
) -> list[PatternOccurrence]:
    if match_mode not in {"exact", "skip-other"}:
        raise ValueError("match_mode must be 'exact' or 'skip-other'")

    occurrences: list[PatternOccurrence] = []
    for pattern in patterns:
        if match_mode == "exact":
            occurrences.extend(find_exact_occurrences(pattern, state_intervals))
        else:
            occurrences.extend(
                find_skip_other_occurrences(
                    pattern,
                    state_intervals,
                    max_skip_duration=timedelta(minutes=max_skip_duration_minutes),
                )
            )
    return occurrences


def find_exact_occurrences(
    pattern: PatternRecord,
    state_intervals: Sequence[StateInterval],
) -> list[PatternOccurrence]:
    length = len(pattern.sequence)
    occurrences: list[PatternOccurrence] = []
    for start_index in range(0, len(state_intervals) - length + 1):
        window = state_intervals[start_index : start_index + length]
        if tuple(item.state_id for item in window) != pattern.sequence:
            continue
        occurrences.append(
            PatternOccurrence(
                pattern_id=pattern.pattern_id,
                pattern_name=pattern.pattern_name,
                sequence=pattern.sequence,
                start_time=window[0].start_time,
                end_time=window[-1].end_time,
            )
        )
    return occurrences


def find_skip_other_occurrences(
    pattern: PatternRecord,
    state_intervals: Sequence[StateInterval],
    max_skip_duration: timedelta,
) -> list[PatternOccurrence]:
    occurrences: list[PatternOccurrence] = []
    for start_index, first_interval in enumerate(state_intervals):
        if first_interval.state_id != pattern.sequence[0]:
            continue
        matched_indices = [start_index]
        seq_index = 1
        skip_count = 0
        cursor = start_index + 1
        while cursor < len(state_intervals) and seq_index < len(pattern.sequence):
            interval = state_intervals[cursor]
            if interval.state_id == pattern.sequence[seq_index]:
                matched_indices.append(cursor)
                seq_index += 1
                cursor += 1
                continue
            if (
                interval.state_id == "その他"
                and skip_count < 1
                and interval.end_time - interval.start_time <= max_skip_duration
            ):
                skip_count += 1
                cursor += 1
                continue
            break
        if seq_index == len(pattern.sequence):
            window = [state_intervals[index] for index in matched_indices]
            occurrences.append(
                PatternOccurrence(
                    pattern_id=pattern.pattern_id,
                    pattern_name=pattern.pattern_name,
                    sequence=pattern.sequence,
                    start_time=window[0].start_time,
                    end_time=window[-1].end_time,
                )
            )
    return occurrences


def assign_patterns_to_adl(
    patterns: Sequence[PatternRecord],
    occurrences: Sequence[PatternOccurrence],
    adl_intervals: Sequence[ADLInterval],
) -> list[PatternADLMapping]:
    occurrences_by_pattern: dict[str, list[PatternOccurrence]] = defaultdict(list)
    for occurrence in occurrences:
        occurrences_by_pattern[occurrence.pattern_id].append(occurrence)

    sorted_labels = sorted(adl_intervals, key=lambda item: item.start_time)
    mappings: list[PatternADLMapping] = []
    for pattern in patterns:
        pattern_occurrences = sorted(
            occurrences_by_pattern.get(pattern.pattern_id, []),
            key=lambda item: item.start_time,
        )
        total_duration = sum(
            duration_seconds(item.start_time, item.end_time)
            for item in pattern_occurrences
        )
        overlap_by_category: dict[str, float] = defaultdict(float)
        label_cursor = 0
        for occurrence in pattern_occurrences:
            while (
                label_cursor < len(sorted_labels)
                and sorted_labels[label_cursor].end_time <= occurrence.start_time
            ):
                label_cursor += 1
            for label in sorted_labels[label_cursor:]:
                if label.start_time >= occurrence.end_time:
                    break
                overlap_by_category[label.adl_category] += interval_overlap_seconds(
                    occurrence.start_time,
                    occurrence.end_time,
                    label.start_time,
                    label.end_time,
                )

        if overlap_by_category:
            assigned_adl, assigned_overlap = max(
                overlap_by_category.items(),
                key=lambda item: (item[1], item[0]),
            )
        else:
            assigned_adl, assigned_overlap = "Unmapped", 0.0

        confidence = assigned_overlap / total_duration if total_duration > 0 else 0.0
        mappings.append(
            PatternADLMapping(
                pattern_id=pattern.pattern_id,
                pattern_name=pattern.pattern_name,
                sequence=pattern.sequence,
                support=len(pattern_occurrences),
                assigned_adl=assigned_adl,
                confidence=confidence,
                total_duration_seconds=total_duration,
            )
        )
    return mappings


def build_predictions(
    occurrences: Sequence[PatternOccurrence],
    mappings: Sequence[PatternADLMapping],
) -> list[PredictionInterval]:
    mapping_by_pattern = {mapping.pattern_id: mapping for mapping in mappings}
    predictions: list[PredictionInterval] = []
    for occurrence in occurrences:
        mapping = mapping_by_pattern.get(occurrence.pattern_id)
        if mapping is None or mapping.assigned_adl == "Unmapped":
            continue
        predictions.append(
            PredictionInterval(
                pattern_id=occurrence.pattern_id,
                pattern_name=occurrence.pattern_name,
                sequence=occurrence.sequence,
                start_time=occurrence.start_time,
                end_time=occurrence.end_time,
                assigned_adl=mapping.assigned_adl,
            )
        )
    return predictions


def unique_preserve_order(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    unique = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return tuple(unique)


def merge_prediction_intervals(
    predictions: Sequence[PredictionInterval],
    merge_gap_minutes: float,
) -> list[MergedPredictionInterval]:
    """Merge nearby predictions within the same assigned ADL category."""
    if merge_gap_minutes < 0:
        raise ValueError("merge_gap_minutes must be non-negative")

    sorted_predictions = sorted(
        predictions,
        key=lambda item: (item.assigned_adl, item.start_time, item.end_time, item.pattern_id),
    )
    if merge_gap_minutes == 0:
        return [
            MergedPredictionInterval(
                prediction_id=f"MP{index:06d}",
                start_time=item.start_time,
                end_time=item.end_time,
                assigned_adl=item.assigned_adl,
                num_merged_occurrences=1,
                source_pattern_ids=(item.pattern_id,),
                source_pattern_names=(item.pattern_name,),
            )
            for index, item in enumerate(sorted_predictions, start=1)
        ]

    max_gap = timedelta(minutes=merge_gap_minutes)
    merged: list[MergedPredictionInterval] = []
    current_category: str | None = None
    current_start: datetime | None = None
    current_end: datetime | None = None
    current_pattern_ids: list[str] = []
    current_pattern_names: list[str] = []
    current_count = 0

    def flush_current() -> None:
        if current_category is None or current_start is None or current_end is None:
            return
        merged.append(
            MergedPredictionInterval(
                prediction_id=f"MP{len(merged) + 1:06d}",
                start_time=current_start,
                end_time=current_end,
                assigned_adl=current_category,
                num_merged_occurrences=current_count,
                source_pattern_ids=unique_preserve_order(current_pattern_ids),
                source_pattern_names=unique_preserve_order(current_pattern_names),
            )
        )

    for prediction in sorted_predictions:
        if current_category is None:
            current_category = prediction.assigned_adl
            current_start = prediction.start_time
            current_end = prediction.end_time
            current_pattern_ids = [prediction.pattern_id]
            current_pattern_names = [prediction.pattern_name]
            current_count = 1
            continue

        assert current_end is not None
        same_category = prediction.assigned_adl == current_category
        close_enough = prediction.start_time - current_end <= max_gap
        if same_category and close_enough:
            current_end = max(current_end, prediction.end_time)
            current_pattern_ids.append(prediction.pattern_id)
            current_pattern_names.append(prediction.pattern_name)
            current_count += 1
            continue

        flush_current()
        current_category = prediction.assigned_adl
        current_start = prediction.start_time
        current_end = prediction.end_time
        current_pattern_ids = [prediction.pattern_id]
        current_pattern_names = [prediction.pattern_name]
        current_count = 1

    flush_current()
    return merged


def load_min_duration_config(path: Path | None) -> dict[str, float]:
    config = {key: float(value) for key, value in DEFAULT_MIN_DURATION_BY_ADL.items()}
    if path is None:
        return config

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Min-duration config must be a JSON object: {path}")
    for key, value in payload.items():
        try:
            config[str(key)] = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid min-duration value for {key!r}: {value!r}") from exc
    if "Other" in config and "Other_ADL" not in payload:
        config["Other_ADL"] = config["Other"]
    return config


def min_duration_for_adl(adl_category: str, min_duration_by_adl: dict[str, float]) -> float:
    if adl_category in min_duration_by_adl:
        return min_duration_by_adl[adl_category]
    return min_duration_by_adl.get("Other_ADL", min_duration_by_adl.get("Other", 0.0))


def filter_predictions_by_duration(
    predictions: Sequence[MergedPredictionInterval],
    min_duration_by_adl: dict[str, float],
) -> tuple[list[MergedPredictionInterval], dict[str, int]]:
    kept: list[MergedPredictionInterval] = []
    removed_by_category: dict[str, int] = defaultdict(int)
    for prediction in predictions:
        duration = duration_seconds(prediction.start_time, prediction.end_time)
        minimum_duration = min_duration_for_adl(prediction.assigned_adl, min_duration_by_adl)
        if duration >= minimum_duration:
            kept.append(prediction)
        else:
            removed_by_category[prediction.assigned_adl] += 1
    return kept, dict(sorted(removed_by_category.items()))


def prediction_duration_row(prediction: MergedPredictionInterval, include_duration: bool) -> dict:
    row = {
        "predicted_adl": prediction.assigned_adl,
        "start_time": prediction.start_time.isoformat(sep=" "),
        "end_time": prediction.end_time.isoformat(sep=" "),
        "num_merged_occurrences": prediction.num_merged_occurrences,
        "source_pattern_ids": "|".join(prediction.source_pattern_ids),
        "source_pattern_names": "|".join(prediction.source_pattern_names),
    }
    if include_duration:
        row["duration_seconds"] = f"{duration_seconds(prediction.start_time, prediction.end_time):.3f}"
    return row


def merged_to_prediction_intervals(
    predictions: Sequence[MergedPredictionInterval],
) -> list[PredictionInterval]:
    converted: list[PredictionInterval] = []
    for prediction in predictions:
        converted.append(
            PredictionInterval(
                pattern_id=prediction.prediction_id,
                pattern_name="|".join(prediction.source_pattern_names),
                sequence=(),
                start_time=prediction.start_time,
                end_time=prediction.end_time,
                assigned_adl=prediction.assigned_adl,
            )
        )
    return converted


def compute_interval_hit_evaluation(
    predictions: Sequence[MergedPredictionInterval],
    truths: Sequence[ADLInterval],
    hit_tolerance_minutes: float,
) -> tuple[list[dict], list[dict]]:
    if hit_tolerance_minutes < 0:
        raise ValueError("hit_tolerance_minutes must be non-negative")

    rows: list[dict] = []
    details: list[dict] = []
    for hit_type, tolerance in (
        ("overlap", timedelta(minutes=0)),
        ("tolerance", timedelta(minutes=hit_tolerance_minutes)),
    ):
        truth_hit_counts: dict[int, set[str]] = defaultdict(set)
        matched_prediction_ids: set[str] = set()
        categories = sorted(
            {truth.adl_category for truth in truths}
            | {prediction.assigned_adl for prediction in predictions}
        )

        for category in categories:
            truth_indices = [
                index for index, truth in enumerate(truths)
                if truth.adl_category == category
            ]
            prediction_indices = [
                index for index, prediction in enumerate(predictions)
                if prediction.assigned_adl == category
            ]
            truth_indices.sort(key=lambda index: truths[index].start_time)
            prediction_indices.sort(key=lambda index: predictions[index].start_time)

            prediction_cursor = 0
            for truth_index in truth_indices:
                truth = truths[truth_index]
                expanded_start = truth.start_time - tolerance
                expanded_end = truth.end_time + tolerance
                while (
                    prediction_cursor < len(prediction_indices)
                    and predictions[prediction_indices[prediction_cursor]].end_time <= expanded_start
                ):
                    prediction_cursor += 1
                cursor = prediction_cursor
                while cursor < len(prediction_indices):
                    prediction = predictions[prediction_indices[cursor]]
                    if prediction.start_time >= expanded_end:
                        break
                    if interval_overlap_seconds(
                        prediction.start_time,
                        prediction.end_time,
                        expanded_start,
                        expanded_end,
                    ) > 0:
                        truth_hit_counts[truth_index].add(prediction.prediction_id)
                        matched_prediction_ids.add(prediction.prediction_id)
                    cursor += 1

        for truth_index, truth in enumerate(truths):
            matched_ids = sorted(truth_hit_counts.get(truth_index, set()))
            details.append(
                {
                    "hit_type": hit_type,
                    "true_adl": truth.adl_category,
                    "start_time": truth.start_time.isoformat(sep=" "),
                    "end_time": truth.end_time.isoformat(sep=" "),
                    "is_hit": bool(matched_ids),
                    "matched_prediction_count": len(matched_ids),
                    "matched_prediction_ids": "|".join(matched_ids),
                }
            )

        for category in categories:
            truth_indices = [
                index for index, truth in enumerate(truths)
                if truth.adl_category == category
            ]
            prediction_ids = {
                prediction.prediction_id
                for prediction in predictions
                if prediction.assigned_adl == category
            }
            hit_intervals = sum(1 for index in truth_indices if truth_hit_counts.get(index))
            matched_prediction_count = len(prediction_ids & matched_prediction_ids)
            rows.append(
                {
                    "hit_type": hit_type,
                    "adl_category": category,
                    "true_intervals": len(truth_indices),
                    "hit_intervals": hit_intervals,
                    "missed_intervals": len(truth_indices) - hit_intervals,
                    "hit_rate": safe_divide(hit_intervals, len(truth_indices)),
                    "prediction_intervals": len(prediction_ids),
                    "matched_prediction_intervals": matched_prediction_count,
                    "unmatched_prediction_intervals": len(prediction_ids) - matched_prediction_count,
                    "prediction_hit_precision": safe_divide(matched_prediction_count, len(prediction_ids)),
                }
            )

    return rows, details


def greedy_match_by_category(
    predictions: Sequence[PredictionInterval],
    truths: Sequence[ADLInterval],
    iou_threshold: float,
) -> tuple[list[MatchRecord], dict[str, dict[str, int]]]:
    categories = sorted(
        {prediction.assigned_adl for prediction in predictions}
        | {truth.adl_category for truth in truths}
    )
    matches: list[MatchRecord] = []
    counts = {
        category: {"tp": 0, "fp": 0, "fn": 0}
        for category in categories
    }

    for category in categories:
        pred_indices = [
            index for index, prediction in enumerate(predictions)
            if prediction.assigned_adl == category
        ]
        truth_indices = [
            index for index, truth in enumerate(truths)
            if truth.adl_category == category
        ]

        pred_indices.sort(key=lambda index: predictions[index].start_time)
        truth_indices.sort(key=lambda index: truths[index].start_time)

        candidate_pairs = []
        truth_cursor = 0
        for pred_index in pred_indices:
            prediction = predictions[pred_index]
            while (
                truth_cursor < len(truth_indices)
                and truths[truth_indices[truth_cursor]].end_time <= prediction.start_time
            ):
                truth_cursor += 1
            for truth_index in truth_indices[truth_cursor:]:
                truth = truths[truth_index]
                if truth.start_time >= prediction.end_time:
                    break
                iou = temporal_iou(
                    prediction.start_time,
                    prediction.end_time,
                    truth.start_time,
                    truth.end_time,
                )
                if iou >= iou_threshold:
                    candidate_pairs.append((iou, pred_index, truth_index))
        candidate_pairs.sort(reverse=True)

        used_predictions: set[int] = set()
        used_truths: set[int] = set()
        for iou, pred_index, truth_index in candidate_pairs:
            if pred_index in used_predictions or truth_index in used_truths:
                continue
            prediction = predictions[pred_index]
            truth = truths[truth_index]
            used_predictions.add(pred_index)
            used_truths.add(truth_index)
            matches.append(
                MatchRecord(
                    category=category,
                    prediction_index=pred_index,
                    truth_index=truth_index,
                    temporal_iou=iou,
                    start_error_minutes=(prediction.start_time - truth.start_time).total_seconds() / 60.0,
                    end_error_minutes=(prediction.end_time - truth.end_time).total_seconds() / 60.0,
                    abs_start_error_minutes=abs((prediction.start_time - truth.start_time).total_seconds() / 60.0),
                    abs_end_error_minutes=abs((prediction.end_time - truth.end_time).total_seconds() / 60.0),
                )
            )

        tp = len(used_predictions)
        fp = len(pred_indices) - tp
        fn = len(truth_indices) - len(used_truths)
        counts[category] = {"tp": tp, "fp": fp, "fn": fn}

    return matches, counts


def safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def metrics_rows_from_counts(counts: dict[str, dict[str, int]]) -> list[dict]:
    rows = []
    for category in sorted(counts):
        tp = counts[category]["tp"]
        fp = counts[category]["fp"]
        fn = counts[category]["fn"]
        precision = safe_divide(tp, tp + fp)
        recall = safe_divide(tp, tp + fn)
        f1 = safe_divide(2 * precision * recall, precision + recall)
        rows.append(
            {
                "adl_category": category,
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "precision": precision,
                "recall": recall,
                "f1": f1,
            }
        )
    return rows


def boundary_rows(matches: Sequence[MatchRecord]) -> list[dict]:
    by_category: dict[str, list[MatchRecord]] = defaultdict(list)
    for match in matches:
        by_category[match.category].append(match)

    rows = []
    for category in sorted(by_category):
        records = by_category[category]
        rows.append(
            {
                "adl_category": category,
                "mean_start_error": statistics.fmean(r.start_error_minutes for r in records),
                "median_abs_start_error": statistics.median(r.abs_start_error_minutes for r in records),
                "mean_end_error": statistics.fmean(r.end_error_minutes for r in records),
                "median_abs_end_error": statistics.median(r.abs_end_error_minutes for r in records),
                "mean_iou": statistics.fmean(r.temporal_iou for r in records),
                "matched_count": len(records),
            }
        )
    return rows


def macro_micro_average(rows: Sequence[dict]) -> dict:
    if not rows:
        return {
            "macro_precision": 0.0,
            "macro_recall": 0.0,
            "macro_f1": 0.0,
            "micro_precision": 0.0,
            "micro_recall": 0.0,
            "micro_f1": 0.0,
        }
    macro_precision = statistics.fmean(row["precision"] for row in rows)
    macro_recall = statistics.fmean(row["recall"] for row in rows)
    macro_f1 = statistics.fmean(row["f1"] for row in rows)
    tp = sum(row["tp"] for row in rows)
    fp = sum(row["fp"] for row in rows)
    fn = sum(row["fn"] for row in rows)
    micro_precision = safe_divide(tp, tp + fp)
    micro_recall = safe_divide(tp, tp + fn)
    micro_f1 = safe_divide(2 * micro_precision * micro_recall, micro_precision + micro_recall)
    return {
        "macro_precision": macro_precision,
        "macro_recall": macro_recall,
        "macro_f1": macro_f1,
        "micro_precision": micro_precision,
        "micro_recall": micro_recall,
        "micro_f1": micro_f1,
    }


def filter_intervals_by_period(
    intervals: Iterable,
    start_time: datetime | None,
    end_time: datetime | None,
) -> list:
    filtered = []
    for interval in intervals:
        if start_time is not None and interval.end_time <= start_time:
            continue
        if end_time is not None and interval.start_time >= end_time:
            continue
        filtered.append(interval)
    return filtered


def split_time_from_ratio(
    intervals: Sequence[ADLInterval],
    train_ratio: float | None,
) -> datetime | None:
    if train_ratio is None:
        return None
    if not intervals:
        return None
    if not 0.0 < train_ratio < 1.0:
        raise ValueError("--train-ratio must be between 0 and 1")
    start_time = min(interval.start_time for interval in intervals)
    end_time = max(interval.end_time for interval in intervals)
    return start_time + (end_time - start_time) * train_ratio


def sequence_text(sequence: Sequence[str]) -> str:
    return "->".join(sequence)


def write_csv_rows(path: Path, rows: Sequence[dict], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_evaluation_outputs(
    output_dir: Path,
    occurrences: Sequence[PatternOccurrence],
    mappings: Sequence[PatternADLMapping],
    metrics_by_threshold: dict[float, list[dict]],
    boundary_by_threshold: dict[float, list[dict]],
    summary: dict,
    merged_predictions: Sequence[MergedPredictionInterval] | None = None,
    filtered_predictions: Sequence[MergedPredictionInterval] | None = None,
    hit_metric_rows: Sequence[dict] | None = None,
    hit_detail_rows: Sequence[dict] | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    write_csv_rows(
        output_dir / "pattern_occurrences.csv",
        [
            {
                "pattern_id": item.pattern_id,
                "pattern_name": item.pattern_name,
                "sequence": sequence_text(item.sequence),
                "start_time": item.start_time.isoformat(sep=" "),
                "end_time": item.end_time.isoformat(sep=" "),
            }
            for item in occurrences
        ],
        ["pattern_id", "pattern_name", "sequence", "start_time", "end_time"],
    )

    write_csv_rows(
        output_dir / "pattern_adl_mapping.csv",
        [
            {
                "pattern_id": item.pattern_id,
                "pattern_name": item.pattern_name,
                "sequence": sequence_text(item.sequence),
                "support": item.support,
                "assigned_adl": item.assigned_adl,
                "confidence": f"{item.confidence:.6f}",
                "total_duration_seconds": f"{item.total_duration_seconds:.3f}",
            }
            for item in mappings
        ],
        [
            "pattern_id",
            "pattern_name",
            "sequence",
            "support",
            "assigned_adl",
            "confidence",
            "total_duration_seconds",
        ],
    )

    if merged_predictions is not None:
        write_csv_rows(
            output_dir / "merged_predictions.csv",
            [
                prediction_duration_row(item, include_duration=False)
                for item in merged_predictions
            ],
            [
                "predicted_adl",
                "start_time",
                "end_time",
                "num_merged_occurrences",
                "source_pattern_ids",
                "source_pattern_names",
            ],
        )

    if filtered_predictions is not None:
        write_csv_rows(
            output_dir / "filtered_predictions.csv",
            [
                prediction_duration_row(item, include_duration=True)
                for item in filtered_predictions
            ],
            [
                "predicted_adl",
                "start_time",
                "end_time",
                "num_merged_occurrences",
                "source_pattern_ids",
                "source_pattern_names",
                "duration_seconds",
            ],
        )

    for threshold, rows in metrics_by_threshold.items():
        suffix = str(threshold)
        write_csv_rows(
            output_dir / f"adl_metrics_iou_{suffix}.csv",
            rows,
            ["adl_category", "tp", "fp", "fn", "precision", "recall", "f1"],
        )
        write_csv_rows(
            output_dir / f"boundary_metrics_iou_{suffix}.csv",
            boundary_by_threshold.get(threshold, []),
            [
                "adl_category",
                "mean_start_error",
                "median_abs_start_error",
                "mean_end_error",
                "median_abs_end_error",
                "mean_iou",
                "matched_count",
            ],
        )

    if hit_metric_rows is not None:
        write_csv_rows(
            output_dir / "adl_interval_hit_metrics.csv",
            hit_metric_rows,
            [
                "hit_type",
                "adl_category",
                "true_intervals",
                "hit_intervals",
                "missed_intervals",
                "hit_rate",
                "prediction_intervals",
                "matched_prediction_intervals",
                "unmatched_prediction_intervals",
                "prediction_hit_precision",
            ],
        )

    if hit_detail_rows is not None:
        write_csv_rows(
            output_dir / "adl_interval_hit_details.csv",
            hit_detail_rows,
            [
                "hit_type",
                "true_adl",
                "start_time",
                "end_time",
                "is_hit",
                "matched_prediction_count",
                "matched_prediction_ids",
            ],
        )

    (output_dir / "evaluation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
