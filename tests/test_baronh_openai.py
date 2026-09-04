#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from baronh.lexicon import load_lexicon
from baronh.openai_backend import (
    GRAMMAR_BRIEF,
    api_url,
    dispatch_tool,
    normalize_api_base,
    retrieve_lexicon_context,
)
from baronh.translate import translate


class ApiBaseTest(unittest.TestCase):
    def test_default(self):
        self.assertEqual(normalize_api_base(""), "https://api.openai.com/v1")

    def test_strips_slash(self):
        self.assertEqual(normalize_api_base("https://api.openai.com/v1/"), "https://api.openai.com/v1")

    def test_adds_v1_for_host_only(self):
        self.assertEqual(normalize_api_base("http://127.0.0.1:1234"), "http://127.0.0.1:1234/v1")

    def test_keeps_custom_path(self):
        self.assertEqual(
            normalize_api_base("https://openrouter.ai/api/v1"),
            "https://openrouter.ai/api/v1",
        )

    def test_chat_url(self):
        self.assertEqual(
            api_url("chat/completions", api_base="http://localhost:8080/v1"),
            "http://localhost:8080/v1/chat/completions",
        )

    def test_speech_url(self):
        self.assertEqual(
            api_url("audio/speech", api_base="https://api.openai.com/v1"),
            "https://api.openai.com/v1/audio/speech",
        )


class RetrieveContextTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex = load_lexicon()

    def test_does_not_dump_whole_lexicon(self):
        local = translate("私はアーヴです", self.lex, source_lang="ja", target_lang="baronh")
        ctx = retrieve_lexicon_context("私はアーヴです", self.lex, local=local)
        self.assertIn("abh", ctx)
        self.assertLess(ctx.count("\n"), 40)
        self.assertNotIn("全文", ctx)

    def test_lookup_tool(self):
        raw = dispatch_tool("lookup_lexicon", {"query": "アーヴ", "lang": "ja"}, self.lex)
        data = json.loads(raw)
        self.assertTrue(data["hits"])
        self.assertTrue(any("abh" in hit for hit in data["hits"]))

    def test_grammar_tool(self):
        raw = dispatch_tool("grammar_note", {"topic": "cases"}, self.lex)
        data = json.loads(raw)
        self.assertIn("主格", data["note"])

    def test_prompt_still_compact(self):
        self.assertIn("lookup_lexicon", GRAMMAR_BRIEF)
        self.assertLess(len(GRAMMAR_BRIEF), 2500)


if __name__ == "__main__":
    unittest.main()
