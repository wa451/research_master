"""
状態遷移可視化システム

このモジュールは、センサーログを読み込み、状態遷移ネットワークを可視化します。
複数のデータフォーマット（テキスト形式、CSV形式）に対応しています。

Author: Data Science Expert
Date: 2026-02-05
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from typing import List, Tuple, Dict, Optional
import networkx as nx
import matplotlib.pyplot as plt
from scipy.spatial.distance import hamming

# 定数定義
DATA_DURATION_DAYS = 14                  # 使用するデータの期間（日数）。None で全期間を使用
DEFAULT_N_STATES = 15                    # 代表状態の数（頻度上位K個を抽出）
DEFAULT_HAMMING_THRESHOLD = 1            # 状態マッピング時のハミング距離閾値（異なるセンサー数の許容値）
DEFAULT_MIN_TRANSITION_PROB = 0.1        # グラフに表示する最小遷移確率（これ以下のエッジは非表示）
SAMPLING_INTERVAL = '1s'                 # 状態ベクトルのサンプリング間隔

# 時間帯モード定義（時間帯別分析用）
DEFAULT_TIME_MODES = {
    'Morning': ('06:00', '10:00'),
    'Daytime': ('10:00', '18:00'),
    'Night': ('18:00', '24:00'),
    'Midnight': ('00:00', '06:00')
}

NODE_SIZE_MULTIPLIER = 100              # ノードサイズの倍率（出現回数 × この値 = ノードサイズ）
FIGURE_SIZE = (36, 32)                   # グラフの図のサイズ（幅, 高さ）インチ単位
FONT_SIZE_LABEL = 24                     # ノードラベルのフォントサイズ
FONT_SIZE_EDGE = 48                      # エッジラベルのフォントサイズ
FONT_SIZE_TITLE = 48                     # タイトルのフォントサイズ

# レイアウト調整パラメータ（ノードの重なりを防ぐ）
LAYOUT_K = 2.5                          # spring_layoutのノード間距離（大きいほど離れる、デフォルト:1.0）
LAYOUT_ITERATIONS = 100                 # レイアウト計算の反復回数（多いほど精度が高い）

# センサー値のON/OFF判定用セット
SENSOR_ON_VALUES  = {'ON', 'OPEN', 'PRESENT', '1', 1}
SENSOR_OFF_VALUES = {'OFF', 'CLOSE', 'ABSENT', '0', 0}

class StateTransitionVisualizer:
    """
    状態遷移可視化クラス
    
    センサーログを読み込み、状態ベクトル化、代表状態の抽出、
    遷移確率の計算、グラフ可視化を行います。
    """
    
    def __init__(self, 
                 n_representative_states: int = DEFAULT_N_STATES,
                 min_transition_prob: float = DEFAULT_MIN_TRANSITION_PROB,
                 hamming_threshold: int = DEFAULT_HAMMING_THRESHOLD,
                 time_modes: Optional[Dict[str, Tuple[str, str]]] = None,
                 data_duration_days: Optional[int] = DATA_DURATION_DAYS):
        """
        初期化
        
        Parameters:
        -----------
        n_representative_states : int
            代表状態の数（頻度上位K個）
        min_transition_prob : float
            可視化する最小遷移確率
        hamming_threshold : int
            代表状態へのマッピング時のハミング距離閾値
        time_modes : Optional[Dict[str, Tuple[str, str]]]
            時間帯モード定義（キー=モード名、値=(開始時刻, 終了時刻)）
        data_duration_days : Optional[int]
            使用するデータの期間（日数）。Noneで全期間を使用
        """
        self.n_representative_states = n_representative_states
        self.min_transition_prob = min_transition_prob
        self.hamming_threshold = hamming_threshold
        self.time_modes = time_modes if time_modes is not None else DEFAULT_TIME_MODES
        self.data_duration_days = data_duration_days
        
        # データ保持用
        self.sensor_list = []
        self.state_vectors_df = None
        self.representative_states = []
        self.state_sequence = []
        self.transition_matrix = None
        self.state_durations = {}
        self.state_occurrences = {}
        self.state_labels = {}
        
        # モードごとのデータ保持用
        self.mode_transition_matrices = {}
        self.mode_state_occurrences = {}
        self.mode_state_sequences = {}
        self.mode_state_durations = {}

# データ読み込み        
    def load_data(self, filepath: str) -> pd.DataFrame:
        """
        センサーデータを読み込み、イベント駆動形式に変換
        
        両方の形式に対応:
        1. イベントログ形式: 日付,時刻,センサー,状態 (aruba.csvなど)
        2. CSV形式: 各センサーが列,タイムスタンプが最後の列
        
        Parameters:
        -----------
        filepath : str
            CSVファイルのパス
            
        Returns:
        --------
        pd.DataFrame
            処理済みのセンサーデータ（イベント駆動形式）
        """
        print("Step 1: データ読み込みと前処理")
        
        # CSV読み込み
        df_csv = pd.read_csv(filepath, header=None if self._is_event_log_format(filepath) else 0)
        
        # 形式を判定
        if self._is_event_log_format(filepath):
            print("  イベントログ形式を検出")
            return self._load_event_log_format(df_csv, filepath)
        else:
            print("  CSV形式を検出")
            return self._load_csv_format(df_csv)
    
    def _is_event_log_format(self, filepath: str) -> bool:
        """ファイルがイベントログ形式かどうかを判定"""
        # 最初の数行を読んで形式を推定
        df_sample = pd.read_csv(filepath, nrows=5, header=None)
        
        known_values = SENSOR_ON_VALUES | SENSOR_OFF_VALUES
        # 4列で、最後の列がON/OFFのようなパターンならイベントログ形式
        if len(df_sample.columns) == 4:
            if any(val in known_values for val in df_sample.iloc[:, 3].unique()):
                return True
        # 3列で、最後の列がON/OFFのパターン（タイムスタンプが1列目）
        if len(df_sample.columns) == 3:
            if any(val in known_values for val in df_sample.iloc[:, 2].unique()):
                return True
        
        return False
    
    def _load_event_log_format(self, df_csv: pd.DataFrame, filepath: str) -> pd.DataFrame:
        """イベントログ形式のデータを読み込む"""
        # 列名を設定
        if len(df_csv.columns) == 4:
            df_csv.columns = ['date', 'time', 'sensor_id', 'value']
            # 日付と時刻を結合してタイムスタンプを作成（混在する形式に対応）
            df_csv['timestamp'] = pd.to_datetime(df_csv['date'] + ' ' + df_csv['time'], format='mixed', errors='coerce')
        elif len(df_csv.columns) == 3:
            df_csv.columns = ['timestamp', 'sensor_id', 'value']
            df_csv['timestamp'] = pd.to_datetime(df_csv['timestamp'], format='mixed', errors='coerce')
        else:
            raise ValueError(f"不明なイベントログ形式: {len(df_csv.columns)}列")
        
        # センサー一覧を取得
        sensor_list = sorted(df_csv['sensor_id'].unique())
        
        print(f"  検出されたセンサー: {len(sensor_list)}個")
        print(f"  期間: {df_csv['timestamp'].min()} ~ {df_csv['timestamp'].max()}")
        print(f"  データ行数: {len(df_csv)}")
        
        # イベントデータを統一形式に変換（ON/OFFを0/1に変換）
        events = []
        for _, row in df_csv.iterrows():
            if row['value'] in SENSOR_ON_VALUES:
                binary_value = 1
            elif row['value'] in SENSOR_OFF_VALUES:
                binary_value = 0
            else:
                continue
            events.append({
                'timestamp': pd.Timestamp(row['timestamp']),
                'sensor_id': row['sensor_id'],
                'value': 'ON' if binary_value else 'OFF',
                'binary_value': binary_value
            })
        
        df = pd.DataFrame(events).sort_values('timestamp').reset_index(drop=True)
        print(f"  イベント数: {len(df)}")
        print(df.head(3))
        
        # 期間制限を適用
        df = self._filter_by_duration(df)
        
        return df
    
    def _load_csv_format(self, df_csv: pd.DataFrame) -> pd.DataFrame:
        """従来のCSV形式（各センサーが列）のデータを読み込む"""
        timestamp_col = 'timestamp' if 'timestamp' in df_csv.columns else df_csv.columns[-1]
        df_csv[timestamp_col] = pd.to_datetime(df_csv[timestamp_col])
        
        # センサー列を抽出
        exclude_cols = [timestamp_col, 'Activity', 'activity', 'label', 'Label']
        sensor_cols = [col for col in df_csv.columns if col not in exclude_cols]
        
        print(f"  検出されたセンサー: {len(sensor_cols)}個")
        print(f"  期間: {df_csv[timestamp_col].min()} ~ {df_csv[timestamp_col].max()}")
        print(f"  データ行数: {len(df_csv)}")
        
        # 全データをイベント駆動形式に変換（センサー個別での圧縮はしない）
        events = []
        for idx, row in df_csv.iterrows():
            for sensor in sensor_cols:
                events.append({
                    'timestamp': pd.Timestamp(row[timestamp_col]),
                    'sensor_id': sensor,
                    'value': 'ON' if row[sensor] == 1 else 'OFF',
                    'binary_value': int(row[sensor])
                })
        
        df = pd.DataFrame(events).sort_values('timestamp').reset_index(drop=True)
        print(f"  イベント数: {len(df)}")
        print(df.head(3))
        
        # 期間制限を適用
        df = self._filter_by_duration(df)
        
        return df
    
    def _filter_by_duration(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        データを指定期間でフィルタリング
        
        Parameters:
        -----------
        df : pd.DataFrame
            イベントデータ
            
        Returns:
        --------
        pd.DataFrame
            フィルタリング後のデータ
        """
        if self.data_duration_days is None:
            return df
        
        start_time = df['timestamp'].min()
        end_time = start_time + timedelta(days=self.data_duration_days)
        
        df_filtered = df[df['timestamp'] < end_time].copy()
        
        print(f"\n  期間制限を適用: 最初の{self.data_duration_days}日間")
        print(f"  開始: {start_time}")
        print(f"  終了: {end_time}")
        print(f"  フィルタリング後のイベント数: {len(df_filtered)}")
        
        return df_filtered

# データ前処理
    def create_state_vectors(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        イベント駆動型ログを1秒ごとの状態ベクトルに変換
        
        Parameters:
        -----------
        df : pd.DataFrame
            センサーイベントデータ
            
        Returns:
        --------
        pd.DataFrame
            行=時刻、列=センサーID、値=0/1 の状態ベクトル
        """
        print("\nStep 2: 状態ベクトル化")
        
        self.sensor_list = sorted(df['sensor_id'].unique())
        print(f"  対象センサー: {len(self.sensor_list)}個")
        
        # 時間範囲を決定（1秒刻み）
        start_time = df['timestamp'].min().replace(microsecond=0)
        end_time = df['timestamp'].max().replace(microsecond=0) + timedelta(seconds=1)
        time_range = pd.date_range(start=start_time, end=end_time, freq=SAMPLING_INTERVAL)
        
        print(f"  時間範囲: {len(time_range)}秒")
        
        # 状態ベクトルを生成
        state_vectors = self._generate_state_vectors(df, time_range)
        
        self.state_vectors_df = pd.DataFrame(state_vectors, 
                                             index=time_range,
                                             columns=self.sensor_list)
        
        print(f"  状態ベクトル生成完了: {len(self.state_vectors_df)}行 × {len(self.sensor_list)}列")
        
        # 状態ベクトル全体として連続する同じものを除去
        self._compress_state_vectors()
        print(self.state_vectors_df.head(3))
        
        return self.state_vectors_df
    
    def _generate_state_vectors(self, df: pd.DataFrame, time_range) -> List[Dict]:
        """状態ベクトルを生成"""
        sensor_states = {sensor: 0 for sensor in self.sensor_list}
        state_vectors = []
        events = df.to_dict('records')
        event_idx = 0
        
        for current_time in time_range:
            # この時刻までに発生したイベントを処理
            while event_idx < len(events) and events[event_idx]['timestamp'] <= current_time:
                sensor_states[events[event_idx]['sensor_id']] = events[event_idx]['binary_value']
                event_idx += 1
            
            state_vectors.append(sensor_states.copy())
        
        return state_vectors
    
    def _compress_state_vectors(self):
        """連続する同じ状態ベクトルを除去"""
        original_length = len(self.state_vectors_df)
        
        # 連続する同じ状態を検出
        state_tuples = [tuple(row) for row in self.state_vectors_df.values]
        keep_indices = [0] + [i for i in range(1, len(state_tuples)) if state_tuples[i] != state_tuples[i - 1]]
        self.state_vectors_df = self.state_vectors_df.iloc[keep_indices]
        
        print(f"  状態ベクトル圧縮: {original_length}行 → {len(self.state_vectors_df)}行")
    
    def _filter_by_time_mode(self, mode_name: str, start_time: str, end_time: str) -> pd.DataFrame:
        """
        時間帯でデータをフィルタリング
        
        Parameters:
        -----------
        mode_name : str
            モード名
        start_time : str
            開始時刻（'HH:MM'形式）
        end_time : str
            終了時刻（'HH:MM'形式）
            
        Returns:
        --------
        pd.DataFrame
            フィルタリングされた状態ベクトル（空の場合もあり）
        """
        if self.state_vectors_df is None or len(self.state_vectors_df) == 0:
            return pd.DataFrame()
        
        # 時刻でフィルタリング（DatetimeIndexは保持されている前提）
        start_hour, start_minute = map(int, start_time.split(':'))
        end_hour, end_minute = map(int, end_time.split(':'))
        
        if end_hour < start_hour:  # 日をまたぐ場合（例: 24:00 -> 06:00）
            # Midnight: 00:00-06:00のケース
            mask = (self.state_vectors_df.index.hour < end_hour) | \
                   ((self.state_vectors_df.index.hour == end_hour) & (self.state_vectors_df.index.minute < end_minute))
        else:
            # 通常のケース
            mask = ((self.state_vectors_df.index.hour > start_hour) | \
                    ((self.state_vectors_df.index.hour == start_hour) & (self.state_vectors_df.index.minute >= start_minute))) & \
                   ((self.state_vectors_df.index.hour < end_hour) | \
                    ((self.state_vectors_df.index.hour == end_hour) & (self.state_vectors_df.index.minute < end_minute)))
        
        return self.state_vectors_df[mask]

# 代表状態の抽出
    def extract_representative_states(self) -> List[Tuple]:
        """
        代表状態の抽出
        
        頻度が高い上位K個の状態パターンを代表状態として選定する。
        
        Returns:
        --------
        List[Tuple]
            代表状態のリスト（各状態はタプル形式）
        """
        print("\nStep 3: 代表状態の定義")
        
        # 全ての状態ベクトルをタプルに変換して頻度集計
        state_tuples = [tuple(row) for row in self.state_vectors_df.values]
        state_counter = Counter(state_tuples)
        
        print(f"  ユニークな状態パターン数: {len(state_counter)}")
        
        # 頻度上位K個を代表状態として選定
        self.representative_states = [
            state for state, _ in state_counter.most_common(self.n_representative_states)
        ]
        
        print(f"  代表状態数: {len(self.representative_states)}")
        
        # 各代表状態にラベルを付与（状態1, 状態2, ...）
        for idx, state in enumerate(self.representative_states, 1):
            self.state_labels[state] = f"状態{idx}"
            # 滞在時間は後で計算するため、ここでは初期化のみ
            self.state_durations[state] = 0
        
        # "その他"状態も初期化
        self.state_durations['Other'] = 0
        self.state_labels['Other'] = 'その他'
        
        return self.representative_states

# 状態マッピング(似た状態を代表状態に割り当てる)
    def _compute_hamming_distance(self, state1: Tuple, state2: Tuple) -> int:
        """2つの状態ベクトル間のハミング距離を計算"""
        return sum(s1 != s2 for s1, s2 in zip(state1, state2))
    
    def _calculate_state_durations(self):
        """各状態の滞在時間を計算（秒単位）"""
        # 滞在時間を初期化
        for state in self.representative_states:
            self.state_durations[state] = 0
        self.state_durations['Other'] = 0
        
        # 時系列インデックスから時間差を計算
        timestamps = self.state_vectors_df.index
        
        for i in range(len(self.state_sequence)):
            state = self.state_sequence[i]
            
            # 次の状態までの時間を計算（最後の状態は1秒とする）
            if i < len(timestamps) - 1:
                duration = (timestamps[i + 1] - timestamps[i]).total_seconds()
            else:
                duration = 1.0  # 最後の状態
            
            self.state_durations[state] += duration
        
        print(f"  滞在時間計算完了:")
        for state in self.representative_states:
            label = self.state_labels[state]
            duration = self.state_durations[state]
            print(f"    {label}: {duration:.1f}秒 ({duration/60:.1f}分)")
        if self.state_durations['Other'] > 0:
            print(f"    その他: {self.state_durations['Other']:.1f}秒 ({self.state_durations['Other']/60:.1f}分)")
    
    def map_to_representative_states(self) -> List:
        """
        全時刻の状態を代表状態にマッピング
        
        各時刻の状態ベクトルを、最も近い代表状態に割り当てる。
        距離が閾値以上の場合は"Other"として扱う。
        
        Returns:
        --------
        List
            代表状態のシーケンス
        """
        print("\nStep 4: 状態マッピング処理")
        
        mapped_states = []
        other_count = 0
        
        for idx, row in self.state_vectors_df.iterrows():
            current_state = tuple(row.values)
            
            # 代表状態に含まれていればそのまま使用
            if current_state in self.representative_states:
                mapped_states.append(current_state)
            else:
                # 最も近い代表状態を探す
                min_distance = float('inf')
                closest_state = None
                
                for rep_state in self.representative_states:
                    distance = self._compute_hamming_distance(current_state, rep_state)
                    if distance < min_distance:
                        min_distance = distance
                        closest_state = rep_state
                
                # 距離が閾値以内なら代表状態に、そうでなければ"Other"
                if min_distance < self.hamming_threshold:# 閾値未満 → 代表状態にマッピング
                    mapped_states.append(closest_state)
                else:
                    mapped_states.append('Other')
                    other_count += 1
        
        print(f"  マッピング完了: {other_count}個を'Other'に分類")
        
        self.state_sequence = mapped_states
        
        # 各状態の滞在時間を計算（秒単位）
        self._calculate_state_durations()
        
        return self.state_sequence

# 遷移確率行列の計算
    def compute_transition_matrix(self) -> Dict[Tuple, Dict[Tuple, float]]:
        """
        遷移確率行列の計算
        
        自分自身への連続遷移を圧縮し、状態間の遷移回数をカウントして
        確率に変換する。
        
        Returns:
        --------
        Dict[Tuple, Dict[Tuple, float]]
            遷移確率行列（from_state -> to_state -> probability）
        """
        print("\nStep 5: 遷移確率行列の計算")
        
        # マッピング後の自己遷移を圧縮
        compressed_sequence = [s for i, s in enumerate(self.state_sequence)
                                if i == 0 or s != self.state_sequence[i - 1]]
        
        print(f"  マッピング後のシーケンス長: {len(self.state_sequence)}")
        print(f"  圧縮後: {len(compressed_sequence)}")
        
        # 各状態の出現回数をカウント（圧縮後のシーケンス内での出現回数）
        occurrence_counter = Counter(compressed_sequence)
        self.state_occurrences = dict(occurrence_counter)
        
        # 遷移回数をカウント
        transition_counts = defaultdict(lambda: defaultdict(int))
        
        for i in range(len(compressed_sequence) - 1):
            from_state = compressed_sequence[i]
            to_state = compressed_sequence[i + 1]
            transition_counts[from_state][to_state] += 1
        
        # 確率に変換
        self.transition_matrix = {}
        
        for from_state, to_states in transition_counts.items():
            total = sum(to_states.values())
            self.transition_matrix[from_state] = {
                to_state: count / total
                for to_state, count in to_states.items()
            }
        
        print(f"  遷移パターン数: {sum(len(v) for v in self.transition_matrix.values())}")
        
        return self.transition_matrix
    
    def compute_transition_matrix_by_modes(self) -> Dict[str, Dict[Tuple, Dict[Tuple, float]]]:
        """
        時間帯モードごとに遷移確率行列を計算
        
        Returns:
        --------
        Dict[str, Dict[Tuple, Dict[Tuple, float]]]
            モード名 -> 遷移確率行列の辞書
        """
        print("\n[モード分割] 時間帯別の遷移行列計算")
        
        self.mode_transition_matrices = {}
        self.mode_state_occurrences = {}
        self.mode_state_sequences = {}
        
        for mode_name, (start_time, end_time) in self.time_modes.items():
            print(f"\n  モード '{mode_name}' ({start_time} - {end_time}) を処理中...")
            
            # 時間帯でフィルタリング
            filtered_df = self._filter_by_time_mode(mode_name, start_time, end_time)
            
            # 空データチェック
            if len(filtered_df) == 0:
                print(f"    Warning: Mode '{mode_name}' has no data. Skipping...")
                continue
            
            print(f"    データ行数: {len(filtered_df)}")
            
            # このモードのデータで状態シーケンスを作成（既存の代表状態を使用）
            mode_sequence = []
            other_count = 0
            
            for idx, row in filtered_df.iterrows():
                current_state = tuple(row.values)
                
                if current_state in self.representative_states:
                    mode_sequence.append(current_state)
                else:
                    # 最も近い代表状態を探す
                    min_distance = float('inf')
                    closest_state = None
                    
                    for rep_state in self.representative_states:
                        distance = self._compute_hamming_distance(current_state, rep_state)
                        if distance < min_distance:
                            min_distance = distance
                            closest_state = rep_state
                    
                    if min_distance < self.hamming_threshold:
                        mode_sequence.append(closest_state)
                    else:
                        mode_sequence.append('Other')
                        other_count += 1
            
            # シーケンスが空の場合はスキップ
            if len(mode_sequence) == 0:
                print(f"    Warning: Mode '{mode_name}' has empty sequence. Skipping...")
                continue
            
            self.mode_state_sequences[mode_name] = mode_sequence
            
            # 自己遷移を圧縮
            compressed_sequence = [s for i, s in enumerate(mode_sequence)
                                    if i == 0 or s != mode_sequence[i - 1]]
            
            print(f"    シーケンス長: {len(mode_sequence)} -> 圧縮後: {len(compressed_sequence)}")
            
            # 遷移が計算できない場合（圧縮後のシーケンスが1以下）はスキップ
            if len(compressed_sequence) <= 1:
                print(f"    Warning: Mode '{mode_name}' has insufficient transitions. Skipping...")
                continue
            
            # 出現回数をカウント
            occurrence_counter = Counter(compressed_sequence)
            self.mode_state_occurrences[mode_name] = dict(occurrence_counter)
            
            # このモードでの各状態の滞在時間を計算
            mode_durations = {state: 0 for state in self.representative_states}
            mode_durations['Other'] = 0
            
            timestamps = filtered_df.index
            for i in range(len(mode_sequence)):
                state = mode_sequence[i]
                if i < len(timestamps) - 1:
                    duration = (timestamps[i + 1] - timestamps[i]).total_seconds()
                else:
                    duration = 1.0
                mode_durations[state] += duration
            
            # モード別の滞在時間を保存
            self.mode_state_durations[mode_name] = mode_durations
            
            # 遷移回数をカウント
            transition_counts = defaultdict(lambda: defaultdict(int))
            
            for i in range(len(compressed_sequence) - 1):
                from_state = compressed_sequence[i]
                to_state = compressed_sequence[i + 1]
                transition_counts[from_state][to_state] += 1
            
            # 確率に変換
            mode_transition_matrix = {}
            
            for from_state, to_states in transition_counts.items():
                total = sum(to_states.values())
                mode_transition_matrix[from_state] = {
                    to_state: count / total
                    for to_state, count in to_states.items()
                }
            
            self.mode_transition_matrices[mode_name] = mode_transition_matrix
            
            print(f"    遷移パターン数: {sum(len(v) for v in mode_transition_matrix.values())}")
        
        print(f"\n  有効なモード数: {len(self.mode_transition_matrices)}/{len(self.time_modes)}")
        
        return self.mode_transition_matrices
    
# 状態テーブル保存
    def save_state_table(self, filepath: str):
        """
        状態の詳細情報を表形式（TSV）で保存
        
        Parameters:
        -----------
        filepath : str
            保存先ファイルパス（拡張子は.txt）
        """
        print("\nStep 7: 状態テーブル保存")
        
        # 保存先ディレクトリが存在しない場合は作成
        save_dir = os.path.dirname(filepath)
        if save_dir and not os.path.exists(save_dir):
            os.makedirs(save_dir)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            # ヘッダー行（状態とセンサーのリスト）
            header = ['状態'] + self.sensor_list
            f.write('\t'.join(header) + '\n')
            
            # 各代表状態のデータ
            for state in self.representative_states:
                label = self.state_labels.get(state, '')
                # 状態ベクトルの値を文字列に変換
                values = [str(int(v)) for v in state]
                row = [label] + values
                f.write('\t'.join(row) + '\n')
            
            # その他状態
            if 'Other' in self.state_durations:
                other_row = ['その他'] + ['-'] * len(self.sensor_list)
                f.write('\t'.join(other_row) + '\n')
        
        print(f"  状態テーブルを保存: {filepath}")

# グラフ可視化
    def _state_to_label(self, state) -> str:
        """状態を可視化用のラベルに変換"""
        return self.state_labels.get(state, 'その他')
    
    def visualize_transition_graph(self, figsize: Tuple[int, int] = FIGURE_SIZE, 
                                   save_path: Optional[str] = None):
        """
        状態遷移グラフの可視化
        
        Parameters:
        -----------
        figsize : Tuple[int, int]
            図のサイズ
        save_path : Optional[str]
            保存先のファイルパス
        """
        print("\nStep 6: グラフ可視化")
        
        self._setup_japanese_font()
        
        # NetworkXグラフの作成
        G = self._create_graph()
        
        print(f"  ノード数: {G.number_of_nodes()}")
        print(f"  エッジ数: {G.number_of_edges()} (閾値 {self.min_transition_prob} 以上)")
        
        # レイアウト計算と正規化
        pos = self._calculate_layout(G)
        
        # 描画
        fig, ax = plt.subplots(figsize=figsize)
        self._draw_graph(G, pos, ax)
        
        # ファイル保存
        if save_path:
            self._save_figure(save_path)
        
        print("  可視化完了")
        return plt
    
    def _setup_japanese_font(self):
        """日本語フォント設定"""
        import matplotlib.font_manager as fm
        
        japanese_fonts = [
            'Hiragino Sans',
            'Hiragino Kaku Gothic ProN',
            'Hiragino Kaku Gothic Pro',
            'Yu Gothic',
            'Meiryo',
            'AppleGothic'
        ]
        
        available_fonts = [f.name for f in fm.fontManager.ttflist]
        selected_font = next((font for font in japanese_fonts if font in available_fonts), None)
        
        if selected_font:
            plt.rcParams['font.sans-serif'] = [selected_font]
            plt.rcParams['font.family'] = 'sans-serif'
            plt.rcParams['axes.unicode_minus'] = False
            fm._load_fontmanager(try_read_cache=False)
            print(f"  使用フォント: {selected_font}")
        else:
            print("  警告: 日本語フォントが見つかりません")
            plt.rcParams['font.family'] = 'sans-serif'
        
        plt.rcParams['axes.unicode_minus'] = False
    
    def _create_graph(self) -> nx.DiGraph:
        """NetworkXグラフを作成"""
        G = nx.DiGraph()
        
        # ノードの追加
        all_states = list(self.representative_states)
        if 'Other' in self.state_durations:
            all_states.append('Other')
        
        for state in all_states:
            G.add_node(state, 
                      label=self._state_to_label(state),
                      occurrences=self.state_occurrences.get(state, 0),
                      duration=self.state_durations.get(state, 0))
        
        # エッジの追加（遷移確率が閾値以上のもののみ）
        for from_state, transitions in self.transition_matrix.items():
            for to_state, prob in transitions.items():
                if prob >= self.min_transition_prob:
                    G.add_edge(from_state, to_state, weight=prob)
        
        return G
    
    def _calculate_layout(self, G: nx.DiGraph) -> Dict:
        """レイアウトを計算して正規化"""
        pos = nx.spring_layout(G, k=LAYOUT_K, iterations=LAYOUT_ITERATIONS, seed=42)
        
        if not pos:
            return pos
        
        # [-0.8, 0.8]の範囲に正規化
        pos_array = np.array(list(pos.values()))
        min_vals = pos_array.min(axis=0)
        max_vals = pos_array.max(axis=0)
        range_vals = max_vals - min_vals
        range_vals[range_vals == 0] = 1  # ゼロ除算防止
        
        for node in pos:
            pos[node] = ((pos[node] - min_vals) / range_vals) * 1.6 - 0.8
        
        return pos
    
    def _draw_graph(self, G: nx.DiGraph, pos: Dict, ax, title_suffix: str = ''):
        """グラフを描画
        
        Parameters:
        -----------
        G : nx.DiGraph
            NetworkXグラフ
        pos : Dict
            ノードの位置
        ax : matplotlib.axes.Axes
            描画先の軸
        title_suffix : str
            タイトルに追加する文字列（モード名など）
        """
        # ノードサイズの計算（滞在時間に基づく）
        node_sizes = [G.nodes[node]['duration'] * NODE_SIZE_MULTIPLIER / 60  # 秒を分に変換して適切なサイズに
                     for node in G.nodes()]
        
        # ノードの描画
        nx.draw_networkx_nodes(G, pos, node_size=node_sizes, node_color='lightblue',
                              alpha=0.8, edgecolors='black', linewidths=4, ax=ax)
        
        # エッジの描画
        edges = G.edges()
        weights = [G[u][v]['weight'] for u, v in edges]
        nx.draw_networkx_edges(G, pos, width=[w * 3 for w in weights], alpha=0.5,
                              edge_color='gray', arrows=True, arrowsize=15,
                              arrowstyle='->', ax=ax, connectionstyle='arc3,rad=0.1')
        
        # ラベルの描画
        labels = {node: G.nodes[node]['label'] for node in G.nodes()}
        nx.draw_networkx_labels(G, pos, labels, font_size=FONT_SIZE_LABEL,
                               font_weight='bold', ax=ax)
        
        # エッジラベル（重要なもののみ）
        edge_labels = {(u, v): f"{G[u][v]['weight']:.2f}"
                      for u, v in G.edges()
                      if G[u][v]['weight'] >= self.min_transition_prob * 1.5}
        nx.draw_networkx_edge_labels(G, pos, edge_labels, font_size=FONT_SIZE_EDGE, ax=ax)
        
        prefix = f'状態遷移ネットワーク - {title_suffix}' if title_suffix else '状態遷移ネットワーク'
        title = (f'{prefix}\n(代表状態数: {len(self.representative_states)}, '
                 f'最小遷移確率: {self.min_transition_prob})')
        ax.set_title(title, fontsize=FONT_SIZE_TITLE, fontweight='bold', pad=20)
        ax.axis('off')
        plt.tight_layout()
    
    def _save_figure(self, save_path: str):
        """図を保存"""
        save_dir = os.path.dirname(save_path)
        if save_dir and not os.path.exists(save_dir):
            os.makedirs(save_dir)
        
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"  図を保存: {save_path}")
    
    def _get_state_color_mapping(self):
        """
        各代表状態に固定の色を割り当て
        
        Returns:
        --------
        Tuple[Dict, matplotlib.colors.ListedColormap]
            (state_to_num: 状態→数値のマッピング, cmap: カラーマップ)
        """
        # 各状態に数値を割り当て（Otherは0、代表状態は1から始まる）
        state_to_num = {'Other': 0}
        for idx, state in enumerate(self.representative_states, 1):
            state_to_num[state] = idx
        
        # 固定の色リストを作成（tab20から取得）
        import matplotlib.cm as cm
        tab20 = cm.get_cmap('tab20', 20)
        
        # Other用の色（グレー）+ 代表状態用の色
        colors = ['#808080']  # Otherの色（グレー）
        for i in range(len(self.representative_states)):
            colors.append(tab20(i % 20))  # tab20から循環して取得
        
        from matplotlib.colors import ListedColormap
        cmap = ListedColormap(colors)
        
        return state_to_num, cmap
    
    def visualize_mode_timeline(self, figsize: Tuple[int, int] = (24, 8),
                                save_path: Optional[str] = None):
        """
        モード（代表状態）の時系列変化を可視化（ヒートマップ風・複数日対応）
        
        Parameters:
        -----------
        figsize : Tuple[int, int]
            図のサイズ
        save_path : Optional[str]
            保存先のファイルパス
        """
        print("\nモード時系列図の可視化")
        
        if self.state_vectors_df is None or not self.state_sequence:
            print("  Warning: No data available. Run pipeline first.")
            return
        
        self._setup_japanese_font()
        
        # 圧縮前の状態ベクトルのインデックスと圧縮後の位置をマッピング
        # state_sequenceは圧縮前の全状態に対応している
        original_indices = self.state_vectors_df.index
        
        if len(self.state_sequence) != len(original_indices):
            print(f"  Warning: Sequence length mismatch. Expected {len(original_indices)}, got {len(self.state_sequence)}")
            return
        
        # 固定の色マッピングを取得
        state_to_num, cmap = self._get_state_color_mapping()
        
        state_nums = [state_to_num.get(state, 0) for state in self.state_sequence]
        
        # 日付ごとにデータを分割
        df_timeline = pd.DataFrame({
            'timestamp': original_indices,
            'state_num': state_nums
        })
        df_timeline['date'] = df_timeline['timestamp'].dt.date
        df_timeline['time'] = df_timeline['timestamp'].dt.hour * 3600 + df_timeline['timestamp'].dt.minute * 60 + df_timeline['timestamp'].dt.second
        
        dates = sorted(df_timeline['date'].unique())
        num_days = len(dates)
        
        # 1日を秒単位で表現（0-86399秒）
        time_slots = np.arange(0, 86400)
        
        # ヒートマップ用の2D配列を作成（行=日、列=秒）
        heatmap_data = np.full((num_days, len(time_slots)), np.nan)
        
        for day_idx, date in enumerate(dates):
            day_data = df_timeline[df_timeline['date'] == date]
            for _, row in day_data.iterrows():
                time_sec = int(row['time'])
                if time_sec < len(time_slots):
                    heatmap_data[day_idx, time_sec] = row['state_num']
        
        # NaNを前方埋め（状態は次の変化まで継続）
        for day_idx in range(num_days):
            heatmap_data[day_idx] = pd.Series(heatmap_data[day_idx]).ffill().values
        
        # プロット作成
        fig, ax = plt.subplots(figsize=figsize)
        
        # ヒートマップを描画（固定のカラーマップを使用）
        im = ax.imshow(heatmap_data, aspect='auto', cmap=cmap, 
                      vmin=0, vmax=len(self.representative_states),
                      interpolation='nearest')
        
        # X軸の設定（時刻）
        hour_ticks = [h * 3600 for h in range(0, 25, 3)]  # 3時間ごと
        hour_labels = [f'{h:02d}:00' for h in range(0, 25, 3)]
        ax.set_xticks(hour_ticks)
        ax.set_xticklabels(hour_labels, fontsize=12)
        ax.set_xlabel('時刻', fontsize=16, fontweight='bold')
        
        # Y軸の設定（日付）
        ax.set_yticks(range(num_days))
        ax.set_yticklabels([str(date) for date in dates], fontsize=12)
        ax.set_ylabel('日付', fontsize=16, fontweight='bold')
        
        # タイトル
        ax.set_title('モード時系列変化（ヒートマップ）', fontsize=20, fontweight='bold', pad=20)
        
        # 主要時刻に縦線を追加（6時、12時、18時、24時）
        for hour in [6, 12, 18, 24]:
            ax.axvline(x=hour * 3600, color='white', linewidth=1.5, linestyle='--', alpha=0.7)
        
        # モード境界線を追加
        for mode_name, (start_time, end_time) in self.time_modes.items():
            start_hour, start_minute = map(int, start_time.split(':'))
            start_sec = start_hour * 3600 + start_minute * 60
            ax.axvline(x=start_sec, color='red', linewidth=2, linestyle='-', alpha=0.5)
        
        # カラーバーの追加（状態の凡例）
        # 実際に出現する状態のみ表示
        unique_states_in_data = sorted(set(self.state_sequence), key=lambda x: state_to_num.get(x, 0))
        tick_positions = [state_to_num[state] for state in unique_states_in_data]
        tick_labels = [self._state_to_label(state) for state in unique_states_in_data]
        
        cbar = plt.colorbar(im, ax=ax, ticks=tick_positions)
        cbar.ax.set_yticklabels(tick_labels, fontsize=12)
        cbar.set_label('状態', fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        
        # 保存
        if save_path:
            self._save_figure(save_path)
        
        print("  モード時系列図の可視化完了")
        return plt
    
    def visualize_mode_timeline_by_modes(self, figsize: Tuple[int, int] = (24, 8),
                                         save_dir: str = 'picture/modes'):
        """
        時間帯モードごとのモード時系列図を可視化・保存（ヒートマップ風・複数日対応）
        
        Parameters:
        -----------
        figsize : Tuple[int, int]
            図のサイズ
        save_dir : str
            保存先ディレクトリ
        """
        print("\n[モード分割] 時系列図の可視化")
        
        if not self.mode_state_sequences:
            print("  Warning: No mode data available. Run compute_transition_matrix_by_modes() first.")
            return
        
        self._setup_japanese_font()
        
        # 保存先ディレクトリを作成
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        
        for mode_name, state_sequence in self.mode_state_sequences.items():
            print(f"\n  モード '{mode_name}' の時系列図を作成中...")
            
            # このモードの時間範囲を取得
            start_time, end_time = self.time_modes[mode_name]
            filtered_df = self._filter_by_time_mode(mode_name, start_time, end_time)
            
            if len(filtered_df) == 0 or len(state_sequence) == 0:
                print(f"    Warning: No data for mode '{mode_name}'. Skipping...")
                continue
            
            if len(state_sequence) != len(filtered_df):
                print(f"    Warning: Sequence length mismatch. Expected {len(filtered_df)}, got {len(state_sequence)}")
                continue
            
            # 固定の色マッピングを取得
            state_to_num, cmap = self._get_state_color_mapping()
            
            state_nums = [state_to_num.get(state, 0) for state in state_sequence]
            time_indices = filtered_df.index
            
            # 日付ごとにデータを分割
            df_timeline = pd.DataFrame({
                'timestamp': time_indices,
                'state_num': state_nums
            })
            df_timeline['date'] = df_timeline['timestamp'].dt.date
            df_timeline['time'] = df_timeline['timestamp'].dt.hour * 3600 + df_timeline['timestamp'].dt.minute * 60 + df_timeline['timestamp'].dt.second
            
            dates = sorted(df_timeline['date'].unique())
            num_days = len(dates)
            
            # モード時間帯の秒範囲を計算
            start_hour, start_minute = map(int, start_time.split(':'))
            end_hour, end_minute = map(int, end_time.split(':'))
            start_sec = start_hour * 3600 + start_minute * 60
            end_sec = end_hour * 3600 + end_minute * 60
            
            if end_sec <= start_sec:  # 日をまたぐ場合
                end_sec = 24 * 3600
            
            time_range = end_sec - start_sec
            time_slots = np.arange(start_sec, end_sec)
            
            # ヒートマップ用の2D配列を作成（行=日、列=秒）
            heatmap_data = np.full((num_days, len(time_slots)), np.nan)
            
            for day_idx, date in enumerate(dates):
                day_data = df_timeline[df_timeline['date'] == date]
                for _, row in day_data.iterrows():
                    time_sec = int(row['time'])
                    if start_sec <= time_sec < end_sec:
                        col_idx = time_sec - start_sec
                        if col_idx < len(time_slots):
                            heatmap_data[day_idx, col_idx] = row['state_num']
            
            # NaNを前方埋め（状態は次の変化まで継続）
            for day_idx in range(num_days):
                heatmap_data[day_idx] = pd.Series(heatmap_data[day_idx]).ffill().values
            
            # プロット作成
            fig, ax = plt.subplots(figsize=figsize)
            
            # ヒートマップを描画（固定のカラーマップを使用）
            im = ax.imshow(heatmap_data, aspect='auto', cmap=cmap,
                          vmin=0, vmax=len(self.representative_states),
                          interpolation='nearest')
            
            # X軸の設定（時刻）
            duration_hours = time_range / 3600
            if duration_hours <= 6:
                tick_interval = 3600  # 1時間ごと
            else:
                tick_interval = 2 * 3600  # 2時間ごと
            
            hour_ticks = [t - start_sec for t in range(start_sec, end_sec + 1, tick_interval)]
            hour_labels = [f'{(start_sec + t) // 3600:02d}:{((start_sec + t) % 3600) // 60:02d}' for t in hour_ticks]
            ax.set_xticks(hour_ticks)
            ax.set_xticklabels(hour_labels, fontsize=12)
            ax.set_xlabel('時刻', fontsize=16, fontweight='bold')
            
            # Y軸の設定（日付）
            ax.set_yticks(range(num_days))
            ax.set_yticklabels([str(date) for date in dates], fontsize=12)
            ax.set_ylabel('日付', fontsize=16, fontweight='bold')
            
            # タイトル
            ax.set_title(f'モード時系列変化 - {mode_name}（ヒートマップ）', fontsize=20, fontweight='bold', pad=20)
            
            # カラーバーの追加（状態の凡例）
            # 実際に出現する状態のみ表示
            unique_states_in_data = sorted(set(state_sequence), key=lambda x: state_to_num.get(x, 0))
            tick_positions = [state_to_num[state] for state in unique_states_in_data]
            tick_labels = [self._state_to_label(state) for state in unique_states_in_data]
            
            cbar = plt.colorbar(im, ax=ax, ticks=tick_positions)
            cbar.ax.set_yticklabels(tick_labels, fontsize=12)
            cbar.set_label('状態', fontsize=14, fontweight='bold')
            
            plt.tight_layout()
            
            # 保存
            save_path = os.path.join(save_dir, f'timeline_{mode_name}.png')
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            plt.close()
            
            print(f"    保存完了: {save_path}")
    
    def visualize_transition_graph_by_modes(self, figsize: Tuple[int, int] = FIGURE_SIZE,
                                           save_dir: str = 'picture/modes'):
        """
        時間帯モードごとに個別の状態遷移グラフを可視化・保存
        
        Parameters:
        -----------
        figsize : Tuple[int, int]
            図のサイズ
        save_dir : str
            保存先ディレクトリ
        """
        print("\n[モード分割] 個別グラフの可視化")
        
        if not self.mode_transition_matrices:
            print("  Warning: No mode data available. Run compute_transition_matrix_by_modes() first.")
            return
        
        # 保存先ディレクトリを作成
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        
        self._setup_japanese_font()
        
        for mode_name, transition_matrix in self.mode_transition_matrices.items():
            print(f"\n  モード '{mode_name}' のグラフを作成中...")
            
            # NetworkXグラフの作成
            G = nx.DiGraph()
            
            # ノードの追加
            all_states = list(self.representative_states)
            if 'Other' in self.mode_state_occurrences[mode_name]:
                all_states.append('Other')
            
            for state in all_states:
                if state in self.mode_state_occurrences[mode_name]:
                    G.add_node(state,
                              label=self._state_to_label(state),
                              occurrences=self.mode_state_occurrences[mode_name].get(state, 0),
                              duration=self.mode_state_durations[mode_name].get(state, 0))
            
            # エッジの追加
            for from_state, transitions in transition_matrix.items():
                for to_state, prob in transitions.items():
                    if prob >= self.min_transition_prob:
                        G.add_edge(from_state, to_state, weight=prob)
            
            print(f"    ノード数: {G.number_of_nodes()}")
            print(f"    エッジ数: {G.number_of_edges()}")
            
            # レイアウト計算
            pos = self._calculate_layout(G)
            
            # 描画
            fig, ax = plt.subplots(figsize=figsize)
            self._draw_graph(G, pos, ax, title_suffix=mode_name)
            
            # 保存
            save_path = os.path.join(save_dir, f'state_transition_{mode_name}.png')
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            plt.close()
            
            print(f"    保存完了: {save_path}")
    
    def run_pipeline(self, filepath: str, save_figure: bool = True, mode_split: bool = False):
        """
        全パイプラインの実行
        
        Parameters:
        -----------
        filepath : str
            ログファイルのパス
        save_figure : bool
            図を保存するかどうか
        mode_split : bool
            時間帯モード分割を行うかどうか
        """
        print("="*70)
        print("状態遷移可視化パイプライン")
        if mode_split:
            print("[モード分割モード: 有効]")
        print("="*70)
        
        # データ処理パイプライン
        df = self.load_data(filepath)
        self.create_state_vectors(df)
        print(df.head(3))
        self.extract_representative_states()
        self.map_to_representative_states()
        self.compute_transition_matrix()
        
        # 保存フォルダとパスの生成
        if save_figure:
            save_folder, save_path, state_table_path = self._generate_save_folder(filepath)
        else:
            save_folder, save_path, state_table_path = None, None, None
        
        # 可視化と保存（全期間）
        plt_obj = self.visualize_transition_graph(save_path=save_path)
        
        # 時系列図の可視化（全期間）
        if save_figure and save_folder:
            timeline_path = os.path.join(save_folder, "timeline_all.png")
            self.visualize_mode_timeline(save_path=timeline_path)
        
        if state_table_path:
            self.save_state_table(state_table_path)
        
        # モード分割処理（オプション）
        if mode_split:
            print("\n" + "="*70)
            print("時間帯別モード分割処理")
            print("="*70)
            
            # モードごとの遷移行列計算
            self.compute_transition_matrix_by_modes()
            
            if self.mode_transition_matrices:
                # 個別グラフの可視化（同じフォルダに保存）
                self.visualize_transition_graph_by_modes(save_dir=save_folder)
                # 個別時系列図の可視化（同じフォルダに保存）
                self.visualize_mode_timeline_by_modes(save_dir=save_folder)
            else:
                print("  Warning: No valid mode data. Skipping visualization.")
        
        return plt_obj
    
    def _generate_save_folder(self, filepath: str) -> Tuple[str, str, str]:
        """保存先フォルダと各ファイルパスを生成"""
        data_filename = os.path.splitext(os.path.basename(filepath))[0]
        
        # 保存先フォルダ: picture/データセット名_代表状態数_ハミング距離閾値/
        save_folder = f"picture/{data_filename}_{self.n_representative_states}_{self.hamming_threshold}"
        
        # フォルダを作成
        if not os.path.exists(save_folder):
            os.makedirs(save_folder)
        
        # 全期間のグラフ保存パス
        save_path = os.path.join(save_folder, "state_transition_all.png")
        
        # 状態テーブル保存パス
        state_table_path = f"state/{data_filename}_{self.n_representative_states}_{self.hamming_threshold}.txt"
        
        return save_folder, save_path, state_table_path


if __name__ == "__main__":
    # 実データファイルのパス
    # data_file = "openshs-datasets-ff6d87d/docs/datasets/openshs-classification/d1_1m_0tm.csv"
    data_file = "openshs-datasets-ff6d87d/docs/datasets/openshs-classification/d2_1m_0tm.csv"
    # data_file = "data/aruba.csv"
    
    if not os.path.exists(data_file):
        print(f"エラー: データファイルが見つかりません: {data_file}")
        exit(1)
    
    print(f"データファイル: {data_file}\n")
    
    # 可視化システムの実行
    # mode_split=Trueで時間帯別モード分割を有効化
    visualizer = StateTransitionVisualizer()
    
    # 時間帯別モード分割を有効にして実行
    visualizer.run_pipeline(data_file, mode_split=True)
    
    # カスタム時間帯定義の例（必要に応じて使用）
    # custom_modes = {
    #     'Morning': ('06:00', '12:00'),
    #     'Afternoon': ('12:00', '18:00'),
    #     'Evening': ('18:00', '24:00')
    # }
    # visualizer_custom = StateTransitionVisualizer(time_modes=custom_modes)
    # visualizer_custom.run_pipeline(data_file, mode_split=True)
