from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Final

from experiment_config import (
    DATASET_NAME,
    DAYS,
    FREQUENCY_MAX_SEQUENCE_LENGTH,
    FREQUENCY_MIN_SEQUENCE_LENGTH,
    FREQUENCY_TOP_K,
    FREQUENCY_USE_HAMMING_GROUPING,
    HAMMING_THRESHOLD as CFG_HAMMING_THRESHOLD,
    N_STATES,
    ROOT_DIR,
    UNKNOWN_STATE,
)
from src.behavior_pattern_mining.states.state_mapping import (
    clip_period,
    events_to_state_sequence,
    load_event_log,
    load_state_mapping,
)


# =============================
# ユーザー設定（必要に応じて変更）
# =============================
# 長さ設定
MIN_SEQUENCE_LENGTH: Final[int] = FREQUENCY_MIN_SEQUENCE_LENGTH
MAX_SEQUENCE_LENGTH: Final[int | None] = FREQUENCY_MAX_SEQUENCE_LENGTH
COUNT_UNBOUNDED_LENGTHS: Final[bool] = False
USE_HAMMING_GROUPING: Final[bool] = FREQUENCY_USE_HAMMING_GROUPING  # True: 近い状態へ寄せる / False: 完全一致のみ
HAMMING_THRESHOLD: Final[int] = CFG_HAMMING_THRESHOLD  # 「距離 <= 閾値」で代表状態へ寄せる

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
TOP_K: Final[int] = FREQUENCY_TOP_K  # 0 の場合は全件を表示・保存。
OUTPUT_DIR: Final[Path] = (
    ROOT_DIR
    / "output"
    / f"{DATASET_NAME}_{N_STATES}_{HAMMING_THRESHOLD}_{PERIOD_DAYS}days"
)
OUTPUT_FILENAME: Final[str] = (
    f"state_sequence_counts_{N_STATES}_{HAMMING_THRESHOLD}_{PERIOD_DAYS}days.json"
)

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
    events,
    period_events,
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
    sensor_cols, state_mapping = load_state_mapping(STATE_DEFINITION_PATH, unknown_state=UNKNOWN_STATE)
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
        hamming_threshold=HAMMING_THRESHOLD,
        unknown_state=UNKNOWN_STATE,
        active_values={"ON", "1", "TRUE"},
        inactive_values={"OFF", "0", "FALSE"},
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
