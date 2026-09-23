"""LLM choices exposed by the local evaluation dashboard.

The dashboard passes these values only to the subprocess it starts.  It never
rewrites the repository's ``.env`` file, so an interactive model change cannot
silently affect another terminal or a later non-dashboard run.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.behavior_pattern_mining.llm.result_paths import (
    ModelIdentity,
    model_identity,
    model_results_root,
)


@dataclass(frozen=True)
class DashboardModel:
    """One supported provider/model pair and its non-secret environment."""

    label: str
    provider: str
    model_id: str

    @property
    def identity(self) -> ModelIdentity:
        return model_identity(self.provider, self.model_id)

    @property
    def result_name(self) -> str:
        return self.identity.result_name

    def results_root(self, project_root: Path) -> Path:
        return model_results_root(project_root, self.identity)

    def environment_overrides(self) -> dict[str, str]:
        if self.provider == "google_gemini":
            return {
                "LLM_PROVIDER": "google_gemini",
                "GEMINI_MODEL_NAME": self.model_id,
            }
        return {
            "LLM_PROVIDER": "bedrock",
            "BEDROCK_MODEL_ID": self.model_id,
        }


# Keep the default first: Streamlit uses this order for the initial selection.
DASHBOARD_MODELS: tuple[DashboardModel, ...] = (
    DashboardModel("GPT-5.6 Sol（既定）", "bedrock", "us.openai.gpt-5.6-sol"),
    DashboardModel("GPT-5.6 Terra", "bedrock", "us.openai.gpt-5.6-terra"),
    DashboardModel("GPT-5.6 Luna", "bedrock", "us.openai.gpt-5.6-luna"),
    DashboardModel("Claude Sonnet 4.6", "bedrock", "us.anthropic.claude-sonnet-4-6"),
    DashboardModel(
        "Claude Haiku 4.5",
        "bedrock",
        "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    ),
    DashboardModel("Gemini 2.5 Pro", "google_gemini", "gemini-2.5-pro"),
)

DEFAULT_DASHBOARD_MODEL_ID = DASHBOARD_MODELS[0].model_id


def dashboard_model(model_id: str) -> DashboardModel:
    """Return a supported dashboard choice, rejecting arbitrary environment input."""
    for model in DASHBOARD_MODELS:
        if model.model_id == model_id:
            return model
    raise ValueError(f"ダッシュボードで未対応のモデルです: {model_id!r}")
