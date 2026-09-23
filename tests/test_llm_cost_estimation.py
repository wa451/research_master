from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, call, patch

from src.behavior_pattern_mining.llm.client import (
    build_bedrock_messages,
    count_bedrock_input_tokens,
)
from src.behavior_pattern_mining.llm.pattern_extractor import (
    mode_checkpoint_paths,
)
from src.behavior_pattern_mining.llm import pattern_extractor
from src.behavior_pattern_mining.llm.pricing import (
    PricingNotConfiguredError,
    build_cost_estimate,
    calculate_cost,
    format_cost_estimate,
)


MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"


class LlmCostEstimationTests(unittest.TestCase):
    def test_pricing_calculation_uses_input_and_output_rates(self) -> None:
        breakdown = calculate_cost(
            input_tokens=1_000_000,
            output_tokens=200_000,
            model_id=MODEL_ID,
        )

        self.assertEqual(breakdown.input_cost_usd, Decimal("1.00"))
        self.assertEqual(breakdown.output_cost_usd, Decimal("1.000"))
        self.assertEqual(breakdown.total_cost_usd, Decimal("2.000"))

    def test_unknown_model_does_not_reuse_another_models_price(self) -> None:
        with self.assertRaisesRegex(
            PricingNotConfiguredError,
            "Pricing information is not configured",
        ):
            calculate_cost(100, 100, "unknown.model-v1:0")

    def test_max_cost_uses_bedrock_max_tokens_per_request(self) -> None:
        estimate = build_cost_estimate(
            model_id=MODEL_ID,
            request_count=2,
            skipped_count=1,
            input_tokens=1_000,
            input_tokens_exact=True,
            input_token_method="Bedrock CountTokens",
            input_token_warning=None,
            estimated_output_tokens_per_request=500,
            max_output_tokens_per_request=8192,
        )

        self.assertEqual(estimate.estimated_output_tokens, 1_000)
        self.assertEqual(estimate.estimated_total_cost_usd, Decimal("0.00600"))
        self.assertEqual(estimate.max_output_tokens, 16_384)
        self.assertEqual(estimate.max_output_cost_usd, Decimal("0.0819200"))
        self.assertEqual(estimate.max_cost_estimate_usd, Decimal("0.0829200"))

    def test_count_tokens_success_uses_shared_messages_and_never_converse(self) -> None:
        bedrock_client = Mock()
        bedrock_client.count_tokens.side_effect = [
            {"inputTokens": 3},
            {"inputTokens": 4},
        ]
        boto3_module = Mock()
        boto3_module.client.return_value = bedrock_client

        with patch(
            "src.behavior_pattern_mining.llm.client.importlib.import_module",
            return_value=boto3_module,
        ):
            result = count_bedrock_input_tokens(
                model_name=MODEL_ID,
                user_messages=["first", "second"],
                region_name="us-east-2",
            )

        self.assertTrue(result.exact)
        self.assertEqual(result.total_tokens, 7)
        self.assertEqual(result.method, "Bedrock CountTokens")
        bedrock_client.count_tokens.assert_has_calls(
            [
                call(
                    modelId=MODEL_ID,
                    input={"converse": {"messages": build_bedrock_messages("first")}},
                ),
                call(
                    modelId=MODEL_ID,
                    input={"converse": {"messages": build_bedrock_messages("second")}},
                ),
            ]
        )
        bedrock_client.converse.assert_not_called()

    def test_count_tokens_deduplicates_only_identical_prompts(self) -> None:
        bedrock_client = Mock()
        bedrock_client.count_tokens.side_effect = [
            {"inputTokens": 3},
            {"inputTokens": 4},
        ]
        boto3_module = Mock()
        boto3_module.client.return_value = bedrock_client

        with patch(
            "src.behavior_pattern_mining.llm.client.importlib.import_module",
            return_value=boto3_module,
        ):
            result = count_bedrock_input_tokens(
                model_name=MODEL_ID,
                user_messages=["same", "same", "different"],
                region_name="us-east-2",
            )

        self.assertEqual(result.total_tokens, 10)
        self.assertEqual(bedrock_client.count_tokens.call_count, 2)
        bedrock_client.converse.assert_not_called()

    def test_count_tokens_failure_falls_back_and_marks_approximate(self) -> None:
        bedrock_client = Mock()
        bedrock_client.count_tokens.side_effect = RuntimeError("unsupported profile")
        boto3_module = Mock()
        boto3_module.client.return_value = bedrock_client

        with patch(
            "src.behavior_pattern_mining.llm.client.importlib.import_module",
            return_value=boto3_module,
        ):
            result = count_bedrock_input_tokens(
                model_name=MODEL_ID,
                user_messages=["first", "second"],
                region_name="us-east-2",
            )

        self.assertFalse(result.exact)
        self.assertGreater(result.total_tokens, 0)
        self.assertIn("approximate fallback", result.method)
        self.assertIn("unsupported profile", result.warning or "")
        self.assertEqual(bedrock_client.count_tokens.call_count, 1)
        bedrock_client.converse.assert_not_called()

        estimate = build_cost_estimate(
            model_id=MODEL_ID,
            request_count=2,
            skipped_count=0,
            input_tokens=result.total_tokens,
            input_tokens_exact=result.exact,
            input_token_method=result.method,
            input_token_warning=result.warning,
            estimated_output_tokens_per_request=None,
            max_output_tokens_per_request=8192,
        )
        report = format_cost_estimate(
            estimate,
            region_name="us-east-2",
            run_ids=[1, 2],
        )
        self.assertIn("Method: approximate fallback", report)
        self.assertIn("~", report)
        self.assertIn("Estimated output:\n  Not configured.", report)
        self.assertIn("No model inference was executed.", report)

    def test_estimate_mode_excludes_checkpoint_and_never_calls_converse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            input_dir = root / "picture"
            output_dir = root / "output"
            input_dir.mkdir()
            morning = input_dir / "state_transition_Morning.json"
            daytime = input_dir / "state_transition_Daytime.json"
            morning.write_text('{"mode":"Morning"}', encoding="utf-8")
            daytime.write_text('{"mode":"Daytime"}', encoding="utf-8")

            checkpoint = mode_checkpoint_paths(output_dir, 6, morning)["records"]
            checkpoint.parent.mkdir(parents=True)
            checkpoint.write_text(
                json.dumps(
                    [
                        {
                            "パターン名": "cached",
                            "ADL系列ラベル": ["Meal"],
                            "解釈の根拠": "cached",
                            "遷移のパターン": ["状態1", "状態2"],
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            bedrock_client = Mock()
            bedrock_client.count_tokens.return_value = {"inputTokens": 50}
            boto3_module = Mock()
            boto3_module.client.return_value = bedrock_client
            env = {
                "LLM_PROVIDER": "bedrock",
                "AWS_REGION": "us-east-2",
                "BEDROCK_MODEL_ID": MODEL_ID,
                "BEDROCK_MAX_TOKENS": "8192",
                "BEDROCK_ESTIMATED_OUTPUT_TOKENS": "1000",
            }

            stdout = io.StringIO()
            with patch.dict(os.environ, env, clear=True), patch(
                "src.behavior_pattern_mining.llm.client.importlib.import_module",
                return_value=boto3_module,
            ), redirect_stdout(stdout):
                pattern_extractor.main(
                    input_modes_dir=input_dir,
                    output_dir=output_dir,
                    run_ids=[6],
                    estimate_cost=True,
                )

            report = stdout.getvalue()
            self.assertIn("Requests to execute: 1", report)
            self.assertIn("Skipped by checkpoint: 1", report)
            self.assertIn("Estimated output cost: $0.0050", report)
            self.assertIn("No model inference was executed.", report)
            self.assertEqual(bedrock_client.count_tokens.call_count, 1)
            bedrock_client.converse.assert_not_called()
            self.assertFalse(
                (output_dir / "llm_sequences_modes_15_1_154days_6.json").exists()
            )


if __name__ == "__main__":
    unittest.main()
