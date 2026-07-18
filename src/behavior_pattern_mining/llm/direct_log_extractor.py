"""
代表状態抽出までを行ったセンサログを直接プロンプトに入れてパターンを抽出する。
"""
from __future__ import annotations

import csv
import json
import os
import tempfile
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
from src.behavior_pattern_mining.evaluation.adl import load_sensor_id_map
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
# 入力ログ。現在の評価ではラベル付きCASASを入力元にし、activity begin/endは使わずセンサーイベントのみを抽出する。
INPUT_LOG_PATH = ROOT_DIR / "new_labeled_data" / f"{DATASET_NAME}.txt"
SENSOR_MAP_PATH = ROOT_DIR / "configs" / "aruba_sensor_map.json"
# 出力ルート（評価6の30日条件では llm_direct_{K}_{H}_{DAYS}days 配下に保存する）
OUTPUT_DIR = ROOT_DIR / "output" / f"llm_direct_{LOG_DAYS}"

DIRECT_METRICS_FIELDNAMES = [
    "run",
    "model",
    "backend",
    "duration_sec",
    "prompt_tokens",
    "response_tokens",
    "total_tokens",
    "attempts",
]


def load_direct_metrics_by_run(path: Path) -> dict[int, dict]:
    """Load existing successful-run metrics so incremental runs do not erase them."""
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    by_run: dict[int, dict] = {}
    for row in rows:
        try:
            run = int(row.get("run", ""))
        except (TypeError, ValueError):
            continue
        by_run[run] = {field: row.get(field) for field in DIRECT_METRICS_FIELDNAMES}
    return by_run


def write_direct_metrics_by_run(path: Path, rows_by_run: dict[int, dict]) -> None:
    """Write one durable metrics row per successful direct-log run."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=DIRECT_METRICS_FIELDNAMES)
        writer.writeheader()
        for run in sorted(rows_by_run):
            writer.writerow(rows_by_run[run])

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

## ADL系列ラベル
各パターンには、解釈に対応するADLラベル集合を `ADL系列ラベル` として付けてください。
使用できるラベルは次の10種類だけです。

```text
Sleep
Wake-up
Meal
Relax
Outing
Hygiene
Housework
Other
Noise
Ambiguous
```

ラベルの意味:
- `Sleep`: 睡眠、就寝、ベッド上での長時間休息
- `Wake-up`: 起床直後の移動、朝の身支度、起床後の家内移動
- `Meal`: 食事準備、調理、食事、食後の片付け
- `Relax`: リビングや椅子での休息、くつろぎ
- `Outing`: 外出、帰宅、玄関を中心とする移動
- `Hygiene`: トイレ、浴室、洗面などの衛生行動
- `Housework`: 掃除、洗濯、片付け、換気などの家事
- `Other`: 上記に分類できるが明確でない行動
- `Noise`: 生活文脈を持たない無意味な往復やノイズ
- `Ambiguous`: 複数候補があり、ADLとして明確に判断できないもの

## 入力データ（状態の時系列）
{LOG_DATA}

## 実行タスク
以下の3つのステップに沿って内部で推論してください。
ただし、最終回答にはStep 1 / Step 2の説明文を一切出力しないでください。
最終回答はStep 3のJSON配列のみです。

### Step 1: 代表状態の解釈（内部推論のみ）
上記の状態定義表を参考に、各状態がどのような生活シーン（例: 就寝、起床、食事など）に対応するかを推測してください。
各状態のON/OFF状態の組み合わせから、居住者がどこで何をしているのかを推測します。

### Step 2: 頻出する行動パターンの抽出（内部推論のみ）
状態の時系列から、居住者がどのような意図を持って行動しているか、
ストーリーとして解釈できるパターンを抽出してください。
【厳守事項】
1. 各パターンの長さは必ず「2〜4個」の範囲内。
2. 同じ状態が連続するもの（状態1→状態1）は圧縮されているため除外。
3. 上記の条件を満たす意味のある行動ルートは、件数の制限を設けず、網羅的にすべて抽出してください。

### Step 3: JSONフォーマットでの最終出力（絶対厳守）
Step 2で抽出した「すべて」のパターンについて、後続のプログラムで読み込むためのJSON配列として出力してください。

出力ルール:
- 最終回答はJSON配列だけにしてください。
- Markdownのコードブロック（```json ... ```）は禁止です。
- JSON配列の前後に説明文、見出し、注釈、謝罪、箇条書き、自然言語を絶対に付けないでください。
- 各要素は必ず以下の4つのキーだけを持つJSONオブジェクトにしてください。
  - `パターン名`
  - `ADL系列ラベル`
  - `解釈の根拠`
  - `遷移のパターン`
- `ADL系列ラベル` は必ず文字列配列にしてください。単一ADLでも `["Sleep"]` のように配列にしてください。
- `ADL系列ラベル` には上記10種類の許可ラベル以外を入れないでください。
- `順序タイプ` や `ラベル信頼度` は出力しないでください。
- `遷移のパターン` は必ず文字列配列にしてください。例: `["状態4", "状態6"]`
- 末尾カンマ、コメント、未エスケープの改行、JSON以外の文字は禁止です。
- 抽出できるパターンがない場合も、空配列 `[]` だけを返してください。

出力例：
[
  {{
    "パターン名": "深夜のトイレ往復行動",
    "ADL系列ラベル": ["Sleep", "Hygiene"],
    "解釈の根拠": "就寝状態から廊下を経てトイレへ行き戻っているため。",
    "遷移のパターン": ["状態4", "状態6", "状態5", "状態1"]
  }},
  {{
    "パターン名": "起床から朝食までのルーチン",
    "ADL系列ラベル": ["Wake-up", "Meal"],
    "解釈の根拠": "寝室の反応から洗面所、キッチンへ移動しているため。",
    "遷移のパターン": ["状態4", "状態10", "状態13"]
  }}
]
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


def convert_labeled_casas_to_event_csv(
    labeled_casas_path: Path,
    output_csv_path: Path,
    sensor_map_path: Path,
) -> int:
    """Extract sensor events from labeled CASAS txt, dropping activity labels."""
    sensor_map = load_sensor_id_map(sensor_map_path if sensor_map_path.exists() else None)
    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    row_count = 0
    with labeled_casas_path.open("r", encoding="utf-8") as src:
        with output_csv_path.open("w", encoding="utf-8", newline="") as dst:
            writer = csv.writer(dst)
            for raw_line in src:
                parts = raw_line.strip().split()
                if len(parts) < 4:
                    continue
                value = parts[3].strip().upper()
                if value not in {"ON", "OFF", "OPEN", "CLOSE", "PRESENT", "ABSENT"}:
                    continue
                sensor = sensor_map.get(parts[2].strip(), parts[2].strip())
                writer.writerow([parts[0], parts[1], sensor, value])
                row_count += 1
    return row_count


def is_labeled_casas_path(path: Path) -> bool:
    return path.suffix.lower() == ".txt"


def records_have_adl_sequence_labels(records: list[dict]) -> bool:
    return all(
        isinstance(record.get("ADL系列ラベル"), list)
        and bool(record.get("ADL系列ラベル"))
        for record in records
    )


def output_has_adl_sequence_labels(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(payload, list) and records_have_adl_sequence_labels(payload)


def prepare_input_csv(input_path: Path) -> tuple[Path, tempfile.TemporaryDirectory | None, int | None]:
    """Return an event CSV path, converting labeled CASAS txt when needed."""
    if not input_path.exists():
        raise FileNotFoundError(f"Input log not found: {input_path}")
    if not is_labeled_casas_path(input_path):
        return input_path, None, None

    tmpdir = tempfile.TemporaryDirectory()
    converted_csv = Path(tmpdir.name) / f"{DATASET_NAME}.csv"
    event_count = convert_labeled_casas_to_event_csv(
        labeled_casas_path=input_path,
        output_csv_path=converted_csv,
        sensor_map_path=SENSOR_MAP_PATH,
    )
    return converted_csv, tmpdir, event_count


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


def main(
    log_days: int | None = None,
    state_days: int | None = None,
    output_dir: Path | None = None,
    runs: int | None = None,
    n_states: int | None = None,
    hamming_threshold: int | None = None,
) -> None:
    effective_log_days = log_days if log_days is not None else LOG_DAYS
    if effective_log_days <= 0:
        raise ValueError("log_days must be >= 1")
    if state_days is not None and state_days <= 0:
        raise ValueError("state_days must be >= 1")
    effective_runs = runs if runs is not None else RUNS
    if effective_runs <= 0:
        raise ValueError("runs must be >= 1")
    effective_n_states = n_states if n_states is not None else N_STATES
    if effective_n_states <= 0:
        raise ValueError("n_states must be >= 1")
    effective_hamming_threshold = (
        hamming_threshold if hamming_threshold is not None else HAMMING_THRESHOLD
    )
    if effective_hamming_threshold < 0:
        raise ValueError("hamming_threshold must be >= 0")
    if MAX_RETRIES_PER_RUN <= 0:
        raise ValueError("MAX_RETRIES_PER_RUN must be >= 1")
    if MAX_ROWS < 0:
        raise ValueError("MAX_ROWS must be >= 0")

    # APIキーの準備
    load_dotenv(ENV_FILE_PATH)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(".env に GEMINI_API_KEY が未設定です。")

    # 入力ログに対して state_transition_visualizer の前処理を適用する。
    # ラベル付きCASAS txtを指定した場合は activity begin/end を捨て、
    # センサーイベントだけを一時CSVへ変換してから既存処理に渡す。
    csv_path, input_tmpdir, converted_event_count = prepare_input_csv(INPUT_LOG_PATH)
    if output_dir is not None:
        effective_output_dir = output_dir
    elif effective_log_days != DAYS or n_states is not None or hamming_threshold is not None:
        effective_output_dir = (
            ROOT_DIR
            / "output"
            / f"llm_direct_{effective_n_states}_{effective_hamming_threshold}_{effective_log_days}days"
        )
    else:
        effective_output_dir = ROOT_DIR / "output" / f"llm_direct_{effective_log_days}"

    try:
        if converted_event_count is not None:
            print(
                f"ラベル付きCASASからセンサーイベントを抽出しました: "
                f"{converted_event_count} events -> {csv_path}"
            )

        # visualizer を初期化（experiment_config から設定を取得）
        visualizer = stv.StateTransitionVisualizer(
            n_representative_states=effective_n_states,
            hamming_threshold=effective_hamming_threshold,
            data_duration_days=effective_log_days
        )
    
        # load_data はイベント形式の DataFrame を返す
        events_df = visualizer.load_data(str(csv_path))
    
        # create_state_vectors で 1 秒解像度→スムージング→圧縮 を実行し、
        # self.state_vectors_df に圧縮後の時刻ごとの 0/1 ベクトルが入る
        state_vectors_df = visualizer.create_state_vectors(events_df)

        # state フォルダから対応する状態定義ファイルを読み込む
        effective_days = visualizer.effective_data_duration_days
        state_file_days = state_days if state_days is not None else effective_days
        state_file = find_state_file(
            DATASET_NAME,
            effective_n_states,
            effective_hamming_threshold,
            state_file_days,
        )
        print(f"状態定義ファイルを読み込み中: {state_file}")
    
        state_label_to_vector, vector_to_label = load_state_definition(state_file)
    
        # 圧縮された状態ベクトル DataFrame を状態ラベルにマッピング
        state_labels_list, state_labels_count = map_vectors_to_states(state_vectors_df, vector_to_label)
    
        print("状態マッピング完了:")
        for label, count in sorted(state_labels_count.items()):
            print(f"  {label}: {count}回")

        # マッピング後の状態パターンをテキスト形式に変換
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
            days=effective_log_days,
            log_text=log_text,
            truncated=truncated
        ).replace("{N_STATES}", str(effective_n_states)).replace("{STATE_TABLE}", state_table_text)
    
        effective_output_dir.mkdir(parents=True, exist_ok=True)

        backend_name = "unknown"
        metrics_path = effective_output_dir / f"llm_direct_metrics_{effective_log_days}days.csv"
        metrics_by_run = load_direct_metrics_by_run(metrics_path)
        for run_idx in range(1, effective_runs + 1):
            output_path = effective_output_dir / f"{run_idx}.json"
            if output_path.exists() and output_has_adl_sequence_labels(output_path):
                print(f"Run {run_idx}: ADL系列ラベル付き出力が既に存在するためスキップします -> {output_path}")
                continue
            if output_path.exists():
                print(f"Run {run_idx}: 既存出力にADL系列ラベルが無いため再生成します -> {output_path}")

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
                    if not records_have_adl_sequence_labels(records):
                        raise RuntimeError("LLM応答にADL系列ラベルが含まれていません。")
                    output_path.write_text(
                        json.dumps(records, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    metrics_by_run[run_idx] = {
                        "run": run_idx,
                        "model": MODEL_NAME,
                        "backend": backend,
                        "duration_sec": duration_sec,
                        "prompt_tokens": usage.get("prompt_tokens"),
                        "response_tokens": usage.get("response_tokens"),
                        "total_tokens": usage.get("total_tokens"),
                        "attempts": attempt + 1,
                    }
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
            print(f"入力ファイル          : {INPUT_LOG_PATH}")
            if converted_event_count is not None:
                print(f"一時イベントCSV       : {csv_path}")
            print(f"対象日数              : {effective_log_days}")
            print(f"代表状態数            : {effective_n_states}")
            print(f"ハミング距離閾値      : {effective_hamming_threshold}")
            print(f"状態定義ファイル      : {state_file}")
            print(f"状態定義日数          : {state_file_days}")
            print(f"状態パターン長      : {len(state_labels_list)}")
            print(f"使用するパターン行数: {prompt_log_lines}")
            print(f"最大行数              : {MAX_ROWS}")
            print(f"モデル                : {MODEL_NAME}")
            print(f"利用SDK               : {backend}")
            print(f"出力ファイル          : {output_path}")
            print(f"抽出パターン数        : {len(records)}")
            print(f"実行回数              : {run_idx}/{effective_runs}")
            print("=" * 80)

        # メトリクスをCSVに保存
        if metrics_by_run:
            write_direct_metrics_by_run(metrics_path, metrics_by_run)
            print(f"トークン使用量と応答時間を保存しました: {metrics_path}")
    finally:
        if input_tmpdir is not None:
            input_tmpdir.cleanup()


if __name__ == "__main__":
    main()
