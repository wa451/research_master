# スマートホーム状態遷移可視化システム

スマートホームのセンサーログ（CSV形式）を読み込み、家全体の状態遷移ネットワークを可視化するPythonシステムです。

## 機能

- CSV形式のセンサーログ読み込み
- イベント駆動型ログの状態ベクトル化（1秒サンプリング）
- 連続する同じ状態の圧縮
- 代表状態の自動抽出（頻度ベース）
- ハミング距離による状態マッピング
- 遷移確率計算
- NetworkXによる状態遷移グラフ可視化
- 時間帯別モード分割（Morning/Daytime/Night/Midnightの4区分）

## 処理フロー（関数呼び出し順序）

`run_pipeline()`メソッドが以下の順序で各処理を実行します：

### Step 1: `load_data(filepath)`
**データ読み込みと前処理**
- CSV形式のセンサーログファイルを読み込み
- タイムスタンプ列とセンサー列を自動検出
- 全データをイベント駆動形式のDataFrameに変換

### Step 2: `create_state_vectors(df)`
**状態ベクトル化と圧縮**
- イベント駆動型ログを1秒ごとの状態ベクトルに変換（Sample-and-Hold方式）
- 各時刻における全センサーの状態（0/1）をベクトル化
- 連続する同じ状態ベクトルを圧縮（状態変化のみ保持）

### Step 3: `extract_representative_states()`
**代表状態の抽出**
- 全状態パターンの出現頻度を集計
- 頻度上位K個を代表状態として選定
- 各代表状態にラベル（状態1, 状態2, ...）を付与

### Step 4: `map_to_representative_states()`
**状態マッピング**
- 全時刻の状態を代表状態にマッピング
- ハミング距離を用いて最も近い代表状態に割り当て
- 距離が閾値以上の場合は「その他」に分類

### Step 5: `compute_transition_matrix()`
**遷移確率行列の計算**
- マッピング後の自己遷移を圧縮（同じ代表状態が連続する場合を圧縮）
- 各状態の出現回数をカウント（圧縮後シーケンス内）
- 状態間の遷移回数をカウントして確率に変換

### オプション: `compute_transition_matrix_by_modes()`
**時間帯別の遷移確率行列計算（mode_split=True時）**
- 各時間帯（Morning/Daytime/Night/Midnight）でデータをフィルタリング
- 時間帯ごとに独立して遷移確率行列を計算
- データが存在しない時間帯は自動的にスキップ

### Step 6: `visualize_transition_graph(save_path)`
**グラフ可視化**
- NetworkXで有向グラフを作成
- ノードサイズは出現回数に比例
- エッジの太さは遷移確率に比例
- Spring layoutでノード配置を最適化
- matplotlib/日本語フォントで描画・保存
- 保存先: `picture/{データセット名}_{日時}/state_transition_all.png`

### オプション: `visualize_transition_graph_by_modes(save_dir)`
**時間帯別グラフ可視化（mode_split=True時）**
- 各時間帯ごとに個別のグラフを生成
- 保存先: `picture/{データセット名}_{日時}/state_transition_{モード名}.png`

### Step 7: `save_state_table(filepath)`
**状態テーブル保存**
- 各代表状態のセンサー値（0/1）を表形式で保存
- stateフォルダにTSV形式で出力
- ファイル名: `{データセット名}_{代表状態数}_{ハミング距離}.txt`

## インストール

```bash
uv sync
```

## 使用方法

### 基本的な使用方法

```python
from main import StateTransitionVisualizer
import matplotlib.pyplot as plt

# 全期間の状態遷移グラフを作成
visualizer = StateTransitionVisualizer(
    n_representative_states=20,
    min_transition_prob=0.1,
    hamming_threshold=1
)

visualizer.run_pipeline('path/to/sensor_data.csv')
plt.show()
```

### 時間帯別モード分割を使用する場合

```python
from main import StateTransitionVisualizer

# 時間帯別の状態遷移グラフを作成
visualizer = StateTransitionVisualizer(
    n_representative_states=20,
    min_transition_prob=0.1,
    hamming_threshold=1
)

# mode_split=Trueで時間帯別分析を有効化
visualizer.run_pipeline('path/to/sensor_data.csv', mode_split=True)
```

### カスタム時間帯定義

```python
# 独自の時間帯を定義
custom_modes = {
    'Morning': ('06:00', '12:00'),
    'Afternoon': ('12:00', '18:00'),
    'Evening': ('18:00', '24:00')
}

visualizer = StateTransitionVisualizer(
    n_representative_states=20,
    time_modes=custom_modes
)

visualizer.run_pipeline('path/to/sensor_data.csv', mode_split=True)
```

## サンプル実行

```bash
uv run python main.py
```

## 依存関係

- pandas >= 2.0.0
- numpy >= 1.24.0
- networkx >= 3.0
- matplotlib >= 3.7.0
- scipy >= 1.10.0

## uv の使い方

### Pythonバージョンの変更

```bash
# 利用可能なPythonバージョンを確認
uv python list

# 特定のバージョンをインストール
uv python install 3.11

# プロジェクトで使用するPythonバージョンを指定
uv python pin 3.11

# pyproject.tomlで指定
# requires-python = ">=3.11"
```

### ライブラリの追加

```bash
# ライブラリを追加（自動でpyproject.tomlに追記される）
uv add seaborn

# 特定のバージョンを指定
uv add "scikit-learn>=1.3.0"

# 開発用の依存関係として追加
uv add --dev pytest

# 複数同時に追加
uv add seaborn scikit-learn plotly
```

### ライブラリの削除

```bash
# ライブラリを削除
uv remove seaborn

# 複数同時に削除
uv remove seaborn plotly
```

### その他の便利なコマンド

```bash
# 依存関係の再同期（pyproject.tomlに合わせる）
uv sync

# インストール済みパッケージの一覧表示
uv pip list

# 仮想環境でコマンドを実行
uv run python script.py
uv run pytest

# 仮想環境を削除して再構築
rm -rf .venv
uv sync

# 依存関係のアップグレード
uv lock --upgrade
uv sync
```
