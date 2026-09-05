#!/usr/bin/env python3
"""Design credits: letters by Morioka, numerals by Akai."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class DesignerCreditTest(unittest.TestCase):
    def test_docs_credit_morioka_letters_and_akai_numerals(self):
        paths = [
            ROOT / "LICENSE.md",
            ROOT / "README.md",
            ROOT / "index.html",
            ROOT / "ath" / "index.html",
            ROOT / "templates" / "digits" / "NOTICE.md",
            ROOT / "templates" / "faces" / "NOTICE.md",
        ]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn("森岡浩之", text)
                self.assertIn("赤井孝美", text)
                self.assertIn("字母", text)
                self.assertIn("数字", text)


if __name__ == "__main__":
    unittest.main()
