from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Final

import pandas as pd

from experiment_config import DATASET_NAME, DAYS, HAMMING_THRESHOLD as CFG_HAMMING_THRESHOLD, N_STATES, ROOT_DIR


# =============================
# ユーザー設定（必要に応じて変更）
# =============================
# 長さ設定
MIN_SEQUENCE_LENGTH: Final[int] = 2
MAX_SEQUENCE_LENGTH: Final[int | None] = 4
COUNT_UNBOUNDED_LENGTHS: Final[bool] = False
USE_HAMMING_GROUPING: Final[bool] = True  # True: 近い状態へ寄せる / False: 完全一致のみ
HAMMING_THRESHOLD: Final[int] = CFG_HAMMING_THRESHOLD  # state_transition_visualizer.py と同様に「距離 <= 閾値」で代表状態へ寄せる

PERIOD_DAYS: Final[int] = DAYS
INPUT_CSV_PATH: Final[Path] = ROOT_DIR / "data" / f"{DATASET_NAME}.csv"
STATE_DEFINITION_PATH: Final[Path] = (
    ROOT_DIR
    / "state"
    / f"{DATASET_NAME}_{N_STATES}_{HAMMING_THRESHOLD}_{PERIOD_DAYS}days.txt"
)
START_DATETIME: Final[str | None] = None


# 入力フィルタ設定
FILTER_VALUE: Final[str | None] = None  # 例: "ON"。None の場合は全イベントを対象。
COMPRESS_CONSECUTIVE_SAME_STATE: Final[bool] = True  # 同じ状態の連続を1つに圧縮する。

# 出力設定
TOP_K: Final[int] = 50  # 0 の場合は全件を表示・保存。
OUTPUT_DIR: Final[Path] = (
    ROOT_DIR
    / "output"
    / f"{DATASET_NAME}_{N_STATES}_{HAMMING_THRESHOLD}_{PERIOD_DAYS}days"
)
OUTPUT_FILENAME: Final[str] = (
    f"state_sequence_counts_{N_STATES}_{HAMMING_THRESHOLD}_{PERIOD_DAYS}days.json"
)

UNKNOWN_STATE = "その他"


def validate_config() -> None:
    """設定値の整合性を先に確認し、後段の処理エラーを減らす。"""
    if PERIOD_DAYS <= 0:
        raise ValueError("PERIOD_DAYS は 1 以上にしてください。")
    if MIN_SEQUENCE_LENGTH < 2:
        raise ValueError("MIN_SEQUENCE_LENGTH は 2 以上にしてください。")
    if not COUNT_UNBOUNDED_LENGTHS and MAX_SEQUENCE_LENGTH is None:
        raise ValueError("COUNT_UNBOUNDED_LENGTHS=False の場合、MAX_SEQUENCE_LENGTH が必要です。")
    if MAX_SEQUENCE_LENGTH is not None and MAX_SEQUENCE_LENGTH < MIN_SEQUENCE_LENGTH:
        raise ValueError("MAX_SEQUENCE_LENGTH は MIN_SEQUENCE_LENGTH 以上にしてください。")
    if TOP_K < 0:
        raise ValueError("TOP_K は 0 以上にしてください。")
    if HAMMING_THRESHOLD < 0:
        raise ValueError("HAMMING_THRESHOLD は 0 以上にしてください。")


def load_event_log(csv_path: Path, filter_value: str | None = None) -> pd.DataFrame:
    """イベントログCSVを読み込み、timestamp/sensor/value の3列に正規化する。"""
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


def load_state_mapping(state_definition_path: Path) -> tuple[list[str], dict[tuple[int, ...], str]]:
    """状態定義TSVを読み込み、センサー順とベクトル->状態名マップを作る。"""
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
        if state_name == UNKNOWN_STATE:
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
    """指定開始時刻から固定日数だけイベントを切り出す。"""
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


def events_to_state_sequence(
    events: pd.DataFrame,
    sensor_cols: list[str],
    state_mapping: dict[tuple[int, ...], str],
    compress_consecutive_same_state: bool,
    use_hamming_grouping: bool,
) -> list[str]:
    """ON/OFFイベント列を、状態名の時系列に変換する。"""
    current_sensor_state = {sensor: 0 for sensor in sensor_cols}
    state_sequence: list[str] = []

    for _, row in events.iterrows():
        sensor = str(row["sensor"]).strip()  # 対象センサー名を取り出す
        value = str(row["value"]).strip().upper()  # 値を正規化（大文字化）する
        if sensor not in current_sensor_state:
            continue  # 状態定義にないセンサーは無視する

        # センサー値を2値化して内部状態を更新する。
        if value in {"ON", "1", "TRUE"}:
            current_sensor_state[sensor] = 1  # 反応ありとして1を立てる
        elif value in {"OFF", "0", "FALSE"}:
            current_sensor_state[sensor] = 0  # 反応なしとして0に戻す
        else:
            continue  # 想定外の値はスキップする

        vector = tuple(current_sensor_state[s] for s in sensor_cols)  # 現在の全センサー状態をベクトル化
        if use_hamming_grouping:
            state_name = map_vector_to_state(
                vector=vector,
                state_mapping=state_mapping,
                hamming_threshold=HAMMING_THRESHOLD,
            )
        else:
            state_name = state_mapping.get(vector, UNKNOWN_STATE)

        if compress_consecutive_same_state and state_sequence and state_sequence[-1] == state_name:
            continue  # 同じ状態の連続は1つに圧縮する
        state_sequence.append(state_name)  # 時系列の状態列に追加する

    return state_sequence


def hamming_distance(vec1: tuple[int, ...], vec2: tuple[int, ...]) -> int:
    """2つの状態ベクトルのハミング距離を返す。"""
    return sum(v1 != v2 for v1, v2 in zip(vec1, vec2))


def map_vector_to_state(
    vector: tuple[int, ...],
    state_mapping: dict[tuple[int, ...], str],
    hamming_threshold: int,
) -> str:
    """state_transition_visualizer.py と同じロジックで、最近傍の代表状態へ割り当てる。"""
    if vector in state_mapping:
        return state_mapping[vector]

    min_distance = float("inf")
    closest_state_vector: tuple[int, ...] | None = None

    for rep_vector in state_mapping:
        dist = hamming_distance(vector, rep_vector)
        if dist < min_distance:
            min_distance = dist
            closest_state_vector = rep_vector

    # state_transition_visualizer.py と同様: 距離が「閾値以下」のとき代表状態に寄せる
    if closest_state_vector is not None and min_distance <= hamming_threshold:
        return state_mapping[closest_state_vector]

    return UNKNOWN_STATE


def count_sequences(
    state_sequence: list[str],
    min_length: int,
    max_length: int | None,
) -> Counter[tuple[str, ...]]:
    """状態系列の連続部分列をカウントする。"""
    n = len(state_sequence)
    if n < min_length:
        return Counter()

    upper = n if max_length is None else min(max_length, n)
    counts: Counter[tuple[str, ...]] = Counter()

    for seq_len in range(min_length, upper + 1):
        for i in range(n - seq_len + 1):
            seq = tuple(state_sequence[i : i + seq_len])
            counts[seq] += 1

    return counts


def sequence_length_label(min_length: int, max_length: int | None) -> str:
    if max_length is None:
        return f">= {min_length} (unbounded)"
    return f"{min_length} to {max_length}"


def top_items(counts: Counter[tuple[str, ...]], top_k: int) -> list[tuple[tuple[str, ...], int]]:
    return counts.most_common(None if top_k == 0 else top_k)


def save_result(
    counts: Counter[tuple[str, ...]],
    output_dir: Path,
    output_filename: str,
    top_k: int,
) -> Path:
    """集計結果を JSON 形式で保存する。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / output_filename

    payload = []
    for idx, (seq, cnt) in enumerate(top_items(counts, top_k), start=1):
        payload.append(
            {
                "rank": idx,
                "sequence": list(seq),
                "count": cnt,
            }
        )

    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def print_summary(
    events: pd.DataFrame,
    period_events: pd.DataFrame,
    state_sequence: list[str],
    max_length: int | None,
) -> None:
    print(f"Input file         : {INPUT_CSV_PATH}")
    print(f"State file         : {STATE_DEFINITION_PATH}")
    print(f"Total events       : {len(events)}")
    print(f"Period events      : {len(period_events)}")
    print(f"Mapped states      : {len(state_sequence)}")

    if not period_events.empty:
        print(f"Period start       : {period_events['timestamp'].min()}")
        print(f"Period end         : {period_events['timestamp'].max()}")

    print(f"Sequence length    : {sequence_length_label(MIN_SEQUENCE_LENGTH, max_length)}")
    print(f"Period days        : {PERIOD_DAYS}")
    print(f"Filter value       : {FILTER_VALUE}")
    print(f"Compress same      : {COMPRESS_CONSECUTIVE_SAME_STATE}")
    print(f"Use hamming group  : {USE_HAMMING_GROUPING}")
    if USE_HAMMING_GROUPING:
        print(f"Hamming threshold  : {HAMMING_THRESHOLD}")


def main() -> None:
    validate_config()
    max_length = None if COUNT_UNBOUNDED_LENGTHS else MAX_SEQUENCE_LENGTH

    # 1) データ読み込みと期間抽出
    events = load_event_log(INPUT_CSV_PATH, filter_value=FILTER_VALUE)
    period_events = clip_period(events, start=START_DATETIME, period_days=PERIOD_DAYS)

    # 2) 状態定義を使って、イベント列を状態列へ変換
    sensor_cols, state_mapping = load_state_mapping(STATE_DEFINITION_PATH)
    """センサー列: ['Bathroom', 'Bedroom', 'DiningRoom', 'GuestRoom', 'Kitchen', 'LivingRoom', 'LoungeChair', 'OtherRoom', 'OutsideDoor', 'WorkArea']
状態マッピング例: [((0, 0, 0, 0, 0, 0, 0, 0, 0, 0), '状態1'), ((0, 0, 0, 0, 0, 0, 1, 0, 0, 0), '状態2'), ((0, 0, 0, 0, 0, 1, 1, 0, 0, 0), '状態3'), ((0, 1, 0, 0, 0, 0, 0, 0, 0, 0), '状態4'), ((0, 0, 1, 0, 0, 1, 1, 0, 0, 0), '状態5')]
    """

    # ログから状態列を生成（['状態4', '状態1', '状態4', '状態1', '状態4', '状態1', '状態4', '状態1', '状態4', '状態1']）
    state_sequence = events_to_state_sequence( 
        period_events,
        sensor_cols=sensor_cols,
        state_mapping=state_mapping,
        compress_consecutive_same_state=COMPRESS_CONSECUTIVE_SAME_STATE,
        use_hamming_grouping=USE_HAMMING_GROUPING,
    )

    # 3) 状態遷移シーケンスを集計
    counts = count_sequences(
        state_sequence,
        min_length=MIN_SEQUENCE_LENGTH,
        max_length=max_length,
    )

    # 4) 画面表示とファイル保存
    print_summary(events, period_events, state_sequence, max_length)
    output_path = save_result(
        counts,
        output_dir=OUTPUT_DIR,
        output_filename=OUTPUT_FILENAME,
        top_k=TOP_K,
    )

if __name__ == "__main__":
    main()
