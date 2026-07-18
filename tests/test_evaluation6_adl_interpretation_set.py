from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.behavior_pattern_mining.evaluation.adl import ADLInterval
from src.behavior_pattern_mining.evaluation.adl_interpretation_set import (
    InterpretationPattern,
    PatternOccurrenceInterval,
    evaluate_interpretation_sets,
    load_interpretation_patterns,
    normalize_adl_label,
    normalize_adl_label_set_value,
    normalize_label_set,
    set_metrics,
)
from src.behavior_pattern_mining.evaluation.llm_usage import (
    load_direct_usage_by_run,
    load_proposed_run_usage,
    summarize_usage,
)


def ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


class Evaluation6ADLInterpretationSetTests(unittest.TestCase):
    def test_llm_usage_comparison_averages_run_totals_across_five_runs(self) -> None:
        fieldnames = [
            "run",
            "mode",
            "duration_sec",
            "prompt_tokens",
            "response_tokens",
            "total_tokens",
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            proposed_usage_rows = []
            for run in range(1, 6):
                path = root / f"llm_modes_metrics_15_1_14days_run{run}.csv"
                with path.open("w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for mode in ("Morning", "Daytime", "Night", "Midnight"):
                        writer.writerow(
                            {
                                "run": run,
                                "mode": mode,
                                "duration_sec": 1.0,
                                "prompt_tokens": 10,
                                "response_tokens": 2,
                                "total_tokens": 12,
                            }
                        )
                usage, reason = load_proposed_run_usage(path, run)
                self.assertIsNone(reason)
                self.assertIsNotNone(usage)
                proposed_usage_rows.append(usage)

            direct_path = root / "llm_direct_metrics_14days.csv"
            with direct_path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "run",
                        "duration_sec",
                        "prompt_tokens",
                        "response_tokens",
                        "total_tokens",
                    ],
                )
                writer.writeheader()
                for run in range(1, 6):
                    writer.writerow(
                        {
                            "run": run,
                            "duration_sec": 3.0,
                            "prompt_tokens": 100,
                            "response_tokens": 10,
                            "total_tokens": 110,
                        }
                    )

            direct_usage_rows, missing = load_direct_usage_by_run(direct_path, range(1, 6))

        self.assertEqual(missing, [])
        proposed_summary = summarize_usage("proposed", list(range(1, 6)), proposed_usage_rows)
        direct_summary = summarize_usage(
            "direct_log_baseline",
            list(range(1, 6)),
            direct_usage_rows,
        )

        self.assertEqual(proposed_summary["num_runs_with_complete_metrics"], 5)
        self.assertEqual(proposed_summary["avg_recorded_api_calls_per_run"], 4.0)
        self.assertEqual(proposed_summary["avg_api_response_duration_sec_per_run"], 4.0)
        self.assertEqual(proposed_summary["avg_total_tokens_per_run"], 48.0)
        self.assertEqual(direct_summary["num_runs_with_complete_metrics"], 5)
        self.assertEqual(direct_summary["avg_recorded_api_calls_per_run"], 1.0)
        self.assertEqual(direct_summary["avg_api_response_duration_sec_per_run"], 3.0)
        self.assertEqual(direct_summary["avg_total_tokens_per_run"], 110.0)

    def test_llm_usage_missing_run_is_not_replaced_with_zero(self) -> None:
        summary = summarize_usage(
            "proposed",
            [1, 2, 3, 4, 5],
            [
                {
                    "method": "proposed",
                    "run": 1,
                    "recorded_api_calls": 4,
                    "api_response_duration_sec": 8.0,
                    "prompt_tokens": 40.0,
                    "response_tokens": 4.0,
                    "total_tokens": 44.0,
                }
            ],
        )

        self.assertEqual(summary["num_runs_evaluated"], 5)
        self.assertEqual(summary["num_runs_with_complete_metrics"], 1)
        self.assertEqual(summary["avg_api_response_duration_sec_per_run"], 8.0)
        self.assertEqual(summary["avg_total_tokens_per_run"], 44.0)

    def test_exact_set_match_ignores_order(self) -> None:
        metrics = set_metrics(["Meal", "Relax"], ["Relax", "Meal"])

        self.assertEqual(metrics["exact_set_match"], 1)
        self.assertAlmostEqual(metrics["jaccard"], 1.0)

    def test_jaccard_for_partial_set_match(self) -> None:
        metrics = set_metrics(["Meal", "Relax"], ["Meal"])

        self.assertEqual(metrics["exact_set_match"], 0)
        self.assertAlmostEqual(metrics["jaccard"], 0.5)
        self.assertAlmostEqual(metrics["multilabel_precision"], 0.5)
        self.assertAlmostEqual(metrics["multilabel_recall"], 1.0)
        self.assertAlmostEqual(metrics["multilabel_f1"], 2 / 3)

    def test_true_labels_are_created_from_overlap_threshold(self) -> None:
        patterns = [
            InterpretationPattern(
                pattern_id="P1",
                pattern_name="meal relax",
                sequence=("状態1", "状態2"),
                pred_adl_labels=("Meal", "Relax"),
            )
        ]
        occurrences = [
            PatternOccurrenceInterval(
                pattern_id="P1",
                pattern_name="meal relax",
                sequence=("状態1", "状態2"),
                start_time=ts("2020-01-01 00:00:00"),
                end_time=ts("2020-01-01 00:10:00"),
            )
        ]
        labels = [
            ADLInterval(ts("2020-01-01 00:00:00"), ts("2020-01-01 00:06:00"), "Meal", "Meal"),
            ADLInterval(ts("2020-01-01 00:06:00"), ts("2020-01-01 00:09:00"), "Relax", "Relax"),
            ADLInterval(ts("2020-01-01 00:09:00"), ts("2020-01-01 00:10:00"), "Housework", "Housework"),
        ]

        detail_rows, _ = evaluate_interpretation_sets(
            patterns,
            occurrences,
            labels,
            min_overlap_ratio_for_true_label=0.2,
        )

        self.assertEqual(detail_rows[0]["true_adl_labels"], "Meal;Relax")
        self.assertEqual(detail_rows[0]["intersection_labels"], "Meal;Relax")

    def test_label_normalization_variants(self) -> None:
        self.assertEqual(normalize_adl_label("wake_up"), "Wake-up")
        self.assertEqual(normalize_adl_label("Meal Preparation"), "Meal")
        self.assertEqual(normalize_adl_label("Rest"), "Relax")
        self.assertEqual(normalize_adl_label("sleeping"), "Sleep")
        self.assertEqual(normalize_adl_label("Leave Home"), "Outing")
        self.assertEqual(normalize_adl_label("Bathroom"), "Hygiene")
        self.assertEqual(normalize_adl_label("Cleaning"), "Housework")
        self.assertEqual(normalize_adl_label_set_value("bed_to_toilet"), ("Wake-up", "Hygiene"))

    def test_unknown_label_defaults_to_other(self) -> None:
        self.assertEqual(normalize_adl_label("not a known label"), "Other")
        self.assertEqual(normalize_label_set(["Meal", "not a known label"]), ("Meal", "Other"))

    def test_bed_to_toilet_overlap_maps_to_wakeup_and_hygiene(self) -> None:
        patterns = [
            InterpretationPattern(
                pattern_id="P1",
                pattern_name="bed toilet",
                sequence=("状態1", "状態2"),
                pred_adl_labels=("Wake-up", "Hygiene"),
            )
        ]
        occurrences = [
            PatternOccurrenceInterval(
                pattern_id="P1",
                pattern_name="bed toilet",
                sequence=("状態1", "状態2"),
                start_time=ts("2020-01-01 00:00:00"),
                end_time=ts("2020-01-01 00:05:00"),
            )
        ]
        labels = [
            ADLInterval(
                ts("2020-01-01 00:00:00"),
                ts("2020-01-01 00:05:00"),
                "Bed_to_Toilet",
                "Wake-up",
            )
        ]

        detail_rows, _ = evaluate_interpretation_sets(
            patterns,
            occurrences,
            labels,
            min_overlap_ratio_for_true_label=0.1,
        )

        self.assertEqual(detail_rows[0]["true_adl_labels"], "Hygiene;Wake-up")
        self.assertEqual(detail_rows[0]["exact_set_match"], 1)

    def test_grouped_time_band_interpretations_expand_to_eval_records(self) -> None:
        payload = [
            {
                "pattern_id": "P001",
                "sequence": ["状態8", "状態13", "状態8"],
                "time_band_interpretations": {
                    "Morning": {
                        "パターン名": "朝の巡回",
                        "ADL系列ラベル": ["Wake-up", "Housework"],
                        "解釈の根拠": "...",
                    },
                    "Midnight": {
                        "パターン名": "深夜の移動",
                        "ADL系列ラベル": ["Hygiene", "Sleep"],
                        "解釈の根拠": "...",
                    },
                },
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "patterns.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            patterns = load_interpretation_patterns(path)

        self.assertEqual([pattern.pattern_id for pattern in patterns], ["P001_Morning", "P001_Midnight"])
        self.assertEqual([pattern.group_pattern_id for pattern in patterns], ["P001", "P001"])
        self.assertEqual([pattern.time_band for pattern in patterns], ["Morning", "Midnight"])

    def test_time_band_aware_evaluation_uses_only_matching_occurrences(self) -> None:
        patterns = [
            InterpretationPattern(
                pattern_id="P001_Morning",
                group_pattern_id="P001",
                pattern_name="morning",
                sequence=("状態8", "状態13", "状態8"),
                pred_adl_labels=("Wake-up",),
                time_band="Morning",
            ),
            InterpretationPattern(
                pattern_id="P001_Midnight",
                group_pattern_id="P001",
                pattern_name="midnight",
                sequence=("状態8", "状態13", "状態8"),
                pred_adl_labels=("Sleep",),
                time_band="Midnight",
            ),
        ]
        occurrences = [
            PatternOccurrenceInterval(
                pattern_id="P001",
                pattern_name="group",
                sequence=("状態8", "状態13", "状態8"),
                start_time=ts("2020-01-01 07:00:00"),
                end_time=ts("2020-01-01 07:10:00"),
            ),
            PatternOccurrenceInterval(
                pattern_id="P001",
                pattern_name="group",
                sequence=("状態8", "状態13", "状態8"),
                start_time=ts("2020-01-02 01:00:00"),
                end_time=ts("2020-01-02 01:10:00"),
            ),
        ]
        labels = [
            ADLInterval(ts("2020-01-01 07:00:00"), ts("2020-01-01 07:10:00"), "Bed_to_Toilet", "Wake-up"),
            ADLInterval(ts("2020-01-02 01:00:00"), ts("2020-01-02 01:10:00"), "Sleeping", "Sleep"),
        ]

        detail_rows, summary = evaluate_interpretation_sets(
            patterns,
            occurrences,
            labels,
            min_overlap_ratio_for_true_label=0.1,
        )

        by_id = {row["eval_pattern_id"]: row for row in detail_rows}
        self.assertEqual(by_id["P001_Morning"]["time_band"], "Morning")
        self.assertEqual(by_id["P001_Morning"]["num_occurrences"], 1)
        self.assertEqual(by_id["P001_Morning"]["true_adl_labels"], "Hygiene;Wake-up")
        self.assertEqual(by_id["P001_Midnight"]["time_band"], "Midnight")
        self.assertEqual(by_id["P001_Midnight"]["num_occurrences"], 1)
        self.assertEqual(by_id["P001_Midnight"]["true_adl_labels"], "Sleep")
        self.assertEqual(summary["num_patterns"], 2)


if __name__ == "__main__":
    unittest.main()
