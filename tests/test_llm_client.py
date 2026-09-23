from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

from src.behavior_pattern_mining.llm.client import (
    call_bedrock,
    call_llm,
    resolve_llm_runtime_config,
)


class LlmClientTests(unittest.TestCase):
    def test_bedrock_settings_do_not_require_gemini_key(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "bedrock",
                "AWS_REGION": "us-east-2",
                "BEDROCK_MODEL_ID": "test.model-v1:0",
                "BEDROCK_MAX_TOKENS": "321",
                "BEDROCK_ESTIMATED_OUTPUT_TOKENS": "123",
            },
            clear=True,
        ):
            config = resolve_llm_runtime_config(
                default_provider="google_gemini",
                gemini_model_name="gemini-test",
                temperature=0.2,
                bedrock_region="us-west-2",
                bedrock_model_id="",
                bedrock_max_tokens=8192,
                bedrock_estimated_output_tokens=None,
            )

        self.assertEqual(config.provider, "bedrock")
        self.assertEqual(config.model_name, "test.model-v1:0")
        self.assertEqual(config.region_name, "us-east-2")
        self.assertEqual(config.max_tokens, 321)
        self.assertEqual(config.estimated_output_tokens, 123)
        self.assertIsNone(config.api_key)

    def test_existing_gemini_settings_remain_supported(self) -> None:
        with patch.dict(
            os.environ,
            {"LLM_PROVIDER": "google_gemini", "GEMINI_API_KEY": "test-key"},
            clear=True,
        ):
            config = resolve_llm_runtime_config(
                default_provider="google_gemini",
                gemini_model_name="gemini-test",
                temperature=0.2,
                bedrock_region="us-east-2",
                bedrock_model_id="",
                bedrock_max_tokens=8192,
                bedrock_estimated_output_tokens=None,
            )

        with patch(
            "src.behavior_pattern_mining.llm.client.call_gemini",
            return_value=("ok", "google-genai", {}, 0.1),
        ) as mocked:
            result = call_llm(config, "prompt")

        self.assertEqual(result[0], "ok")
        mocked.assert_called_once_with(
            api_key="test-key",
            model_name="gemini-test",
            user_message="prompt",
            temperature=0.2,
        )

    def test_bedrock_converse_response_uses_existing_text_and_usage_contract(self) -> None:
        bedrock_client = Mock()
        bedrock_client.converse.return_value = {
            "output": {
                "message": {
                    "content": [{"text": "first"}, {"text": "second"}],
                }
            },
            "usage": {
                "inputTokens": 10,
                "outputTokens": 4,
                "totalTokens": 14,
            },
        }
        boto3_module = Mock()
        boto3_module.client.return_value = bedrock_client

        with patch(
            "src.behavior_pattern_mining.llm.client.importlib.import_module",
            return_value=boto3_module,
        ):
            text, backend, usage, duration = call_bedrock(
                model_name="test.model-v1:0",
                user_message="prompt",
                temperature=0.2,
                region_name="us-east-2",
                max_tokens=512,
            )

        self.assertEqual(text, "first\nsecond")
        self.assertEqual(backend, "aws-bedrock-converse")
        self.assertEqual(
            usage,
            {"prompt_tokens": 10, "response_tokens": 4, "total_tokens": 14},
        )
        self.assertGreaterEqual(duration, 0.0)
        boto3_module.client.assert_called_once_with(
            "bedrock-runtime", region_name="us-east-2"
        )
        bedrock_client.converse.assert_called_once_with(
            modelId="test.model-v1:0",
            messages=[{"role": "user", "content": [{"text": "prompt"}]}],
            inferenceConfig={"maxTokens": 512, "temperature": 0.2},
        )

    def test_bedrock_missing_credentials_has_actionable_error(self) -> None:
        no_credentials_error = type("NoCredentialsError", (Exception,), {})
        bedrock_client = Mock()
        bedrock_client.converse.side_effect = no_credentials_error("missing")
        boto3_module = Mock()
        boto3_module.client.return_value = bedrock_client

        with patch(
            "src.behavior_pattern_mining.llm.client.importlib.import_module",
            return_value=boto3_module,
        ):
            with self.assertRaisesRegex(RuntimeError, "AWS認証情報"):
                call_bedrock(
                    model_name="test.model-v1:0",
                    user_message="prompt",
                    temperature=0.2,
                    region_name="us-east-2",
                    max_tokens=512,
                )

    def test_bedrock_rejects_unexpected_response_shape(self) -> None:
        bedrock_client = Mock()
        bedrock_client.converse.return_value = {"usage": {"totalTokens": 1}}
        boto3_module = Mock()
        boto3_module.client.return_value = bedrock_client

        with patch(
            "src.behavior_pattern_mining.llm.client.importlib.import_module",
            return_value=boto3_module,
        ):
            with self.assertRaisesRegex(RuntimeError, "output.message.content"):
                call_bedrock(
                    model_name="test.model-v1:0",
                    user_message="prompt",
                    temperature=0.2,
                    region_name="us-east-2",
                    max_tokens=512,
                )


if __name__ == "__main__":
    unittest.main()
