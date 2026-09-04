#!/usr/bin/env python3
"""OpenAI-compatible Base URL, retrieval, and TTS URL tests."""

from __future__ import annotations

import io
import json
import unittest
from pathlib import Path
from unittest import mock

import ath_openai as api
import ath_retrieve as kr
import ath_translate_llm as llm

ROOT = Path(__file__).resolve().parent.parent


class BaseUrlTests(unittest.TestCase):
    def test_default_is_official_openai(self):
        self.assertEqual(api.chat_completions_url(None), "https://api.openai.com/v1/chat/completions")
        self.assertEqual(api.chat_completions_url(""), "https://api.openai.com/v1/chat/completions")
        self.assertEqual(api.chat_completions_url("https://api.openai.com"), "https://api.openai.com/v1/chat/completions")
        self.assertEqual(api.audio_speech_url(None), "https://api.openai.com/v1/audio/speech")

    def test_compatible_roots(self):
        self.assertEqual(
            api.chat_completions_url("http://127.0.0.1:11434/v1"),
            "http://127.0.0.1:11434/v1/chat/completions",
        )
        self.assertEqual(
            api.audio_speech_url("https://openrouter.ai/api/v1/"),
            "https://openrouter.ai/api/v1/audio/speech",
        )
        self.assertEqual(
            api.chat_completions_url("http://localhost:1234"),
            "http://localhost:1234/v1/chat/completions",
        )


class RetrieveTests(unittest.TestCase):
    def test_lexicon_finds_abh(self):
        hits = kr.search_lexicon("アーヴ")
        self.assertTrue(any(e["baronh"] == "abh" for e in hits))

    def test_grammar_finds_cases(self):
        hits = kr.search_grammar("生格 関係節")
        ids = [c["id"] for c in hits]
        self.assertIn("noun-cases", ids)

    def test_retrieve_does_not_dump_entire_lexicon(self):
        pack = kr.retrieve("星")
        self.assertLess(len(pack["lexicon"]), len(kr.load_lexicon()))
        self.assertTrue(any(e["ja"] == "星" for e in pack["lexicon"]))

    def test_keys_to_ipa(self):
        self.assertIn("k", kr.keys_to_ipa("acA"))  # c → k, A → ai
        self.assertTrue(kr.keys_to_ipa("ath").startswith("a"))


class TranslateLoopTests(unittest.TestCase):
    def test_posts_to_custom_base_and_fills_ipa(self):
        captured = {}

        class FakeResponse:
            def __init__(self, payload):
                self._raw = json.dumps(payload).encode("utf-8")

            def read(self):
                return self._raw

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(req, timeout=60):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return FakeResponse({
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "baronh": "abh",
                            "notesJa": ["種辞書の abh を使いました。"],
                            "used": ["abh"],
                        }, ensure_ascii=False)
                    }
                }]
            })

        result = llm.translate(
            "アーヴ",
            base_url="http://127.0.0.1:8765/v1",
            api_key="sk-compat",
            model="compat-demo",
            urlopen=fake_urlopen,
        )
        self.assertEqual(captured["url"], "http://127.0.0.1:8765/v1/chat/completions")
        self.assertEqual(captured["body"]["model"], "compat-demo")
        self.assertTrue(captured["body"]["messages"][1]["content"])
        self.assertEqual(result["baronh"], "abh")
        self.assertTrue(result["ipa"])
        self.assertEqual(result["speechUrl"], "http://127.0.0.1:8765/v1/audio/speech")

    def test_tool_round_then_answer(self):
        calls = []

        class FakeResponse:
            def __init__(self, payload):
                self._raw = json.dumps(payload).encode("utf-8")

            def read(self):
                return self._raw

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(req, timeout=60):
            calls.append(json.loads(req.data.decode("utf-8")))
            if len(calls) == 1:
                return FakeResponse({
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "tool_calls": [{
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "search_lexicon",
                                    "arguments": json.dumps({"query": "星"}),
                                },
                            }],
                        }
                    }]
                })
            return FakeResponse({
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "baronh": "greuc",
                            "notesJa": ["search_lexicon で greuc を引きました。"],
                            "used": ["greuc"],
                        }, ensure_ascii=False)
                    }
                }]
            })

        result = llm.translate("星", base_url="http://127.0.0.1:9/v1", urlopen=fake_urlopen)
        self.assertEqual(result["baronh"], "greuc")
        self.assertTrue(any(step.get("name") == "search_lexicon" for step in result["trace"]))
        self.assertEqual(len(calls), 2)

    def test_demo_exposes_compat_base_and_tts_explanation(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("ath-api-base", html)
        self.assertIn("互換 API", html)
        self.assertIn("audio/speech", html)
        self.assertIn("search_lexicon", html)


if __name__ == "__main__":
    unittest.main()
