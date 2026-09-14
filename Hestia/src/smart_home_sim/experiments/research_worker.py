"""Executed with master-research's Python, without importing the simulator.

Only this adapter depends on the external research repository. No files in that
repository are modified. The native preprocessing and extraction implementations
are reused, while expensive visualization rendering is deliberately skipped.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "extract"])
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--run-id", type=int, default=1)
    args = parser.parse_args()
    sys.path.insert(0, str(args.research_root))
    from experiment_config import SAMPLING_INTERVAL, TIME_MODES  # type: ignore

    expected_modes = {
        "Midnight": ("00:00", "06:00"),
        "Morning": ("06:00", "10:00"),
        "Daytime": ("10:00", "18:00"),
        "Night": ("18:00", "24:00"),
    }
    if SAMPLING_INTERVAL != "1s" or expected_modes != TIME_MODES:
        raise ValueError(
            "research sampling interval/time modes changed; review the evaluation adapter"
        )
    settings = json.loads((args.run / "run.json").read_text(encoding="utf-8"))
    plan = settings["plan"]
    analysis = args.run / "analysis"
    if args.action == "prepare":
        from scripts.run_build_network_from_labeled_casas import (  # type: ignore
            convert_labeled_casas_to_event_csv,
        )
        from src.behavior_pattern_mining.evaluation.adl import (  # type: ignore
            build_network_equivalent_state_series_from_labeled_casas,
        )
        from src.behavior_pattern_mining.visualization.state_transition_visualizer import (  # type: ignore
            StateTransitionVisualizer,
        )

        mapping = json.loads((args.run / "input/sensor_map.json").read_text(encoding="utf-8"))
        converted = analysis / "train.csv"
        convert_labeled_casas_to_event_csv(args.run / "input/train.txt", converted, mapping)
        visualizer = StateTransitionVisualizer(
            data_duration_days=plan["train_days"],
            n_representative_states=plan["n_states"],
            hamming_threshold=plan["hamming_threshold"],
            smoothing_window_sec=plan["smoothing_window_sec"],
        )
        visualizer.create_state_vectors(visualizer.load_data(str(converted)))
        visualizer.extract_representative_states()
        visualizer.map_to_representative_states()
        visualizer.compute_transition_matrix()
        networks = analysis / "networks"
        networks.mkdir(exist_ok=True)
        visualizer.export_to_json(str(networks / "state_transition_all.json"))
        visualizer.save_state_table(str(analysis / "states.txt"))
        visualizer.compute_transition_matrix_by_modes()
        for mode in sorted(visualizer.mode_transition_matrices):
            visualizer.export_mode_to_json(mode, str(networks / f"state_transition_{mode}.json"))
        intervals = build_network_equivalent_state_series_from_labeled_casas(
            labeled_casas_path=args.run / "input/sensors.txt",
            state_table_path=analysis / "states.txt",
            hamming_threshold=plan["hamming_threshold"],
            smoothing_window_sec=plan["smoothing_window_sec"],
            sensor_map_path=args.run / "input/sensor_map.json",
            duration_days=plan["train_days"] + plan["test_days"],
        )
        timezone = datetime.fromisoformat(plan["start_datetime"]).tzinfo
        with (analysis / "state_series.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["start_time", "end_time", "state_id"])
            writer.writeheader()
            for interval in intervals:
                writer.writerow(
                    {
                        "start_time": interval.start_time.replace(tzinfo=timezone).isoformat(
                            timespec="microseconds"
                        ),
                        "end_time": interval.end_time.replace(tzinfo=timezone).isoformat(
                            timespec="microseconds"
                        ),
                        "state_id": interval.state_id,
                    }
                )
        # 保存するプロンプトは外部ファイル必須。埋込の旧版へのフォールバックは禁止。
        prompt = (args.research_root / "prompts/pattern_extraction_prompt.md").read_text(
            encoding="utf-8"
        )
        if prompt.count("単身高齢者宅") != 1:
            raise ValueError("research prompt changed; review the household-assumption adapter")
        prompt = prompt.replace(
            "単身高齢者宅", f"住人{settings['condition']['residents']}人の模擬住宅"
        )
        (analysis / "prompt.md").write_text(prompt, encoding="utf-8")
        from src.behavior_pattern_mining.llm import pattern_extractor  # type: ignore

        (analysis / "llm_settings.json").write_text(
            json.dumps(
                {
                    "model": pattern_extractor.MODEL_NAME,
                    "temperature": pattern_extractor.TEMPERATURE,
                    "max_parse_retries": pattern_extractor.MAX_PARSE_RETRIES,
                },
                sort_keys=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    else:
        from src.behavior_pattern_mining.llm import pattern_extractor  # type: ignore

        llm_settings = json.loads((analysis / "llm_settings.json").read_text(encoding="utf-8"))
        pattern_extractor.PROMPT_TEMPLATE = (analysis / "prompt.md").read_text(encoding="utf-8")
        pattern_extractor.MODEL_NAME = llm_settings["model"]
        pattern_extractor.TEMPERATURE = llm_settings["temperature"]
        pattern_extractor.OUTPUT_FILE_PATH = None
        pattern_extractor.main(
            days=plan["train_days"],
            input_modes_dir=analysis / "networks",
            output_dir=args.run / "predictions/llm",
            run_ids=[args.run_id],
            n_states=plan["n_states"],
            hamming_threshold=plan["hamming_threshold"],
        )


if __name__ == "__main__":
    main()
