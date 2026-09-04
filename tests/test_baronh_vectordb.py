#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from baronh.agent import (
    AgentModelRequired,
    agent_system_prompt,
    build_agent_user_prompt,
    dispatch_agent_tool,
    translate_agent,
)
from baronh.grammar import grammar_context
from baronh.lexicon import load_lexicon
from baronh.vectordb import get_index


class VectorIndexTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex = load_lexicon()
        cls.index = get_index(cls.lex)

    def test_light_ranks_shining_thing_first(self):
        hits = self.index.search("光", limit=8)
        self.assertTrue(hits)
        self.assertEqual(hits[0].entry.lemma, "sairiac")
        lemmas = [hit.entry.lemma for hit in hits]
        glosses = " ".join(hit.entry.gloss_ja for hit in hits)
        self.assertNotIn("凝集光銃", glosses)
        self.assertNotIn("光源弾倉", glosses)
        self.assertIn("sairiac", lemmas)

    def test_see_finds_mire(self):
        hits = self.index.search("見る", limit=8)
        lemmas = [hit.entry.lemma for hit in hits]
        self.assertTrue({"mire", "bie", "bicoth"} & set(lemmas))

    def test_search_lexicon_tool(self):
        raw = dispatch_agent_tool("search_lexicon", {"query": "光", "limit": 6}, self.lex)
        data = json.loads(raw)
        self.assertEqual(data["query"], "光")
        self.assertTrue(any(hit["lemma"] == "sairiac" for hit in data["hits"]))
        self.assertFalse(any("凝集光銃" in (hit.get("gloss_ja") or "") for hit in data["hits"]))


class AgentPromptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex = load_lexicon()

    def test_system_prompt_embeds_full_grammar(self):
        prompt = agent_system_prompt("baronh")
        grammar = grammar_context()
        self.assertIn(grammar, prompt)
        self.assertIn("ベクトル検索", prompt)
        self.assertNotIn("規則ベースの下訳は渡しません。なぞらないでください。", grammar)
        self.assertIn("規則ベースの下訳は渡しません", prompt)

    def test_user_prompt_uses_vector_hits_not_rule_draft(self):
        prompt = build_agent_user_prompt(
            "星たちの光を見ます",
            self.lex,
            source_lang="ja",
            target_lang="baronh",
        )
        self.assertIn("ベクトル検索", prompt)
        self.assertIn("sairiac", prompt)
        self.assertIn("search_lexicon", prompt)
        self.assertNotIn("規則ベースの下訳（誤り・抜けあり", prompt)


class AgentRequiresModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex = load_lexicon()

    def test_raises_without_model(self):
        env = {"OPENAI_API_KEY": "", "OPENAI_BASE_URL": "", "OPENAI_API_BASE": ""}
        with mock.patch.dict("os.environ", env, clear=False):
            with self.assertRaises(AgentModelRequired):
                translate_agent(
                    "星たちの光を見ます",
                    self.lex,
                    source_lang="ja",
                    target_lang="baronh",
                    api_key="",
                    api_base="",
                )


class AgentFakeChatTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex = load_lexicon()

    def test_tool_loop_with_vector_search(self):
        calls = {"n": 0, "payloads": []}

        def chat_once(payload):
            calls["n"] += 1
            calls["payloads"].append(payload)
            if calls["n"] == 1:
                return {
                    "choices": [{
                        "message": {
                            "tool_calls": [{
                                "id": "1",
                                "function": {
                                    "name": "search_lexicon",
                                    "arguments": json.dumps({"query": "光"}),
                                },
                            }]
                        }
                    }]
                }
            return {"choices": [{"message": {"content": "gereulacr sairiac mire."}}]}

        out = translate_agent(
            "星たちの光を見ます",
            self.lex,
            source_lang="ja",
            target_lang="baronh",
            chat_once=chat_once,
        )
        self.assertEqual(out.engine, "agent")
        self.assertEqual(out.source_text, "星たちの光を見ます")
        self.assertIn("sairia", out.text)
        self.assertIn("mire", out.text)
        self.assertGreaterEqual(calls["n"], 2)
        first = calls["payloads"][0]
        system = first["messages"][0]["content"]
        user = first["messages"][1]["content"]
        self.assertIn("主格", system)
        self.assertIn("直説法", system)
        self.assertIn("sairiac", user)
        self.assertNotIn("規則ベースの下訳（誤り・抜けあり", user)
        invented = [note for note in out.notes if "辞書にない語形" in note]
        self.assertFalse(invented)


if __name__ == "__main__":
    unittest.main()
