"""Provider-aware orchestration for inference-free LLM cost estimates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src.behavior_pattern_mining.llm.client import (
    LLMRuntimeConfig,
    count_bedrock_input_tokens,
)
from src.behavior_pattern_mining.llm.pricing import (
    CostEstimate,
    build_cost_estimate,
    format_cost_estimate,
    load_model_pricing,
)


@dataclass(frozen=True)
class BedrockTokenEstimate:
    """Inference-free token quantities before model pricing is applied."""

    request_count: int
    skipped_count: int
    input_tokens: int
    input_tokens_exact: bool
    input_token_method: str
    input_token_warning: str | None
    estimated_output_tokens_per_request: int | None
    estimated_output_tokens: int | None
    max_output_tokens_per_request: int
    max_output_tokens: int


def estimate_bedrock_tokens(
    *,
    llm_config: LLMRuntimeConfig,
    user_messages: Sequence[str],
    skipped_count: int,
) -> BedrockTokenEstimate:
    """Count one model's inputs and derive output quantities without inference."""
    if llm_config.provider != "bedrock":
        raise RuntimeError(
            "--estimate-cost currently supports LLM_PROVIDER=bedrock only."
        )
    token_count = count_bedrock_input_tokens(
        model_name=llm_config.model_name,
        user_messages=user_messages,
        region_name=llm_config.region_name or "",
    )
    request_count = len(user_messages)
    estimated_output_tokens = (
        None
        if llm_config.estimated_output_tokens is None
        else request_count * llm_config.estimated_output_tokens
    )
    max_output_tokens_per_request = llm_config.max_tokens or 0
    if max_output_tokens_per_request <= 0:
        raise ValueError("maximum output tokens must be positive")
    return BedrockTokenEstimate(
        request_count=request_count,
        skipped_count=skipped_count,
        input_tokens=token_count.total_tokens,
        input_tokens_exact=token_count.exact,
        input_token_method=token_count.method,
        input_token_warning=token_count.warning,
        estimated_output_tokens_per_request=llm_config.estimated_output_tokens,
        estimated_output_tokens=estimated_output_tokens,
        max_output_tokens_per_request=max_output_tokens_per_request,
        max_output_tokens=request_count * max_output_tokens_per_request,
    )


def estimate_bedrock_cost(
    *,
    llm_config: LLMRuntimeConfig,
    user_messages: Sequence[str],
    skipped_count: int,
) -> CostEstimate:
    """Count input tokens and price planned requests without model inference."""
    if llm_config.provider != "bedrock":
        raise RuntimeError(
            "--estimate-cost currently supports LLM_PROVIDER=bedrock only."
        )
    load_model_pricing(llm_config.model_name)
    token_estimate = estimate_bedrock_tokens(
        llm_config=llm_config,
        user_messages=user_messages,
        skipped_count=skipped_count,
    )
    return build_cost_estimate(
        model_id=llm_config.model_name,
        request_count=token_estimate.request_count,
        skipped_count=token_estimate.skipped_count,
        input_tokens=token_estimate.input_tokens,
        input_tokens_exact=token_estimate.input_tokens_exact,
        input_token_method=token_estimate.input_token_method,
        input_token_warning=token_estimate.input_token_warning,
        estimated_output_tokens_per_request=(
            token_estimate.estimated_output_tokens_per_request
        ),
        max_output_tokens_per_request=token_estimate.max_output_tokens_per_request,
    )


def print_bedrock_cost_estimate(
    *,
    llm_config: LLMRuntimeConfig,
    user_messages: Sequence[str],
    skipped_count: int,
    run_ids: Sequence[int],
) -> CostEstimate:
    """Print and return an inference-free Bedrock cost estimate."""
    estimate = estimate_bedrock_cost(
        llm_config=llm_config,
        user_messages=user_messages,
        skipped_count=skipped_count,
    )
    print(
        format_cost_estimate(
            estimate,
            region_name=llm_config.region_name or "",
            run_ids=run_ids,
        )
    )
    return estimate
