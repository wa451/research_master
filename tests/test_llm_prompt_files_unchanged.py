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
        "fa543d02cef6a47ebc0a54a81842ce5f79d8240460902db5874eb3eff9d50599"
    ),
    "src/behavior_pattern_mining/llm/direct_log_extractor.py": (
        "85ca19a237087bf56503b67e78216b1145885f241e6d26d02a66d5d19dec1574"
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
