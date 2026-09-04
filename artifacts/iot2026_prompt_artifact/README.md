# IoT 2026 Anonymous Prompt Artifact

This artifact records the prompts, input/output contracts, and LLM settings
used for the proposed method and the LLM-only comparison in the anonymous
IoT 2026 submission. It is intended for public release through OSF.

The prompt text is copied from the runtime prompt files without rewriting or
adding instructions. Only run-dependent input sections are replaced by the
placeholders documented below.

## Contents and repository sources

| Artifact file                            | Repository source                                                                                                                    |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `prompts/proposed_user_prompt.txt`     | `prompts/pattern_extraction_prompt.md`; runtime assembly in `src/behavior_pattern_mining/llm/pattern_extractor.py`               |
| `prompts/llm_only_user_prompt.txt`     | `prompts/direct_log_pattern_extraction_prompt.md`; runtime assembly in `src/behavior_pattern_mining/llm/direct_log_extractor.py` |
| `schemas/pattern_response.schema.json` | Prompt output contract and normalization in `src/behavior_pattern_mining/llm/client.py`                                            |
| `examples/proposed_input_example.json` | Structure of `picture/aruba_15_0_14days/state_transition_*.json`                                                                   |
| `examples/llm_only_input_example.json` | Tab-separated sequence construction in `src/behavior_pattern_mining/llm/direct_log_extractor.py`                                  |
| `examples/output_example.json`         | Normalized per-call outputs under `output/aruba_15_0_14days/llm_mode_records_run*/` and `output/llm_direct_15_0_14days/`          |
| `experiment_settings.md`               | `configs/default.yaml`, LLM client/extractors, and retained 14-day metrics logs                                                    |

All paths above are repository-relative source references. Local absolute paths
and private input data are not included in this artifact.

The source prompt files are protected by
`tests/test_llm_prompt_files_unchanged.py`. Their repository SHA-256 values
used for this extraction are:

- `prompts/pattern_extraction_prompt.md`:
  `935a08cd4e5930118d2c214d864a0e4501c5428db045345a3aac5c590b9e9f75`
- `prompts/direct_log_pattern_extraction_prompt.md`:
  `c33039e6e5fec9835e17d9dca34ccb6c4bb72f6142255c351d9cbb3afa3dd37f`

## Prompt assembly

### Proposed method

At runtime, `{MODE}` in the source prompt was replaced by a time-period label,
and `{JSON_DATA}` was replaced by the state-transition-network JSON wrapped in
a Markdown `json` code fence. The artifact preserves that fence and uses:

- `{{TIME_PERIOD}}`: one of `Morning: 06:00-10:00`,
  `Daytime: 10:00-18:00`, `Night: 18:00-24:00`, or
  `Midnight: 00:00-06:00`.
- `{{STATE_TRANSITION_NETWORK_JSON}}`: the complete JSON text for one
  time-period-specific state-transition network.

### LLM-only comparison

The runtime prompt used the fixed experiment context `aruba / 14 days` and
representative-state count `15`. It then inserted two tab-separated text
blocks:

- `{{REPRESENTATIVE_STATE_TABLE_TSV}}`: the representative-state definition
  table, including its header, read from `state/aruba_15_0_14days.txt`.
- `{{REPRESENTATIVE_STATE_SEQUENCE}}`: the complete compressed 14-day sequence,
  with one `timestamp<TAB>state label` record per line.

`examples/llm_only_input_example.json` is a JSON string containing a small
anonymized example value for `{{REPRESENTATIVE_STATE_SEQUENCE}}`. The API input
was not a JSON object: the full rendered prompt was sent as one text user
message.

## Output contract

Both API paths requested a top-level JSON array in natural-language prompt
instructions. No API `response_schema` or JSON MIME type was configured.
`schemas/pattern_response.schema.json` documents the expected four-key response
contract used by the prompt and the normalized records consumed by the code;
it was not sent to the API.

The response parser also tolerated Markdown fences, wrapper objects, alternate
key spellings, and arrow-separated sequences before normalizing records. The
example output shows the canonical normalized structure, not a claim that the
API enforced the schema.

## Files intentionally not included

- No system-prompt file is present because neither API path set
  `systemInstruction` or another system message.
- No repair/retry prompt is present. The proposed-method implementation can
  append JSON-only repair instructions after a parse failure, but every
  retained 14-day mode metric reports `attempt: 1`, and no failed-response file
  exists for that condition. The LLM-only path retries the unchanged user
  message and has no separate repair prompt; all retained runs report one
  attempt.
- Embedded fallback prompts are not included because the external prompt files
  existed and were loaded for the retained experiments. The fallback prompts
  differ from the external prompts and should not be treated as the experiment
  prompt.
- Raw sensor logs, full representative-state tables, full model inputs, raw
  model responses, API credentials, and identifying metadata are excluded.

## Integrity

`SHA256SUMS` contains SHA-256 digests for every other file in this directory.
Run the following command from the artifact directory:

```sh
sha256sum -c SHA256SUMS
```
