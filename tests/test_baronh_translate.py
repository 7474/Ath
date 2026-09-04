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
        self.assertIn("F'a", out.text)
        self.assertIn("usere", out.text)

    def test_i_am_abh(self):
        out = translate("私はアーヴです", self.lex, source_lang="ja", target_lang="baronh")
        self.assertIn("F'a", out.text)
        self.assertIn("bale", out.text)

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
        self.assertIn("fac", out.text.lower())
        self.assertIn("sa", out.text)

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


class PhonologyTest(unittest.TestCase):
    def test_ath_keys_digraphs(self):
        self.assertEqual(to_ath_keys("sairh"), "sArh")
        self.assertEqual(to_ath_keys("laure"), "lIre")
        self.assertEqual(to_ath_keys("greuc"), "grEc")

    def test_reading_abh(self):
        reading = reading_ja("abh")
        self.assertTrue(reading)
        self.assertIn("ア", reading)


if __name__ == "__main__":
    unittest.main()
