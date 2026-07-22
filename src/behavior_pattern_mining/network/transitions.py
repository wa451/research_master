"""状態系列の圧縮と遷移確率計算を行う純粋関数。"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Generic, Hashable, Iterable, Sequence, TypeVar


StateT = TypeVar("StateT", bound=Hashable)


@dataclass(frozen=True)
class TransitionStatistics(Generic[StateT]):
    """圧縮済み状態系列から得た出現回数と条件付き遷移確率。"""

    occurrences: dict[StateT, int]
    probabilities: dict[StateT, dict[StateT, float]]


def compress_consecutive_states(state_sequence: Sequence[StateT]) -> list[StateT]:
    """連続する同一状態を1状態へ圧縮し、元の出現順で返す。

    自己連続遷移を遷移ネットワークのエッジとして数えないための処理である。
    非連続に再出現する状態は削除せず、時間帯や日境界も新たに区切らない。
    したがって、現在の全期間・時間帯別集計の系列定義をそのまま維持する。
    """
    return [
        state
        for index, state in enumerate(state_sequence)
        if index == 0 or state != state_sequence[index - 1]
    ]


def compute_transition_statistics(
    compressed_sequence: Sequence[StateT],
) -> TransitionStatistics[StateT]:
    """圧縮済み系列の出現回数と遷移元ごとの確率を計算する。

    状態の出現回数は系列中の各状態を数える。遷移確率は隣接する状態対を
    数え、各遷移元から出る全遷移数を分母として正規化する。辞書は系列で
    最初に現れた状態・遷移の順に挿入し、JSON出力とLLM入力の順序を変えない。
    """
    occurrences = dict(Counter(compressed_sequence))
    transition_counts: defaultdict[StateT, defaultdict[StateT, int]] = defaultdict(
        lambda: defaultdict(int)
    )

    for index in range(len(compressed_sequence) - 1):
        from_state = compressed_sequence[index]
        to_state = compressed_sequence[index + 1]
        transition_counts[from_state][to_state] += 1

    probabilities: dict[StateT, dict[StateT, float]] = {}
    for from_state, to_states in transition_counts.items():
        total = sum(to_states.values())
        probabilities[from_state] = {
            to_state: count / total
            for to_state, count in to_states.items()
        }

    return TransitionStatistics(
        occurrences=occurrences,
        probabilities=probabilities,
    )


def compute_state_durations(
    state_sequence: Sequence[StateT],
    timestamps: Sequence[datetime],
    known_states: Iterable[StateT],
    final_duration_seconds: float = 1.0,
) -> dict[StateT, float]:
    """状態変化点の時刻差から状態ごとの総滞在秒数を計算する。

    ``state_sequence`` と ``timestamps`` は同じ位置が対応する圧縮済み系列である。
    各状態は次の変化時刻まで滞在したものとし、最後の状態だけは既存仕様の
    ``final_duration_seconds``（既定1秒）を加える。``known_states`` の順序で
    0秒の状態も初期化し、JSON node順と欠損状態の扱いを維持する。
    """
    # 出現しない状態は従来どおり整数0のまま保持し、内部スナップショットも変えない。
    durations = {state: 0 for state in known_states}
    for index, state in enumerate(state_sequence):
        if index < len(timestamps) - 1:
            duration = (timestamps[index + 1] - timestamps[index]).total_seconds()
        else:
            duration = final_duration_seconds
        durations[state] += duration
    return durations
