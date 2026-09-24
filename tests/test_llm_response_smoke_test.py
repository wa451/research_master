"""Regression tests for the one-request LLM response smoke test."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.command_builder import build_llm_response_smoke_test_step
from scripts import test_llm_pattern_response as smoke_test
from src.behavior_pattern_mining.llm.client import LLMRuntimeConfig


class LlmResponseSmokeTestTests(unittest.TestCase):
    def _input_dir(self, root: Path) -> Path:
        input_dir = root / "picture"
        input_dir.mkdir(parents=True)
        (input_dir / "state_transition_Morning.json").write_text(
            json.dumps({"nodes": [], "edges": []}), encoding="utf-8"
        )
        return input_dir

    def _config(self) -> LLMRuntimeConfig:
        return LLMRuntimeConfig(
            provider="bedrock",
            model_name="us.openai.gpt-5.6-sol",
            temperature=0.2,
            region_name="us-east-2",
            max_tokens=8192,
        )

    def test_success_sends_one_request_and_writes_validation_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_dir = self._input_dir(root)
            output_dir = root / "results" / "smoke"
            response = json.dumps(
                [
                    {
                        "パターン名": "朝の移動",
                        "ADL系列ラベル": ["Wake-up"],
                        "解釈の根拠": "朝の状態遷移です。",
                        "遷移のパターン": ["状態1", "状態2"],
                    }
                ],
                ensure_ascii=False,
            )
            with (
                patch.object(smoke_test, "load_dotenv"),
                patch.object(smoke_test, "resolve_llm_runtime_config", return_value=self._config()),
                patch.object(
                    smoke_test,
                    "call_llm",
                    return_value=(
                        response,
                        "aws-bedrock-converse",
                        {"prompt_tokens": 10, "response_tokens": 4, "total_tokens": 14},
                        0.3,
                    ),
                ) as call_llm,
            ):
                result = smoke_test.main(
                    [
                        "--allow-api",
                        "--input-modes-dir",
                        str(input_dir),
                        "--output-dir",
                        str(output_dir),
                    ]
                )

            self.assertEqual(result, 0)
            call_llm.assert_called_once()
            validation = json.loads((output_dir / "response_validation.json").read_text(encoding="utf-8"))
            self.assertEqual(validation["status"], "passed")
            self.assertEqual(validation["request_count"], 1)
            self.assertEqual(validation["retry_count"], 0)
            self.assertEqual(validation["parsed_record_count"], 1)
            self.assertTrue((output_dir / "raw_response.txt").exists())
            self.assertTrue((output_dir / "parsed_records.json").exists())

    def test_strict_format_failure_is_saved_without_a_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_dir = self._input_dir(root)
            output_dir = root / "results" / "smoke"
            with (
                patch.object(smoke_test, "load_dotenv"),
                patch.object(smoke_test, "resolve_llm_runtime_config", return_value=self._config()),
                patch.object(
                    smoke_test,
                    "call_llm",
                    return_value=("```json\n[]\n```", "aws-bedrock-converse", {}, 0.1),
                ) as call_llm,
            ):
                result = smoke_test.main(
                    [
                        "--allow-api",
                        "--input-modes-dir",
                        str(input_dir),
                        "--output-dir",
                        str(output_dir),
                    ]
                )

            self.assertEqual(result, 1)
            call_llm.assert_called_once()
            validation = json.loads((output_dir / "response_validation.json").read_text(encoding="utf-8"))
            self.assertEqual(validation["status"], "failed")
            self.assertEqual(validation["request_count"], 1)
            self.assertTrue(validation["strict_format_errors"])

    def test_dashboard_step_requires_explicit_api_opt_in_and_has_one_mode_input(self) -> None:
        settings = {
            "runner": "python",
            "dataset": "aruba",
            "smoke_test_days": 14,
            "smoke_test_n_states": 15,
            "smoke_test_hamming_threshold": 0,
            "smoke_test_mode": "Morning",
            "smoke_test_output_dir": "results/gpt-5.6-sol/api_smoke_tests/test",
            "smoke_test_allow_api": False,
        }
        blocked_step = build_llm_response_smoke_test_step(settings)
        self.assertNotIn("--allow-api", blocked_step.command)
        self.assertEqual(len(blocked_step.required_inputs), 1)
        self.assertTrue(blocked_step.required_inputs[0].name.endswith("Morning.json"))

        settings["smoke_test_allow_api"] = True
        allowed_step = build_llm_response_smoke_test_step(settings)
        self.assertEqual(allowed_step.command.count("--allow-api"), 1)
        self.assertEqual(allowed_step.command[allowed_step.command.index("--mode") + 1], "Morning")


if __name__ == "__main__":
    unittest.main()
