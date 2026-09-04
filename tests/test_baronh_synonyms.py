#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from baronh.agent import dispatch_agent_tool, translate_agent
from baronh.lexicon import load_lexicon
from baronh.synonyms import coverage_plan, find_synonyms, paraphrase_source, uncovered_tokens
from baronh.translate import translate


class SynonymSearchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex = load_lexicon()

    def test_light_maps_to_shining_thing(self):
        hits = find_synonyms("光", self.lex)
        lemmas = [hit.entry.lemma for hit in hits]
        self.assertIn("sairiac", lemmas)
        self.assertNotIn("clanh", lemmas)
        via = {hit.entry.lemma: hit.via for hit in hits}
        self.assertEqual(via["sairiac"], "輝くもの")

    def test_does_not_swallow_light_compounds(self):
        hits = find_synonyms("光", self.lex)
        glosses = " ".join(hit.entry.gloss_ja for hit in hits)
        self.assertNotIn("凝集光銃", glosses)
        self.assertNotIn("光源弾倉", glosses)

    def test_see_is_exact_not_synonym_only(self):
        hits = find_synonyms("見る", self.lex)
        self.assertTrue(hits)
        self.assertEqual(hits[0].relation, "exact")
        self.assertIn(hits[0].entry.lemma, {"mire", "bie", "bicoth"})

    def test_death_bridges_to_die(self):
        hits = find_synonyms("死", self.lex)
        self.assertTrue(any(hit.entry.lemma == "rine" for hit in hits))

    def test_tool_accepts_model_paraphrases(self):
        raw = dispatch_agent_tool(
            "find_synonyms",
            {"query": "ひかり", "extra_keys": ["輝くもの", "光"]},
            self.lex,
        )
        data = json.loads(raw)
        self.assertTrue(any(hit["lemma"] == "sairiac" for hit in data["hits"]))


class SynonymCoverageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex = load_lexicon()

    def test_starlight_unknown_becomes_synonym(self):
        local = translate("星たちの光を見ます", self.lex, source_lang="ja", target_lang="baronh")
        self.assertIn("光", uncovered_tokens(local))
        plan = coverage_plan(local, self.lex)
        synonym = next(item for item in plan if item.source == "光")
        self.assertEqual(synonym.status, "synonym")
        self.assertEqual(synonym.lemma, "sairiac")
        rewritten, subs = paraphrase_source(local.source_text, plan, source_lang="ja")
        self.assertIn("輝くもの", rewritten)
        self.assertNotIn("光を", rewritten)
        self.assertEqual(subs[0]["lemma"], "sairiac")

    def test_proper_noun_is_not_synonym_replaced(self):
        local = translate("私はジントです", self.lex, source_lang="ja", target_lang="baronh")
        self.assertEqual(uncovered_tokens(local), [])
        plan = coverage_plan(local, self.lex)
        self.assertTrue(any(item.status == "phonetic" and "ジント" in item.source for item in plan))
        rewritten, subs = paraphrase_source(local.source_text, plan, source_lang="ja")
        self.assertEqual(rewritten, local.source_text)
        self.assertEqual(subs, [])

    def test_agent_without_model_uses_dictionary_synonym(self):
        out = translate_agent(
            "星たちの光を見ます",
            self.lex,
            source_lang="ja",
            target_lang="baronh",
            use_model=False,
        )
        self.assertEqual(out.engine, "agent")
        self.assertIn("sairiac", out.text.lower() + " " + json.dumps(out.substitutions, ensure_ascii=False))
        self.assertTrue(any(item.get("from") == "光" for item in out.substitutions))
        self.assertNotIn("光", out.text)
        self.assertEqual(out.source_text, "星たちの光を見ます")
        self.assertFalse(any("未登録の語は原文のまま" in note for note in out.notes))
        self.assertIn("mire", out.text)
        self.assertIn("gereulac", out.text)

    def test_agent_keeps_known_sentence(self):
        out = translate_agent(
            "私はアーヴです",
            self.lex,
            source_lang="ja",
            target_lang="baronh",
            use_model=False,
        )
        self.assertEqual(out.text, "F'a bale.")

    def test_agent_tool_loop_with_fake_chat(self):
        calls = {"n": 0}

        def chat_once(payload):
            calls["n"] += 1
            if calls["n"] == 1:
                return {
                    "choices": [{
                        "message": {
                            "tool_calls": [{
                                "id": "1",
                                "function": {
                                    "name": "find_synonyms",
                                    "arguments": json.dumps({"query": "光", "extra_keys": ["輝くもの"]}),
                                },
                            }]
                        }
                    }]
                }
            return {"choices": [{"message": {"content": "gereulacr sairiac miree."}}]}

        out = translate_agent(
            "星たちの光を見ます",
            self.lex,
            source_lang="ja",
            target_lang="baronh",
            chat_once=chat_once,
        )
        self.assertEqual(out.engine, "agent")
        self.assertIn("sairia", out.text)
        self.assertGreaterEqual(calls["n"], 2)
        invented = [note for note in out.notes if "辞書にない語形" in note]
        self.assertFalse(invented)


if __name__ == "__main__":
    unittest.main()
