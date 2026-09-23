from __future__ import annotations

from pathlib import Path

from src.behavior_pattern_mining.config import get_config_value, load_config
from src.behavior_pattern_mining.llm.result_paths import (
    ModelIdentity,
    model_results_root,
    resolve_project_model_identity,
)


ROOT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = ROOT_DIR / "configs" / "default.yaml"
CONFIG = load_config(CONFIG_PATH)

DATASET_NAME = str(get_config_value(CONFIG, "dataset.name", "aruba"))
N_STATES = int(get_config_value(CONFIG, "state_extraction.representative_states_k", 15))
HAMMING_THRESHOLD = int(get_config_value(CONFIG, "state_extraction.hamming_threshold", 1))
DAYS = int(get_config_value(CONFIG, "dataset.days", 154))
DATA_DURATION_RATIO = float(get_config_value(CONFIG, "dataset.duration_ratio_when_days_is_null", 0.7))
SAMPLING_INTERVAL = str(get_config_value(CONFIG, "state_extraction.sampling_interval", "1s"))
SMOOTHING_WINDOW_SEC = int(get_config_value(CONFIG, "state_extraction.smoothing_window_sec", 5))
UNKNOWN_STATE = str(get_config_value(CONFIG, "state_extraction.unknown_state", "その他"))

TIME_MODES = {
    name: tuple(values)
    for name, values in get_config_value(
        CONFIG,
        "time_modes",
        {
            "Morning": ["06:00", "10:00"],
            "Daytime": ["10:00", "18:00"],
            "Night": ["18:00", "24:00"],
            "Midnight": ["00:00", "06:00"],
        },
    ).items()
}

LLM_MODEL_NAME = str(get_config_value(CONFIG, "llm.model", "gemini-2.5-pro"))
LLM_PROVIDER = str(get_config_value(CONFIG, "llm.provider", "google_gemini"))
LLM_TEMPERATURE = float(get_config_value(CONFIG, "llm.temperature", 0.2))
LLM_RUNS_DEFAULT = int(get_config_value(CONFIG, "llm.runs_default", 1))
LLM_BATCH_RUNS = int(get_config_value(CONFIG, "llm.batch_runs", 5))
LLM_MAX_RETRIES_PER_RUN = int(get_config_value(CONFIG, "llm.max_retries_per_run", 3))
BEDROCK_REGION = str(get_config_value(CONFIG, "llm.bedrock.region", "us-east-2"))
BEDROCK_MODEL_ID = str(get_config_value(CONFIG, "llm.bedrock.model_id", ""))
BEDROCK_MAX_TOKENS = int(get_config_value(CONFIG, "llm.bedrock.max_tokens", 8192))
_BEDROCK_ESTIMATED_OUTPUT_TOKENS = get_config_value(
    CONFIG,
    "llm.bedrock.estimated_output_tokens",
    None,
)
BEDROCK_ESTIMATED_OUTPUT_TOKENS = (
    None
    if _BEDROCK_ESTIMATED_OUTPUT_TOKENS is None
    else int(_BEDROCK_ESTIMATED_OUTPUT_TOKENS)
)


def current_model_identity() -> ModelIdentity:
    """Return the active provider/model used to namespace LLM results."""
    return resolve_project_model_identity(
        ROOT_DIR,
        default_provider=LLM_PROVIDER,
        gemini_model_name=LLM_MODEL_NAME,
        bedrock_model_id=BEDROCK_MODEL_ID,
    )


def current_model_results_root() -> Path:
    return model_results_root(ROOT_DIR, current_model_identity())

TRANSITION_PROBABILITY_THRESHOLD = float(
    get_config_value(CONFIG, "baselines.transition_probability.threshold", 0.2)
)
MIN_SEQUENCE_LENGTH = int(get_config_value(CONFIG, "baselines.transition_probability.min_sequence_length", 2))
MAX_SEQUENCE_LENGTH = int(get_config_value(CONFIG, "baselines.transition_probability.max_sequence_length", 4))
TRANSITION_EXCLUDED_STATES = list(
    get_config_value(CONFIG, "baselines.transition_probability.excluded_states", ["その他"])
)
TRANSITION_ALLOW_REVISIT = bool(
    get_config_value(CONFIG, "baselines.transition_probability.allow_revisit", False)
)
TRANSITION_TOP_N = int(get_config_value(CONFIG, "baselines.transition_probability.top_n", 0))

FREQUENCY_MIN_SEQUENCE_LENGTH = int(get_config_value(CONFIG, "baselines.frequency.min_sequence_length", 2))
FREQUENCY_MAX_SEQUENCE_LENGTH = int(get_config_value(CONFIG, "baselines.frequency.max_sequence_length", 4))
FREQUENCY_TOP_K = int(get_config_value(CONFIG, "baselines.frequency.top_k", 50))
FREQUENCY_USE_HAMMING_GROUPING = bool(
    get_config_value(CONFIG, "baselines.frequency.use_hamming_grouping", True)
)

MIN_TRANSITION_PROB_FOR_VISUALIZATION = float(
    get_config_value(CONFIG, "transition_network.min_transition_probability_for_visualization", 0.1)
)
ALLOW_BASELINE_CONTAINS_LLM = bool(
    get_config_value(CONFIG, "evaluation.allow_baseline_contains_llm", False)
)
ALLOW_LLM_CONTAINS_BASELINE = bool(
    get_config_value(CONFIG, "evaluation.allow_llm_contains_baseline", False)
)
