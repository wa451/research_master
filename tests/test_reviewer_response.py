import unittest

from src.behavior_pattern_mining.evaluation.reviewer_response import make_blind_sample, pattern_identity, reviewer_eval5_rows, strict_common_run_rows


class ReviewerResponseTests(unittest.TestCase):
    def test_pattern_identity_keeps_time_band(self):
        self.assertNotEqual(pattern_identity("Morning", ["状態1", "状態2"]), pattern_identity("Night", ["状態1", "状態2"]))

    def test_fragmentation_without_pairs_is_na(self):
        rows = reviewer_eval5_rows([{"method": "proposed", "run": "1", "evaluation_status": "evaluated", "fragmentation_candidate_status": "no_comparable", "is_fragmented": "0", "train_support": "1", "test_support": "1"}])
        self.assertEqual(rows[0]["fragmentation_status"], "N/A")
        self.assertIsNone(rows[0]["fragmentation_rate"])

    def test_strict_requires_common_runs(self):
        rows = strict_common_run_rows([
            {"run": "1", "method": "proposed_strict", "mean_multilabel_precision": "1", "mean_multilabel_recall": "1", "mean_multilabel_f1": "1", "mean_jaccard": "1", "mean_exact_set_match": "1"},
            {"run": "1", "method": "llm_only_strict", "mean_multilabel_precision": "0.5", "mean_multilabel_recall": "0.5", "mean_multilabel_f1": "0.5", "mean_jaccard": "0.5", "mean_exact_set_match": "0.5"},
            {"run": "2", "method": "proposed_strict", "mean_multilabel_precision": "1", "mean_multilabel_recall": "1", "mean_multilabel_f1": "1", "mean_jaccard": "1", "mean_exact_set_match": "1"},
        ])
        self.assertEqual([row["run"] for row in rows], [1])
        self.assertEqual(rows[0]["delta_f1"], 0.5)

    def test_blind_sample_hides_method_and_run(self):
        records = [{"internal_method": "proposed", "internal_run": 1, "internal_index": 1, "time_band": "Morning", "state_sequence": "状態1 -> 状態2", "sensor_state_context": "状態1: S1", "pattern_name": "name", "adl_labels": "Meal", "rationale": "because"}]
        items, key = make_blind_sample(records, count=1, seed=1)
        self.assertEqual(items[0]["anonymous_id"], "HE001")
        self.assertNotIn("internal_method", items[0])
        self.assertEqual(key[0]["method"], "proposed")
