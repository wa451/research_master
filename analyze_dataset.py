import pandas as pd
from collections import Counter
from datetime import datetime

# CSVファイルの読み込み
file_path = "openshs-datasets-ff6d87d/docs/datasets/openshs-classification/d1_1m_0tm.csv"
df = pd.read_csv(file_path)

print("=" * 80)
print("データセット統計情報")
print("=" * 80)

# 1. データセットの長さ
dataset_length = len(df)
print(f"\n1. データセットの長さ: {dataset_length} 行")

# 2. ユニークな行の長さとそれぞれの出現回数
# タイムスタンプとアクティビティ列を除外
exclude_cols = ['timestamp', 'Activity']
feature_cols = [col for col in df.columns if col not in exclude_cols]
df_features = df[feature_cols]

# ユニークな行とその出現回数を計算
unique_rows = df_features.value_counts()
print(f"\n2. ユニークな行の数（timestamp, Activity列を除く）: {len(unique_rows)} パターン")
print("\n各パターンの出現回数（上位20件）:")
for idx, (pattern, count) in enumerate(unique_rows.head(20).items(), 1):
    print(f"  パターン {idx}: {count} 回")

# 全体の統計
print(f"\n  最頻出パターン: {unique_rows.iloc[0]} 回")
print(f"  最小出現回数: {unique_rows.iloc[-1]} 回")
print(f"  平均出現回数: {unique_rows.mean():.2f} 回")

# 3. 連続した同じ行を一つにまとめた場合の行数
# タイムスタンプとアクティビティ列を除いた特徴量で比較
consecutive_count = 0
previous_row = None

for _, row in df_features.iterrows():
    current_row = tuple(row)
    if current_row != previous_row:
        consecutive_count += 1
        previous_row = current_row

print(f"\n3. 連続した同じ行をまとめた場合の行数: {consecutive_count} 行")
print(f"   (元の {dataset_length} 行から {dataset_length - consecutive_count} 行削減)")
print(f"   (削減率: {(dataset_length - consecutive_count) / dataset_length * 100:.2f}%)")

# 4. タイムスタンプに注目して何時台のデータがそれぞれ何行あるか
# タイムスタンプ列をdatetime型に変換
df['timestamp'] = pd.to_datetime(df['timestamp'])
df['hour'] = df['timestamp'].dt.hour

hour_counts = df['hour'].value_counts().sort_index()

print(f"\n4. 時間帯別データ数:")
for hour, count in hour_counts.items():
    percentage = (count / dataset_length) * 100
    bar = "█" * int(percentage / 2)  # 視覚化用
    print(f"   {hour:2d}時台: {count:5d} 行 ({percentage:5.2f}%) {bar}")

print(f"\n   データの時間範囲: {df['timestamp'].min()} ~ {df['timestamp'].max()}")

# 追加統計情報
print(f"\n" + "=" * 80)
print("追加情報")
print("=" * 80)
print(f"センサー数（特徴量列数）: {len(feature_cols)} 個")
print(f"アクティビティの種類数: {df['Activity'].nunique()} 種類")
print(f"アクティビティの内訳:")
activity_counts = df['Activity'].value_counts()
for activity, count in activity_counts.items():
    percentage = (count / dataset_length) * 100
    print(f"  - {activity}: {count} 回 ({percentage:.2f}%)")

"""
================================================================================
データセット統計情報
================================================================================

1. データセットの長さ: 18800 行

2. ユニークな行の数（timestamp, Activity列を除く）: 82 パターン

各パターンの出現回数（上位20件）:
  パターン 1: 4417 回
  パターン 2: 2636 回
  パターン 3: 1500 回
  パターン 4: 1375 回
  パターン 5: 1316 回
  パターン 6: 1240 回
  パターン 7: 1063 回
  パターン 8: 865 回
  パターン 9: 665 回
  パターン 10: 268 回
  パターン 11: 256 回
  パターン 12: 256 回
  パターン 13: 248 回
  パターン 14: 221 回
  パターン 15: 187 回
  パターン 16: 130 回
  パターン 17: 124 回
  パターン 18: 121 回
  パターン 19: 99 回
  パターン 20: 83 回

  最頻出パターン: 4417 回
  最小出現回数: 1 回
  平均出現回数: 229.27 回

3. 連続した同じ行をまとめた場合の行数: 1423 行
   (元の 18800 行から 17377 行削減)
   (削減率: 92.43%)

4. 時間帯別データ数:
    8時台:  4330 行 (23.03%) ███████████
    9時台:  4053 行 (21.56%) ██████████
   18時台:  7843 行 (41.72%) ████████████████████
   21時台:  2574 行 (13.69%) ██████

   データの時間範囲: 2016-02-01 08:15:00 ~ 2016-03-01 18:20:52

================================================================================
追加情報
================================================================================
センサー数（特徴量列数）: 29 個
アクティビティの種類数: 5 種類
アクティビティの内訳:
  - personal: 10798 回 (57.44%)
  - leisure: 3875 回 (20.61%)
  - eat: 1640 回 (8.72%)
  - sleep: 1366 回 (7.27%)
  - other: 1121 回 (5.96%)
"""