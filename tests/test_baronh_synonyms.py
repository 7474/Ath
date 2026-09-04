#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from baronh.agent import dictionary_hints, dispatch_agent_tool
from baronh.grammar import FormIndex
from baronh.lexicon import load_lexicon
from baronh.openai_backend import invented_baronh_forms
from baronh.phonology import transcribe_proper_noun
from baronh.synonyms import (
    coverage_plan,
    find_synonyms,
    hint_query_pieces,
    name_for_transcription,
    paraphrase_source,
    resolve_lexicon_hits,
    uncovered_tokens,
)
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


class ColloquialLexiconTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex = load_lexicon()

    def test_spoken_bridges(self):
        talk = {hit.entry.lemma for hit in find_synonyms("喋る", self.lex)}
        self.assertTrue({"cadase", "canse", "banas", "clare", "ie"} & talk)
        self.assertTrue(any(hit.entry.lemma == "farh" for hit in find_synonyms("俺ら", self.lex)))
        self.assertTrue(any(hit.entry.lemma in {"batta", "bata"} for hit in find_synonyms("完璧", self.lex)))
        self.assertTrue(any(hit.entry.lemma == "éni" for hit in find_synonyms("いい", self.lex)))
        machine = {hit.entry.lemma for hit in find_synonyms("翻訳機", self.lex)}
        self.assertIn("catorac", machine)
        self.assertTrue(any(hit.entry.lemma == "rire" for hit in find_synonyms("覚える", self.lex)))

    def test_hint_peels_katakana_name(self):
        self.assertEqual(hint_query_pieces("リン・ジントって奴"), ["リン・ジント"])
        self.assertEqual(name_for_transcription("リン・ジントって奴"), "リン・ジント")
        lemma, _kind = transcribe_proper_noun(name_for_transcription("リン・ジントって奴"))
        self.assertIn("rin", lemma)
        self.assertIn("ghint", lemma)
        self.assertNotIn("linghinth", lemma.replace(" ", ""))
        raw = dispatch_agent_tool("transcribe_name", {"name": "リン・ジントって奴"}, self.lex)
        data = json.loads(raw)
        self.assertIn("rin", data["lemma"])
        self.assertIn("ghint", data["lemma"])

    def test_search_prefers_dictionary_over_weak_vector(self):
        hits = resolve_lexicon_hits("頭の出来がいい", self.lex)
        lemmas = {hit["lemma"] for hit in hits}
        glosses = " ".join(str(hit.get("gloss_ja") or "") for hit in hits)
        self.assertTrue({"almec", "éni"} & lemmas)
        self.assertNotIn("領民", glosses)
        raw = dispatch_agent_tool("search_lexicon", {"query": "頭の出来がいい"}, self.lex)
        data = json.loads(raw)
        tool_lemmas = {hit["lemma"] for hit in data["hits"]}
        self.assertTrue({"almec", "éni"} & tool_lemmas)
        self.assertFalse(any("領民" in (hit.get("gloss_ja") or "") for hit in data["hits"]))
        light = json.loads(dispatch_agent_tool("search_lexicon", {"query": "光"}, self.lex))
        self.assertTrue(any(hit["lemma"] == "sairiac" for hit in light["hits"]))
        bother = resolve_lexicon_hits("困る", self.lex)
        self.assertFalse(any(hit["lemma"] == "cigamh" for hit in bother))

    def test_hints_expose_name_and_lexicon_not_leftover_chunk(self):
        hints = dictionary_hints("リン・ジントって奴はあれでなかなか頭の出来がいい。", self.lex, "ja")
        self.assertIn("リン・ジント", hints)
        self.assertNotIn("リン・ジントって奴", hints)
        self.assertIn("almec", hints)
        self.assertIn("éni", hints)

    def test_grammar_affixes_are_not_invented(self):
        self.assertNotIn("lér", invented_baronh_forms("cadase lér.", self.lex))
        self.assertNotIn("ad", invented_baronh_forms("fac ad e.", self.lex))
        self.assertNotIn("iri", invented_baronh_forms("iri sacre.", self.lex))
        self.assertTrue(FormIndex(self.lex).lookup("iri"))
        self.assertIn("xyzzy", invented_baronh_forms("F'a xyzzy.", self.lex))


if __name__ == "__main__":
    unittest.main()
