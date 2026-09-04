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
    build_user_prompt,
    clean_model_text,
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
        self.assertLess(len(GRAMMAR_BRIEF), 2500)
        self.assertLess(len(system_prompt("baronh")), 8000)
        self.assertIn("F'a bale.", system_prompt("baronh"))

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
        from baronh.openai_backend import CHAT_TOOLS

        lookup = next(tool["function"] for tool in CHAT_TOOLS if tool["function"]["name"] == "lookup_lexicon")
        self.assertEqual(lookup["parameters"]["required"], ["queries"])
        self.assertNotIn("query", lookup["parameters"]["properties"])

    def test_lookup_tool_batches_queries(self):
        from baronh.openai_backend import collect_lookup_queries

        self.assertEqual(collect_lookup_queries({"queries": ["頭", "星", "頭"]}), ["頭", "星"])
        self.assertEqual(collect_lookup_queries({"query": "頭"}), ["頭"])
        raw = dispatch_tool("lookup_lexicon", {"queries": ["アーヴ", "見る"], "lang": "ja"}, self.lex)
        data = json.loads(raw)
        self.assertEqual([row["query"] for row in data["results"]], ["アーヴ", "見る"])
        self.assertTrue(any("abh" in hit for hit in data["results"][0]["hits"]))

    def test_prompt_asks_to_batch(self):
        self.assertIn("queries", GRAMMAR_BRIEF)
        self.assertIn("1語ずつ", GRAMMAR_BRIEF)

    def test_tool_loop_forces_answer_after_one_batch(self):
        from baronh.openai_backend import TOOL_ANSWER_NOW, run_chat_tool_loop

        payloads: list[dict] = []

        def fake_chat(payload):
            payloads.append(json.loads(json.dumps(payload)))
            if len(payloads) == 1:
                return {
                    "choices": [{
                        "message": {
                            "tool_calls": [{
                                "id": "c1",
                                "function": {
                                    "name": "lookup_lexicon",
                                    "arguments": json.dumps({"queries": ["アーヴ", "私"]}, ensure_ascii=False),
                                },
                            }]
                        }
                    }]
                }
            return {"choices": [{"message": {"content": "F'a bale."}}]}

        messages = [{"role": "user", "content": "私はアーヴです"}]
        out, rounds = run_chat_tool_loop(
            url="http://example/v1/chat/completions",
            api_key="no-key",
            model="gemini-3.5-flash-lite",
            messages=messages,
            lexicon=self.lex,
            use_tools=True,
            chat_once=fake_chat,
        )
        self.assertEqual(out, "F'a bale.")
        self.assertEqual(rounds, 2)
        self.assertEqual(payloads[0]["tool_choice"], "auto")
        self.assertEqual(payloads[1]["tool_choice"], "none")
        self.assertEqual(messages[-1]["content"], TOOL_ANSWER_NOW)


class ChatRequestRetryTest(unittest.TestCase):
    def test_retries_503_then_succeeds(self):
        import io
        from unittest import mock
        from urllib.error import HTTPError

        from baronh.openai_backend import _request

        calls = {"n": 0}

        def fake_urlopen(req, timeout=60):
            calls["n"] += 1
            if calls["n"] < 3:
                raise HTTPError(req.full_url, 503, "unavailable", hdrs=None, fp=io.BytesIO(b"busy"))

            class Resp:
                def read(self):
                    return b'{"ok":true}'

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

            return Resp()

        with mock.patch("baronh.openai_backend.urllib.request.urlopen", fake_urlopen):
            with mock.patch("baronh.openai_backend._sleep"):
                raw = _request("http://example.test/v1/chat/completions", "key", {"model": "x"})
        self.assertEqual(raw, b'{"ok":true}')
        self.assertEqual(calls["n"], 3)

    def test_does_not_retry_400(self):
        import io
        from unittest import mock
        from urllib.error import HTTPError

        from baronh.openai_backend import _request

        calls = {"n": 0}

        def fake_urlopen(req, timeout=60):
            calls["n"] += 1
            raise HTTPError(req.full_url, 400, "bad", hdrs=None, fp=io.BytesIO(b"no"))

        with mock.patch("baronh.openai_backend.urllib.request.urlopen", fake_urlopen):
            with mock.patch("baronh.openai_backend._sleep"):
                with self.assertRaises(RuntimeError) as ctx:
                    _request("http://example.test/v1/chat/completions", "key", {"model": "x"})
        self.assertIn("400", str(ctx.exception))
        self.assertEqual(calls["n"], 1)


if __name__ == "__main__":
    unittest.main()
