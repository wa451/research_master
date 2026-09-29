from __future__ import annotations

import json
import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.behavior_pattern_mining.evaluation.adl_interpretation_set import load_interpretation_patterns
from src.behavior_pattern_mining.evaluation.strict_ablation import (
    build_strict_prompt,
    completed_run_ids,
    load_strict_condition,
    normalize_strict_record,
    postprocess_strict_records,
)
from src.behavior_pattern_mining.llm.client import parse_pattern_records


STRICT_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_evaluation6_strict_ablation.py"
SPEC = importlib.util.spec_from_file_location("strict_generator", STRICT_SCRIPT)
assert SPEC and SPEC.loader
strict_generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(strict_generator)


class Evaluation6StrictAblationTests(unittest.TestCase):
    def test_strict_schema_survives_parser_and_normalizer(self) -> None:
        response = json.dumps([{
            "time_band": "Morning",
            "pattern_name": "Morning routine",
            "adl_sequence": ["Wake-up", "Hygiene", "Meal"],
            "rationale": "The resident moves from the bedroom to the bathroom and kitchen.",
            "state_sequence": ["State 1", "State 3", "State 5"],
        }])
        parsed = parse_pattern_records(response)
        self.assertEqual(parsed[0]["ADL系列ラベル"], ["Wake-up", "Hygiene", "Meal"])
        self.assertEqual(parsed[0]["解釈の根拠"], "The resident moves from the bedroom to the bathroom and kitchen.")
        normalized = normalize_strict_record(parsed[0], "Morning")
        self.assertIsNotNone(normalized)
        self.assertEqual(set(normalized["adl_sequence"]), {"Wake-up", "Hygiene", "Meal"})
        self.assertEqual(normalized["rationale"], "The resident moves from the bedroom to the bathroom and kitchen.")
        self.assertEqual(normalized["state_sequence"], ["State 1", "State 3", "State 5"])

    def test_legacy_adl_sequence_labels_remain_compatible(self) -> None:
        parsed = parse_pattern_records(json.dumps([{
            "pattern_name": "legacy", "adl_sequence_labels": ["Meal"],
            "reason": "observed", "state_sequence": ["State 1", "State 2"],
        }]))
        normalized = normalize_strict_record(parsed[0], "Morning")
        self.assertIsNotNone(normalized)
        self.assertEqual(normalized["adl_sequence"], ["Meal"])

    def test_both_methods_use_the_same_strict_schema(self) -> None:
        response = json.dumps([{
            "pattern_name": "pattern", "adl_sequence": ["Meal"],
            "rationale": "observed", "state_sequence": ["State 1", "State 2"],
        }])
        for method in ("proposed", "llm_only"):
            record = normalize_strict_record(parse_pattern_records(response)[0], "Morning")
            self.assertIsNotNone(record, method)
            self.assertEqual(
                set(record),
                {"time_band", "pattern_name", "adl_sequence", "rationale", "state_sequence"},
            )

    def test_resume_reuses_only_nonempty_validated_time_band(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            normalized_path = Path(tmpdir) / "normalized.json"
            normalized_path.write_text(json.dumps([{
                "time_band": "Morning", "pattern_name": "meal", "adl_sequence": ["Meal"],
                "rationale": "observed", "state_sequence": ["State 1", "State 2"],
            }]), encoding="utf-8")
            complete = {
                "status": "success",
                "normalized_output_path": str(normalized_path),
            }
            self.assertTrue(strict_generator._valid_completed_band(complete))
            normalized_path.write_text("[]", encoding="utf-8")
            self.assertFalse(strict_generator._valid_completed_band(complete))

    def test_one_prompt_template_has_no_proposed_only_threshold(self) -> None:
        prompt_path = Path(__file__).resolve().parents[1] / "prompts" / "evaluation6_strict_ablation_prompt.md"
        template = prompt_path.read_text(encoding="utf-8")
        self.assertNotIn("20%", template)
        proposed = build_strict_prompt(
            template, state_table="STATE_TABLE", time_band="Morning",
            representation_description="NETWORK", representation_data="NETWORK_DATA",
        )
        direct = build_strict_prompt(
            template, state_table="STATE_TABLE", time_band="Morning",
            representation_description="SERIES", representation_data="SERIES_DATA",
        )
        self.assertIn("Sleep", proposed)
        self.assertIn("Sleep", direct)
        self.assertIn('"adl_sequence"', proposed)
        self.assertIn('"adl_sequence"', direct)
        self.assertIn("NETWORK", proposed)
        self.assertIn("SERIES", direct)

    def test_common_postprocessor_normalizes_and_deduplicates_by_time_band_sequence(self) -> None:
        records = [
            {
                "time_band": "Morning", "pattern_name": "first", "adl_sequence": ["meal"],
                "rationale": "observed", "state_sequence": ["状態1", "状態2"],
            },
            {
                "time_band": "Morning", "pattern_name": "duplicate", "adl_sequence": ["Meal"],
                "rationale": "observed", "state_sequence": ["状態1", "状態2"],
            },
            {
                "time_band": "Night", "pattern_name": "same states other band", "adl_sequence": ["Meal"],
                "rationale": "observed", "state_sequence": ["状態1", "状態2"],
            },
            {
                "time_band": "Morning", "pattern_name": "invalid", "adl_sequence": ["Not an ADL"],
                "rationale": "observed", "state_sequence": ["状態1", "状態2"],
            },
        ]
        output = postprocess_strict_records(records)
        self.assertEqual(len(output), 2)
        self.assertEqual(output[0]["adl_sequence"], ["Meal"])
        self.assertEqual(set(output[0]), {"time_band", "pattern_name", "adl_sequence", "rationale", "state_sequence"})

    def test_strict_schema_is_read_by_the_existing_set_scorer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "strict.json"
            path.write_text(json.dumps([{
                "time_band": "Morning", "pattern_name": "meal", "adl_sequence": ["Meal"],
                "rationale": "observed", "state_sequence": ["状態1", "状態2"],
            }], ensure_ascii=False), encoding="utf-8")
            patterns = load_interpretation_patterns(path)
        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0].sequence, ("状態1", "状態2"))
        self.assertEqual(patterns[0].pred_adl_labels, ("Meal",))
        self.assertEqual(patterns[0].time_band, "Morning")

    def test_manifest_period_contract_rejects_test_leakage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            path.write_text(json.dumps({
                "K": 10, "h": 2, "sensor_representation": "individual", "generation_days": 14,
                "split_mode": "holdout", "validation_start_day": 15, "validation_end_day": 154,
                "test_start_day": 154, "test_end_day": 220,
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Day 1-14"):
                load_strict_condition(path)

    def test_common_completed_runs_are_the_intersection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            proposed = root / "proposed"
            direct = root / "direct"
            for directory, complete in ((proposed, {1, 2, 3}), (direct, {1, 3})):
                directory.mkdir()
                for run_id in complete:
                    (directory / f"run_{run_id}.json").write_text("[]", encoding="utf-8")
                    (directory / f"run_{run_id}_metadata.json").write_text(
                        json.dumps({"status": "complete"}), encoding="utf-8"
                    )
            self.assertEqual(completed_run_ids(proposed, range(1, 4)), [1, 2, 3])
            self.assertEqual(completed_run_ids(direct, range(1, 4)), [1, 3])
            self.assertEqual(
                sorted(set(completed_run_ids(proposed, range(1, 4))) & set(completed_run_ids(direct, range(1, 4)))),
                [1, 3],
            )

    def test_k_h_override_mismatch_fails_fast(self) -> None:
        condition = SimpleNamespace(n_states=10, hamming_threshold=2)
        args = SimpleNamespace(runs=5, n_states=15, hamming_threshold=None)
        with self.assertRaisesRegex(ValueError, "n-states"):
            strict_generator._validate_overrides(args, condition)

    def test_per_run_provenance_records_identical_shared_input_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            prompt = root / "prompt.md"
            state_table = root / "state.txt"
            source_log = root / "source.txt"
            manifest = root / "manifest.json"
            for path in (prompt, state_table, source_log):
                path.write_text("same input", encoding="utf-8")
            manifest.write_text(json.dumps({
                "generation_start": "2020-01-01 00:00:00",
                "generation_end": "2020-01-15 00:00:00",
            }), encoding="utf-8")
            provenance = strict_generator._provenance(
                condition=SimpleNamespace(
                    n_states=10, hamming_threshold=2, sensor_representation="individual",
                    generation_days=14, validation_start_day=15, validation_end_day=154,
                    test_start_day=155, test_end_day=220,
                ),
                identity=SimpleNamespace(provider="bedrock", model_id="model", result_name="model"),
                prompt_path=prompt, state_table=state_table, source_log=source_log, manifest_path=manifest,
            )
        self.assertEqual(provenance["n_states"], 10)
        self.assertEqual(provenance["hamming_threshold"], 2)
        self.assertEqual(provenance["prompt_sha256"], provenance["state_table_sha256"])
        self.assertEqual(provenance["test_start"], "2020-06-03 00:00:00")


if __name__ == "__main__":
    unittest.main()
