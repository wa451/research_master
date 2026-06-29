"""Shared event-log and representative-state mapping utilities."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


DEFAULT_UNKNOWN_STATE = "その他"


def load_event_log(csv_path: Path, filter_value: str | None = None) -> pd.DataFrame:
    """Load a CASAS-style event log and normalize it to timestamp/sensor/value."""
    if not csv_path.exists():
        raise FileNotFoundError(f"Input CSV not found: {csv_path}")

    df = pd.read_csv(csv_path, header=None)
    if len(df.columns) < 4:
        raise ValueError("Unsupported CSV format. Expected 4 columns: date,time,sensor,value")

    df = df.iloc[:, :4].copy()
    df.columns = ["date", "time", "sensor", "value"]
    df["timestamp"] = pd.to_datetime(
        df["date"].astype(str) + " " + df["time"].astype(str),
        errors="coerce",
    )

    df = df.dropna(subset=["timestamp", "sensor", "value"]).copy()
    if filter_value is not None:
        df = df[df["value"].astype(str) == str(filter_value)].copy()

    df = df.sort_values("timestamp").reset_index(drop=True)
    return df[["timestamp", "sensor", "value"]]


def load_state_mapping(
    state_definition_path: Path,
    unknown_state: str = DEFAULT_UNKNOWN_STATE,
) -> tuple[list[str], dict[tuple[int, ...], str]]:
    """Load a representative-state TSV as sensor columns and vector-to-state mapping."""
    if not state_definition_path.exists():
        raise FileNotFoundError(f"State definition file not found: {state_definition_path}")

    state_df = pd.read_csv(state_definition_path, sep="\t")
    if state_df.shape[1] < 2:
        raise ValueError("State definition file must have state column and sensor columns")

    state_col = state_df.columns[0]
    sensor_cols = list(state_df.columns[1:])
    mapping: dict[tuple[int, ...], str] = {}

    for _, row in state_df.iterrows():
        state_name = str(row[state_col]).strip()
        if state_name == unknown_state:
            continue

        bits: list[int] = []
        valid = True
        for sensor in sensor_cols:
            value = str(row[sensor]).strip()
            if value not in {"0", "1"}:
                valid = False
                break
            bits.append(int(value))

        if valid:
            mapping[tuple(bits)] = state_name

    return sensor_cols, mapping


def clip_period(events: pd.DataFrame, start: str | None, period_days: int) -> pd.DataFrame:
    """Clip events to a fixed number of days from start or the first timestamp."""
    if events.empty:
        return events

    if start is None:
        start_ts = events["timestamp"].min()
    else:
        start_ts = pd.to_datetime(start, errors="coerce")
        if pd.isna(start_ts):
            raise ValueError(f"Invalid START_DATETIME: {start}")

    end_ts = start_ts + pd.Timedelta(days=period_days)
    return events[(events["timestamp"] >= start_ts) & (events["timestamp"] < end_ts)].copy()


def hamming_distance(vec1: tuple[int, ...], vec2: tuple[int, ...]) -> int:
    """Return the Hamming distance between two state vectors."""
    return sum(v1 != v2 for v1, v2 in zip(vec1, vec2))


def map_vector_to_state(
    vector: tuple[int, ...],
    state_mapping: dict[tuple[int, ...], str],
    hamming_threshold: int,
    unknown_state: str = DEFAULT_UNKNOWN_STATE,
) -> str:
    """Map a vector to an exact or nearest representative state."""
    if vector in state_mapping:
        return state_mapping[vector]

    min_distance = float("inf")
    closest_state_vector: tuple[int, ...] | None = None

    for rep_vector in state_mapping:
        dist = hamming_distance(vector, rep_vector)
        if dist < min_distance:
            min_distance = dist
            closest_state_vector = rep_vector

    if closest_state_vector is not None and min_distance <= hamming_threshold:
        return state_mapping[closest_state_vector]

    return unknown_state


def events_to_state_sequence(
    events: pd.DataFrame,
    sensor_cols: list[str],
    state_mapping: dict[tuple[int, ...], str],
    compress_consecutive_same_state: bool,
    use_hamming_grouping: bool,
    hamming_threshold: int,
    unknown_state: str = DEFAULT_UNKNOWN_STATE,
    active_values: set[str] | None = None,
    inactive_values: set[str] | None = None,
) -> list[str]:
    """Convert ON/OFF events into a representative-state sequence."""
    active = active_values if active_values is not None else {"ON", "OPEN", "PRESENT", "1", "TRUE"}
    inactive = inactive_values if inactive_values is not None else {"OFF", "CLOSE", "ABSENT", "0", "FALSE"}
    current_sensor_state = {sensor: 0 for sensor in sensor_cols}
    state_sequence: list[str] = []

    for _, row in events.iterrows():
        sensor = str(row["sensor"]).strip()
        value = str(row["value"]).strip().upper()
        if sensor not in current_sensor_state:
            continue

        if value in active:
            current_sensor_state[sensor] = 1
        elif value in inactive:
            current_sensor_state[sensor] = 0
        else:
            continue

        vector = tuple(current_sensor_state[s] for s in sensor_cols)
        if use_hamming_grouping:
            state_name = map_vector_to_state(
                vector=vector,
                state_mapping=state_mapping,
                hamming_threshold=hamming_threshold,
                unknown_state=unknown_state,
            )
        else:
            state_name = state_mapping.get(vector, unknown_state)

        if compress_consecutive_same_state and state_sequence and state_sequence[-1] == state_name:
            continue
        state_sequence.append(state_name)

    return state_sequence
