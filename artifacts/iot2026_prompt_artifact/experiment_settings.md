# Experiment Settings

The table below distinguishes settings explicitly passed by the experiment
code from values that were not recorded. Unspecified values are not inferred
from current provider defaults.

## Shared API configuration

| Setting | Confirmed value |
|---|---|
| Provider | Google Gemini |
| Model ID sent to the API | `gemini-2.5-pro` |
| Model revision | Not confirmed. The ID is an unversioned API alias and no date-specific revision was recorded. |
| Backend recorded in retained logs | `google-genai` |
| Exact SDK version used for the retained runs | Not confirmed. The version was not saved in the experiment logs. |
| Temperature | `0.2` |
| System instruction | Not used |
| API response MIME type | Not explicitly configured |
| API response schema | Not used |
| Response handling | Text response parsed and normalized as a JSON array |
| Thinking configuration | Not explicitly configured; the applied thinking mode/budget cannot be confirmed |
| Seed | Not explicitly configured |
| Maximum output tokens | Not explicitly configured |
| Top-p | Not explicitly configured |
| Top-k | Not explicitly configured |
| Safety settings | Not explicitly configured |
| Tools/function calling | Not used |
| API context cache/cached content | Not used |
| Provider/SDK internal retry policy | Not explicitly configured and not recorded |

The retained usage logs sometimes report total tokens greater than prompt plus
candidate tokens. The repository computes “reasoning tokens” as that
difference, but the logs do not record an explicit thinking configuration.

The API call passed the prompt through the `contents`/user-message argument and
constructed `GenerateContentConfig` with only `temperature`. The legacy SDK
fallback was implemented but the retained logs identify the newer
`google-genai` backend.

## Proposed method

| Setting | Confirmed value |
|---|---|
| Input condition used in the LLM-only comparison | First 14 days, `K=15`, `h=0` |
| API input unit | One time-period-specific state-transition network |
| Time periods | Morning, Daytime, Night, Midnight |
| User prompt source | `prompts/pattern_extraction_prompt.md` |
| Dynamic prompt values | Time-period label and complete network JSON |
| Network JSON insertion | Wrapped in a Markdown `json` code fence |
| Saved comparison runs | Five runs, four time-period calls per run |
| Parse-attempt limit | Three attempts per run/time-period call |
| Retry behavior | On parse failure, resend the original prompt with appended JSON-only repair instructions |
| Retained-run retry evidence | All retained 14-day mode metrics report `attempt: 1`; no repair prompt is evidenced as used |
| Application checkpoint reuse | Implemented through per-run/per-mode JSON checkpoints; this is not API context caching |

After each call, accepted records are normalized to the four-key pattern
structure. Identical state sequences are then merged across time periods into
records with `pattern_id`, `sequence`, and `time_band_interpretations`. That
post-processing structure was not requested from the model.

## LLM-only comparison

| Setting | Confirmed value |
|---|---|
| Input condition | First 14 days, `K=15`, `h=0` |
| API input unit | One complete representative-state sequence |
| State-table construction period | First 14 days |
| User prompt source | `prompts/direct_log_pattern_extraction_prompt.md` |
| Dynamic prompt values | Representative-state table and compressed timestamp/state sequence |
| Maximum input rows | `0` (unlimited) |
| Saved comparison runs | Five |
| Attempt limit per run | Three |
| Retry behavior | Resend the unchanged user message after an exception; no separate repair prompt |
| Retained-run retry evidence | All five retained rows report `attempts=1` |
| Application checkpoint reuse | Existing successful run JSON can skip a call; this is not API context caching |

## Evidence used

- `configs/default.yaml`
- `src/behavior_pattern_mining/llm/client.py`
- `src/behavior_pattern_mining/llm/pattern_extractor.py`
- `src/behavior_pattern_mining/llm/direct_log_extractor.py`
- `prompts/pattern_extraction_prompt.md`
- `prompts/direct_log_pattern_extraction_prompt.md`
- `output/aruba_15_0_14days/llm_mode_records_run*/state_transition_*_metrics.json`
- `output/aruba_15_0_14days/llm_modes_metrics_15_0_14days_run*.csv`
- `output/llm_direct_15_0_14days/llm_direct_metrics_14days.csv`

The retained artifacts do not include a serialized API request object, exact
SDK version, model revision, or provider-applied default values. Those items
therefore remain unconfirmed.
