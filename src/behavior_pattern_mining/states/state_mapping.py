"""イベントログと代表状態写像で共有する処理。"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd


DEFAULT_UNKNOWN_STATE = "その他"
DEFAULT_ACTIVE_VALUES = frozenset({"ON", "OPEN", "PRESENT", "1", "TRUE"})
DEFAULT_INACTIVE_VALUES = frozenset({"OFF", "CLOSE", "ABSENT", "0", "FALSE"})

StateVector = tuple[int, ...]


def load_event_log(csv_path: Path, filter_value: str | None = None) -> pd.DataFrame:
    """CASAS形式のイベントログを時刻・センサー・値の3列へ正規化する。"""
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
    """代表状態TSVからセンサー列順と状態ベクトルの対応表を読み込む。"""
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
    """指定開始時刻または先頭イベントから固定日数の半開区間を切り出す。"""
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


def hamming_distance(vec1: StateVector, vec2: StateVector) -> int:
    """2つの0/1状態ベクトルで値が異なる要素数を返す。"""
    return sum(v1 != v2 for v1, v2 in zip(vec1, vec2))


def find_nearest_representative_vector(
    vector: StateVector,
    representative_vectors: Iterable[StateVector],
    hamming_threshold: int,
) -> StateVector | None:
    """閾値内で最も近い代表状態ベクトルを返す。

    同じ最小距離の候補が複数ある場合は、入力で先に現れた代表状態を採用する。
    代表状態の頻度順位に基づく既存のtie-breakを保つため、候補をソートしたり
    集合へ変換したりしない。最小距離が閾値を超える場合は ``None`` を返す。
    """
    minimum_distance = float("inf")
    nearest_vector: StateVector | None = None

    for representative_vector in representative_vectors:
        distance = hamming_distance(vector, representative_vector)
        if distance < minimum_distance:
            minimum_distance = distance
            nearest_vector = representative_vector

    if nearest_vector is not None and minimum_distance <= hamming_threshold:
        return nearest_vector
    return None


def map_vector_to_state(
    vector: StateVector,
    state_mapping: dict[StateVector, str],
    hamming_threshold: int,
    unknown_state: str = DEFAULT_UNKNOWN_STATE,
) -> str:
    """状態ベクトルを完全一致または最近傍の代表状態名へ写像する。"""
    if vector in state_mapping:
        return state_mapping[vector]

    nearest_vector = find_nearest_representative_vector(
        vector,
        representative_vectors=state_mapping,
        hamming_threshold=hamming_threshold,
    )
    if nearest_vector is not None:
        return state_mapping[nearest_vector]

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
    """ON/OFFイベントを入力順の代表状態系列へ変換する。

    状態表のセンサー列順で0/1ベクトルを作り、指定時だけハミング距離による
    最近傍写像と連続同一状態の圧縮を適用する。これらのフラグはベースラインの
    実験条件なので、呼び出し側が明示した値を変更しない。
    """
    active = active_values if active_values is not None else DEFAULT_ACTIVE_VALUES
    inactive = inactive_values if inactive_values is not None else DEFAULT_INACTIVE_VALUES
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
