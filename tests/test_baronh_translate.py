#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from baronh.lexicon import load_lexicon
from baronh.phonology import reading_ja, to_ath_keys
from baronh.translate import detect_lang, translate


class TranslateJaBaronhTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex = load_lexicon([])

    def test_i_immigrate(self):
        out = translate("私は移民します", self.lex, source_lang="ja", target_lang="baronh")
        self.assertEqual(out.text, "F'a usere.")

    def test_i_am_abh(self):
        out = translate("私はアーヴです", self.lex, source_lang="ja", target_lang="baronh")
        self.assertEqual(out.text, "F'a bale.")
        self.assertNotIn("usere", out.text)

    def test_your_family(self):
        out = translate("あなたの家族は？", self.lex, source_lang="ja", target_lang="baronh")
        self.assertIn("dar", out.text.lower())
        self.assertIn("saurh", out.text)
        self.assertTrue(out.text.endswith("?") or "sa" in out.text)

    def test_stars_vocative(self):
        out = translate("星たちよ", self.lex, source_lang="ja", target_lang="baronh")
        self.assertIn("éü", out.text)
        self.assertTrue("gereulach" in out.text or "greuc" in out.text)

    def test_do_you_understand(self):
        out = translate("分かりますか", self.lex, source_lang="ja", target_lang="baronh")
        self.assertRegex(out.text, r"face")
        self.assertIn("sa", out.text)
        self.assertNotIn("ります", out.text)

    def test_fa_usere_to_ja(self):
        out = translate("F'a usere.", self.lex, source_lang="baronh", target_lang="ja")
        self.assertIn("私", out.text)
        self.assertIn("移民", out.text)

    def test_fa_bale_to_ja(self):
        out = translate("F'a bale.", self.lex, source_lang="baronh", target_lang="ja")
        self.assertIn("アーヴ", out.text)

    def test_detect_ja(self):
        self.assertEqual(detect_lang("私はアーヴです", self.lex), "ja")

    def test_detect_baronh(self):
        self.assertEqual(detect_lang("F'a usere.", self.lex), "baronh")

    def test_arigatou(self):
        from baronh.translate import _tokenize_ja

        self.assertEqual(_tokenize_ja("ありがとう", self.lex), ["ありがとう"])
        out = translate("ありがとう", self.lex, source_lang="ja", target_lang="baronh")
        self.assertIn("zom", out.text.lower())
        self.assertNotIn("férsi", out.text)
        self.assertNotIn("う.", out.text)

    def test_hai_not_split_as_topic(self):
        out = translate("はい", self.lex, source_lang="ja", target_lang="baronh")
        self.assertIn("dara", out.text.lower())

    def test_unknown_proper_noun_phonetic(self):
        out = translate("私はジントです", self.lex, source_lang="ja", target_lang="baronh")
        self.assertEqual(out.text, "F'a ghintole.")
        self.assertTrue(any("発音転記" in (item.note or "") for item in out.analysis))
        self.assertTrue(any("発音から転記" in note for note in out.notes))
        self.assertIn("ジント→ghintoc", " ".join(out.notes))
        self.assertNotRegex(out.text, r"[jkwvJKWV]")
        self.assertIn("ジント", out.reading_ja)

    def test_unknown_proper_noun_topic(self):
        out = translate("ジントはアーヴです", self.lex, source_lang="ja", target_lang="baronh")
        self.assertEqual(out.text, "ghintoc a bale.")
        self.assertNotIn("ジント", out.text)
        self.assertNotIn("jinto", out.text.lower())
        self.assertIn("ジント", out.reading_ja)

    def test_dictionary_name_not_phonetic(self):
        out = translate("私はアーヴです", self.lex, source_lang="ja", target_lang="baronh")
        self.assertEqual(out.text, "F'a bale.")
        self.assertFalse(any("発音転記" in note for note in out.notes))

    def test_english_capitalized_name(self):
        out = translate("Jinto is Abh", self.lex, source_lang="en", target_lang="baronh")
        self.assertIn("ghintoc", out.text.lower())
        self.assertIn("bale", out.text)
        self.assertTrue(any("発音から転記" in note for note in out.notes))
        self.assertNotIn("jinto", out.text.lower())

    def test_baronh_unknown_name_to_kana(self):
        out = translate("Jinto a bale.", self.lex, source_lang="baronh", target_lang="ja")
        self.assertIn("ジント", out.text)
        self.assertIn("アーヴ", out.text)
        self.assertTrue(any("発音から転記" in note for note in out.notes))


class TranslateWithIngestedLexiconTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex = load_lexicon()

    def test_expanded_dictionary(self):
        self.assertGreater(len(self.lex.entries), 2000)

    def test_i_immigrate_still_holds(self):
        out = translate("私は移民します", self.lex, source_lang="ja", target_lang="baronh")
        self.assertEqual(out.text, "F'a usere.")

    def test_i_am_abh_still_holds(self):
        out = translate("私はアーヴです", self.lex, source_lang="ja", target_lang="baronh")
        self.assertEqual(out.text, "F'a bale.")

    def test_arigatou_from_fan_sources(self):
        hits = self.lex.lookup("ありがとう", lang="ja")
        self.assertTrue(hits)
        out = translate("ありがとう", self.lex, source_lang="ja", target_lang="baronh")
        self.assertIn("zom", out.text.lower())

    def test_unknown_proper_noun_with_fan_lexicon(self):
        out = translate("私はジントです", self.lex, source_lang="ja", target_lang="baronh")
        self.assertEqual(out.text, "F'a ghintole.")
        self.assertTrue(any("発音から転記" in note for note in out.notes))

    def test_local_vector_search_is_opt_in(self):
        off = translate("星たちの光を見ます", self.lex, source_lang="ja", target_lang="baronh")
        self.assertIn("光", off.text)
        self.assertFalse(off.substitutions)
        on = translate(
            "星たちの光を見ます",
            self.lex,
            source_lang="ja",
            target_lang="baronh",
            vector_search=True,
        )
        self.assertIn("sairiac", on.text)
        self.assertNotIn("光", on.unknown)
        self.assertTrue(any(item.get("lemma") == "sairiac" for item in on.substitutions))
        self.assertTrue(any("ベクトル検索" in note for note in on.notes))

    def test_local_vector_search_skips_proper_nouns(self):
        on = translate(
            "私はジントです",
            self.lex,
            source_lang="ja",
            target_lang="baronh",
            vector_search=True,
        )
        self.assertEqual(on.text, "F'a ghintole.")
        self.assertFalse(on.substitutions)


class PhonologyTest(unittest.TestCase):
    def test_ath_keys_digraphs(self):
        self.assertEqual(to_ath_keys("sairh"), "sArh")
        self.assertEqual(to_ath_keys("laure"), "lIre")
        self.assertEqual(to_ath_keys("greuc"), "grEc")

    def test_reading_abh(self):
        reading = reading_ja("abh")
        self.assertTrue(reading)
        self.assertIn("ア", reading)

    def test_kana_to_baronh_jinto(self):
        from baronh.phonology import kana_to_baronh, transcribe_proper_to_baronh

        self.assertEqual(kana_to_baronh("ジント"), "ghinto")
        self.assertEqual(transcribe_proper_to_baronh("ジント"), "ghintoc")
        self.assertEqual(kana_to_baronh("トウキョウ"), "tocio")
        self.assertEqual(kana_to_baronh("ヴァンス"), "bhansu")
        self.assertEqual(reading_ja("ghintoc a bale."), "ジント ア バレ。")


if __name__ == "__main__":
    unittest.main()
