"""
CASASデータセットを用いたスマートホーム状態遷移可視化システム

このモジュールは、スマートホームのセンサーログ（CASASフォーマット）を読み込み、
家全体の状態遷移ネットワークを可視化します。

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


class SmartHomeStateVisualizer:
    """
    スマートホーム状態遷移可視化クラス
    
    CASASデータセットを読み込み、状態ベクトル化、代表状態の抽出、
    遷移確率の計算、グラフ可視化を行う。
    """
    
    def __init__(self, 
                 n_representative_states: int = 15,
                 min_transition_prob: float = 0.1,
                 chattering_threshold: int = 5,
                 hamming_threshold: int = 2):
        """
        初期化
        
        Parameters:
        -----------
        n_representative_states : int
            代表状態の数（頻度上位K個）
        min_transition_prob : float
            可視化する最小遷移確率
        chattering_threshold : int
            チャタリング除去の閾値（秒）
        hamming_threshold : int
            代表状態へのマッピング時のハミング距離閾値
        """
        self.n_representative_states = n_representative_states
        self.min_transition_prob = min_transition_prob
        self.chattering_threshold = chattering_threshold
        self.hamming_threshold = hamming_threshold
        
        self.sensor_list = []
        self.state_vectors_df = None
        self.representative_states = []
        self.state_sequence = []
        self.transition_matrix = None
        self.state_durations = {}
        self.state_occurrences = {}  # 各状態の出現回数（遷移回数）
        self.state_labels = {}  # 状態ID → ラベル（状態1, 状態2, ...）のマッピング
        
    def load_casas_data(self, filepath: str) -> pd.DataFrame:
        """
        センサーログファイルを読み込む
        
        2つのフォーマットに対応:
        1. CASAS形式: "Date Time SensorID Value"
        2. CSV形式: カンマ区切りのセンサー状態データ
        
        Parameters:
        -----------
        filepath : str
            ログファイルのパス
            
        Returns:
        --------
        pd.DataFrame
            処理済みのセンサーデータ
        """
        print("Step 1: データ読み込みと前処理")
        
        # ファイル形式を判定
        with open(filepath, 'r') as f:
            first_line = f.readline().strip()
        
        # カンマが含まれていればCSV形式
        if ',' in first_line:
            return self._load_csv_format(filepath)
        else:
            return self._load_casas_format(filepath)
    
    def _load_casas_format(self, filepath: str) -> pd.DataFrame:
        """
        CASAS形式のログファイルを読み込む
        フォーマット: Date Time SensorID Value [Label(Optional)]
        """
        data_rows = []
        
        with open(filepath, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 4:
                    date_str = parts[0]
                    time_str = parts[1]
                    sensor_id = parts[2]
                    value = parts[3]
                    
                    # M*** (Motion) と D*** (Door) センサーのみを対象
                    if sensor_id.startswith('M') or sensor_id.startswith('D'):
                        # Datetime オブジェクトを作成
                        timestamp = datetime.strptime(f"{date_str} {time_str}", 
                                                     "%Y-%m-%d %H:%M:%S.%f")
                        data_rows.append({
                            'timestamp': timestamp,
                            'sensor_id': sensor_id,
                            'value': value
                        })
        
        df = pd.DataFrame(data_rows)
        
        # 値をバイナリ化（ON/OPEN = 1, OFF/CLOSE = 0）
        df['binary_value'] = df['value'].apply(
            lambda x: 1 if x in ['ON', 'OPEN'] else 0
        )
        
        # タイムスタンプでソート
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        print(f"  読み込み完了: {len(df)} イベント")
        print(f"  センサー数: {df['sensor_id'].nunique()}")
        print(f"  期間: {df['timestamp'].min()} ~ {df['timestamp'].max()}")
        
        return df
    
    def _load_csv_format(self, filepath: str) -> pd.DataFrame:
        """
        CSV形式のセンサーデータを読み込む
        カンマ区切りで、各列がセンサー、最後の列がタイムスタンプ
        """
        # CSVファイルを読み込み
        df_csv = pd.read_csv(filepath)
        
        # タイムスタンプ列を特定
        timestamp_col = 'timestamp' if 'timestamp' in df_csv.columns else df_csv.columns[-1]
        
        # タイムスタンプをdatetimeに変換
        df_csv[timestamp_col] = pd.to_datetime(df_csv[timestamp_col])
        
        # センサー列を抽出（数値列のみ、Activity/labelなどは除外）
        sensor_cols = [col for col in df_csv.columns 
                      if col not in [timestamp_col, 'Activity', 'activity', 'label', 'Label']]
        
        print(f"  検出されたセンサー: {len(sensor_cols)}個")
        print(f"  期間: {df_csv[timestamp_col].min()} ~ {df_csv[timestamp_col].max()}")
        
        # イベント駆動形式に変換（状態が変化したときのみ記録）
        data_rows = []
        
        for sensor in sensor_cols:
            # 各センサーの状態変化を検出
            values = df_csv[sensor].values
            timestamps = df_csv[timestamp_col].values
            
            # 初期状態を記録
            if len(values) > 0:
                prev_value = values[0]
                data_rows.append({
                    'timestamp': pd.Timestamp(timestamps[0]),
                    'sensor_id': sensor,
                    'value': 'ON' if prev_value == 1 else 'OFF',
                    'binary_value': int(prev_value)
                })
                
                # 状態変化を検出
                for i in range(1, len(values)):
                    if values[i] != prev_value:
                        data_rows.append({
                            'timestamp': pd.Timestamp(timestamps[i]),
                            'sensor_id': sensor,
                            'value': 'ON' if values[i] == 1 else 'OFF',
                            'binary_value': int(values[i])
                        })
                        prev_value = values[i]
        
        # DataFrameに変換してソート
        df = pd.DataFrame(data_rows)
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        print(f"  イベント数: {len(df)}")
        
        return df
    
    def create_state_vectors(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        イベント駆動型ログを1秒ごとの状態ベクトルに変換
        
        Sample-and-Hold方式: センサーがONになったら、
        次にOFFイベントが来るまで状態を維持する。
        
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
        
        # センサーリストを取得
        self.sensor_list = sorted(df['sensor_id'].unique())
        print(f"  対象センサー: {len(self.sensor_list)}個")
        
        # 時間範囲を決定（1秒刻み）
        start_time = df['timestamp'].min().replace(microsecond=0)
        end_time = df['timestamp'].max().replace(microsecond=0) + timedelta(seconds=1)
        time_range = pd.date_range(start=start_time, end=end_time, freq='1s')
        
        print(f"  時間範囲: {len(time_range)}秒")
        
        # 各センサーの状態を時系列で追跡
        sensor_states = {sensor: 0 for sensor in self.sensor_list}
        state_vectors = []
        
        event_idx = 0
        events = df.to_dict('records')
        
        for current_time in time_range:
            # この時刻までに発生したイベントを処理
            while event_idx < len(events):
                event = events[event_idx]
                if event['timestamp'] <= current_time:
                    sensor_states[event['sensor_id']] = event['binary_value']
                    event_idx += 1
                else:
                    break
            
            # 現在の状態ベクトルを記録
            state_vectors.append(sensor_states.copy())
        
        # DataFrameに変換
        self.state_vectors_df = pd.DataFrame(state_vectors, 
                                             index=time_range,
                                             columns=self.sensor_list)
        
        print(f"  状態ベクトル生成完了: {len(self.state_vectors_df)}行 × {len(self.sensor_list)}列")
        
        # チャタリング除去（オプション）
        if self.chattering_threshold > 0:
            self._remove_chattering()
        
        return self.state_vectors_df
    
    def _remove_chattering(self):
        """
        チャタリング除去: 短時間（閾値未満）の状態変化を除去
        """
        print(f"  チャタリング除去（閾値: {self.chattering_threshold}秒）")
        
        for sensor in self.sensor_list:
            values = self.state_vectors_df[sensor].values.copy()
            
            i = 0
            while i < len(values) - 1:
                current_val = values[i]
                
                # 状態が変化した点を探す
                change_idx = i + 1
                while change_idx < len(values) and values[change_idx] == current_val:
                    change_idx += 1
                
                if change_idx >= len(values):
                    break
                
                # 次の変化点を探す
                next_change_idx = change_idx + 1
                changed_val = values[change_idx]
                while next_change_idx < len(values) and values[next_change_idx] == changed_val:
                    next_change_idx += 1
                
                # 状態変化の持続時間を確認
                duration = next_change_idx - change_idx
                
                if duration < self.chattering_threshold:
                    # 短時間の変化 → 前の状態で埋める
                    values[change_idx:next_change_idx] = current_val
                    i = change_idx
                else:
                    i = change_idx
            
            self.state_vectors_df[sensor] = values
    
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
            self.state_durations[state] = state_counter[state]
        
        # "その他"状態の出現回数も記録
        other_count = sum(
            count for state, count in state_counter.items()
            if state not in self.representative_states
        )
        if other_count > 0:
            self.state_durations['Other'] = other_count
            self.state_labels['Other'] = 'その他'
        
        return self.representative_states
    
    def _compute_hamming_distance(self, state1: Tuple, state2: Tuple) -> int:
        """
        2つの状態ベクトル間のハミング距離を計算
        
        Parameters:
        -----------
        state1, state2 : Tuple
            比較する状態ベクトル
            
        Returns:
        --------
        int
            異なるビット数
        """
        return sum(s1 != s2 for s1, s2 in zip(state1, state2))
    
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
        print("\n  状態マッピング処理")
        
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
                if min_distance < self.hamming_threshold:
                    mapped_states.append(closest_state)
                else:
                    mapped_states.append('Other')
                    other_count += 1
        
        print(f"  マッピング完了: {other_count}個を'Other'に分類")
        
        self.state_sequence = mapped_states
        return self.state_sequence
    
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
        print("\nStep 4: 遷移確率行列の計算")
        
        # 自己遷移を圧縮（同じ状態が連続する場合は1つにまとめる）
        compressed_sequence = []
        for state in self.state_sequence:
            if not compressed_sequence or state != compressed_sequence[-1]:
                compressed_sequence.append(state)
        
        print(f"  元のシーケンス長: {len(self.state_sequence)}")
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
    
    def _state_to_label(self, state) -> str:
        """
        状態を可視化用のラベルに変換
        
        Parameters:
        -----------
        state : Tuple or str
            状態ベクトルまたは"Other"
            
        Returns:
        --------（状態1, 状態2, ...）
        """
        return self.state_labels.get(state, 'その他')
    
    def _get_state_details(self, state) -> str:
        """
        状態の詳細情報を取得
        
        Parameters:
        -----------
        state : Tuple or str
            状態ベクトルまたは"Other"
            
        Returns:
        --------
        str
            状態の詳細（各センサーの値）
        """
        if state == 'Other':
            return 'その他の状態'
        
        # 各センサーの状態をリスト化
        details = []
        for i, sensor in enumerate(self.sensor_list):
            value = state[i]
            details.append(f"{sensor}={value}")
        
        return ', '.join(details)
    
    def save_state_details(self, filepath: str):
        """
        状態の詳細情報をファイルに保存
        
        Parameters:
        -----------
        filepath : str
            保存先ファイルパス
        """
        # 保存先ディレクトリが存在しない場合は作成
        save_dir = os.path.dirname(filepath)
        if save_dir and not os.path.exists(save_dir):
            os.makedirs(save_dir)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write("状態詳細情報\n")
            f.write("="*80 + "\n\n")
            
            # 代表状態の詳細
            for state in self.representative_states:
                label = self.state_labels.get(state, '')
                details = self._get_state_details(state)
                duration = self.state_durations.get(state, 0)
                
                f.write(f"{label}\n")
                f.write(f"  出現回数: {duration}秒\n")
                f.write(f"  センサー状態: {details}\n")
                f.write("\n")
            
            # その他状態
            if 'Other' in self.state_durations:
                f.write("その他\n")
                f.write(f"  出現回数: {self.state_durations['Other']}秒\n")
                f.write(f"  説明: 代表状態に含まれないその他の状態パターン\n")
                f.write("\n")
            
            # 遷移情報
            f.write("="*80 + "\n")
            f.write("状態遷移情報\n")
            f.write("="*80 + "\n\n")
            
            for from_state, transitions in self.transition_matrix.items():
                from_label = self.state_labels.get(from_state, 'その他')
                f.write(f"{from_label} → \n")
                
                # 遷移確率でソート
                sorted_transitions = sorted(transitions.items(), 
                                           key=lambda x: x[1], reverse=True)
                
                for to_state, prob in sorted_transitions:
                    to_label = self.state_labels.get(to_state, 'その他')
                    f.write(f"  {to_label}: {prob:.3f} ({prob*100:.1f}%)\n")
                f.write("\n")
        
        print(f"  状態詳細を保存: {filepath}")
    
    def save_state_table(self, filepath: str):
        """
        状態の詳細情報を表形式（TSV）で保存
        
        Parameters:
        -----------
        filepath : str
            保存先ファイルパス（拡張子は.txt）
        """
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
    
    def visualize_transition_graph(self, figsize: Tuple[int, int] = (36, 32), 
                                   save_path: Optional[str] = None):
        """
        状態遷移グラフの可視化
        
        Parameters:
        -----------
        figsize : Tuple[int, int]
            図のサイズ
        save_path : Optional[str]
            保存先のファイルパス。指定されない場合は保存しない
        """
        print("\nStep 5: 可視化")
        
        # 日本語フォントの設定（複数候補を試す）
        import matplotlib.font_manager as fm
        
        # macOSで使用可能な日本語フォントのリストを優先度順に試す
        japanese_fonts = [
            'Hiragino Sans',
            'Hiragino Kaku Gothic ProN',
            'Hiragino Kaku Gothic Pro',
            'Yu Gothic',
            'Meiryo',
            'AppleGothic'
        ]
        
        # 利用可能なフォントを探す
        available_fonts = [f.name for f in fm.fontManager.ttflist]
        selected_font = None
        for font in japanese_fonts:
            if font in available_fonts:
                selected_font = font
                break
        
        if selected_font:
            # フォント設定を徹底的に適用
            plt.rcParams['font.sans-serif'] = [selected_font]
            plt.rcParams['font.family'] = 'sans-serif'
            plt.rcParams['axes.unicode_minus'] = False
            # matplotlibのフォントキャッシュをクリア
            fm._load_fontmanager(try_read_cache=False)
            print(f"  使用フォント: {selected_font}")
        else:
            print("  警告: 日本語フォントが見つかりません")
            plt.rcParams['font.family'] = 'sans-serif'
        
        plt.rcParams['axes.unicode_minus'] = False
        
        # NetworkXグラフの作成
        G = nx.DiGraph()
        
        # ノードの追加（代表状態 + Other）
        all_states = list(self.representative_states)
        if 'Other' in self.state_durations:
            all_states.append('Other')
        
        for state in all_states:
            label = self._state_to_label(state)
            occurrences = self.state_occurrences.get(state, 0)
            G.add_node(state, label=label, occurrences=occurrences)
        
        # エッジの追加（遷移確率が閾値以上のもののみ）
        edges_added = 0
        for from_state, transitions in self.transition_matrix.items():
            for to_state, prob in transitions.items():
                if prob >= self.min_transition_prob:
                    G.add_edge(from_state, to_state, weight=prob)
                    edges_added += 1
        
        print(f"  ノード数: {G.number_of_nodes()}")
        print(f"  エッジ数: {edges_added} (閾値 {self.min_transition_prob} 以上)")
        
        # レイアウト計算
        pos = nx.spring_layout(G, k=0.3, iterations=100, seed=42) #k: ノード間距離の目安
        
        # レイアウトを正規化して[-0.8, 0.8]の範囲に収める
        if pos:
            pos_array = np.array(list(pos.values()))
            min_vals = pos_array.min(axis=0)
            max_vals = pos_array.max(axis=0)
            range_vals = max_vals - min_vals
            range_vals[range_vals == 0] = 1  # ゼロ除算を防ぐ
            
            # [-0.8, 0.8]の範囲に正規化
            for node in pos:
                pos[node] = ((pos[node] - min_vals) / range_vals) * 1.6 - 0.8
        
        # 描画
        fig, ax = plt.subplots(figsize=figsize)
        
        # ノードサイズ（出現回数に比例、最大値を制限）
        occurrences = [G.nodes[node]['occurrences'] for node in G.nodes()]
        max_occurrences = max(occurrences) if occurrences else 1
        node_sizes = [
            # min(, 10000)
            G.nodes[node]['occurrences'] * 1000
            for node in G.nodes()
        ]
        print(node_sizes)
        
        # ノードの描画
        nx.draw_networkx_nodes(
            G, pos,
            node_size=node_sizes,
            node_color='lightblue',
            alpha=0.8,
            edgecolors='black',
            linewidths=4,
            ax=ax
        )
        
        # エッジの描画（太さは遷移確率に比例）
        edges = G.edges()
        weights = [G[u][v]['weight'] for u, v in edges]
        
        nx.draw_networkx_edges(
            G, pos,
            width=[w * 3 for w in weights],
            alpha=0.5,
            edge_color='gray',
            arrows=True,
            arrowsize=15,
            arrowstyle='->',
            ax=ax,
            connectionstyle='arc3,rad=0.1'
        )
        
        # ラベルの描画
        labels = {node: G.nodes[node]['label'] for node in G.nodes()}
        nx.draw_networkx_labels(
            G, pos,
            labels,
            font_size=18,
            font_weight='bold',
            ax=ax
        )
        
        # エッジラベル（遷移確率）- 重要なもののみ表示
        edge_labels = {
            (u, v): f"{G[u][v]['weight']:.2f}"
            for u, v in G.edges()
            if G[u][v]['weight'] >= self.min_transition_prob * 1.5
        }
        nx.draw_networkx_edge_labels(
            G, pos,
            edge_labels,
            font_size=12,
            ax=ax
        )
        
        ax.set_title('スマートホーム状態遷移ネットワーク\n'
                    f'(代表状態数: {len(self.representative_states)}, '
                    f'最小遷移確率: {self.min_transition_prob})',
                    fontsize=20, fontweight='bold', pad=20)
        ax.axis('off')
        
        # 表示範囲を固定して全体が収まるように
        # ax.set_xlim(-1.0, 1.0)
        # ax.set_ylim(-1.0, 1.0)
        
        plt.tight_layout()
        
        # ファイル保存
        if save_path:
            # 保存先ディレクトリが存在しない場合は作成
            save_dir = os.path.dirname(save_path)
            if save_dir and not os.path.exists(save_dir):
                os.makedirs(save_dir)
            
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"  図を保存: {save_path}")
        
        print("  可視化完了")
        
        return plt
    
    def run_pipeline(self, filepath: str, save_figure: bool = True):
        """
        全パイプラインの実行
        
        Parameters:
        -----------
        filepath : str
            CASASログファイルのパス
        save_figure : bool
            図をpictureフォルダに保存するかどうか
        """
        print("="*70)
        print("CASASデータセット状態遷移可視化パイプライン")
        print("="*70)
        
        # Step 1: データ読み込み
        df = self.load_casas_data(filepath)
        
        # Step 2: 状態ベクトル化
        self.create_state_vectors(df)
        
        # Step 3: 代表状態の抽出
        self.extract_representative_states()
        
        # Step 3続き: 状態マッピング
        self.map_to_representative_states()
        
        # Step 4: 遷移確率計算
        self.compute_transition_matrix()
        
        # 保存パスの生成
        save_path = None
        state_table_path = None
        if save_figure:
            # データファイル名から図のファイル名を生成
            data_filename = os.path.splitext(os.path.basename(filepath))[0]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = f"picture/state_transition_{data_filename}_{timestamp}.png"
            # 状態テーブルの保存パス（stateフォルダ、入力ファイルと同じ名前）
            state_table_path = f"state/{data_filename}.txt"
        
        # Step 5: 可視化
        plt_obj = self.visualize_transition_graph(save_path=save_path)
        
        # 状態テーブルの保存
        if state_table_path:
            self.save_state_table(state_table_path)
        
        print("\n" + "="*70)
        print("パイプライン完了")
        print("="*70)
        
        return plt_obj


if __name__ == "__main__":
    # 実データファイルのパス
    data_file = "openshs-datasets-ff6d87d/docs/datasets/openshs-classification/d1_1m_0tm.csv"
    
    # ファイル存在チェック
    if not os.path.exists(data_file):
        print(f"エラー: データファイルが見つかりません: {data_file}")
        print("正しいファイルパスを指定してください。")
        exit(1)
    
    print(f"データファイル: {data_file}\n")
    
    # 可視化システムの実行
    visualizer = SmartHomeStateVisualizer(
        n_representative_states=15,
        min_transition_prob=0.001,
        chattering_threshold=0,  # チャタリング除去なし（自己遷移のみ圧縮）
        hamming_threshold=2
    )
    
    visualizer.run_pipeline(data_file)
    
    # グラフ表示
    # plt.show()
    
    print("\n" + "="*70)
    print("使用方法")
    print("="*70)
    print("visualizer = SmartHomeStateVisualizer(")
    print("    n_representative_states=10,  # 代表状態の数")
    print("    min_transition_prob=0.05,     # 可視化する最小遷移確率")
    print("    chattering_threshold=5,       # チャタリング除去閾値(秒)")
    print("    hamming_threshold=2           # 状態マッピング距離閾値")
    print(")")
    print("visualizer.run_pipeline('path/to/casas_data.csv')")
    print("plt.show()")
