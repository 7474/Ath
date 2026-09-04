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
    CHAT_TOOLS,
    GRAMMAR_BRIEF,
    TOOL_ANSWER_NOW,
    TOOL_BATCH_RULE,
    _run_tool_loop,
    api_url,
    build_user_prompt,
    clean_model_text,
    collect_grammar_topics,
    collect_lookup_queries,
    describe_gaps,
    dispatch_tool,
    invented_baronh_forms,
    normalize_api_base,
    retrieve_lexicon_context,
    retrieve_lexicon_entries,
    system_prompt,
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
        self.assertIn("queries", GRAMMAR_BRIEF)
        self.assertIn("1語ずつ", GRAMMAR_BRIEF)
        self.assertIn("queries", TOOL_BATCH_RULE)
        self.assertLess(len(GRAMMAR_BRIEF), 2500)
        self.assertLess(len(system_prompt("baronh")), 8000)
        self.assertIn("F'a bale.", system_prompt("baronh"))
        prompt = build_user_prompt(
            "私はアーヴです",
            self.lex,
            local=translate("私はアーヴです", self.lex, source_lang="ja", target_lang="baronh"),
            target_lang="baronh",
        )
        self.assertIn("queries", prompt)
        self.assertIn("1語ずつ", prompt)

    def test_immigrate_retrieves_user(self):
        src = "私は移民します"
        local = translate(src, self.lex, source_lang="ja", target_lang="baronh")
        lemmas = {entry.lemma for entry in retrieve_lexicon_entries(src, self.lex, local=local)}
        self.assertIn("user", lemmas)
        self.assertIn("fe", lemmas)

    def test_typo_vu_bu_retrieves_abh(self):
        from baronh.lexicon import fold_for_match, fuzzy_points

        self.assertEqual(fold_for_match("アーブ"), fold_for_match("アーヴ"))
        self.assertGreaterEqual(fuzzy_points("アーブ", "アーヴ"), 300)
        self.assertEqual(fuzzy_points("ジント", "サイ・ジント様"), 0)
        src = "私はアーブです"
        local = translate(src, self.lex, source_lang="ja", target_lang="baronh")
        lemmas = {entry.lemma for entry in retrieve_lexicon_entries(src, self.lex, local=local)}
        self.assertIn("abh", lemmas)
        gaps = describe_gaps(local, self.lex)
        self.assertIn("abh", gaps)
        self.assertIn("優先", gaps)

    def test_kana_long_vowel_retrieves_abh(self):
        src = "私はあーヴです"
        local = translate(src, self.lex, source_lang="ja", target_lang="baronh")
        lemmas = {entry.lemma for entry in retrieve_lexicon_entries(src, self.lex, local=local)}
        self.assertIn("abh", lemmas)

    def test_jinto_still_not_a_dictionary_substring(self):
        src = "ジントはアーヴです"
        local = translate(src, self.lex, source_lang="ja", target_lang="baronh")
        lemmas = [entry.lemma for entry in retrieve_lexicon_entries(src, self.lex, local=local)]
        self.assertIn("abh", lemmas)
        self.assertNotIn("saïc ramh ghinter", lemmas)
        self.assertNotIn("bate", lemmas)
        self.assertEqual(local.text, "ghintoc a bale.")
        gaps = describe_gaps(local, self.lex)
        self.assertNotIn("サイ・ジント", gaps)
        self.assertIn("発音転記", gaps)

    def test_full_scan_ranks_abh(self):
        local = translate("私はアーヴです", self.lex, source_lang="ja", target_lang="baronh")
        lemmas = {entry.lemma for entry in retrieve_lexicon_entries("私はアーヴです", self.lex, local=local)}
        self.assertTrue({"fe", "a", "abh"} <= lemmas)
        self.assertNotIn("bar frybarec", lemmas)
        self.assertLess(len(lemmas), 12)

    def test_full_scan_finds_stars_and_see(self):
        src = "星たちの光を見ます"
        local = translate(src, self.lex, source_lang="ja", target_lang="baronh")
        lemmas = [entry.lemma for entry in retrieve_lexicon_entries(src, self.lex, local=local)]
        self.assertIn("gereulach", lemmas)
        self.assertIn("mire", lemmas)
        self.assertNotIn("clanh", lemmas)
        self.assertNotIn("sacochoth", lemmas)
        self.assertNotIn("slona", lemmas)
        gaps = describe_gaps(local, self.lex)
        self.assertIn("光", gaps)
        self.assertIn("造語せず", gaps)

    def test_user_prompt_includes_gaps_and_draft(self):
        src = "星たちの光を見ます"
        local = translate(src, self.lex, source_lang="ja", target_lang="baronh")
        prompt = build_user_prompt(src, self.lex, local=local, target_lang="baronh")
        self.assertIn("下訳", prompt)
        self.assertIn("光", prompt)
        self.assertIn("gereulach", prompt)

    def test_lookup_tool_strips_masu(self):
        raw = dispatch_tool("lookup_lexicon", {"query": "見ます", "lang": "ja"}, self.lex)
        data = json.loads(raw)
        self.assertTrue(data["hits"])
        self.assertTrue(any("mire" in hit or "見る" in hit for hit in data["hits"]))
        from baronh.lexicon import ja_query_variants
        self.assertIn("移民する", ja_query_variants("移民します"))

    def test_invented_forms_detected(self):
        local = translate("私はアーヴです", self.lex, source_lang="ja", target_lang="baronh")
        self.assertEqual(invented_baronh_forms("F'a bale.", self.lex, local=local), [])
        self.assertIn("xyzzy", invented_baronh_forms("F'a xyzzy.", self.lex, local=local))
        phonetic = translate("私はジントです", self.lex, source_lang="ja", target_lang="baronh")
        self.assertEqual(invented_baronh_forms(phonetic.text, self.lex, local=phonetic), [])
        self.assertEqual(invented_baronh_forms("F'a ghintoc.", self.lex, local=phonetic), [])
        self.assertIn("jinto", invented_baronh_forms("F'a jinto.", self.lex, local=phonetic))

    def test_clean_model_text(self):
        self.assertEqual(clean_model_text("```\nF'a bale.\n```"), "F'a bale.")

    def test_search_does_not_dump_light_compounds(self):
        ctx = retrieve_lexicon_context("光", self.lex)
        self.assertLess(ctx.count("\n"), 12)


class BatchToolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex = load_lexicon()

    def test_schema_requires_queries_array(self):
        lookup = next(tool["function"] for tool in CHAT_TOOLS if tool["function"]["name"] == "lookup_lexicon")
        grammar = next(tool["function"] for tool in CHAT_TOOLS if tool["function"]["name"] == "grammar_note")
        self.assertEqual(lookup["parameters"]["required"], ["queries"])
        self.assertEqual(lookup["parameters"]["properties"]["queries"]["type"], "array")
        self.assertNotIn("query", lookup["parameters"]["properties"])
        self.assertEqual(grammar["parameters"]["required"], ["topics"])
        self.assertNotIn("topic", grammar["parameters"]["properties"])
        self.assertIn("1語ずつ", lookup["description"])

    def test_collect_lookup_queries_batches_and_dedupes(self):
        self.assertEqual(collect_lookup_queries({"queries": ["頭", "星", "頭"]}), ["頭", "星"])
        self.assertEqual(collect_lookup_queries({"query": "頭"}), ["頭"])
        self.assertEqual(collect_lookup_queries({"queries": "頭、星,見る"}), ["頭", "星", "見る"])
        self.assertEqual(collect_lookup_queries({"queries": ["頭"], "query": "星"}), ["頭", "星"])

    def test_lookup_tool_batches_queries(self):
        raw = dispatch_tool("lookup_lexicon", {"queries": ["アーヴ", "見る"], "lang": "ja"}, self.lex)
        data = json.loads(raw)
        self.assertEqual([row["query"] for row in data["results"]], ["アーヴ", "見る"])
        abh = data["results"][0]["hits"]
        see = data["results"][1]["hits"]
        self.assertTrue(any("abh" in hit for hit in abh))
        self.assertTrue(any("mire" in hit or "見る" in hit for hit in see))

    def test_grammar_tool_batches_topics(self):
        self.assertEqual(collect_grammar_topics({"topics": ["cases", "verbs"]}), ["cases", "verbs"])
        raw = dispatch_tool("grammar_note", {"topics": ["cases", "verbs"]}, self.lex)
        data = json.loads(raw)
        self.assertEqual([row["topic"] for row in data["notes"]], ["cases", "verbs"])
        self.assertIn("主格", data["notes"][0]["note"])
        self.assertIn("直説法", data["notes"][1]["note"])

    def test_web_engine_matches_batch_schema(self):
        src = (ROOT / "web" / "js" / "engine.js").read_text(encoding="utf-8")
        app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('required: ["queries"]', src)
        self.assertIn('required: ["topics"]', src)
        self.assertIn("TOOL_ANSWER_NOW", src)
        self.assertIn("1語ずつ", src)
        self.assertIn('tool_choice = answerNow ? "none" : "auto"', app)
        self.assertIn("TOOL_ANSWER_NOW", app)

    def test_tool_loop_batches_then_forces_answer(self):
        payloads: list[dict] = []

        def fake_chat(_url, _key, payload):
            payloads.append(json.loads(json.dumps(payload)))
            if len(payloads) == 1:
                return {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "id": "c1",
                                        "type": "function",
                                        "function": {
                                            "name": "lookup_lexicon",
                                            "arguments": json.dumps(
                                                {"queries": ["アーヴ", "私"]},
                                                ensure_ascii=False,
                                            ),
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            return {"choices": [{"message": {"role": "assistant", "content": "F'a bale."}}]}

        from unittest.mock import patch

        messages = [{"role": "user", "content": "私はアーヴです"}]
        with patch("baronh.openai_backend._chat_once", side_effect=fake_chat):
            out, rounds = _run_tool_loop(
                url="http://example/v1/chat/completions",
                api_key="no-key",
                model="gemini-3.5-flash-lite",
                messages=messages,
                lexicon=self.lex,
                use_tools=True,
            )
        self.assertEqual(out, "F'a bale.")
        self.assertEqual(rounds, 2)
        self.assertEqual(payloads[0]["tool_choice"], "auto")
        self.assertEqual(payloads[1]["tool_choice"], "none")
        self.assertEqual(messages[-1]["content"], TOOL_ANSWER_NOW)
        self.assertEqual(messages[-1]["role"], "user")
        tool_msg = next(m for m in messages if m.get("role") == "tool")
        data = json.loads(tool_msg["content"])
        self.assertEqual([row["query"] for row in data["results"]], ["アーヴ", "私"])

    def test_tool_loop_ignores_second_single_token_call(self):
        payloads: list[dict] = []

        def fake_chat(_url, _key, payload):
            payloads.append(payload)
            if len(payloads) == 1:
                return {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "id": "c1",
                                        "function": {
                                            "name": "lookup_lexicon",
                                            "arguments": '{"query":"頭"}',
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            if payload.get("tool_choice") == "none":
                return {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "id": "c2",
                                        "function": {
                                            "name": "lookup_lexicon",
                                            "arguments": '{"query":"星"}',
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            return {"choices": [{"message": {"role": "assistant", "content": "F'a bale."}}]}

        from unittest.mock import patch

        messages = [{"role": "user", "content": "頭"}]
        with patch("baronh.openai_backend._chat_once", side_effect=fake_chat):
            out, rounds = _run_tool_loop(
                url="http://example/v1/chat/completions",
                api_key="no-key",
                model="gemini-3.5-flash-lite",
                messages=messages,
                lexicon=self.lex,
                use_tools=True,
            )
        self.assertEqual(out, "F'a bale.")
        self.assertEqual(rounds, 3)
        self.assertEqual(payloads[1]["tool_choice"], "none")
        self.assertNotIn("tools", payloads[2])
        self.assertEqual(sum(1 for m in messages if m.get("role") == "tool"), 1)
        first_tool = next(m for m in messages if m.get("role") == "tool")
        self.assertIn("頭", first_tool["content"])
        self.assertNotIn('"query": "星"', first_tool["content"])


if __name__ == "__main__":
    unittest.main()
