"""
Gemini APIを用いて、時間帯モード別JSONからパターンを抽出し統合するスクリプト。

要件:
- state_transition_all.json と同じ階層にある mode JSON を対象にする
- 各 mode で抽出したパターンを統合する
- 同じパターンは1つのグループにまとめ、時間帯別解釈を保持する
- output フォルダに保存する
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, List, Tuple

from experiment_config import (
    DATASET_NAME,
    DAYS,
    HAMMING_THRESHOLD,
    LLM_MODEL_NAME,
    LLM_RUNS_DEFAULT,
    LLM_TEMPERATURE,
    N_STATES,
    ROOT_DIR,
    TIME_MODES,
)
from src.behavior_pattern_mining.io.csv_io import write_csv
from src.behavior_pattern_mining.llm.client import call_gemini, load_dotenv, parse_pattern_records


# =============================
# ユーザー設定（必要に応じて変更）
# =============================
# モードJSONが置かれているディレクトリを直接指定する
INPUT_MODES_DIR = ROOT_DIR / "picture" / f"{DATASET_NAME}_{N_STATES}_{HAMMING_THRESHOLD}_{DAYS}days"
MODE_FILE_GLOB = "state_transition_*.json"
ENV_FILE_PATH = ROOT_DIR / ".env"
PROMPT_FILE_PATH = ROOT_DIR / "prompts" / "pattern_extraction_prompt.md"
MODEL_NAME = LLM_MODEL_NAME
TEMPERATURE = LLM_TEMPERATURE
# 実行回数（同じ入力で複数回生成）
RUNS = LLM_RUNS_DEFAULT
OUTPUT_FILE_PATH: Path | None = None
MAX_PARSE_RETRIES = 3
MODE_CHECKPOINT_DIR_PREFIX = "llm_mode_records_run"
FAILED_RESPONSE_DIR_NAME = "failed_responses"

# transition-network builder の DEFAULT_TIME_MODES と同じ定義
DEFAULT_TIME_MODES = TIME_MODES

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

## 実行タスク
以下の3つのステップに沿って内部で推論してください。
ただし、最終回答にはStep 1 / Step 2の説明文を一切出力しないでください。
最終回答はStep 3のJSON配列のみです。

### Step 1: 主要な状態（ノード）の解釈（内部推論のみ）
`avg_duration_minutes_per_day` が長い状態や、特徴的なセンサーの組み合わせを持つ状態をいくつかピックアップし、それぞれが「どのような生活行動」を表しているか短く推測してください。

### Step 2: 頻出する行動パターンの抽出（内部推論のみ）
遷移確率がおおむね20%以上のエッジをたどり、居住者がどのような意図を持って行動しているか、ストーリーとして解釈できるパターンを抽出してください。
【厳守事項】
1. 各パターンの長さは必ず「2〜4個」の範囲内。
2. 無意味に同じ状態を連続させるもの（A→A）は除外。
3. 上記の条件を満たす意味のある行動ルートは、件数の制限を設けず、網羅的にすべて抽出してください。

### Step 3: JSONフォーマットでの最終出力（絶対厳守）
Step 2で抽出した「すべて」のパターンについて、後続のプログラムで読み込むためのJSON配列として出力してください。

出力ルール:
- 最終回答はJSON配列だけにしてください。
- Markdownのコードブロック（```json ... ```）は禁止です。
- JSON配列の前後に説明文、見出し、注釈、謝罪、箇条書き、自然言語を絶対に付けないでください。
- トップレベルは必ずJSONオブジェクトではなくJSON配列 `[...]` にしてください。
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
  {
    "パターン名": "深夜のトイレ往復行動",
    "ADL系列ラベル": ["Sleep", "Hygiene"],
    "解釈の根拠": "状態4（寝室/長時間滞在）から状態6（廊下）を経て、状態5（トイレ/短時間滞在）へ遷移し戻っているため。",
    "遷移のパターン": ["状態4", "状態6", "状態5", "状態1"]
  },
  {
    "パターン名": "起床から朝食までのルーチン",
    "ADL系列ラベル": ["Wake-up", "Meal"],
    "解釈の根拠": "状態4（寝室/長時間滞在）から状態10（洗面所）を経て状態13（キッチン）へと遷移しているため。",
    "遷移のパターン": ["状態4", "状態10", "状態13"]
  }
]
""".strip()


def load_prompt_template(prompt_path: Path, fallback: str) -> str:
    """Read the external prompt template, falling back to the embedded copy."""
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8").strip()
    return fallback


PROMPT_TEMPLATE = load_prompt_template(PROMPT_FILE_PATH, PROMPT_TEMPLATE)


def build_user_message(prompt_template: str, graph_json_text: str, mode_label: str) -> str:
    """プロンプト中の {JSON_DATA} / {MODE} を置換して返す。"""
    json_block = f"```json\n{graph_json_text.strip()}\n```"
    return (
        prompt_template
        .replace("{JSON_DATA}", json_block)
        .replace("{MODE}", mode_label)
    )


def mode_label_from_path(mode_path: Path) -> str:
    """state_transition_{MODE}.json の MODE から時間帯ラベルを返す。"""
    mode_name = mode_path.stem.replace("state_transition_", "", 1)
    if mode_name in DEFAULT_TIME_MODES:
        start, end = DEFAULT_TIME_MODES[mode_name]
        return f"{mode_name}: {start}-{end}"
    return mode_name


def sort_mode_files(mode_files: List[Path]) -> List[Path]:
    """設定済みのモード順 (Morning, Daytime, Night, Midnight) で並べる。"""
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


def write_json(path: Path, payload: Any) -> None:
    """Write JSON with UTF-8 and ensure the parent directory exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def checkpoint_dir_for_run(output_dir: Path, run_idx: int) -> Path:
    """Return the directory that stores per-mode successful LLM results."""
    return output_dir / f"{MODE_CHECKPOINT_DIR_PREFIX}{run_idx}"


def mode_checkpoint_paths(output_dir: Path, run_idx: int, mode_path: Path) -> dict[str, Path]:
    """Return checkpoint paths for one run/mode pair."""
    checkpoint_dir = checkpoint_dir_for_run(output_dir, run_idx)
    return {
        "records": checkpoint_dir / f"{mode_path.stem}.json",
        "raw": checkpoint_dir / f"{mode_path.stem}_raw.txt",
        "metrics": checkpoint_dir / f"{mode_path.stem}_metrics.json",
    }


def failed_response_path(output_dir: Path, run_idx: int, mode_path: Path, attempt: int) -> Path:
    """Return the raw-response path for a failed parsing attempt."""
    return (
        output_dir
        / FAILED_RESPONSE_DIR_NAME
        / f"run{run_idx}_{mode_path.stem}_attempt{attempt}.txt"
    )


def load_checkpoint_records(path: Path) -> List[dict]:
    """Load per-mode checkpoint records produced by a previous successful run."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise RuntimeError(f"チェックポイントの形式が不正です: {path}")
    return data


def load_checkpoint_metrics(path: Path) -> dict:
    """Load per-mode checkpoint metrics if they exist."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def records_have_adl_sequence_labels(records: List[dict]) -> bool:
    """Return True when every extracted pattern already has ADL interpretation labels."""
    return all(
        isinstance(record.get("ADL系列ラベル"), list)
        and bool(record.get("ADL系列ラベル"))
        for record in records
    )


def save_successful_mode_checkpoint(
    output_dir: Path,
    run_idx: int,
    mode_path: Path,
    records: List[dict],
    llm_text: str,
    backend: str,
    usage: dict,
    duration_sec: float,
    attempt: int,
) -> None:
    """Persist a successful mode result immediately for resume-safe execution."""
    paths = mode_checkpoint_paths(output_dir, run_idx, mode_path)
    write_json(paths["records"], records)
    paths["raw"].write_text(llm_text, encoding="utf-8")
    write_json(
        paths["metrics"],
        {
            "run": run_idx,
            "mode": mode_label_from_path(mode_path),
            "mode_file": mode_path.name,
            "model": MODEL_NAME,
            "backend": backend,
            "duration_sec": duration_sec,
            "usage": usage,
            "attempt": attempt,
            "status": "success",
        },
    )


def save_failed_response(
    output_dir: Path,
    run_idx: int,
    mode_path: Path,
    attempt: int,
    llm_text: str,
    error: Exception,
) -> Path:
    """Persist a raw LLM response that could not be parsed."""
    path = failed_response_path(output_dir, run_idx, mode_path, attempt)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f"mode_file: {mode_path.name}",
                f"run: {run_idx}",
                f"attempt: {attempt}",
                f"error: {error}",
                "",
                "raw_response:",
                llm_text,
            ]
        ),
        encoding="utf-8",
    )
    return path


def build_retry_message(original_message: str, error: Exception, attempt: int) -> str:
    """Append stricter JSON-only instructions after a parse failure."""
    return (
        original_message
        + "\n\n"
        + "重要: 前回の応答は後続プログラムでJSONとして解釈できませんでした。\n"
        + f"再試行 {attempt} 回目です。次の条件を必ず守ってください。\n"
        + "- 回答はJSON配列 `[...]` のみ。\n"
        + "- Markdownコードブロック、説明文、見出し、注釈は禁止。\n"
        + "- 各要素は `パターン名`, `ADL系列ラベル`, `解釈の根拠`, `遷移のパターン` の4キーのみ。\n"
        + "- `ADL系列ラベル` は許可ラベルだけを含む文字列配列。\n"
        + "- `遷移のパターン` は `状態1` のような文字列の配列。\n"
        + "- JSONとして不正な末尾カンマ、コメント、未エスケープ改行は禁止。\n"
        + f"- 前回のパースエラー: {error}\n"
    )


def mode_name_from_path(mode_path: Path) -> str:
    """Return the short time-band name from a state_transition_{MODE}.json path."""
    return mode_path.stem.replace("state_transition_", "", 1)


def merge_unique_patterns(per_mode_records: List[Tuple[str, List[dict]]]) -> List[dict]:
    """Group identical patterns while preserving per-time-band interpretations."""
    grouped_by_sequence: dict[tuple[str, ...], dict] = {}

    for time_band, records in per_mode_records:
        for record in records:
            seq = tuple(
                record.get("遷移のパターン")
                or record.get("遷移のシーケンス")
                or record.get("sequence")
                or []
            )
            if len(seq) < 2:
                continue
            group = grouped_by_sequence.setdefault(
                seq,
                {
                    "sequence": list(seq),
                    "time_band_interpretations": {},
                },
            )
            interpretations = group["time_band_interpretations"]
            # Same pattern + same time band is the only true duplicate.
            if time_band in interpretations:
                continue
            interpretations[time_band] = {
                "パターン名": record.get("パターン名", ""),
                "ADL系列ラベル": record.get("ADL系列ラベル", []),
                "解釈の根拠": record.get("解釈の根拠", ""),
            }

    merged: List[dict] = []
    for index, group in enumerate(grouped_by_sequence.values(), start=1):
        merged.append(
            {
                "pattern_id": f"P{index:03d}",
                "sequence": group["sequence"],
                "time_band_interpretations": group["time_band_interpretations"],
            }
        )
    return merged


def print_summary(
    mode_files: List[Path],
    per_mode_counts: List[Tuple[str, int]],
    merged: List[dict],
    backend: str,
    output_path: Path,
    input_modes_dir: Path,
) -> None:
    """実行結果の概要を表示する。"""
    print("=" * 80)
    print("LLMパターン抽出（モード別統合）")
    print("=" * 80)
    print(f"モデル                : {MODEL_NAME}")
    print(f"対象フォルダ            : {input_modes_dir}")
    print(f"モードJSON数            : {len(mode_files)}")
    print("モード別生成件数          :")
    for mode_name, count in per_mode_counts:
        print(f"  - {mode_name}: {count}")
    print(f"ユニークパターン数      : {len(merged)}")
    print(f"最終統合件数            : {len(merged)}")
    print(f"利用SDK               : {backend}")
    print(f"出力ファイル            : {output_path}")
    print("=" * 80)


def extract_sequences_for_mode_file(
    mode_path: Path,
    api_key: str,
    output_dir: Path,
    run_idx: int,
    max_parse_retries: int = MAX_PARSE_RETRIES,
) -> Tuple[List[dict], str, dict, float]:
    """1つのモードJSONからLLMでパターンを抽出する。"""
    graph_json_text = mode_path.read_text(encoding="utf-8")
    mode_label = mode_label_from_path(mode_path)
    user_message = build_user_message(PROMPT_TEMPLATE, graph_json_text, mode_label)
    last_error: Exception | None = None

    for attempt in range(1, max_parse_retries + 1):
        request_message = (
            user_message
            if attempt == 1
            else build_retry_message(user_message, last_error or RuntimeError("unknown"), attempt)
        )
        llm_text, backend, usage, duration_sec = call_gemini(
            api_key=api_key,
            model_name=MODEL_NAME,
            user_message=request_message,
            temperature=TEMPERATURE,
        )

        try:
            if not llm_text:
                raise RuntimeError(f"Geminiから空の応答が返されました: {mode_path.name}")
            records = parse_pattern_records(llm_text)
        except RuntimeError as err:
            last_error = err
            failed_path = save_failed_response(
                output_dir=output_dir,
                run_idx=run_idx,
                mode_path=mode_path,
                attempt=attempt,
                llm_text=llm_text,
                error=err,
            )
            print(f"  -> parse failed (attempt {attempt}/{max_parse_retries}): {failed_path}")
            if attempt == max_parse_retries:
                raise RuntimeError(
                    f"{mode_path.name} のLLM応答をJSON配列として解釈できませんでした。"
                    f"失敗応答を確認してください: {failed_path}"
                ) from err
            continue

        save_successful_mode_checkpoint(
            output_dir=output_dir,
            run_idx=run_idx,
            mode_path=mode_path,
            records=records,
            llm_text=llm_text,
            backend=backend,
            usage=usage,
            duration_sec=duration_sec,
            attempt=attempt,
        )
        return records, backend, usage, duration_sec

    raise RuntimeError(f"{mode_path.name} のLLM抽出に失敗しました。")


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


def output_path_for_run(
    output_dir: Path,
    run_idx: int,
    days: int = DAYS,
    n_states: int = N_STATES,
    hamming_threshold: int = HAMMING_THRESHOLD,
) -> Path:
    """Return the LLM output path for a run.

    The batch runner sets OUTPUT_FILE_PATH to the exact file it will later
    evaluate. Standalone runs use the same historical suffix style as
    compare: ..._{run_idx}.json.
    """
    if OUTPUT_FILE_PATH is not None:
        explicit_path = Path(OUTPUT_FILE_PATH)
        if RUNS == 1:
            return explicit_path
        return explicit_path.with_name(
            f"{explicit_path.stem}_{run_idx}{explicit_path.suffix}"
        )

    return output_dir / (
        f"llm_sequences_modes_{n_states}_{hamming_threshold}_{days}days_{run_idx}.json"
    )


def main(
    days: int | None = None,
    input_modes_dir: Path | None = None,
    output_dir: Path | None = None,
    runs: int | None = None,
    run_ids: list[int] | None = None,
    n_states: int | None = None,
    hamming_threshold: int | None = None,
) -> None:
    effective_days = days if days is not None else DAYS
    if effective_days <= 0:
        raise ValueError("days must be >= 1")
    effective_runs = runs if runs is not None else RUNS
    if effective_runs <= 0:
        raise ValueError("runs must be >= 1")
    effective_run_ids = list(run_ids) if run_ids is not None else list(range(1, effective_runs + 1))
    if not effective_run_ids or any(run_id < 1 for run_id in effective_run_ids):
        raise ValueError("run IDs must all be >= 1")
    if len(set(effective_run_ids)) != len(effective_run_ids):
        raise ValueError("run IDs must be unique")
    effective_n_states = n_states if n_states is not None else N_STATES
    if effective_n_states <= 0:
        raise ValueError("n_states must be >= 1")
    effective_hamming_threshold = (
        hamming_threshold if hamming_threshold is not None else HAMMING_THRESHOLD
    )
    if effective_hamming_threshold < 0:
        raise ValueError("hamming_threshold must be >= 0")

    # 1) APIキーの準備
    load_dotenv(ENV_FILE_PATH)

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(".env に GEMINI_API_KEY が未設定です。")

    # 2) 対象モードJSONを列挙
    effective_input_modes_dir = (
        input_modes_dir
        or ROOT_DIR
        / "picture"
        / f"{DATASET_NAME}_{effective_n_states}_{effective_hamming_threshold}_{effective_days}days"
    )
    mode_files = find_mode_json_files(effective_input_modes_dir)

    all_metrics_rows: List[dict] = []
    effective_output_dir = (
        output_dir
        or ROOT_DIR
        / "output"
        / f"{DATASET_NAME}_{effective_n_states}_{effective_hamming_threshold}_{effective_days}days"
    )
    effective_output_dir.mkdir(parents=True, exist_ok=True)

    # 3) 同じ入力で複数回実行
    for run_position, run_idx in enumerate(effective_run_ids, start=1):
        per_mode_records: List[Tuple[str, List[dict]]] = []
        per_mode_counts: List[Tuple[str, int]] = []
        backend_name = "unknown"
        metrics_rows: List[dict] = []

        print(f"\n=== Run {run_idx} ({run_position}/{len(effective_run_ids)}) ===")
        for mode_path in mode_files:
            print(f"Processing mode file: {mode_path.name}")
            checkpoint_paths = mode_checkpoint_paths(effective_output_dir, run_idx, mode_path)
            checkpoint_metrics = load_checkpoint_metrics(checkpoint_paths["metrics"])

            if checkpoint_paths["records"].exists():
                records = load_checkpoint_records(checkpoint_paths["records"])
                if records_have_adl_sequence_labels(records):
                    backend = str(checkpoint_metrics.get("backend") or "cached")
                    usage = checkpoint_metrics.get("usage")
                    if not isinstance(usage, dict):
                        usage = {}
                    duration_sec = checkpoint_metrics.get("duration_sec")
                    print(f"  -> skipped existing checkpoint: {checkpoint_paths['records']}")
                else:
                    print(f"  -> stale checkpoint without ADL labels, regenerating: {checkpoint_paths['records']}")
                    records, backend, usage, duration_sec = extract_sequences_for_mode_file(
                        mode_path=mode_path,
                        api_key=api_key,
                        output_dir=effective_output_dir,
                        run_idx=run_idx,
                    )
            else:
                records, backend, usage, duration_sec = extract_sequences_for_mode_file(
                    mode_path=mode_path,
                    api_key=api_key,
                    output_dir=effective_output_dir,
                    run_idx=run_idx,
                )

            backend_name = backend
            per_mode_records.append((mode_name_from_path(mode_path), records))

            mode_label = mode_label_from_path(mode_path)
            per_mode_counts.append((mode_label, len(records)))
            print(f"  -> generated patterns: {len(records)}")
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

        # 4) モード間で同じパターンをグループ化し、時間帯別解釈を保持
        output_records = merge_unique_patterns(per_mode_records)

        # 5) output へ保存（run別）
        output_path = output_path_for_run(
            effective_output_dir,
            run_idx,
            effective_days,
            effective_n_states,
            effective_hamming_threshold,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(output_records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if metrics_rows:
            metrics_path = (
                effective_output_dir
                / f"llm_modes_metrics_{effective_n_states}_{effective_hamming_threshold}_{effective_days}days_run{run_idx}.csv"
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
        print_summary(
            mode_files,
            per_mode_counts,
            output_records,
            backend_name,
            output_path,
            effective_input_modes_dir,
        )

    # 6) 平均メトリクスを保存
    if all_metrics_rows:
        averages = compute_average_metrics(all_metrics_rows)
        avg_metrics_path = (
            effective_output_dir
            / f"llm_modes_metrics_avg_{effective_n_states}_{effective_hamming_threshold}_{effective_days}days.csv"
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
