"""Pure pricing helpers and human-readable preflight cost reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Optional, Sequence


ROOT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_PRICING_PATH = ROOT_DIR / "configs" / "llm_pricing.json"
TOKENS_PER_MILLION = Decimal("1000000")


class PricingNotConfiguredError(RuntimeError):
    """Raised when no exact pricing entry exists for a requested model ID."""


@dataclass(frozen=True)
class ModelPricing:
    model_id: str
    input_usd_per_1m_tokens: Decimal
    output_usd_per_1m_tokens: Decimal
    note: str = ""


@dataclass(frozen=True)
class CostBreakdown:
    input_tokens: int
    output_tokens: int
    input_cost_usd: Decimal
    output_cost_usd: Decimal
    total_cost_usd: Decimal


@dataclass(frozen=True)
class CostEstimate:
    pricing: ModelPricing
    request_count: int
    skipped_count: int
    input_tokens: int
    input_tokens_exact: bool
    input_token_method: str
    input_token_warning: Optional[str]
    input_cost_usd: Decimal
    estimated_output_tokens_per_request: Optional[int]
    estimated_output_tokens: Optional[int]
    estimated_output_cost_usd: Optional[Decimal]
    estimated_total_cost_usd: Optional[Decimal]
    max_output_tokens_per_request: int
    max_output_tokens: int
    max_output_cost_usd: Decimal
    max_cost_estimate_usd: Decimal


def load_model_pricing(
    model_id: str,
    pricing_path: Path = DEFAULT_PRICING_PATH,
) -> ModelPricing:
    """Load the exact Bedrock model price; never substitute another model."""
    payload = json.loads(pricing_path.read_text(encoding="utf-8"))
    bedrock_prices = payload.get("bedrock") if isinstance(payload, dict) else None
    entry = bedrock_prices.get(model_id) if isinstance(bedrock_prices, dict) else None
    if not isinstance(entry, dict):
        raise PricingNotConfiguredError(
            f"Pricing information is not configured for this model: {model_id}"
        )

    try:
        input_price = Decimal(str(entry["input_usd_per_1m_tokens"]))
        output_price = Decimal(str(entry["output_usd_per_1m_tokens"]))
    except (KeyError, InvalidOperation, ValueError) as exc:
        raise RuntimeError(
            f"Pricing configuration is invalid for model: {model_id}"
        ) from exc
    if input_price < 0 or output_price < 0:
        raise RuntimeError(f"Pricing values must be non-negative for model: {model_id}")

    return ModelPricing(
        model_id=model_id,
        input_usd_per_1m_tokens=input_price,
        output_usd_per_1m_tokens=output_price,
        note=str(entry.get("note") or ""),
    )


def calculate_token_cost(
    input_tokens: int,
    output_tokens: int,
    pricing: ModelPricing,
) -> CostBreakdown:
    """Calculate token charges with Decimal arithmetic."""
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("token counts must be non-negative")
    input_cost = Decimal(input_tokens) / TOKENS_PER_MILLION * pricing.input_usd_per_1m_tokens
    output_cost = Decimal(output_tokens) / TOKENS_PER_MILLION * pricing.output_usd_per_1m_tokens
    return CostBreakdown(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        input_cost_usd=input_cost,
        output_cost_usd=output_cost,
        total_cost_usd=input_cost + output_cost,
    )


def calculate_cost(
    input_tokens: int,
    output_tokens: int,
    model_id: str,
    pricing_path: Path = DEFAULT_PRICING_PATH,
) -> CostBreakdown:
    """Load model pricing and calculate a reusable pre/post-execution cost."""
    return calculate_token_cost(
        input_tokens,
        output_tokens,
        load_model_pricing(model_id, pricing_path),
    )


def build_cost_estimate(
    *,
    model_id: str,
    request_count: int,
    skipped_count: int,
    input_tokens: int,
    input_tokens_exact: bool,
    input_token_method: str,
    input_token_warning: Optional[str],
    estimated_output_tokens_per_request: Optional[int],
    max_output_tokens_per_request: int,
    pricing_path: Path = DEFAULT_PRICING_PATH,
) -> CostEstimate:
    """Build expected and maximum-output estimates from one shared price."""
    if request_count < 0 or skipped_count < 0:
        raise ValueError("request counts must be non-negative")
    if estimated_output_tokens_per_request is not None and estimated_output_tokens_per_request < 0:
        raise ValueError("estimated output tokens must be non-negative")
    if max_output_tokens_per_request <= 0:
        raise ValueError("maximum output tokens must be positive")

    pricing = load_model_pricing(model_id, pricing_path)
    input_breakdown = calculate_token_cost(input_tokens, 0, pricing)
    max_output_tokens = request_count * max_output_tokens_per_request
    max_breakdown = calculate_token_cost(input_tokens, max_output_tokens, pricing)

    estimated_output_tokens: Optional[int] = None
    estimated_output_cost: Optional[Decimal] = None
    estimated_total_cost: Optional[Decimal] = None
    if estimated_output_tokens_per_request is not None:
        estimated_output_tokens = request_count * estimated_output_tokens_per_request
        estimated_breakdown = calculate_token_cost(
            input_tokens,
            estimated_output_tokens,
            pricing,
        )
        estimated_output_cost = estimated_breakdown.output_cost_usd
        estimated_total_cost = estimated_breakdown.total_cost_usd

    return CostEstimate(
        pricing=pricing,
        request_count=request_count,
        skipped_count=skipped_count,
        input_tokens=input_tokens,
        input_tokens_exact=input_tokens_exact,
        input_token_method=input_token_method,
        input_token_warning=input_token_warning,
        input_cost_usd=input_breakdown.input_cost_usd,
        estimated_output_tokens_per_request=estimated_output_tokens_per_request,
        estimated_output_tokens=estimated_output_tokens,
        estimated_output_cost_usd=estimated_output_cost,
        estimated_total_cost_usd=estimated_total_cost,
        max_output_tokens_per_request=max_output_tokens_per_request,
        max_output_tokens=max_output_tokens,
        max_output_cost_usd=max_breakdown.output_cost_usd,
        max_cost_estimate_usd=max_breakdown.total_cost_usd,
    )


def _format_usd(value: Decimal) -> str:
    return f"${value.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP):,.4f}"


def format_cost_estimate(
    estimate: CostEstimate,
    *,
    region_name: str,
    run_ids: Sequence[int],
) -> str:
    """Render exact and approximate quantities without conflating them."""
    token_prefix = "" if estimate.input_tokens_exact else "~"
    run_text = ", ".join(str(run_id) for run_id in run_ids)
    lines = [
        "=== LLM Cost Estimate ===",
        "",
        "Provider: AWS Bedrock",
        f"Model: {estimate.pricing.model_id}",
        f"Region: {region_name}",
        f"Run IDs: {run_text}",
        "",
        f"Requests to execute: {estimate.request_count:,}",
        f"Skipped by checkpoint: {estimate.skipped_count:,}",
        "",
        "Input token count:",
        f"  {token_prefix}{estimate.input_tokens:,} tokens",
        f"  Method: {estimate.input_token_method}",
        "",
        "Input price:",
        f"  ${estimate.pricing.input_usd_per_1m_tokens:.2f} / 1M tokens",
        "",
        "Output price:",
        f"  ${estimate.pricing.output_usd_per_1m_tokens:.2f} / 1M tokens",
        "",
        "Estimated input cost:",
        f"  {_format_usd(estimate.input_cost_usd)}",
        "",
        "Estimated output:",
    ]
    if estimate.estimated_output_tokens_per_request is None:
        lines.extend(
            [
                "  Not configured.",
                "  Set BEDROCK_ESTIMATED_OUTPUT_TOKENS or llm.bedrock.estimated_output_tokens.",
                "",
                "Estimated total:",
                "  Not available without an estimated output-token setting.",
            ]
        )
    else:
        lines.extend(
            [
                f"  {estimate.estimated_output_tokens_per_request:,} tokens/request",
                f"  {estimate.estimated_output_tokens or 0:,} tokens",
                f"  Estimated output cost: {_format_usd(estimate.estimated_output_cost_usd or Decimal(0))}",
                "",
                "Estimated total:",
                f"  {_format_usd(estimate.estimated_total_cost_usd or Decimal(0))}",
            ]
        )
    lines.extend(
        [
            "",
            "Maximum output:",
            f"  {estimate.max_output_tokens_per_request:,} tokens/request",
            f"  {estimate.max_output_tokens:,} tokens",
            f"  Maximum-output cost: {_format_usd(estimate.max_output_cost_usd)}",
            "",
            "Max-cost estimate:",
            f"  {_format_usd(estimate.max_cost_estimate_usd)}",
        ]
    )
    if estimate.input_token_warning:
        lines.extend(["", f"Warning: {estimate.input_token_warning}"])
    if estimate.pricing.note:
        lines.extend(["", f"Pricing note: {estimate.pricing.note}"])
    lines.extend(
        [
            "",
            "Retries caused by API or response-parse failures are not included.",
            "No model inference was executed.",
        ]
    )
    return "\n".join(lines)
