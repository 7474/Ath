#!/usr/bin/env python3
"""Glyph vector integrity: reverse-winding contours vs source-raster holes."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import generate_aarth_font as aarth  # noqa: E402

TTF = ROOT / "aarth.ttf"
SOURCE = aarth.FILLED_TEMPLATE


class EnclosedHoleCountTest(unittest.TestCase):
    def test_solid_blob_has_no_hole(self):
        ink = np.zeros((20, 20), np.uint8)
        ink[4:16, 4:16] = 255
        self.assertEqual(aarth.count_enclosed_holes(ink), 0)

    def test_ring_has_one_hole(self):
        ink = np.zeros((24, 24), np.uint8)
        ink[2:22, 2:22] = 255
        ink[8:16, 8:16] = 0
        self.assertEqual(aarth.count_enclosed_holes(ink), 1)


class CommittedFontVectorTest(unittest.TestCase):
    def test_no_extra_reverse_winding_vs_filled_template(self):
        self.assertTrue(TTF.is_file(), TTF)
        self.assertTrue(SOURCE.is_file(), SOURCE)
        reports = aarth.check_font_vectors(TTF, SOURCE)
        self.assertEqual(len(reports), 38)
        bad = [row for row in reports if not row["ok"]]
        self.assertEqual(
            bad, [],
            msg=aarth.format_vector_report(reports),
        )

    def test_check_vectors_cli_exits_zero(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "generate_aarth_font.py"),
                "--check-vectors",
                str(TTF),
                "--image",
                str(SOURCE),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("0 glyph(s) with extra reverse-winding contours", completed.stdout)


class CssWeightCoverageTest(unittest.TestCase):
    def test_aarth_css_registers_bold_against_regular_files(self):
        css = (ROOT / "aarth.css").read_text(encoding="utf-8")
        self.assertIn("font-weight: 400;", css)
        self.assertIn("font-weight: 600;", css)
        self.assertIn("font-weight: 700;", css)
        self.assertNotIn("font-weight: normal;", css)
        self.assertIn("font-synthesis: none;", css)

    def test_ath_demo_disables_heading_bold(self):
        demo = (ROOT / "ath" / "index.html").read_text(encoding="utf-8")
        self.assertIn("font-synthesis: none", demo)
        self.assertIn("font-weight: 400", demo)
        site = (ROOT / "site.css").read_text(encoding="utf-8")
        self.assertIn("body:not(.translated) .page-content :is(h1, h2, h3, h4, h5, h6, strong, b, th)", site)
        self.assertIn("font-synthesis: none", site)


if __name__ == "__main__":
    unittest.main()
