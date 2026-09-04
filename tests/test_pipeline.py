#!/usr/bin/env python3
"""Smoke tests for the Aarth font pipeline.

Dependabot / package bumps can be merged only when glyph detection and
font generation still succeed against the pinned requirements.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import generate_aarth_font as aarth  # noqa: E402

SOURCE_PNG = ROOT / "Ath_alphabet.png"


class DependencyImportTest(unittest.TestCase):
    def test_runtime_packages_import(self):
        import brotli  # noqa: F401
        import cv2  # noqa: F401
        import numpy  # noqa: F401
        import PIL  # noqa: F401
        from fontTools.ttLib import TTFont  # noqa: F401


class DetectGlyphsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE_PNG.is_file():
            raise AssertionError(f"missing source image: {SOURCE_PNG}")
        cls.binary = aarth.load_and_binarize(SOURCE_PNG)
        cls.boxes = aarth.find_glyph_boxes(cls.binary)

    def test_finds_expected_glyph_count(self):
        self.assertEqual(len(self.boxes), len(aarth.ALPHABET_CODEPOINTS))

    def test_boxes_have_positive_size(self):
        for i, (_x, _y, w, h) in enumerate(self.boxes):
            with self.subTest(i=i, name=aarth.GLYPH_NAMES[i]):
                self.assertGreater(w, 0)
                self.assertGreater(h, 0)


class GenerateFontTest(unittest.TestCase):
    output_dir: Path

    @classmethod
    def setUpClass(cls):
        cls.output_dir = Path(tempfile.mkdtemp(prefix="aarth-ci-"))
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "generate_aarth_font.py"),
                "--image",
                str(SOURCE_PNG),
                "--output-dir",
                str(cls.output_dir),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise AssertionError(
                "font generation failed:\n"
                f"{completed.stdout}\n{completed.stderr}"
            )

    def test_output_files_exist(self):
        ttf = self.output_dir / "aarth.ttf"
        woff2 = self.output_dir / "aarth.woff2"
        self.assertTrue(ttf.is_file(), ttf)
        self.assertTrue(woff2.is_file(), woff2)
        self.assertGreater(ttf.stat().st_size, 0)
        self.assertGreater(woff2.stat().st_size, 0)

    def test_ttf_cmap_and_outlines(self):
        from fontTools.pens.boundsPen import BoundsPen
        from fontTools.ttLib import TTFont

        font = TTFont(self.output_dir / "aarth.ttf")
        cmap = font.getBestCmap()
        self.assertIsNotNone(cmap)
        for codepoint, name in zip(aarth.ALPHABET_CODEPOINTS, aarth.ALPHABET_NAMES):
            with self.subTest(name=name, codepoint=f"U+{codepoint:04X}"):
                self.assertIn(codepoint, cmap)
                self.assertEqual(cmap[codepoint], name)
                charstrings = font["CFF "].cff.topDictIndex[0].CharStrings
                self.assertIn(name, charstrings)
                pen = BoundsPen(None)
                charstrings[name].draw(pen)
                self.assertIsNotNone(pen.bounds, f"{name} has an empty outline")
                x_min, y_min, x_max, y_max = pen.bounds
                self.assertGreater(x_max - x_min, 0)
                self.assertGreater(y_max - y_min, 0)

    def test_woff2_loads(self):
        from fontTools.ttLib import TTFont

        font = TTFont(self.output_dir / "aarth.woff2")
        self.assertEqual(font.flavor, "woff2")
        cmap = font.getBestCmap()
        self.assertEqual(len(cmap), len(aarth.ALPHABET_CODEPOINTS))


if __name__ == "__main__":
    unittest.main()
