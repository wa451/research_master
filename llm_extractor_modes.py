"""
Gemini APIを用いて、時間帯モード別JSONからシーケンスを抽出し統合するスクリプト。

要件:
- state_transition_all.json と同じ階層にある mode JSON を対象にする
- 各 mode で抽出したシーケンスを統合する
- 完全一致の重複は1つにまとめる
- output フォルダに保存する
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Tuple

from experiment_config import DATASET_NAME, DAYS, HAMMING_THRESHOLD, N_STATES, ROOT_DIR
from utils.io_utils import write_csv
from utils.llm_utils import call_gemini, load_dotenv, parse_pattern_records


# =============================
# ユーザー設定（必要に応じて変更）
# =============================
# モードJSONが置かれているディレクトリを直接指定する
INPUT_MODES_DIR = ROOT_DIR / "picture" / f"{DATASET_NAME}_{N_STATES}_{HAMMING_THRESHOLD}_{DAYS}days"
MODE_FILE_GLOB = "state_transition_*.json"
ENV_FILE_PATH = ROOT_DIR / ".env"
MODEL_NAME = "gemini-2.5-pro"
TEMPERATURE = 0.2
# 実行回数（同じ入力で複数回生成）
RUNS = 1

# state_transition_visualizer.py の DEFAULT_TIME_MODES と同じ定義
DEFAULT_TIME_MODES = {
    "Morning": ("06:00", "10:00"),
    "Daytime": ("10:00", "18:00"),
    "Night": ("18:00", "24:00"),
    "Midnight": ("00:00", "06:00"),
}

PROMPT_TEMPLATE = """
あなたはスマートホームのデータサイエンティストであり、人間の行動分析のエキスパートです。
以下のJSONデータは、ある単身高齢者宅の長期間のセンサーログから抽出された時間帯（{MODE}）の「生活行動の状態遷移ネットワーク」です。

このデータをもとに、居住者の「主要な生活行動のパターン」を検出し、その意味を解釈してください。

## 入力データ
{JSON_DATA}

## データの前提知識
- `nodes` : 家の中の「状態（シーン）」。
- `active_sensors` : その状態で検知されている場所（部屋名や家具）。空配列 `[]` の場合は「どのセンサーも反応していない状態（就寝、外出など）」を意味します。
- `avg_duration_minutes_per_day` : 1日の中でその状態に滞在している平均合計時間（分）。
- `edges` : 状態間の遷移確率（`probability`）。

## 実行タスク
以下の3つのステップに沿って推論を行ってください。出力はStep 3のJSONのみを自動処理で読み取ります。

### Step 1: 主要な状態（ノード）の解釈（テキスト出力）
`avg_duration_minutes_per_day` が長い状態や、特徴的なセンサーの組み合わせを持つ状態をいくつかピックアップし、それぞれが「どのような生活行動」を表しているか短く推測してください。

### Step 2: 頻出する行動シーケンスの抽出（テキスト出力）
遷移確率がおおむね20%以上のエッジをたどり、居住者がどのような意図を持って行動しているか、ストーリーとして解釈できるシーケンスを抽出してください。
【厳守事項】
1. 各シーケンスの長さは必ず「2〜4個」の範囲内。
2. 無意味に同じ状態を連続させるもの（A→A）は除外。
3. 上記の条件を満たす意味のある行動ルートは、件数の制限を設けず、網羅的にすべて抽出してください。

### Step 3: JSONフォーマットでの最終出力（絶対厳守）
Step 2で抽出した「すべて」のパターンについて、後続のプログラムで読み込むためのJSON配列として出力してください。
必ずコードブロック（```json ... ```）を使用し、以下の3つのキーを持つオブジェクトの配列にしてください。

出力例：
```json
[
  {
    "パターン名": "深夜のトイレ往復行動",
    "解釈の根拠": "状態4（寝室/長時間滞在）から状態6（廊下）を経て、状態5（トイレ/短時間滞在）へ遷移し戻っているため。",
    "遷移のシーケンス": ["状態4", "状態6", "状態5", "状態1"]
  },
  {
    "パターン名": "起床から朝食までのルーチン",
    "解釈の根拠": "状態4（寝室/長時間滞在）から状態10（洗面所）を経て状態13（キッチン）へと遷移しているため。",
    "遷移のシーケンス": ["状態4", "状態10", "状態13"]
  }
]
""".strip()


def build_user_message(prompt_template: str, graph_json_text: str, mode_label: str) -> str:
    """プロンプト中の {JSON_DATA} / {MODE} を置換して返す。"""
    json_block = f"```json\n{graph_json_text.strip()}\n```"
    return (
        prompt_template
        .replace("{JSON_DATA}", json_block)
        .replace("{MODE}", mode_label)
    )


def mode_label_from_path(mode_path: Path) -> str:
    """state_transition_{MODE}.json の MODE から state_transition_visualizer.py 定義の時間帯ラベルを返す。"""
    mode_name = mode_path.stem.replace("state_transition_", "", 1)
    if mode_name in DEFAULT_TIME_MODES:
        start, end = DEFAULT_TIME_MODES[mode_name]
        return f"{mode_name}: {start}-{end}"
    return mode_name


def sort_mode_files(mode_files: List[Path]) -> List[Path]:
    """state_transition_visualizer.py のモード順 (Morning, Daytime, Night, Midnight) で並べる。"""
    mode_order = list(DEFAULT_TIME_MODES.keys())

    def mode_sort_key(path: Path) -> tuple[int, str]:
        mode_name = path.stem.replace("state_transition_", "", 1)
        if mode_name in mode_order:
            return (mode_order.index(mode_name), mode_name)
        # 既知モード以外は後ろに回して名前順
        return (len(mode_order), mode_name)

    return sorted(mode_files, key=mode_sort_key)


def find_mode_json_files(input_modes_dir: Path) -> List[Path]:
    """指定ディレクトリからモードJSONを列挙する。"""
    if not input_modes_dir.exists() or not input_modes_dir.is_dir():
        raise FileNotFoundError(f"モードJSONディレクトリが見つかりません: {input_modes_dir}")

    candidates = list(input_modes_dir.glob(MODE_FILE_GLOB))

    # all は除外して、時間帯モードのみ対象にする
    mode_files = [p for p in candidates if p.name != "state_transition_all.json"]
    mode_files = sort_mode_files(mode_files)

    if not mode_files:
        raise RuntimeError(f"モードJSONが見つかりません: {input_modes_dir}")

    return mode_files


def merge_unique_patterns(per_mode_records: List[List[dict]]) -> List[dict]:
    """シーケンス完全一致で重複を削除し、LLMのパターン名を保持して統合する。"""
    merged: List[dict] = []
    seen = set()

    for records in per_mode_records:
        for record in records:
            seq = record["遷移のシーケンス"]
            key = tuple(seq)
            if key in seen:
                continue
            seen.add(key)
            merged.append(record)

    return merged


def print_summary(
    mode_files: List[Path],
    per_mode_counts: List[Tuple[str, int]],
    merged: List[dict],
    backend: str,
    output_path: Path,
) -> None:
    """実行結果の概要を表示する。"""
    print("=" * 80)
    print("LLM系列抽出（モード別統合）")
    print("=" * 80)
    print(f"モデル                : {MODEL_NAME}")
    print(f"対象フォルダ            : {INPUT_MODES_DIR}")
    print(f"モードJSON数            : {len(mode_files)}")
    print("モード別生成件数          :")
    for mode_name, count in per_mode_counts:
        print(f"  - {mode_name}: {count}")
    print(f"ユニーク系列数          : {len(merged)}")
    print(f"最終統合件数            : {len(merged)}")
    print(f"利用SDK               : {backend}")
    print(f"出力ファイル            : {output_path}")
    print("=" * 80)


def extract_sequences_for_mode_file(mode_path: Path, api_key: str) -> Tuple[List[dict], str, dict, float]:
    """1つのモードJSONからLLMでシーケンスを抽出する。"""
    graph_json_text = mode_path.read_text(encoding="utf-8")
    mode_label = mode_label_from_path(mode_path)
    user_message = build_user_message(PROMPT_TEMPLATE, graph_json_text, mode_label)

    llm_text, backend, usage, duration_sec = call_gemini(
        api_key=api_key,
        model_name=MODEL_NAME,
        user_message=user_message,
        temperature=TEMPERATURE,
    )

    if not llm_text:
        raise RuntimeError(f"Geminiから空の応答が返されました: {mode_path.name}")

    return parse_pattern_records(llm_text), backend, usage, duration_sec


def compute_average_metrics(metrics_rows: List[dict]) -> List[dict]:
    """modeごとの平均メトリクスを計算する。"""
    buckets: dict[str, List[dict]] = {}
    for row in metrics_rows:
        buckets.setdefault(row["mode"], []).append(row)

    averages: List[dict] = []
    for mode, rows in buckets.items():
        def mean(values: List[float]) -> float:
            return sum(values) / len(values) if values else 0.0

        durations = [r["duration_sec"] for r in rows if r["duration_sec"] is not None]
        prompt_tokens = [r["prompt_tokens"] for r in rows if r["prompt_tokens"] is not None]
        response_tokens = [r["response_tokens"] for r in rows if r["response_tokens"] is not None]
        total_tokens = [r["total_tokens"] for r in rows if r["total_tokens"] is not None]

        averages.append(
            {
                "mode": mode,
                "avg_duration_sec": mean(durations),
                "avg_prompt_tokens": mean(prompt_tokens),
                "avg_response_tokens": mean(response_tokens),
                "avg_total_tokens": mean(total_tokens),
                "samples": len(rows),
            }
        )

    return averages


def main() -> None:
    # 1) APIキーの準備
    load_dotenv(ENV_FILE_PATH)

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(".env に GEMINI_API_KEY が未設定です。")

    # 2) 対象モードJSONを列挙
    mode_files = find_mode_json_files(INPUT_MODES_DIR)

    all_metrics_rows: List[dict] = []
    output_dir = (
        ROOT_DIR
        / "output"
        / f"{DATASET_NAME}_{N_STATES}_{HAMMING_THRESHOLD}_{DAYS}days"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    # 3) 同じ入力で複数回実行
    for run_idx in range(1, RUNS + 1):
        per_mode_records: List[List[dict]] = []
        per_mode_counts: List[Tuple[str, int]] = []
        backend_name = "unknown"
        metrics_rows: List[dict] = []

        print(f"\n=== Run {run_idx}/{RUNS} ===")
        for mode_path in mode_files:
            print(f"Processing mode file: {mode_path.name}")
            records, backend, usage, duration_sec = extract_sequences_for_mode_file(mode_path, api_key)
            backend_name = backend
            per_mode_records.append(records)

            mode_label = mode_label_from_path(mode_path)
            per_mode_counts.append((mode_label, len(records)))
            print(f"  -> generated sequences: {len(records)}")
            metrics_rows.append(
                {
                    "run": run_idx,
                    "mode": mode_label,
                    "mode_file": mode_path.name,
                    "model": MODEL_NAME,
                    "backend": backend,
                    "duration_sec": duration_sec,
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "response_tokens": usage.get("response_tokens"),
                    "total_tokens": usage.get("total_tokens"),
                }
            )

        # 4) モード間で完全一致の重複を排除して統合
        output_records = merge_unique_patterns(per_mode_records)

        # 5) output へ保存（run別）
        output_path = (
            output_dir
            / f"llm_sequences_modes_{N_STATES}_{HAMMING_THRESHOLD}_{DAYS}days_run{run_idx}.json"
        )
        output_path.write_text(
            json.dumps(output_records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if metrics_rows:
            metrics_path = (
                output_dir
                / f"llm_modes_metrics_{N_STATES}_{HAMMING_THRESHOLD}_{DAYS}days_run{run_idx}.csv"
            )
            write_csv(
                metrics_path,
                metrics_rows,
                fieldnames=[
                    "run",
                    "mode",
                    "mode_file",
                    "model",
                    "backend",
                    "duration_sec",
                    "prompt_tokens",
                    "response_tokens",
                    "total_tokens",
                ],
            )
            print(f"トークン使用量と応答時間を保存しました: {metrics_path}")

        all_metrics_rows.extend(metrics_rows)
        print_summary(mode_files, per_mode_counts, output_records, backend_name, output_path)

    # 6) 平均メトリクスを保存
    if all_metrics_rows:
        averages = compute_average_metrics(all_metrics_rows)
        avg_metrics_path = (
            output_dir
            / f"llm_modes_metrics_avg_{N_STATES}_{HAMMING_THRESHOLD}_{DAYS}days.csv"
        )
        write_csv(
            avg_metrics_path,
            averages,
            fieldnames=[
                "mode",
                "avg_duration_sec",
                "avg_prompt_tokens",
                "avg_response_tokens",
                "avg_total_tokens",
                "samples",
            ],
        )
        print(f"平均メトリクスを保存しました: {avg_metrics_path}")
    # print(json.dumps(output_records, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
