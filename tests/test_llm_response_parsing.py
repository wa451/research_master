from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.behavior_pattern_mining.llm.client import parse_pattern_records
from src.behavior_pattern_mining.llm.direct_log_extractor import (
    convert_labeled_casas_to_event_csv,
    output_has_adl_sequence_labels,
)
from src.behavior_pattern_mining.llm.pattern_extractor import (
    load_checkpoint_records,
    merge_unique_patterns,
    mode_checkpoint_paths,
    save_successful_mode_checkpoint,
)


class LlmResponseParsingTests(unittest.TestCase):
    def test_parse_json_array_only_response(self) -> None:
        records = parse_pattern_records(
            json.dumps(
                [
                    {
                        "パターン名": "朝の移動",
                        "ADL系列ラベル": ["Wake-up"],
                        "解釈の根拠": "状態遷移が朝の動線を表すため。",
                        "遷移のパターン": ["状態1", "状態2"],
                    }
                ],
                ensure_ascii=False,
            )
        )

        self.assertEqual(records[0]["パターン名"], "朝の移動")
        self.assertEqual(records[0]["ADL系列ラベル"], ["Wake-up"])
        self.assertEqual(records[0]["遷移のパターン"], ["状態1", "状態2"])

    def test_merge_unique_patterns_keeps_time_band_interpretations_without_duplicate_sequence(self) -> None:
        merged = merge_unique_patterns(
            [
                (
                    "Morning",
                    [
                        {
                            "パターン名": "朝の移動",
                            "ADL系列ラベル": ["Wake-up"],
                            "解釈の根拠": "朝の動線。",
                            "遷移のパターン": ["状態1", "状態2"],
                        }
                    ],
                ),
                (
                    "Midnight",
                    [
                        {
                            "パターン名": "深夜の移動",
                            "ADL系列ラベル": ["Sleep", "Hygiene"],
                            "解釈の根拠": "深夜の動線。",
                            "遷移のパターン": ["状態1", "状態2"],
                        }
                    ],
                ),
            ]
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(set(merged[0].keys()), {"pattern_id", "sequence", "time_band_interpretations"})
        self.assertEqual(merged[0]["sequence"], ["状態1", "状態2"])
        self.assertNotIn("遷移のパターン", merged[0]["time_band_interpretations"]["Morning"])
        self.assertNotIn("sequence", merged[0]["time_band_interpretations"]["Morning"])
        self.assertEqual(
            sorted(merged[0]["time_band_interpretations"].keys()),
            ["Midnight", "Morning"],
        )

    def test_parse_wrapper_object_and_arrow_sequence(self) -> None:
        records = parse_pattern_records(
            json.dumps(
                {
                    "patterns": [
                        {
                            "name": "身支度",
                            "reason": "洗面所からキッチンへ移動しているため。",
                            "sequence": "状態3 -> 状態4 -> 状態5",
                        }
                    ]
                },
                ensure_ascii=False,
            )
        )

        self.assertEqual(records[0]["パターン名"], "身支度")
        self.assertEqual(records[0]["遷移のパターン"], ["状態3", "状態4", "状態5"])

    def test_parse_json_inside_markdown_text(self) -> None:
        response = """
        以下が結果です。
        ```json
        [
          {"パターン名": "休息", "解釈の根拠": "長時間滞在", "遷移のパターン": ["状態7", "状態8"]}
        ]
        ```
        """

        records = parse_pattern_records(response)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["遷移のパターン"], ["状態7", "状態8"])

    def test_empty_json_array_is_valid(self) -> None:
        self.assertEqual(parse_pattern_records("[]"), [])

    def test_direct_log_conversion_drops_activity_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            labeled_path = tmp_path / "aruba.txt"
            output_csv = tmp_path / "events.csv"
            sensor_map = tmp_path / "sensor_map.json"
            labeled_path.write_text(
                "\n".join(
                    [
                        "2010-01-01 00:00:00 M003 ON Sleeping begin",
                        "2010-01-01 00:00:05 M003 OFF Sleeping end",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            sensor_map.write_text('{"M003": "Bedroom"}', encoding="utf-8")

            count = convert_labeled_casas_to_event_csv(labeled_path, output_csv, sensor_map)
            rows = output_csv.read_text(encoding="utf-8").splitlines()

            self.assertEqual(count, 2)
            self.assertEqual(rows[0], "2010-01-01,00:00:00,Bedroom,ON")
            self.assertNotIn("Sleeping", "\n".join(rows))

    def test_direct_log_output_staleness_checks_adl_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "1.json"
            output_path.write_text(
                json.dumps(
                    [
                        {
                            "パターン名": "朝",
                            "ADL系列ラベル": ["Wake-up"],
                            "解釈の根拠": "",
                            "遷移のパターン": ["状態1", "状態2"],
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            self.assertTrue(output_has_adl_sequence_labels(output_path))

            output_path.write_text(
                json.dumps([{"パターン名": "旧形式", "遷移のパターン": ["状態1", "状態2"]}], ensure_ascii=False),
                encoding="utf-8",
            )
            self.assertFalse(output_has_adl_sequence_labels(output_path))

    def test_success_checkpoint_can_be_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            mode_path = output_dir / "state_transition_Morning.json"
            records = [
                {
                    "パターン名": "朝の移動",
                    "解釈の根拠": "",
                    "遷移のパターン": ["状態1", "状態2"],
                }
            ]

            save_successful_mode_checkpoint(
                output_dir=output_dir,
                run_idx=1,
                mode_path=mode_path,
                records=records,
                llm_text=json.dumps(records, ensure_ascii=False),
                backend="test",
                usage={"prompt_tokens": 1, "response_tokens": 2, "total_tokens": 3},
                duration_sec=0.1,
                attempt=1,
            )

            paths = mode_checkpoint_paths(output_dir, 1, mode_path)

            self.assertEqual(load_checkpoint_records(paths["records"]), records)
            self.assertTrue(paths["raw"].exists())
            self.assertTrue(paths["metrics"].exists())


if __name__ == "__main__":
    unittest.main()
