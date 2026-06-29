"""
代表状態抽出までを行ったセンサログを直接プロンプトに入れてパターンを抽出する。
"""
from __future__ import annotations

import csv
import json
import os
from datetime import timedelta
from pathlib import Path
from typing import List, Tuple

import pandas as pd

from experiment_config import (
    DATASET_NAME,
    DAYS,
    HAMMING_THRESHOLD,
    LLM_MAX_RETRIES_PER_RUN,
    LLM_MODEL_NAME,
    LLM_RUNS_DEFAULT,
    LLM_TEMPERATURE,
    N_STATES,
    ROOT_DIR,
)
from src.behavior_pattern_mining.llm.client import call_gemini, load_dotenv, parse_pattern_records
from src.behavior_pattern_mining.visualization import state_transition_visualizer as stv


# =============================
# ユーザー設定（必要に応じて変更）
# =============================
ENV_FILE_PATH = ROOT_DIR / ".env"
PROMPT_FILE_PATH = ROOT_DIR / "prompts" / "direct_log_pattern_extraction_prompt.md"
MODEL_NAME = LLM_MODEL_NAME
TEMPERATURE = LLM_TEMPERATURE
# 解析に使うログ日数
LOG_DAYS = DAYS
# プロンプトに入れる最大行数（0で無制限）
MAX_ROWS = 0
# 実行回数（同じ入力で複数回生成）
RUNS = LLM_RUNS_DEFAULT
# 1回の実行で失敗した場合の最大リトライ回数
MAX_RETRIES_PER_RUN = LLM_MAX_RETRIES_PER_RUN
# 入力CSV（イベントログ形式）
INPUT_CSV_PATH = ROOT_DIR / "data" / f"{DATASET_NAME}.csv"
# 出力ルート（デフォルトで llm_direct_{LOG_DAYS} 配下になるよう設定）
OUTPUT_DIR = ROOT_DIR / "output" / f"llm_direct_{LOG_DAYS}"

PROMPT_TEMPLATE = """
あなたはスマートホームのデータサイエンティストであり、人間の行動分析のエキスパートです。
以下の入力は、ある単身高齢者宅のセンサログ（{DATASET}）から抽出された「代表状態の時系列」です。

## 状態の定義（デバイス対応表）
各状態がどのデバイスをON/OFFにしているかを以下の表に示します。
セルの値は 0（OFF）または 1（ON）です。

{STATE_TABLE}

## 入力データの背景
- 元のセンサログは、複数の状態パターンに圧縮・要約されています
- 各行は日時と、その時点での代表状態を示しています
- 状態は「状態1」「状態2」...「状態{N_STATES}」のように番号付けされています（ただしすべてが表れるとは限りません）

## 入力データ（状態の時系列）
{LOG_DATA}

## 実行タスク
以下の3つのステップに沿って推論を行ってください。出力はStep 3のJSONのみを自動処理で読み取ります。

### Step 1: 代表状態の解釈（テキスト出力）
上記の状態定義表を参考に、各状態がどのような生活シーン（例: 就寝、起床、食事など）に対応するかを推測してください。
各状態のON/OFF状態の組み合わせから、居住者がどこで何をしているのかを推測します。

### Step 2: 頻出する行動シーケンスの抽出（テキスト出力）
状態の時系列から、居住者がどのような意図を持って行動しているか、
ストーリーとして解釈できるシーケンスを抽出してください。
【厳守事項】
1. 各シーケンスの長さは必ず「2〜4個」の範囲内。
2. 同じ状態が連続するもの（状態1→状態1）は圧縮されているため除外。
3. 上記の条件を満たす意味のある行動ルートは、件数の制限を設けず、網羅的にすべて抽出してください。

### Step 3: JSONフォーマットでの最終出力（絶対厳守）
Step 2で抽出した「すべて」のパターンについて、後続のプログラムで読み込むためのJSON配列として出力してください。
必ずコードブロック（```json ... ```）を使用し、以下の3つのキーを持つオブジェクトの配列にしてください。

出力例：
```json
[
  {{
    "パターン名": "深夜のトイレ往復行動",
    "解釈の根拠": "就寝状態から廊下を経てトイレへ行き戻っているため。",
    "遷移のシーケンス": ["状態4", "状態6", "状態5", "状態1"]
  }},
  {{
    "パターン名": "起床から朝食までのルーチン",
    "解釈の根拠": "寝室の反応から洗面所、キッチンへ移動しているため。",
    "遷移のシーケンス": ["状態4", "状態10", "状態13"]
  }}
]
```
""".strip()


def load_prompt_template(prompt_path: Path, fallback: str) -> str:
    """Read the external prompt template, falling back to the embedded copy."""
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8").strip()
    return fallback


PROMPT_TEMPLATE = load_prompt_template(PROMPT_FILE_PATH, PROMPT_TEMPLATE)


def read_event_log(csv_path: Path) -> pd.DataFrame:
    """イベントログCSVを読み込み、timestamp/sensor/value に正規化する。"""
    if not csv_path.exists():
        raise FileNotFoundError(f"Input CSV not found: {csv_path}")

    # イベントログ形式（4列）/ 簡易形式（3列）の両対応
    df = pd.read_csv(csv_path, header=None)
    if len(df.columns) < 3:
        raise ValueError("Unsupported CSV format. Expected at least 3 columns.")

    if len(df.columns) >= 4:
        df = df.iloc[:, :4].copy()
        df.columns = ["date", "time", "sensor", "value"]
        df["timestamp"] = pd.to_datetime(
            df["date"].astype(str) + " " + df["time"].astype(str),
            errors="coerce",
        )
    else:
        df = df.iloc[:, :3].copy()
        df.columns = ["timestamp", "sensor", "value"]
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

    df = df.dropna(subset=["timestamp", "sensor", "value"]).copy()
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df[["timestamp", "sensor", "value"]]


def build_log_text(df: pd.DataFrame, max_rows: int) -> Tuple[str, bool]:
    truncated = False
    if max_rows > 0 and len(df) > max_rows:
        df = df.head(max_rows).copy()
        truncated = True

    # プロンプトに入れるタブ区切りログを構築
    lines = []
    for _, row in df.iterrows():
        ts = row["timestamp"]
        sensor = str(row["sensor"])
        value = str(row["value"])
        lines.append(f"{ts}\t{sensor}\t{value}")

    return "\n".join(lines), truncated


def build_prompt(dataset_name: str, days: int, log_text: str, truncated: bool) -> str:
    header = f"{dataset_name} / {days} days"
    log_section = log_text
    if truncated:
        # 入力が途中で切れていることを明示
        log_section = "[注: ログは先頭のみ抜粋]\n" + log_section

    return (
        PROMPT_TEMPLATE
        .replace("{DATASET}", header)
        .replace("{LOG_DATA}", log_section)
    )


def find_state_file(dataset_name: str, n_states: int, hamming_threshold: int, num_days: int) -> Path:
    """
    state フォルダから対応する状態定義ファイルを探す
    
    ファイル名パターン: {DATASET_NAME}_{N_STATES}_{HAMMING_THRESHOLD}_{num_days}days.txt
                   または {DATASET_NAME}_{N_STATES}_{HAMMING_THRESHOLD}.txt
    
    Returns:
    --------
    Path
        見つかった状態ファイルのパス
        
    Raises:
    -------
    FileNotFoundError
        対応するファイルが見つからない場合
    """
    state_dir = ROOT_DIR / "state"
    
    # パターン1: {DATASET}_{N_STATES}_{H}_{days}days.txt
    pattern1 = state_dir / f"{dataset_name}_{n_states}_{hamming_threshold}_{num_days}days.txt"
    if pattern1.exists():
        return pattern1
    
    # パターン2: {DATASET}_{N_STATES}_{H}.txt
    pattern2 = state_dir / f"{dataset_name}_{n_states}_{hamming_threshold}.txt"
    if pattern2.exists():
        return pattern2
    
    raise FileNotFoundError(
        f"状態定義ファイルが見つかりません。"
        f"以下のファイルを確認してください:\n"
        f"  - {pattern1}\n"
        f"  - {pattern2}"
    )


def load_state_definition(state_file: Path) -> Tuple[dict, dict]:
    """
    状態定義ファイルを読み込み、状態ラベルと状態ベクトル(タプル)をマッピング
    
    ファイル形式（TSV）:
    状態    Sensor1  Sensor2  ...
    状態1   0        1        ...
    状態2   1        0        ...
    ...
    
    Returns:
    --------
    Tuple[dict, dict]
        (state_label_to_vector, vector_to_label)
        - state_label_to_vector: "状態1" -> (0, 1, 0, ...) のマッピング
        - vector_to_label: (0, 1, 0, ...) -> "状態1" のマッピング
    """
    df = pd.read_csv(state_file, sep="\t", index_col=0)
    
    state_label_to_vector = {}
    vector_to_label = {}
    
    for state_label, row in df.iterrows():
        # 状態ベクトルをタプルに変換（-1 は除外）
        vector = tuple(int(v) for v in row.values if v != "-")
        state_label_to_vector[state_label] = vector
        vector_to_label[vector] = state_label
    
    return state_label_to_vector, vector_to_label


def state_table_to_text(state_file: Path) -> str:
    """
    状態定義ファイルをテキスト形式に変換（プロンプト用）
    
    Parameters:
    -----------
    state_file : Path
        状態定義ファイルのパス
    
    Returns:
    --------
    str
        TSV形式のテーブルテキスト
    """
    with open(state_file, "r", encoding="utf-8") as f:
        return f.read()


def map_vectors_to_states(state_vectors_df: pd.DataFrame, vector_to_label: dict) -> Tuple[List[str], dict]:
    """
    圧縮された状態ベクトル DataFrame の各行を、状態ラベルにマッピング
    
    Parameters:
    -----------
    state_vectors_df : pd.DataFrame
        圧縮後の状態ベクトル（行=時刻、列=センサー）
    vector_to_label : dict
        状態ベクトル(タプル) -> ラベルのマッピング
    
    Returns:
    --------
    Tuple[List[str], dict]
        (state_labels, state_labels_dict)
        - state_labels: 各行のラベル（"状態1" など）
        - state_labels_dict: デバッグ情報
    """
    state_labels = []
    state_labels_dict = {}
    
    for idx, row in state_vectors_df.iterrows():
        vector = tuple(int(v) for v in row.values)
        
        if vector in vector_to_label:
            label = vector_to_label[vector]
        else:
            label = "その他"
        
        state_labels.append(label)
        if label not in state_labels_dict:
            state_labels_dict[label] = 0
        state_labels_dict[label] += 1
    
    return state_labels, state_labels_dict


def main() -> None:
    if LOG_DAYS <= 0:
        raise ValueError("LOG_DAYS must be >= 1")
    if RUNS <= 0:
        raise ValueError("RUNS must be >= 1")
    if MAX_RETRIES_PER_RUN <= 0:
        raise ValueError("MAX_RETRIES_PER_RUN must be >= 1")
    if MAX_ROWS < 0:
        raise ValueError("MAX_ROWS must be >= 0")

    # APIキーの準備
    load_dotenv(ENV_FILE_PATH)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(".env に GEMINI_API_KEY が未設定です。")

    # 入力ログに対して state_transition_visualizer の前処理を適用する
    # これにより 0/1 ベクトル化、チャタリング除去、状態区間圧縮が行われる
    csv_path = INPUT_CSV_PATH
    output_dir = OUTPUT_DIR

    # visualizer を初期化（experiment_config から設定を取得）
    visualizer = stv.StateTransitionVisualizer(
        n_representative_states=N_STATES,
        hamming_threshold=HAMMING_THRESHOLD,
        data_duration_days=LOG_DAYS
    )
    
    # load_data はイベント形式の DataFrame を返す
    events_df = visualizer.load_data(str(csv_path))
    
    # create_state_vectors で 1 秒解像度→スムージング→圧縮 を実行し、
    # self.state_vectors_df に圧縮後の時刻ごとの 0/1 ベクトルが入る
    state_vectors_df = visualizer.create_state_vectors(events_df)

    # state フォルダから対応する状態定義ファイルを読み込む
    effective_days = visualizer.effective_data_duration_days
    state_file = find_state_file(DATASET_NAME, N_STATES, HAMMING_THRESHOLD, effective_days)
    print(f"状態定義ファイルを読み込み中: {state_file}")
    
    state_label_to_vector, vector_to_label = load_state_definition(state_file)
    
    # 圧縮された状態ベクトル DataFrame を状態ラベルにマッピング
    state_labels_list, state_labels_count = map_vectors_to_states(state_vectors_df, vector_to_label)
    
    print(f"状態マッピング完了:")
    for label, count in sorted(state_labels_count.items()):
        print(f"  {label}: {count}回")

    # マッピング後の状態シーケンスをテキスト形式に変換
    # 出力形式: "タイムスタンプ<TAB>状態ラベル（例: 状態1）"
    lines = []
    for timestamp, state_label in zip(visualizer.state_vectors_df.index, state_labels_list):
        lines.append(f"{timestamp}\t{state_label}")
    
    log_text = "\n".join(lines)
    
    # MAX_ROWS が設定されていれば先頭からその行数だけ使用
    log_lines = lines
    if MAX_ROWS > 0 and len(lines) > MAX_ROWS:
        log_lines = lines[:MAX_ROWS]
        log_text = "\n".join(log_lines)
        truncated = True
    else:
        truncated = False
    
    prompt_log_lines = len(log_lines)

    # プロンプトを構築（N_STATES と STATE_TABLE を埋め込む）
    state_table_text = state_table_to_text(state_file)
    user_message = build_prompt(
        dataset_name=DATASET_NAME,
        days=LOG_DAYS,
        log_text=log_text,
        truncated=truncated
    ).replace("{N_STATES}", str(N_STATES)).replace("{STATE_TABLE}", state_table_text)
# print(user_message)
# 2010-11-06 23:40:04     状態1
# 2010-11-06 23:40:14     その他
    
    output_dir.mkdir(parents=True, exist_ok=True)

    backend_name = "unknown"
    metrics_rows: List[dict] = []
    for run_idx in range(1, RUNS + 1):
        output_path = output_dir / f"{run_idx}.json"
        if output_path.exists():
            print(f"Run {run_idx}: 出力が既に存在するためスキップします -> {output_path}")
            continue

        # Geminiに問い合わせ
        attempt = 0
        while True:
            try:
                llm_text, backend, usage, duration_sec = call_gemini(
                    api_key=api_key,
                    model_name=MODEL_NAME,
                    user_message=user_message,
                    temperature=TEMPERATURE,
                )

                if not llm_text:
                    raise RuntimeError("Geminiから空の応答が返されました。")

                # 応答をJSON配列として解釈し保存
                records = parse_pattern_records(llm_text)
                output_path.write_text(
                    json.dumps(records, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                metrics_rows.append(
                    {
                        "run": run_idx,
                        "model": MODEL_NAME,
                        "backend": backend,
                        "duration_sec": duration_sec,
                        "prompt_tokens": usage.get("prompt_tokens"),
                        "response_tokens": usage.get("response_tokens"),
                        "total_tokens": usage.get("total_tokens"),
                        "attempts": attempt + 1,
                    }
                )
                break
            except Exception as exc:
                attempt += 1
                print(f"Run {run_idx} failed (attempt {attempt}/{MAX_RETRIES_PER_RUN}): {exc}")
                if attempt >= MAX_RETRIES_PER_RUN:
                    print(f"Run {run_idx} exceeded max retries. Aborting.")
                    raise

        backend_name = backend
        print("=" * 80)
        print("LLM系列抽出（状態定義ファイル利用）")
        print("=" * 80)
        print(f"入力ファイル          : {csv_path}")
        print(f"対象日数              : {LOG_DAYS}")
        print(f"代表状態数            : {N_STATES}")
        print(f"ハミング距離閾値      : {HAMMING_THRESHOLD}")
        print(f"状態定義ファイル      : {state_file}")
        print(f"状態シーケンス長      : {len(state_labels_list)}")
        print(f"使用するシーケンス行数: {prompt_log_lines}")
        print(f"最大行数              : {MAX_ROWS}")
        print(f"モデル                : {MODEL_NAME}")
        print(f"利用SDK               : {backend}")
        print(f"出力ファイル          : {output_path}")
        print(f"抽出パターン数        : {len(records)}")
        print(f"実行回数              : {run_idx}/{RUNS}")
        print("=" * 80)

    # メトリクスをCSVに保存
    if metrics_rows:
        metrics_path = output_dir / f"llm_direct_metrics_{LOG_DAYS}days.csv"
        with open(metrics_path, "w", encoding="utf-8", newline="") as f:
            fieldnames = [
                "run",
                "model",
                "backend",
                "duration_sec",
                "prompt_tokens",
                "response_tokens",
                "total_tokens",
                "attempts",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(metrics_rows)
        print(f"トークン使用量と応答時間を保存しました: {metrics_path}")


if __name__ == "__main__":
    main()
