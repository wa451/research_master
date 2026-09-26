from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from src.behavior_pattern_mining.llm import direct_log_extractor as extractor
from src.behavior_pattern_mining.llm.result_paths import ModelIdentity


TIMESTAMPS = pd.to_datetime(
    [
        "2020-01-01 00:00:00",
        "2020-01-01 06:00:00",
        "2020-01-01 07:00:00",
        "2020-01-01 10:00:00",
        "2020-01-01 18:00:00",
    ]
)
STATE_LABELS = ["状態0", "状態6", "状態7", "状態10", "状態18"]


class _FakeVisualizer:
    effective_data_duration_days = 14
    timestamps = TIMESTAMPS

    def __init__(self, **_kwargs: object) -> None:
        self.state_vectors_df: pd.DataFrame | None = None

    def load_data(self, _path: str) -> object:
        return object()

    def create_state_vectors(self, _events: object) -> pd.DataFrame:
        self.state_vectors_df = pd.DataFrame(
            {"sensor": range(len(self.timestamps))}, index=self.timestamps
        )
        return self.state_vectors_df


class DirectLogTimeSplitTests(unittest.TestCase):
    def test_partition_uses_common_half_open_time_periods_and_preserves_order(self) -> None:
        grouped = extractor.split_state_labels_by_time_period(TIMESTAMPS, STATE_LABELS)

        self.assertEqual(list(grouped), ["Morning", "Daytime", "Night", "Midnight"])
        self.assertEqual(
            {period: [label for _, label in items] for period, items in grouped.items()},
            {
                "Morning": ["状態6", "状態7"],
                "Daytime": ["状態10"],
                "Night": ["状態18"],
                "Midnight": ["状態0"],
            },
        )
        self.assertEqual(
            sum(len(items) for items in grouped.values()),
            len(STATE_LABELS),
        )

    def test_split_output_attaches_time_period_to_each_pattern(self) -> None:
        records = extractor.attach_time_period_to_records(
            [{"遷移のパターン": ["状態6", "状態7"], "ADL系列ラベル": ["Meal"]}],
            "Morning",
            1,
        )

        self.assertEqual(records[0]["pattern_id"], "D001_Morning")
        self.assertEqual(records[0]["time_period"], "Morning")
        self.assertEqual(records[0]["sequence"], ["状態6", "状態7"])

    def test_time_period_token_totals_sum_only_api_calls(self) -> None:
        totals = extractor.time_period_token_totals(
            [
                {"status": "success", "prompt_tokens": 10, "response_tokens": 2, "total_tokens": 12},
                {"status": "empty_prediction", "prompt_tokens": 20, "response_tokens": 3, "total_tokens": 23},
                {"status": "no_input", "prompt_tokens": None, "response_tokens": None, "total_tokens": None},
            ]
        )

        self.assertEqual(
            totals,
            {
                "api_call_count": 2,
                "prompt_tokens": 30,
                "completion_tokens": 5,
                "api_total_tokens": 35,
            },
        )

    def _run_extractor(
        self,
        mode: str,
        *,
        timestamps: pd.DatetimeIndex = TIMESTAMPS,
        state_labels: list[str] = STATE_LABELS,
        empty_response: bool = False,
    ) -> tuple[list[str], list[dict], list[dict[str, str]]]:
        prompts: list[str] = []

        def fake_call(_config: object, prompt: str) -> tuple[str, str, dict, float]:
            prompts.append(prompt)
            response = [] if empty_response else [
                {
                        "パターン名": "mock pattern",
                        "遷移のパターン": ["状態6", "状態7"],
                        "ADL系列ラベル": ["Meal"],
                        "解釈の根拠": "mock",
                }
            ]
            return (
                json.dumps(response, ensure_ascii=False),
                "mock",
                {"prompt_tokens": 10, "response_tokens": 2, "total_tokens": 12},
                0.25,
            )

        config = SimpleNamespace(
            provider="test",
            model_name="test-model",
            temperature=0.0,
            region_name=None,
            max_tokens=100,
        )
        identity = ModelIdentity(provider="test", model_id="test-model", result_name="test-model")
        fake_visualizer = type("FakeVisualizer", (_FakeVisualizer,), {"timestamps": timestamps})
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "direct"
            with (
                patch.object(extractor, "load_dotenv"),
                patch.object(extractor, "resolve_llm_runtime_config", return_value=config),
                patch.object(extractor, "model_identity", return_value=identity),
                patch.object(extractor, "prepare_input_csv", return_value=(Path(tmpdir) / "events.csv", None, None)),
                patch.object(extractor.stv, "StateTransitionVisualizer", fake_visualizer),
                patch.object(extractor, "find_state_file", return_value=Path(tmpdir) / "states.txt"),
                patch.object(extractor, "load_state_definition", return_value=({}, {})),
                patch.object(extractor, "map_vectors_to_states", return_value=(state_labels, {})),
                patch.object(extractor, "state_table_to_text", return_value="state table"),
                patch.object(extractor, "call_llm", side_effect=fake_call),
            ):
                extractor.main(
                    log_days=14,
                    state_days=14,
                    output_dir=output_dir,
                    runs=1,
                    n_states=15,
                    hamming_threshold=1,
                    llm_only_time_mode=mode,
                )

            patterns = json.loads((output_dir / "1.json").read_text(encoding="utf-8"))
            with (output_dir / "llm_direct_metrics_14days.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                metrics = list(csv.DictReader(handle))
        return prompts, patterns, metrics

    def test_split_mode_calls_once_per_period_and_keeps_inputs_separate(self) -> None:
        prompts, patterns, metrics = self._run_extractor("split")

        self.assertEqual(len(prompts), 4)
        self.assertEqual([record["time_period"] for record in patterns], [
            "Morning", "Daytime", "Night", "Midnight",
        ])
        self.assertEqual([row["time_period"] for row in metrics], [
            "Daytime", "Midnight", "Morning", "Night",
        ])
        self.assertTrue(all(row["status"] == "success" for row in metrics))
        morning_prompt = next(prompt for prompt in prompts if "Morning (06:00–10:00)" in prompt)
        self.assertIn("状態6", morning_prompt)
        self.assertNotIn("状態0", morning_prompt)
        self.assertNotIn("状態18", morning_prompt)

    def test_legacy_mode_keeps_the_single_unsplit_call(self) -> None:
        prompts, patterns, metrics = self._run_extractor("legacy")

        self.assertEqual(len(prompts), 1)
        self.assertEqual(len(patterns), 1)
        self.assertNotIn("time_period", patterns[0])
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0]["time_period"], "")

    def test_no_input_skips_api_call_and_empty_response_is_recorded(self) -> None:
        only_morning = pd.to_datetime(["2020-01-01 07:00:00"])
        prompts, patterns, metrics = self._run_extractor(
            "split",
            timestamps=only_morning,
            state_labels=["状態7"],
            empty_response=True,
        )

        self.assertEqual(len(prompts), 1)
        self.assertEqual(patterns, [])
        statuses = {row["time_period"]: row["status"] for row in metrics}
        self.assertEqual(statuses["Morning"], "empty_prediction")
        self.assertEqual(statuses["Daytime"], "no_input")
        self.assertEqual(statuses["Night"], "no_input")
        self.assertEqual(statuses["Midnight"], "no_input")


if __name__ == "__main__":
    unittest.main()
