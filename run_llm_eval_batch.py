"""
llm_extractor_modes.py と evaluate_metrics.py を複数回実行し、
評価指標を Excel 形式で保存する。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import time

import evaluate_metrics
import llm_extractor_modes
from openpyxl import Workbook

from experiment_config import DATASET_NAME, DAYS, HAMMING_THRESHOLD, N_STATES, ROOT_DIR


# 実行回数
RUNS = 5
# API負荷を下げたい場合の待機秒数
SLEEP_BETWEEN_RUNS_SEC = 0
# 1回の実行で失敗した場合の最大リトライ回数
MAX_RETRIES_PER_RUN = 3
# 出力先（Excel）
OUTPUT_XLSX_PATH = None


def main() -> None:
    # 出力フォルダ（今回の実行用）を作成
    batch_dir = (
        ROOT_DIR
        / "output"
        / f"{DATASET_NAME}_{N_STATES}_{HAMMING_THRESHOLD}_{DAYS}days"
    )
    batch_dir.mkdir(parents=True, exist_ok=True)

    # Excelの保存先を今回のフォルダに固定
    global OUTPUT_XLSX_PATH
    OUTPUT_XLSX_PATH = batch_dir / (
        "llm_eval_runs_"
        f"{N_STATES}_{HAMMING_THRESHOLD}_"
        f"{DAYS}days.xlsx"
    )

    # 既に完成した試行のrun_idxを検出して、実行開始位置を決める
    first_incomplete_run = RUNS + 1
    for run_idx in range(1, RUNS + 1):
        check_output_path = batch_dir / (
            "llm_sequences_modes_"
            f"{N_STATES}_{HAMMING_THRESHOLD}_"
            f"{DAYS}days_{run_idx}.json"
        )
        if not check_output_path.exists():
            first_incomplete_run = run_idx
            break
    
    if first_incomplete_run > 1:
        print(f"\n=== Resuming from run {first_incomplete_run} ===")
        print(f"Found existing outputs for runs 1-{first_incomplete_run - 1}")
    
    # 各試行の結果を保存する
    rows: list[list[str | int | float]] = []
    for run_idx in range(1, RUNS + 1):
        # 1) LLM抽出: 1回分の出力ファイル名を設定
        llm_output_path = batch_dir / (
            "llm_sequences_modes_"
            f"{N_STATES}_{HAMMING_THRESHOLD}_"
            f"{DAYS}days_{run_idx}.json"
        )
        
        # ファイルが既に存在する場合はLLM抽出をスキップ
        if llm_output_path.exists():
            print(f"\nRun {run_idx}: LLM output already exists, skipping extraction")
        else:
            # LLM抽出を実行
            print(f"\nRun {run_idx}: Starting LLM extraction...")
            llm_extractor_modes.OUTPUT_FILE_PATH = llm_output_path

            # 失敗した場合は同じ run_idx をやり直す
            attempt = 0
            while True:
                try:
                    llm_extractor_modes.main()
                    break
                except Exception as exc:
                    attempt += 1
                    print(
                        f"Run {run_idx} failed (attempt {attempt}/{MAX_RETRIES_PER_RUN}): {exc}"
                    )
                    if attempt >= MAX_RETRIES_PER_RUN:
                        print(f"Run {run_idx} exceeded max retries. Aborting.")
                        raise
                    if SLEEP_BETWEEN_RUNS_SEC > 0:
                        time.sleep(SLEEP_BETWEEN_RUNS_SEC)

        # 2) 評価レポートを書き出し（modes_only）
        report_path = batch_dir / (
            "evaluation_report_"
            f"{N_STATES}_{HAMMING_THRESHOLD}_"
            f"{DAYS}days_{run_idx}.txt"
        )
        print(f"Run {run_idx}: Evaluating metrics...")
        prob_result, state_result = evaluate_metrics.evaluate_modes_only(
            llm_output_path, report_path
        )

        rows.append(
            [
                run_idx,
                prob_result.precision,
                prob_result.recall,
                prob_result.f1,
                state_result.precision,
                state_result.recall,
                state_result.f1,
            ]
        )

        if SLEEP_BETWEEN_RUNS_SEC > 0:
            # API呼び出し間隔を空ける
            time.sleep(SLEEP_BETWEEN_RUNS_SEC)

    # 平均値を計算
    if rows:
        prob_precision_avg = sum(r[1] for r in rows) / len(rows)
        prob_recall_avg = sum(r[2] for r in rows) / len(rows)
        prob_f1_avg = sum(r[3] for r in rows) / len(rows)
        state_precision_avg = sum(r[4] for r in rows) / len(rows)
        state_recall_avg = sum(r[5] for r in rows) / len(rows)
        state_f1_avg = sum(r[6] for r in rows) / len(rows)
    else:
        prob_precision_avg = prob_recall_avg = prob_f1_avg = 0.0
        state_precision_avg = state_recall_avg = state_f1_avg = 0.0

    timestamp = datetime.now().isoformat(timespec="seconds")

    # Excelに書き込み
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "metrics"

    # ヘッダー
    sheet.append(
        [
            "run",
            "prob_precision",
            "prob_recall",
            "prob_f1",
            "state_precision",
            "state_recall",
            "state_f1",
        ]
    )
    # 各試行の結果
    for row in rows:
        sheet.append(row)
    # 平均行
    sheet.append(
        [
            "avg",
            prob_precision_avg,
            prob_recall_avg,
            prob_f1_avg,
            state_precision_avg,
            state_recall_avg,
            state_f1_avg,
        ]
    )
    # 生成日時
    sheet.append(["generated_at", timestamp])

    workbook.save(OUTPUT_XLSX_PATH)

    print(f"Saved metrics to: {OUTPUT_XLSX_PATH}")
    print(f"Batch outputs saved under: {batch_dir}")


if __name__ == "__main__":
    main()
