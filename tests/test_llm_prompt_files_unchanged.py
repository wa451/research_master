from __future__ import annotations

import hashlib
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
EXPECTED_SHA256 = {
    "prompts/pattern_extraction_prompt.md": (
        "935a08cd4e5930118d2c214d864a0e4501c5428db045345a3aac5c590b9e9f75"
    ),
    "prompts/direct_log_pattern_extraction_prompt.md": (
        "c33039e6e5fec9835e17d9dca34ccb6c4bb72f6142255c351d9cbb3afa3dd37f"
    ),
    "src/behavior_pattern_mining/llm/pattern_extractor.py": (
        "ed02d18c2d1edd76334d46678d93090fa797c72b0b990e314656d52ec4a29aa8"
    ),
    "src/behavior_pattern_mining/llm/direct_log_extractor.py": (
        "6d3ba0dbaeba8f768c8fb4875498c2dc1f41a4989028f72321f3228571379b13"
    ),
}


class LLMPromptFilesUnchangedTests(unittest.TestCase):
    def test_prompt_files_and_prompt_generation_modules_are_unchanged(self) -> None:
        actual = {
            relative_path: hashlib.sha256(
                (ROOT_DIR / relative_path).read_bytes()
            ).hexdigest()
            for relative_path in EXPECTED_SHA256
        }
        self.assertEqual(actual, EXPECTED_SHA256)


if __name__ == "__main__":
    unittest.main()
