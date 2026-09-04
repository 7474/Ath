#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from baronh.fanlex import clean_ja_gloss, entries_from_dadh_pairs, entries_from_mule_table, parse_dadh_html
from baronh.lexicon import _split_ja_aliases
from baronh.ingest import _TableParser
from baronh.phonology import fold_ascii_acute, fold_fan_romanization, fold_latin1_oelig


MULE_HTML = """
<table>
<tr><th>アーヴ語（ローマ字）</th><th>アーヴ語（カナ）</th><th>日本語</th><th>語源</th><th>参照・備考</th><th>出典</th><th>頁</th><th>綴り</th></tr>
<tr><td>zom</td><td></td><td>ありがとう。どうも</td><td>どうも</td><td></td><td>nata</td><td></td><td></td></tr>
<tr><td>usere</td><td></td><td>移る。移民する</td><td>移る</td><td></td><td>ピック</td><td></td><td></td></tr>
<tr><td>b&#339;rh</td><td>ベール</td><td>子爵。爵位の１つ</td><td>守</td><td></td><td>紋章読本</td><td></td><td></td></tr>
<tr><td>boe</td><td></td><td>思う</td><td>思う</td><td></td><td>ピック</td><td></td><td></td></tr>
<tr><td>r&uuml;&eacute; spe'nec</td><td>ルエ・スペーヌ</td><td>帝国元帥</td><td></td><td></td><td></td><td></td><td></td></tr>
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
<dt>murrautec</dt><dd>【名】故郷; (特に)ラクファカール。[jp. ふるさと]</dd>
<dt>se</dt><dd>【代名】(pl. cnac)〔人称代名詞、三人称単数主格〕かれ(は)、それ(は)〔知性体にのみ用いる。性別を特定しない〕。[jp. か(彼)]</dd>
<dt>arobe</dt><dd>【動】遊ぶ; (楽器を)演奏する。[jp. あそぶ]</dd>
<dt>symh</dt><dd>【名】隊; sarérh symr 隊長。[jp. くみ]</dd>
<dt>dhadai</dt><dd>【後】主に文末に付加し、文意の強調、聞き手への同意の請求、あるいは軽い非難の意を表わす。じゃない。ね。[jp. じゃない]</dd>
<dt>ÿéni</dt><dd>【接続】【後】理由を表す。〜だから。[jp. ゆへ(え)に]</dd>
<dt>asith</dt><dd>【名】〔昆虫〕蜻蛉。[jp. あきつ]</dd>
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
        self.assertEqual(lemmas["bœrh"].gloss_ja, "子爵")
        self.assertIn("爵位の１つ", lemmas["bœrh"].notes)
        self.assertIn("boe", lemmas)
        self.assertNotIn("boerh", lemmas)
        self.assertIn("rüé spénec", lemmas)
        self.assertNotIn("rüé spe'nec", lemmas)

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
        self.assertEqual(by_lemma["murrautec"].gloss_ja, "故郷")
        self.assertIn("ラクファカール", by_lemma["murrautec"].notes)
        self.assertNotIn("ラクファカール", by_lemma["murrautec"].gloss_ja)
        self.assertEqual(by_lemma["se"].pos, "pronoun")
        self.assertEqual(by_lemma["se"].gloss_ja, "かれ / それ")
        self.assertEqual(by_lemma["arobe"].gloss_ja, "遊ぶ / 演奏する")
        self.assertEqual(by_lemma["symh"].gloss_ja, "隊")
        self.assertIn("sarérh", by_lemma["symh"].notes)
        self.assertIn("じゃない", by_lemma["dhadai"].gloss_ja)
        self.assertIn("ね", by_lemma["dhadai"].gloss_ja)
        self.assertEqual(by_lemma["ÿéni"].gloss_ja, "〜だから")
        self.assertEqual(by_lemma["asith"].gloss_ja, "蜻蛉")
        self.assertIn("昆虫", by_lemma["asith"].notes)


class CleanJaGlossTest(unittest.TestCase):
    def test_viscount_encyclopedia_is_note(self):
        gloss, notes = clean_ja_gloss(
            "子爵。爵位の一。男爵の上、伯爵の下。有人化可能な惑星を領地にもつ貴族。"
        )
        self.assertEqual(gloss, "子爵")
        self.assertIn("爵位の一", notes)

    def test_compound_examples_are_notes(self):
        gloss, notes = clean_ja_gloss("週。- lyga 来週")
        self.assertEqual(gloss, "週")
        self.assertIn("lyga", notes)

    def test_semicolon_usage_note(self):
        gloss, notes = clean_ja_gloss("故郷; (特に)ラクファカール")
        self.assertEqual(gloss, "故郷")
        self.assertIn("ラクファカール", notes)
        self.assertNotIn("ラクファカール", gloss)

    def test_semicolon_keeps_real_senses(self):
        gloss, notes = clean_ja_gloss("遊ぶ; (楽器を)演奏する")
        self.assertEqual(gloss, "遊ぶ / 演奏する")
        self.assertIn("楽器を", notes)

    def test_semicolon_latin_example_is_note(self):
        gloss, notes = clean_ja_gloss("隊; sarérh symr 隊長")
        self.assertEqual(gloss, "隊")
        self.assertIn("sarérh", notes)

    def test_period_encyclopedia_note(self):
        gloss, notes = clean_ja_gloss("子爵。爵位の１つ")
        self.assertEqual(gloss, "子爵")
        self.assertIn("爵位の１つ", notes)

    def test_domain_label(self):
        gloss, notes = clean_ja_gloss("〔昆虫〕蜻蛉")
        self.assertEqual(gloss, "蜻蛉")
        self.assertIn("昆虫", notes)

    def test_invariable_number(self):
        gloss, notes = clean_ja_gloss("(不変化)百")
        self.assertEqual(gloss, "百")
        self.assertIn("不変化", notes)

    def test_pos_mark_and_reason(self):
        gloss, _notes = clean_ja_gloss("【後】理由を表す。〜だから")
        self.assertEqual(gloss, "〜だから")

    def test_speculation(self):
        gloss, notes = clean_ja_gloss("赤の意か")
        self.assertEqual(gloss, "赤")
        self.assertIn("の意か", notes)

    def test_pronoun_grammar_wrapper(self):
        gloss, notes = clean_ja_gloss(
            "(pl. cnac)〔人称代名詞、三人称単数主格〕かれ(は)、それ(は)〔知性体にのみ用いる〕"
        )
        self.assertEqual(gloss, "かれ / それ")
        self.assertIn("人称代名詞", notes)

    def test_latin_wrapper_and_mixed_example(self):
        gloss, notes = clean_ja_gloss("(一説に osnac)女の子")
        self.assertEqual(gloss, "女の子")
        self.assertIn("osnac", notes)
        gloss, notes = clean_ja_gloss("愛 frymec/frycec négr")
        self.assertEqual(gloss, "愛")
        self.assertIn("frymec", notes)

    def test_aliases_drop_tokuni_supplement(self):
        aliases = _split_ja_aliases("故郷; (特に)ラクファカール")
        self.assertIn("故郷", aliases)
        self.assertFalse(any("ラクファカール" in item for item in aliases))

    def test_long_sibling_definition_is_note(self):
        gloss, notes = clean_ja_gloss(
            "閣下。貴族、領主代行、千翔長以上の軍士、前者に相当する高級官僚、領民代表および他国の相当する役職にあるもの等の称号。"
        )
        self.assertEqual(gloss, "閣下")
        self.assertIn("称号", notes)

    def test_quoted_prefix(self):
        gloss, _notes = clean_ja_gloss("「大きい」「規模の大きな」を示す")
        self.assertEqual(gloss, "大きい / 規模の大きな")


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

    def test_ascii_acute_and_non_ath_letters(self):
        self.assertEqual(fold_ascii_acute("spe'nec"), "spénec")
        self.assertEqual(fold_ascii_acute("F'a"), "F'a")
        self.assertEqual(fold_fan_romanization("ïku"), "ïcu")
        self.assertEqual(fold_fan_romanization("rüé spe'nec"), "rüé spénec")


if __name__ == "__main__":
    unittest.main()
