#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from baronh.asr import recognize
from baronh.g2p import compact_reading, g2p_ipa, g2p_reading_ja
from baronh.langpack import (
    decline_entry,
    grammar_context_for,
    init_lang,
    list_pack_ids,
    load_pack,
    noun_stem,
)
from baronh.lexicon import load_lexicon
from baronh.phonology import reading_ja
from baronh.transfer import translate_pack
from baronh.translate import translate


class LangpackLoadTest(unittest.TestCase):
    def test_lists_builtin_packs(self):
        ids = list_pack_ids()
        self.assertIn("mina", ids)
        self.assertIn("baronh", ids)

    def test_mina_fields(self):
        pack = load_pack("mina")
        self.assertEqual(pack.names["ja"], "ミーナ語")
        self.assertEqual(pack.syntax.topic.particle, "ya")
        self.assertEqual(pack.morphology.verb_endings[("indicative", "indefinite")], "u")
        lex = pack.load_lexicon()
        self.assertTrue(lex.lookup("mina", lang="mina"))
        self.assertTrue(lex.lookup("私", lang="ja"))

    def test_baronh_pack_delegates_lexicon(self):
        pack = load_pack("baronh")
        lex = pack.load_lexicon()
        self.assertTrue(lex.lookup("abh", lang="baronh"))
        self.assertIn("主格", grammar_context_for(pack))


class MinaMorphologyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = load_pack("mina")
        cls.lex = cls.pack.load_lexicon()

    def _noun(self, lemma: str):
        return next(e for e in self.lex.lookup(lemma, lang="mina") if e.pos in {"noun", "pronoun"})

    def test_mina_ins(self):
        forms = decline_entry(self._noun("mina"), self.pack)
        self.assertEqual(noun_stem(self._noun("mina"), self.pack), "min")
        self.assertEqual(forms["nom"], "mina")
        self.assertEqual(forms["acc"], "mino")
        self.assertEqual(forms["ins"], "minde")

    def test_sora_acc(self):
        forms = decline_entry(self._noun("sora"), self.pack)
        self.assertEqual(forms["acc"], "soro")

    def test_nama_dat(self):
        forms = decline_entry(self._noun("nama"), self.pack)
        self.assertEqual(forms["dat"], "nami")

    def test_pronoun_paradigm(self):
        forms = decline_entry(self._noun("na"), self.pack)
        self.assertEqual(forms["ins"], "nade")


class MinaTranslateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = load_pack("mina")
        cls.lex = cls.pack.load_lexicon()

    def test_i_am_mina(self):
        out = translate_pack("私はミーナです", self.pack, self.lex, source_lang="ja", target_lang="mina")
        self.assertEqual(out.text, "na ya minde.")
        self.assertEqual(out.engine, "transfer")

    def test_see_star(self):
        out = translate_pack("星を見る", self.pack, self.lex, source_lang="ja", target_lang="mina")
        self.assertEqual(out.text, "soro miru.")

    def test_go_to_water(self):
        out = translate_pack("水に行く", self.pack, self.lex, source_lang="ja", target_lang="mina")
        self.assertEqual(out.text, "nami piru.")

    def test_question(self):
        out = translate_pack("星を見ますか", self.pack, self.lex, source_lang="ja", target_lang="mina")
        self.assertIn("soro", out.text)
        self.assertIn("miru", out.text)
        self.assertTrue(out.text.endswith("?") or "ka" in out.text)

    def test_back_to_ja(self):
        out = translate_pack("na ya minde.", self.pack, self.lex, source_lang="mina", target_lang="ja")
        self.assertIn("私", out.text)
        self.assertIn("ミーナ", out.text)
        self.assertNotIn("がは", out.text)
        self.assertIn("は", out.text)

    def test_en_see_star(self):
        out = translate_pack("see the star", self.pack, self.lex, source_lang="en", target_lang="mina")
        self.assertIn("soro", out.text)
        self.assertIn("miru", out.text)


class G2pAsrTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mina = load_pack("mina")
        cls.baronh = load_pack("baronh")

    def test_mina_reading(self):
        reading = g2p_reading_ja("na ya minde.", self.mina)
        compact = compact_reading(reading)
        self.assertIn("ナ", compact)
        self.assertIn("ヤ", compact)
        self.assertIn("ミンデ", compact)

    def test_mina_ipa(self):
        ipa = g2p_ipa("mina", self.mina)
        self.assertIn("m", ipa)
        self.assertIn("i", ipa)

    def test_mina_recognize_roundtrip(self):
        spoken = g2p_reading_ja("na ya minde.", self.mina)
        result = recognize(spoken, self.mina)
        self.assertIn("na", result.text)
        self.assertIn("ya", result.text)
        self.assertIn("minde", result.text)
        self.assertFalse(result.unknown)

    def test_baronh_g2p_matches_legacy(self):
        sample = "F'a bale."
        self.assertEqual(g2p_reading_ja(sample, self.baronh), reading_ja(sample))

    def test_baronh_recognize_kana(self):
        spoken = reading_ja("F'a bale.")
        result = recognize(spoken, self.baronh)
        compact_out = compact_reading(reading_ja(result.text))
        self.assertEqual(compact_out, compact_reading(spoken))
        self.assertEqual(result.text, "F'a bale.")

    def test_baronh_builtin_untouched(self):
        lex = load_lexicon([])
        out = translate("私はアーヴです", lex, source_lang="ja", target_lang="baronh")
        self.assertEqual(out.text, "F'a bale.")


class InitLangTest(unittest.TestCase):
    def test_copy_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = init_lang(
                "keth",
                name_ja="ケス語",
                name_en="Keth",
                autonym="keth",
                langs_dir=Path(tmp),
                template_id="mina",
            )
            pack = load_pack("keth", langs_dir=Path(tmp))
            self.assertEqual(pack.id, "keth")
            self.assertEqual(pack.name_ja, "ケス語")
            self.assertTrue((dest / "lexicon.json").is_file())
            meta = json.loads((dest / "lexicon.json").read_text(encoding="utf-8"))["meta"]
            self.assertEqual(meta["language"], "keth")


class CliLangpackTest(unittest.TestCase):
    def test_translate_mina_cli(self):
        from baronh.cli import main
        from io import StringIO
        import contextlib

        buf = StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["translate", "私はミーナです", "--from", "ja", "--to", "mina"])
        self.assertEqual(code, 0)
        self.assertEqual(buf.getvalue().strip(), "na ya minde.")

    def test_languages_cli(self):
        from baronh.cli import main
        from io import StringIO
        import contextlib

        buf = StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["languages"])
        self.assertEqual(code, 0)
        self.assertIn("mina", buf.getvalue())
        self.assertIn("baronh", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
