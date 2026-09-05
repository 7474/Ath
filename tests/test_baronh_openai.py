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

    def test_tool_loop_restates_source_after_tools(self):
        from baronh.openai_backend import run_chat_tool_loop, tool_answer_now

        payloads: list[dict] = []

        def fake_chat(payload):
            payloads.append(payload)
            if len(payloads) == 1:
                return {
                    "choices": [{
                        "message": {
                            "tool_calls": [{
                                "id": "c1",
                                "function": {
                                    "name": "lookup_lexicon",
                                    "arguments": json.dumps({"queries": ["アーヴ"]}, ensure_ascii=False),
                                },
                            }]
                        }
                    }]
                }
            return {"choices": [{"message": {"content": "F'a bale."}}]}

        src = "私はアーヴです"
        messages = [{"role": "user", "content": src}]
        out, rounds = run_chat_tool_loop(
            url="http://example/v1/chat/completions",
            api_key="no-key",
            model="gemini-3.5-flash-lite",
            messages=messages,
            lexicon=self.lex,
            use_tools=True,
            chat_once=fake_chat,
            source_text=src,
            max_tokens=2048,
        )
        self.assertEqual(out, "F'a bale.")
        self.assertEqual(rounds, 2)
        last = messages[-1]["content"]
        self.assertEqual(last, tool_answer_now(src))
        self.assertIn(src, last)
        self.assertIn("省略せず", last)
        self.assertEqual(payloads[-1].get("max_tokens"), 2048)


class SourceCoverageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex = load_lexicon()

    def test_split_sample_paragraph(self):
        from baronh.openai_backend import (
            coverage_incomplete,
            finalize_translation,
            format_numbered_source,
            split_source_units,
        )

        src = (
            "アーヴ語翻訳機\n\n"
            "リン・ジントって奴はあれでなかなか頭の出来がいい。"
            "なんたって故郷、俺らの、ついでにアーヴ語を読み書き出来るんだからな。"
            "よく分からん言葉を喋ってると別人に見えて困る。"
            "だからと言ってアーヴ語なんて覚える気はない、覚えられない訳じゃないぜ？"
            "　とは言えアーヴ語で何を喋ってるのか気にならんこともない。"
            "てな訳で機械に翻訳機を作って貰った。"
            "これでアーヴ語の読み書きは完璧だぜ。\n\n"
            "って、何喋ってるかは分からないじゃねーか！"
        )
        units = split_source_units(src)
        self.assertGreaterEqual(len(units), 8)
        self.assertEqual(units[0], "アーヴ語翻訳機")
        self.assertTrue(units[-1].endswith("！") or "分からない" in units[-1])
        numbered = format_numbered_source(src)
        self.assertIn("[1]", numbered)
        self.assertIn("[2]", numbered)
        short = "ringhintoc a almee éni. murrautec farh, lo barone gobhoth."
        self.assertTrue(coverage_incomplete(src, short))
        self.assertFalse(coverage_incomplete("私はアーヴです", "F'a bale."))
        numbered_out = "[1] F'a bale.\n[2] face sa?"
        self.assertEqual(
            finalize_translation("私はアーヴです。分かりますか。", numbered_out),
            "F'a bale.\nface sa?",
        )

    def test_agent_continues_same_session_for_missing_units(self):
        from baronh.agent import translate_agent

        src = "私はアーヴです。分かりますか。"
        calls: list[dict] = []

        def chat_once(payload):
            calls.append(json.loads(json.dumps(payload)))
            last = payload["messages"][-1]
            n = len(calls)
            if n == 1:
                return {
                    "choices": [{
                        "message": {
                            "tool_calls": [{
                                "id": "1",
                                "function": {
                                    "name": "search_lexicon",
                                    "arguments": json.dumps({"queries": ["アーヴ"]}),
                                },
                            }]
                        }
                    }]
                }
            if "未訳" in last.get("content", "") or "欠けて" in last.get("content", ""):
                self.assertTrue(any(m.get("role") == "tool" for m in payload["messages"]))
                return {
                    "choices": [{
                        "message": {"content": "[1] F'a bale.\n[2] face sa?"}
                    }]
                }
            if payload.get("tool_choice") == "none":
                self.assertIn("私はアーヴです", last.get("content", ""))
                self.assertIn("[1]", last.get("content", ""))
                return {"choices": [{"message": {"content": "F'a bale."}}]}
            return {"choices": [{"message": {"content": "[1] F'a bale.\n[2] face sa?"}}]}

        out = translate_agent(src, self.lex, source_lang="ja", target_lang="baronh", chat_once=chat_once)
        self.assertIn("bale", out.text)
        self.assertIn("face", out.text)
        self.assertNotIn("[1]", out.text)
        self.assertNotIn("[2]", out.text)
        self.assertGreaterEqual(len(calls), 3)
        self.assertTrue(any("未訳単位" in note or "追記" in note for note in out.notes))

    def test_rewrite_keeps_tool_history(self):
        from baronh.agent import translate_agent

        src = "私はアーヴです"
        calls: list[dict] = []

        def chat_once(payload):
            calls.append(payload)
            n = len(calls)
            if n == 1:
                return {
                    "choices": [{
                        "message": {
                            "tool_calls": [{
                                "id": "1",
                                "function": {
                                    "name": "search_lexicon",
                                    "arguments": json.dumps({"queries": ["アーヴ"]}),
                                },
                            }]
                        }
                    }]
                }
            if n == 2:
                return {"choices": [{"message": {"content": "F'a xyzzy."}}]}
            roles = [m.get("role") for m in payload["messages"]]
            self.assertIn("tool", roles)
            self.assertTrue(any("xyzzy" in str(m.get("content") or "") for m in payload["messages"]))
            return {"choices": [{"message": {"content": "F'a bale."}}]}

        out = translate_agent(src, self.lex, source_lang="ja", target_lang="baronh", chat_once=chat_once)
        self.assertIn("bale", out.text)
        self.assertGreaterEqual(len(calls), 3)


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
