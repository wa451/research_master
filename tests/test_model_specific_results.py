"""Model-specific result routing and checkpoint isolation regression tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiment_config import ROOT_DIR, current_model_results_root
from scripts.evaluate_6_compare_adl_interpretation_set import default_output_root
from scripts.evaluate_7_parameter_sensitivity_adl_interpretation import default_pattern_path
from scripts.evaluate_8_frequency_stratified_adl_consistency import default_output_dir
from scripts.evaluate_adl_correspondence import default_paths as evaluation5_default_paths
from scripts.migrate_gemini_results import cleanup_verified_sources
from src.behavior_pattern_mining.llm.result_paths import (
    MODEL_RESULT_NAMES,
    ensure_model_artifact_directory,
    model_identity,
    resolve_model_identity,
)
from src.behavior_pattern_mining.llm.client import LLMRuntimeConfig
from src.behavior_pattern_mining.llm import pattern_extractor


MODEL_CASES = {
    "gemini-2.5-pro": "gemini-2.5-pro",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": "claude-haiku-4.5",
    "us.anthropic.claude-sonnet-4-6": "claude-sonnet-4.6",
    "us.openai.gpt-5.6-luna": "gpt-5.6-luna",
    "us.openai.gpt-5.6-terra": "gpt-5.6-terra",
    "us.openai.gpt-5.6-sol": "gpt-5.6-sol",
}


class ModelSpecificResultTests(unittest.TestCase):
    def test_all_requested_models_resolve_to_stable_directory_names(self) -> None:
        self.assertEqual(MODEL_RESULT_NAMES, MODEL_CASES)
        for model_id, result_name in MODEL_CASES.items():
            provider = "google_gemini" if model_id == "gemini-2.5-pro" else "bedrock"
            environment = {
                "LLM_PROVIDER": provider,
                "GEMINI_MODEL_NAME": model_id if provider == "google_gemini" else "",
                "BEDROCK_MODEL_ID": model_id if provider == "bedrock" else "",
            }
            with self.subTest(model_id=model_id), patch.dict(
                os.environ, environment, clear=False
            ):
                identity = resolve_model_identity(
                    default_provider="google_gemini",
                    gemini_model_name="gemini-2.5-pro",
                    bedrock_model_id="",
                )
                self.assertEqual(identity.result_name, result_name)
                self.assertEqual(
                    current_model_results_root(),
                    ROOT_DIR / "results" / result_name,
                )

    def test_evaluations_5_to_8_default_to_active_model_root(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "bedrock",
                "BEDROCK_MODEL_ID": "us.openai.gpt-5.6-sol",
            },
            clear=False,
        ):
            root = ROOT_DIR / "results/gpt-5.6-sol"
            self.assertTrue(
                evaluation5_default_paths()["proposed"].is_relative_to(root)
            )
            self.assertEqual(default_output_root(), root / "6_adl_match")
            self.assertTrue(default_pattern_path("aruba", 15, 0, 30).is_relative_to(root))
            self.assertEqual(
                default_output_dir("comparison_14days"),
                root / "8_vs_llm_own_id_fixed",
            )

    def test_proposed_extractor_routes_all_models_without_api_calls(self) -> None:
        for model_id, result_name in MODEL_CASES.items():
            provider = "google_gemini" if model_id == "gemini-2.5-pro" else "bedrock"
            config = LLMRuntimeConfig(
                provider=provider,
                model_name=model_id,
                temperature=0.2,
                api_key="unused" if provider == "google_gemini" else None,
                region_name="us-east-2" if provider == "bedrock" else None,
                max_tokens=8192 if provider == "bedrock" else None,
            )
            with self.subTest(model_id=model_id), patch.object(
                pattern_extractor, "load_dotenv"
            ), patch.object(
                pattern_extractor, "resolve_llm_runtime_config", return_value=config
            ), patch.object(
                pattern_extractor, "find_mode_json_files", return_value=[]
            ), patch.object(
                pattern_extractor,
                "plan_mode_llm_requests",
                return_value=([], 0),
            ) as planner, patch.object(
                pattern_extractor, "print_bedrock_cost_estimate"
            ):
                pattern_extractor.main(
                    days=14,
                    run_ids=[1],
                    n_states=15,
                    hamming_threshold=0,
                    estimate_cost=True,
                )
                routed = planner.call_args.args[2]
                self.assertEqual(
                    routed,
                    ROOT_DIR / "results" / result_name / "aruba_15_0_14days",
                )

    def test_model_binding_allows_same_model_and_rejects_other_model(self) -> None:
        gemini = model_identity("google_gemini", "gemini-2.5-pro")
        sol = model_identity("bedrock", "us.openai.gpt-5.6-sol")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifacts"
            ensure_model_artifact_directory(path, gemini, temperature=0.2)
            checkpoint = path / "llm_mode_records_run1/state_transition_Morning.json"
            checkpoint.parent.mkdir(parents=True)
            checkpoint.write_text("[]\n", encoding="utf-8")

            # Same-model resume preserves the existing checkpoint.
            ensure_model_artifact_directory(path, gemini, temperature=0.2)
            self.assertEqual(json.loads(checkpoint.read_text(encoding="utf-8")), [])

            # A different model cannot bind to or reuse the directory.
            with self.assertRaises(RuntimeError):
                ensure_model_artifact_directory(path, sol, temperature=0.2)

    def test_unbound_legacy_directory_requires_explicit_migration(self) -> None:
        gemini = model_identity("google_gemini", "gemini-2.5-pro")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy"
            path.mkdir()
            (path / "1.json").write_text("[]\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                ensure_model_artifact_directory(path, gemini)

    def test_cleanup_removes_only_hash_verified_legacy_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "output/legacy/llm.json"
            destination = root / "results/gemini-2.5-pro/legacy/llm.json"
            source.parent.mkdir(parents=True)
            destination.parent.mkdir(parents=True)
            source.write_text("same\n", encoding="utf-8")
            destination.write_text("same\n", encoding="utf-8")

            deleted, pruned = cleanup_verified_sources({source: destination}, root)

            self.assertEqual(deleted, [str(source)])
            self.assertFalse(source.exists())
            self.assertIn(str(root / "output/legacy"), pruned)
            self.assertTrue(destination.exists())

    def test_cleanup_rejects_a_mismatched_destination_without_deleting_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "output/legacy/llm.json"
            destination = root / "results/gemini-2.5-pro/legacy/llm.json"
            source.parent.mkdir(parents=True)
            destination.parent.mkdir(parents=True)
            source.write_text("source\n", encoding="utf-8")
            destination.write_text("different\n", encoding="utf-8")

            with self.assertRaises(RuntimeError):
                cleanup_verified_sources({source: destination}, root)
            self.assertTrue(source.exists())


if __name__ == "__main__":
    unittest.main()
