from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.estimate_evaluation_costs import build_parser
from src.behavior_pattern_mining.llm.client import LLMRuntimeConfig
from src.behavior_pattern_mining.llm.evaluation_costs import (
    build_evaluation_plans,
    estimate_evaluation_plans,
    estimate_models,
    format_model_comparison,
    save_model_comparison_reports,
    save_evaluation_cost_report,
)


MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"


def _write_mode(directory: Path, name: str = "Morning", marker: str = "x") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"state_transition_{name}.json").write_text(
        json.dumps({"mode": name, "marker": marker}),
        encoding="utf-8",
    )


class EvaluationCostEstimateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        _write_mode(self.root / "picture/aruba_15_0_154days", marker="eval5")
        _write_mode(self.root / "picture/aruba_15_0_14days", marker="eval6")

        for n_states in (10, 15, 20, 25, 30, 35, 40):
            for hamming in (0, 1, 2, 3):
                _write_mode(
                    self.root / f"picture/aruba_{n_states}_{hamming}_14days",
                    marker=f"{n_states}-{hamming}",
                )

        self.hestia = self.root / "output/9_hestia/full"
        self.hestia.mkdir(parents=True)
        (self.hestia / "experiment.json").write_text(
            json.dumps({"conditions": [{"id": "compact_base"}], "seeds": [11]}),
            encoding="utf-8",
        )
        hestia_run = self.hestia / "runs/compact_base/seed_11"
        hestia_run.mkdir(parents=True)
        (hestia_run / "run.json").write_text(
            json.dumps({"plan": {"llm_runs": 2}}),
            encoding="utf-8",
        )
        (hestia_run / "analysis").mkdir(parents=True)
        (hestia_run / "analysis/prompt.md").write_text(
            "Mode={MODE}\n{JSON_DATA}",
            encoding="utf-8",
        )
        _write_mode(hestia_run / "analysis/networks", marker="hestia")

        self.hestia_duration = self.root / "output/9_hestia/duration"
        self.hestia_duration.mkdir(parents=True)
        (self.hestia_duration / "duration.json").write_text(
            json.dumps({"train_days": [3, 7, 14, 28]}),
            encoding="utf-8",
        )
        for train_days in (3, 7, 14, 28):
            duration_window = (
                self.hestia_duration / "windows" / f"train_{train_days}d"
            )
            duration_window.mkdir(parents=True)
            (duration_window / "experiment.json").write_text(
                json.dumps(
                    {"conditions": [{"id": "compact_base"}], "seeds": [11]}
                ),
                encoding="utf-8",
            )
            duration_run = duration_window / "runs/compact_base/seed_11"
            duration_run.mkdir(parents=True)
            (duration_run / "run.json").write_text(
                json.dumps(
                    {"plan": {"llm_runs": 2, "train_days": train_days}}
                ),
                encoding="utf-8",
            )
            (duration_run / "analysis").mkdir(parents=True)
            (duration_run / "analysis/prompt.md").write_text(
                "Mode={MODE}\n{JSON_DATA}",
                encoding="utf-8",
            )
            _write_mode(
                duration_run / "analysis/networks",
                marker=f"duration-{train_days}",
            )

        self.switchbot = self.root / "output/10_switchbot/snapshot"
        self.switchbot.mkdir(parents=True)
        (self.switchbot / "preparation.json").write_text(
            json.dumps(
                {
                    "split": {"train_days": 4},
                    "parameters": {"n_states": 15, "hamming_threshold": 0},
                }
            ),
            encoding="utf-8",
        )
        _write_mode(self.switchbot / "network", marker="switchbot")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _plans(self):
        return build_evaluation_plans(
            root=self.root,
            evaluations=[5, 6, 7, 8, 9, 10],
            evaluation9_experiment=self.hestia,
            evaluation9_duration_experiment=self.hestia_duration,
            evaluation10_output_dir=self.switchbot,
            direct_message_builder=lambda **_: "direct-log prompt",
        )

    def test_cli_accepts_multiple_model_ids(self) -> None:
        args = build_parser().parse_args(
            ["--run-ids", "5", "6", "--models", "model-a", "model-b"]
        )
        self.assertEqual(args.evaluations, [5, 6])
        self.assertEqual(args.models, ["model-a", "model-b"])
        self.assertIsNone(args.evaluation9_duration_experiment)

    def test_plans_cover_each_evaluation_and_full_rerun_ignores_checkpoints(self) -> None:
        checkpoint = self.root / (
            "output/aruba_15_0_154days/llm_mode_records_run1/"
            "state_transition_Morning.json"
        )
        checkpoint.parent.mkdir(parents=True)
        checkpoint.write_text('[{"ADL系列ラベル":["Meal"]}]', encoding="utf-8")
        before = checkpoint.read_bytes()

        plans = self._plans()

        self.assertEqual([plan.evaluation for plan in plans], [5, 6, 7, 8, 9, 10])
        self.assertEqual(
            [plan.request_count for plan in plans],
            [5, 10, 140, 0, 10, 1],
        )
        self.assertEqual(
            plans[2].run_plan,
            "28 conditions, days=14, runs=1-5 for every condition",
        )
        self.assertIn("4 duration windows", plans[4].run_plan)
        self.assertEqual(checkpoint.read_bytes(), before)

    def test_total_csv_json_and_count_tokens_never_use_converse(self) -> None:
        plans = self._plans()
        bedrock_client = Mock()
        bedrock_client.count_tokens.return_value = {"inputTokens": 10}
        boto3_module = Mock()
        boto3_module.client.return_value = bedrock_client
        config = LLMRuntimeConfig(
            provider="bedrock",
            model_name=MODEL_ID,
            temperature=0.2,
            region_name="us-east-2",
            max_tokens=8192,
            estimated_output_tokens=1000,
        )

        with patch(
            "src.behavior_pattern_mining.llm.client.importlib.import_module",
            return_value=boto3_module,
        ):
            report = estimate_evaluation_plans(llm_config=config, plans=plans)

        self.assertEqual(report.total.requests, sum(row.requests for row in report.rows))
        self.assertEqual(
            report.total.input_tokens,
            sum(row.input_tokens for row in report.rows),
        )
        self.assertEqual(
            report.total.estimated_output_tokens,
            sum(row.estimated_output_tokens or 0 for row in report.rows),
        )
        self.assertEqual(
            report.total.max_output_tokens,
            sum(row.max_output_tokens for row in report.rows),
        )
        bedrock_client.converse.assert_not_called()

        csv_path = self.root / "saved/estimate.csv"
        json_path = self.root / "saved/estimate.json"
        save_evaluation_cost_report(report, csv_path=csv_path, json_path=json_path)
        with csv_path.open(encoding="utf-8", newline="") as handle:
            csv_rows = list(csv.DictReader(handle))
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual([row["evaluation"] for row in csv_rows], ["5", "6", "7", "8", "9", "10", "TOTAL"])
        self.assertEqual(payload["settings"]["checkpoint_policy"], "ignored (read-only)")
        self.assertFalse(payload["settings"]["inference_executed"])
        self.assertEqual(payload["total"]["requests"], 166)
        self.assertEqual(payload["model_id"], MODEL_ID)

    def test_fallback_is_recorded_per_evaluation(self) -> None:
        plans = self._plans()[:1]
        bedrock_client = Mock()
        bedrock_client.count_tokens.side_effect = RuntimeError("not authorized")
        boto3_module = Mock()
        boto3_module.client.return_value = bedrock_client
        config = LLMRuntimeConfig(
            provider="bedrock",
            model_name=MODEL_ID,
            temperature=0.2,
            region_name="us-east-2",
            max_tokens=8192,
            estimated_output_tokens=1000,
        )

        with patch(
            "src.behavior_pattern_mining.llm.client.importlib.import_module",
            return_value=boto3_module,
        ):
            report = estimate_evaluation_plans(llm_config=config, plans=plans)

        self.assertFalse(report.rows[0].input_tokens_exact)
        self.assertIn("approximate fallback", report.rows[0].input_token_method)
        self.assertIn("not authorized", report.rows[0].input_token_warning or "")
        bedrock_client.converse.assert_not_called()

    def test_models_are_counted_independently_and_unpriced_model_is_not_substituted(self) -> None:
        plans = self._plans()[:1]
        unknown_model = "us.example.unpriced-model-v1:0"
        configs = [
            LLMRuntimeConfig(
                provider="bedrock",
                model_name=model_id,
                temperature=0.2,
                region_name="us-east-2",
                max_tokens=8192,
                estimated_output_tokens=1000,
            )
            for model_id in (MODEL_ID, unknown_model)
        ]
        priced_client = Mock()
        priced_client.count_tokens.return_value = {"inputTokens": 10}
        unpriced_client = Mock()
        unpriced_client.count_tokens.side_effect = RuntimeError("CountTokens unavailable")
        boto3_module = Mock()
        boto3_module.client.side_effect = [priced_client, unpriced_client]

        with patch(
            "src.behavior_pattern_mining.llm.client.importlib.import_module",
            return_value=boto3_module,
        ):
            reports = estimate_models(llm_configs=configs, plans=plans)

        self.assertEqual([report.llm_config.model_name for report in reports], [MODEL_ID, unknown_model])
        self.assertEqual(reports[0].total.input_tokens, 50)
        self.assertNotEqual(reports[1].total.input_tokens, reports[0].total.input_tokens)
        self.assertTrue(reports[0].total.pricing_available)
        self.assertFalse(reports[1].total.pricing_available)
        self.assertIsNone(reports[1].total.estimated_total_cost_usd)
        self.assertIn("not configured", reports[1].pricing_error or "")
        self.assertIn("approximate fallback", reports[1].total.input_token_method)
        priced_client.count_tokens.assert_called_once()
        unpriced_client.count_tokens.assert_called_once()
        self.assertEqual(
            priced_client.count_tokens.call_args.kwargs["modelId"],
            MODEL_ID,
        )
        self.assertEqual(
            unpriced_client.count_tokens.call_args.kwargs["modelId"],
            unknown_model,
        )
        priced_client.converse.assert_not_called()
        unpriced_client.converse.assert_not_called()

        csv_path = self.root / "comparison/details.csv"
        json_path = self.root / "comparison/details.json"
        summary_path = self.root / "comparison/model_comparison_summary.csv"
        save_model_comparison_reports(
            reports,
            csv_path=csv_path,
            json_path=json_path,
            summary_csv_path=summary_path,
        )
        with csv_path.open(encoding="utf-8", newline="") as handle:
            detail_rows = list(csv.DictReader(handle))
        with summary_path.open(encoding="utf-8", newline="") as handle:
            summary_rows = list(csv.DictReader(handle))
        payload = json.loads(json_path.read_text(encoding="utf-8"))

        self.assertEqual(len(detail_rows), 4)
        self.assertEqual({row["model_id"] for row in detail_rows}, {MODEL_ID, unknown_model})
        self.assertEqual([row["model_id"] for row in summary_rows], [MODEL_ID, unknown_model])
        self.assertEqual(summary_rows[1]["estimated_total_cost_usd"], "")
        self.assertEqual(len(payload["models"]), 2)
        self.assertFalse(payload["models"][1]["pricing_available"])
        terminal = format_model_comparison(
            reports,
            csv_path=csv_path,
            json_path=json_path,
            summary_csv_path=summary_path,
        )
        self.assertIn("=== Model Comparison ===", terminal)
        self.assertIn(MODEL_ID, terminal)
        self.assertIn(unknown_model, terminal)
        self.assertIn("Pricing unavailable", terminal)
        self.assertIn("No model inference was executed.", terminal)


if __name__ == "__main__":
    unittest.main()
