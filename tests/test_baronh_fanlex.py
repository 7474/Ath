#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from baronh.fanlex import entries_from_dadh_pairs, entries_from_mule_table, parse_dadh_html
from baronh.ingest import _TableParser
from baronh.phonology import fold_latin1_oelig


MULE_HTML = """
<table>
<tr><th>アーヴ語（ローマ字）</th><th>アーヴ語（カナ）</th><th>日本語</th><th>語源</th><th>参照・備考</th><th>出典</th><th>頁</th><th>綴り</th></tr>
<tr><td>zom</td><td></td><td>ありがとう。どうも</td><td>どうも</td><td></td><td>nata</td><td></td><td></td></tr>
<tr><td>usere</td><td></td><td>移る。移民する</td><td>移る</td><td></td><td>ピック</td><td></td><td></td></tr>
<tr><td>b&#339;rh</td><td>ベール</td><td>子爵。爵位の１つ</td><td>守</td><td></td><td>紋章読本</td><td></td><td></td></tr>
<tr><td>boe</td><td></td><td>思う</td><td>思う</td><td></td><td>ピック</td><td></td><td></td></tr>
</table>
"""

DADH_HTML = """
<dl>
<dt>zom</dt><dd>【感】ありがとう。どうも。[jp. どうも]</dd>
<dt>Abh</dt><dd>【名】gen. Bar. アーヴ。[jp. あま]</dd>
<dt>agaime</dt><dd>【動】殺す。殺害する。[jp. あやむ]</dd>
<dt>boerh</dt><dd>【名】gen. Boerr. 子爵。[jp. もり]</dd>
<dt>ramgoe</dt><dd>【動】さまよう。[jp. まよふ]</dd>
<dt>luzoee</dt><dd>【動】集まる。[jp. つどふ]</dd>
</dl>
"""


class FanlexParseTest(unittest.TestCase):
    def test_mule_table(self):
        parser = _TableParser()
        parser.feed(MULE_HTML)
        entries = entries_from_mule_table(parser.tables[0], source="mule")
        lemmas = {e.lemma: e for e in entries}
        self.assertIn("zom", lemmas)
        self.assertIn("ありがとう", lemmas["zom"].gloss_ja)
        self.assertEqual(lemmas["zom"].pos, "noun")
        self.assertEqual(lemmas["usere"].pos, "verb")
        self.assertEqual(lemmas["usere"].stem, "user")
        self.assertIn("bœrh", lemmas)
        self.assertEqual(lemmas["bœrh"].gloss_ja, "子爵。爵位の１つ")
        self.assertIn("boe", lemmas)
        self.assertNotIn("boerh", lemmas)

    def test_dadh_dl(self):
        pairs = parse_dadh_html(DADH_HTML)
        entries = entries_from_dadh_pairs(pairs, source="dadh")
        by_lemma = {e.lemma: e for e in entries}
        self.assertEqual(by_lemma["abh"].pos, "noun")
        self.assertEqual(by_lemma["abh"].paradigm.get("gen"), "bar")
        self.assertEqual(by_lemma["agaime"].pos, "verb")
        self.assertEqual(by_lemma["zom"].pos, "interjection")
        self.assertIn("bœrh", by_lemma)
        self.assertEqual(by_lemma["bœrh"].paradigm.get("gen"), "bœrr")
        self.assertIn("ramgoe", by_lemma)
        self.assertEqual(by_lemma["ramgoe"].stem, "ramgo")
        self.assertEqual(by_lemma["luzœe"].pos, "verb")
        self.assertEqual(by_lemma["luzœe"].stem, "luzœ")
        self.assertNotIn("boerh", by_lemma)
        self.assertNotIn("luzoee", by_lemma)


class AthRomanizationFoldTest(unittest.TestCase):
    def test_latin1_oe_becomes_oelig(self):
        self.assertEqual(fold_latin1_oelig("boerh"), "bœrh")
        self.assertEqual(fold_latin1_oelig("loedame"), "lœdame")
        self.assertEqual(fold_latin1_oelig("luzoee"), "luzœe")
        self.assertEqual(fold_latin1_oelig("cafoer-ec"), "cafœr-ec")
        self.assertEqual(fold_latin1_oelig("faicec syrgzoedér"), "faicec syrgzœdér")
        self.assertEqual(fold_latin1_oelig("bœrh"), "bœrh")

    def test_word_final_oe_is_stem_plus_infinitive(self):
        self.assertEqual(fold_latin1_oelig("boe"), "boe")
        self.assertEqual(fold_latin1_oelig("roe"), "roe")
        self.assertEqual(fold_latin1_oelig("ramgoe"), "ramgoe")


if __name__ == "__main__":
    unittest.main()
