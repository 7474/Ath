#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from baronh.ingest import extract_pairs_from_html, ingest_file
from baronh.lexicon import write_seed_lexicon
from baronh.openai_backend import GRAMMAR_BRIEF


class IngestTest(unittest.TestCase):
    def test_html_table(self):
        html = """
        <table>
          <tr><th>アーヴ語</th><th>日本語</th></tr>
          <tr><td>abh</td><td>アーヴ</td></tr>
          <tr><td>lamh</td><td>真珠</td></tr>
        </table>
        """
        pairs = extract_pairs_from_html(html)
        lemmas = {lemma for lemma, _ja in pairs}
        self.assertIn("abh", lemmas)
        self.assertIn("lamh", lemmas)

    def test_csv_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "extra.csv"
            path.write_text("lemma,gloss_ja,gloss_en,pos\nfoo,フー,foo,noun\n", encoding="utf-8")
            doc = ingest_file(path)
            self.assertEqual(doc["count"], 1)
            self.assertEqual(doc["entries"][0]["lemma"], "foo")

    def test_parenthetical_pairs(self):
        from baronh.ingest import extract_pairs_from_text

        pairs = extract_pairs_from_text("例: usere（移る）と sace（書く）。")
        self.assertIn(("usere", "移る"), pairs)
        self.assertIn(("sace", "書く"), pairs)


class CliSmokeTest(unittest.TestCase):
    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "baronh", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_translate_agent_cli_requires_model(self):
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in {"OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE"}
        }
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "baronh",
                "translate",
                "星たちの光を見ます",
                "--from",
                "ja",
                "--to",
                "baronh",
                "--engine",
                "agent",
                "--json",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn("生成 AI", completed.stderr)

    def test_lookup_cli(self):
        completed = self._run("lookup", "abh")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("アーヴ", completed.stdout)

    def test_lookup_latin1_oe_finds_wikipedia_oelig(self):
        completed = self._run("lookup", "boerh")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("bœrh", completed.stdout)
        self.assertIn("子爵", completed.stdout)
        completed = self._run("lookup", "boe")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("boe", completed.stdout)
        self.assertIn("思う", completed.stdout)

    def test_decline_cli(self):
        completed = self._run("decline", "lamh")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("lamhle", completed.stdout)

    def test_info_cli(self):
        completed = self._run("info")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("entries:", completed.stdout)
        self.assertIn("mule.s59.xrea.com", completed.stdout)
        self.assertIn("dadh-baronr", completed.stdout)
        self.assertIn("スペシャルサンクス", completed.stdout)

    def test_web_lexicon_is_merged(self):
        path = ROOT / "web" / "data" / "lexicon.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertGreater(len(data["entries"]), 2000)
        thanks = " ".join(data.get("meta", {}).get("thanks") or [])
        self.assertIn("mule.s59.xrea.com", thanks)
        self.assertIn("dadh-baronr", thanks)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lexicon.json"
            write_seed_lexicon(path)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertGreater(len(data["entries"]), 40)
            self.assertEqual(data["entries"][0]["lemma"], "fe")

    def test_ingested_dadh_uses_wikipedia_oelig(self):
        path = ROOT / "data" / "ingested.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        lemmas = {entry["lemma"] for entry in data["entries"]}
        self.assertIn("bœrh", lemmas)
        self.assertNotIn("boerh", lemmas)
        self.assertIn("lœdame", lemmas)
        self.assertNotIn("loedame", lemmas)
        self.assertIn("luzœe", lemmas)
        self.assertNotIn("luzoee", lemmas)
        self.assertIn("boe", lemmas)
        self.assertIn("roe", lemmas)
        self.assertIn("ramgoe", lemmas)
        for entry in data["entries"]:
            if "dadh-baronr" not in (entry.get("tags") or []):
                continue
            lemma = entry["lemma"]
            for token in lemma.split():
                body = token[:-2] if token.endswith("oe") and len(token) >= 2 else token
                self.assertNotIn("oe", body, lemma)


class OpenAIPromptTest(unittest.TestCase):
    def test_prompt_mentions_cases(self):
        self.assertIn("主格", GRAMMAR_BRIEF)
        self.assertIn("F'a", GRAMMAR_BRIEF)
        self.assertIn("固有名詞", GRAMMAR_BRIEF)


if __name__ == "__main__":
    unittest.main()
