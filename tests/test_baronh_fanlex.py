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


MULE_HTML = """
<table>
<tr><th>アーヴ語（ローマ字）</th><th>アーヴ語（カナ）</th><th>日本語</th><th>語源</th><th>参照・備考</th><th>出典</th><th>頁</th><th>綴り</th></tr>
<tr><td>zom</td><td></td><td>ありがとう。どうも</td><td>どうも</td><td></td><td>nata</td><td></td><td></td></tr>
<tr><td>usere</td><td></td><td>移る。移民する</td><td>移る</td><td></td><td>ピック</td><td></td><td></td></tr>
</table>
"""

DADH_HTML = """
<dl>
<dt>zom</dt><dd>【感】ありがとう。どうも。[jp. どうも]</dd>
<dt>Abh</dt><dd>【名】gen. Bar. アーヴ。[jp. あま]</dd>
<dt>agaime</dt><dd>【動】殺す。殺害する。[jp. あやむ]</dd>
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

    def test_dadh_dl(self):
        pairs = parse_dadh_html(DADH_HTML)
        entries = entries_from_dadh_pairs(pairs, source="dadh")
        by_lemma = {e.lemma: e for e in entries}
        self.assertEqual(by_lemma["abh"].pos, "noun")
        self.assertEqual(by_lemma["abh"].paradigm.get("gen"), "bar")
        self.assertEqual(by_lemma["agaime"].pos, "verb")
        self.assertEqual(by_lemma["zom"].pos, "interjection")


if __name__ == "__main__":
    unittest.main()
