"""センサー状態ベクトルの前処理を行う純粋関数。"""

from __future__ import annotations

import pandas as pd


def build_sample_and_hold_state_vectors(
    events: pd.DataFrame,
    time_range: pd.DatetimeIndex,
    sensor_columns: list[str],
) -> pd.DataFrame:
    """イベント列を指定時刻ごとのSample-and-Hold状態ベクトルへ変換する。

    入力 ``events`` は時刻順で、``timestamp``, ``sensor_id``,
    ``binary_value`` 列を持つことを前提とする。各イベントは、その時刻以上で
    最初のサンプル時刻から状態へ反映する。同一サンプル時刻・同一センサーに
    複数イベントがある場合は入力順で最後の値を採用し、イベント発生前は0とする。

    センサーごとの変更点だけを表にしてから前方補完するため、全サンプルを
    Pythonのdictとして逐次生成しない。サンプリング規則と列順は維持したまま、
    長期間ログでのCPU時間と一時オブジェクト数を削減する。
    """
    if time_range.empty:
        return pd.DataFrame(index=time_range, columns=sensor_columns, dtype=int)
    if events.empty:
        return pd.DataFrame(0, index=time_range, columns=sensor_columns, dtype=int)

    updates = events[["timestamp", "sensor_id", "binary_value"]].copy()
    # 絶対時刻をfreq単位で丸めると、開始位置がずれた格子や7秒刻みなどで
    # 旧ループと異なるサンプルへ入る。実際のtime_rangeに対して、イベント以上の
    # 最初の位置を探すことで任意のサンプル間隔でもSample-and-Holdを維持する。
    sample_positions = time_range.searchsorted(updates["timestamp"], side="left")
    updates = updates.loc[sample_positions < len(time_range)].copy()
    sample_positions = sample_positions[sample_positions < len(time_range)]
    updates["sample_time"] = time_range.take(sample_positions)

    # 旧ループは同じサンプルまでに並ぶイベントを順に適用するため、最後の値が残る。
    updates = updates.drop_duplicates(
        subset=["sample_time", "sensor_id"],
        keep="last",
    )
    changes = updates.pivot(
        index="sample_time",
        columns="sensor_id",
        values="binary_value",
    )

    # 開始時刻より前の更新は先頭サンプルへ割り当て済みなので、旧ループと同様に
    # その時点までで最後に現れたセンサー値から系列を開始する。
    combined_index = changes.index.union(time_range).sort_values()
    state_vectors = (
        changes.reindex(index=combined_index, columns=sensor_columns)
        .ffill()
        .reindex(time_range)
        .fillna(0)
        .astype(int)
    )
    state_vectors.index.name = time_range.name
    state_vectors.columns.name = None
    return state_vectors


def apply_delayed_off_smoothing(
    state_vectors: pd.DataFrame,
    window_size: int,
) -> pd.DataFrame:
    """過去 ``window_size`` 行の最大値で遅延OFF平滑化を適用する。

    入力は行が等間隔の時刻、列がセンサー、値が0/1の状態ベクトルである。
    過去の窓内にONが一度でもあれば現在行をONに保ち、短いOFF区間による
    チャタリングが状態系列を過剰に分割することを防ぐ。現在の研究条件では
    1行が1秒なので、窓の行数は秒数と一致する。0以下では従来どおり処理を
    無効化し、入力をそのまま返す。

    この関数は入力DataFrameを変更せず、平滑化が有効な場合は新しい
    DataFrameを返す。列順、index、整数型への変換は従来実装を維持する。
    """
    if window_size <= 0:
        return state_vectors

    return state_vectors.rolling(window=window_size, min_periods=1).max().astype(int)


def compress_consecutive_state_vectors(state_vectors: pd.DataFrame) -> pd.DataFrame:
    """連続する同一状態ベクトルを各区間の先頭1行へ圧縮する。

    入力の列順を状態ベクトルの要素順として比較し、同一状態が続く区間では
    最初のtimestampだけを残す。これにより滞在時間の長さで状態出現回数が
    重複することを防ぎつつ、後段が次の変化時刻との差から滞在時間を復元できる。
    離れた位置に再出現した同じ状態は別の出現として保持する。
    """
    if state_vectors.empty:
        return state_vectors.iloc[0:0]

    # 行ごとのtupleを大量生成せず、直前行との差を列方向にまとめて判定する。
    changed_from_previous = state_vectors.ne(state_vectors.shift()).any(axis=1)
    changed_from_previous.iloc[0] = True
    return state_vectors.loc[changed_from_previous]
