#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from baronh.grammar import analyze_form, conjugate, decline, topic_contract
from baronh.lexicon import load_lexicon


class DeclensionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex = load_lexicon([])

    def _entry(self, lemma: str, pos: str = "noun"):
        hits = [e for e in self.lex.lookup(lemma, lang="baronh") if e.pos == pos]
        self.assertTrue(hits, lemma)
        return hits[0]

    def test_type1_abh(self):
        forms = decline(self._entry("abh"))
        self.assertEqual(forms["nom"], "abh")
        self.assertEqual(forms["acc"], "abe")
        self.assertEqual(forms["gen"], "bar")
        self.assertEqual(forms["dat"], "bari")
        self.assertEqual(forms["all"], "baré")
        self.assertEqual(forms["abl"], "abhar")
        self.assertEqual(forms["ins"], "bale")

    def test_type2_lamh(self):
        forms = decline(self._entry("lamh"))
        self.assertEqual(forms, {
            "nom": "lamh",
            "acc": "lame",
            "gen": "lamr",
            "dat": "lami",
            "all": "lamé",
            "abl": "lamhar",
            "ins": "lamhle",
        })

    def test_type3_duc(self):
        forms = decline(self._entry("duc"))
        self.assertEqual(forms["acc"], "dul")
        self.assertEqual(forms["all"], "dugh")
        self.assertEqual(forms["abl"], "dusar")

    def test_type4_saidiac(self):
        forms = decline(self._entry("saidiac"))
        self.assertEqual(forms["acc"], "saidél")
        self.assertEqual(forms["gen"], "saidér")
        self.assertEqual(forms["abl"], "saidiasar")
        self.assertEqual(forms["ins"], "saidéle")

    def test_pronoun_fe(self):
        forms = decline(self._entry("fe", "pronoun"))
        self.assertEqual(forms["acc"], "fal")
        self.assertEqual(forms["gen"], "far")
        self.assertEqual(topic_contract(forms["nom"]), "F'a")


class ConjugationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex = load_lexicon([])

    def _verb(self, lemma: str):
        return next(e for e in self.lex.lookup(lemma, lang="baronh") if e.pos == "verb")

    def test_sac_endings(self):
        sac = self._verb("sac")
        self.assertEqual(conjugate(sac), "sace")
        self.assertEqual(conjugate(sac, aspect="perfect"), "sacle")
        self.assertEqual(conjugate(sac, voices=("causative", "passive")), "sacasare")
        self.assertEqual(conjugate(sac, voices=("passive", "negative")), "sacarade")
        self.assertEqual(conjugate(sac, voices=("causative", "passive", "negative")), "sacasarade")

    def test_user_indefinite(self):
        self.assertEqual(conjugate(self._verb("user")), "usere")

    def test_analyze_sace(self):
        hits = analyze_form("sace", self.lex)
        self.assertTrue(hits)
        self.assertEqual(hits[0].entry.lemma, "sac")
        self.assertEqual(hits[0].mood, "indicative")


if __name__ == "__main__":
    unittest.main()
