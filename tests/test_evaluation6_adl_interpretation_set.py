from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.behavior_pattern_mining.evaluation.adl import ADLInterval
from src.behavior_pattern_mining.evaluation.adl_interpretation_set import (
    ALLOWED_LABELS,
    InterpretationPattern,
    PatternOccurrenceInterval,
    evaluate_interpretation_sets,
    load_interpretation_patterns,
    normalize_adl_label,
    normalize_adl_label_set_value,
    normalize_label_set,
    normalize_prediction_labels,
    occurrence_is_within_time_band,
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
        self.assertEqual(normalize_adl_label("Toileting"), "Toileting")
        self.assertEqual(normalize_adl_label("Work"), "Work")
        for out_of_vocabulary_label in (
            "Meal Preparation",
            "Rest",
            "sleeping",
            "Leave Home",
            "Bathroom",
            "Cleaning",
            "bed_to_toilet",
        ):
            self.assertIsNone(normalize_adl_label(out_of_vocabulary_label))
            self.assertEqual(
                normalize_adl_label_set_value(out_of_vocabulary_label),
                (),
            )

    def test_unknown_label_is_not_converted_to_other(self) -> None:
        self.assertIsNone(normalize_adl_label("not a known label"))
        self.assertEqual(
            normalize_label_set(["Meal", "not a known label"]),
            ("Meal",),
        )
        normalized = normalize_prediction_labels(["Meal", "not a known label"])
        self.assertEqual(normalized.status, "unknown")
        self.assertEqual(normalized.normalized_labels, ("Meal",))
        self.assertEqual(normalized.unknown_labels, ("not a known label",))

    def test_noise_and_ambiguous_are_not_adl_categories(self) -> None:
        self.assertNotIn("Noise", ALLOWED_LABELS)
        self.assertNotIn("Ambiguous", ALLOWED_LABELS)
        self.assertEqual(normalize_prediction_labels(["Noise"]).status, "unknown")
        self.assertEqual(normalize_prediction_labels(["Ambiguous"]).status, "unknown")
        self.assertEqual(normalize_prediction_labels(["Bathroom"]).status, "unknown")

    def test_bed_to_toilet_overlap_maps_to_wakeup_and_toileting(self) -> None:
        patterns = [
            InterpretationPattern(
                pattern_id="P1",
                pattern_name="bed toilet",
                sequence=("状態1", "状態2"),
                pred_adl_labels=("Wake-up", "Toileting"),
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

        self.assertEqual(detail_rows[0]["true_adl_labels"], "Toileting;Wake-up")
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

    def test_loader_warns_for_legacy_noise_or_ambiguous_labels(self) -> None:
        payload = [
            {
                "pattern_id": "P001",
                "遷移のパターン": ["状態1", "状態2"],
                "ADL系列ラベル": ["Noise", "Ambiguous"],
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "patterns.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            with self.assertWarnsRegex(UserWarning, "unknown ADL label"):
                patterns = load_interpretation_patterns(path)

        self.assertEqual(patterns[0].prediction_status, "unknown")
        self.assertEqual(
            patterns[0].unknown_pred_adl_labels,
            ("Noise", "Ambiguous"),
        )

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
        self.assertEqual(by_id["P001_Morning"]["true_adl_labels"], "Toileting;Wake-up")
        self.assertEqual(by_id["P001_Midnight"]["time_band"], "Midnight")
        self.assertEqual(by_id["P001_Midnight"]["num_occurrences"], 1)
        self.assertEqual(by_id["P001_Midnight"]["true_adl_labels"], "Sleep")
        self.assertEqual(summary["num_patterns"], 2)

    def test_own_id_match_prevents_cross_id_sequence_duplication(self) -> None:
        patterns = [
            InterpretationPattern("P1", "one", ("A", "B"), ("Meal",)),
            InterpretationPattern("P2", "two", ("A", "B"), ("Meal",)),
        ]
        occurrences = [
            PatternOccurrenceInterval(
                "P1",
                "one",
                ("A", "B"),
                ts("2020-01-01 12:00:00"),
                ts("2020-01-01 12:01:00"),
            ),
            PatternOccurrenceInterval(
                "P2",
                "two",
                ("A", "B"),
                ts("2020-01-01 13:00:00"),
                ts("2020-01-01 13:01:00"),
            ),
        ]
        labels = [
            ADLInterval(
                ts("2020-01-01 12:00:00"),
                ts("2020-01-01 12:01:00"),
                "Eating",
                "Meal",
            ),
            ADLInterval(
                ts("2020-01-01 13:00:00"),
                ts("2020-01-01 13:01:00"),
                "Eating",
                "Meal",
            ),
        ]

        detail_rows, _ = evaluate_interpretation_sets(
            patterns,
            occurrences,
            labels,
            min_overlap_ratio_for_true_label=0.1,
        )

        self.assertEqual(
            {row["pattern_id"]: row["num_occurrences"] for row in detail_rows},
            {"P1": 1, "P2": 1},
        )

    def test_no_occurrence_and_no_adl_overlap_are_distinct(self) -> None:
        patterns = [
            InterpretationPattern("P1", "absent", ("A", "B"), ("Meal",)),
            InterpretationPattern("P2", "unlabeled", ("B", "C"), ("Meal",)),
        ]
        occurrences = [
            PatternOccurrenceInterval(
                "P2",
                "unlabeled",
                ("B", "C"),
                ts("2020-01-01 12:00:00"),
                ts("2020-01-01 12:05:00"),
            )
        ]

        rows, summary = evaluate_interpretation_sets(
            patterns,
            occurrences,
            [],
            min_overlap_ratio_for_true_label=0.1,
        )
        by_id = {row["pattern_id"]: row for row in rows}
        self.assertEqual(by_id["P1"]["occurrence_status"], "no_occurrence")
        self.assertEqual(by_id["P1"]["end_to_end_multilabel_f1"], 0.0)
        self.assertEqual(by_id["P2"]["occurrence_status"], "matched")
        self.assertEqual(by_id["P2"]["truth_status"], "no_adl_overlap")
        self.assertIsNone(by_id["P2"]["end_to_end_multilabel_f1"])
        self.assertEqual(summary["num_no_occurrence"], 1)
        self.assertEqual(summary["num_no_adl_overlap"], 1)
        self.assertEqual(summary["num_end_to_end_evaluable_patterns"], 1)

    def test_missing_prediction_is_recorded_and_scores_zero(self) -> None:
        normalized = normalize_prediction_labels(None)
        pattern = InterpretationPattern(
            "P1",
            "missing",
            ("A", "B"),
            normalized.normalized_labels,
            raw_pred_adl_labels=normalized.raw_labels,
            unknown_pred_adl_labels=normalized.unknown_labels,
            prediction_status=normalized.status,
        )
        occurrence = PatternOccurrenceInterval(
            "P1",
            "missing",
            ("A", "B"),
            ts("2020-01-01 12:00:00"),
            ts("2020-01-01 12:05:00"),
        )
        truth = ADLInterval(
            ts("2020-01-01 12:00:00"),
            ts("2020-01-01 12:05:00"),
            "Meal_Preparation",
            "Meal",
        )

        rows, summary = evaluate_interpretation_sets(
            [pattern],
            [occurrence],
            [truth],
            min_overlap_ratio_for_true_label=0.1,
        )
        row = rows[0]
        self.assertEqual(row["prediction_status"], "missing")
        self.assertEqual(row["is_metric_evaluable"], 1)
        self.assertEqual(row["conditional_exact_set_match"], 0)
        self.assertEqual(row["end_to_end_multilabel_f1"], 0.0)
        self.assertEqual(summary["num_prediction_missing"], 1)

    def test_unknown_prediction_preserves_raw_label_and_scores_zero(self) -> None:
        normalized = normalize_prediction_labels(["Meal", "Noise"])
        pattern = InterpretationPattern(
            "P1",
            "unknown",
            ("A", "B"),
            normalized.normalized_labels,
            raw_pred_adl_labels=normalized.raw_labels,
            unknown_pred_adl_labels=normalized.unknown_labels,
            prediction_status=normalized.status,
        )
        occurrence = PatternOccurrenceInterval(
            "P1",
            "unknown",
            ("A", "B"),
            ts("2020-01-01 12:00:00"),
            ts("2020-01-01 12:05:00"),
        )
        truth = ADLInterval(
            ts("2020-01-01 12:00:00"),
            ts("2020-01-01 12:05:00"),
            "Meal_Preparation",
            "Meal",
        )

        rows, _ = evaluate_interpretation_sets(
            [pattern],
            [occurrence],
            [truth],
            min_overlap_ratio_for_true_label=0.1,
        )
        self.assertEqual(rows[0]["prediction_status"], "unknown")
        self.assertEqual(rows[0]["unknown_pred_adl_labels"], "Noise")
        self.assertEqual(rows[0]["raw_pred_adl_labels"], "Meal;Noise")
        self.assertEqual(rows[0]["conditional_multilabel_f1"], 0.0)

    def test_time_band_half_open_boundary_rule(self) -> None:
        self.assertTrue(
            occurrence_is_within_time_band(
                ts("2020-01-01 09:59:00"),
                ts("2020-01-01 10:00:00"),
                "Morning",
            )
        )
        self.assertFalse(
            occurrence_is_within_time_band(
                ts("2020-01-01 09:59:00"),
                ts("2020-01-01 10:00:01"),
                "Morning",
            )
        )


if __name__ == "__main__":
    unittest.main()
