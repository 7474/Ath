#!/usr/bin/env python3
"""Tests for Ath glyph detection and the stroke-trace preprocessing."""

import unittest
from pathlib import Path

import numpy as np

from generate_aarth_font import (
    GLYPH_CODEPOINTS,
    GLYPH_NAMES,
    TRACE_BLACKLEVEL,
    binarize,
    crop_glyph,
    find_glyph_boxes,
    load_grayscale,
    prepare_glyph_for_trace,
)

IMAGE = Path(__file__).resolve().parent / "Ath_alphabet.png"


def _horizontal_breaks(mask: np.ndarray) -> int:
    """Count paper pixels that have ink immediately on both left and right."""
    count = 0
    for row in mask:
        for x in range(1, len(row) - 1):
            if row[x] == 0 and row[x - 1] == 255 and row[x + 1] == 255:
                count += 1
    return count


class GlyphTracePrepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gray = load_grayscale(IMAGE)
        cls.binary = binarize(cls.gray)
        cls.boxes = find_glyph_boxes(cls.binary)

    def test_detects_full_alphabet(self):
        self.assertEqual(len(self.boxes), len(GLYPH_CODEPOINTS))

    def test_trace_crop_is_native_grayscale(self):
        box = self.boxes[0]
        native = crop_glyph(self.gray, box)
        prepared = prepare_glyph_for_trace(self.gray, box)
        self.assertEqual(prepared.shape, native.shape)
        self.assertLess(int(prepared.min()), 40)
        self.assertGreater(int(prepared.max()), 200)

    def test_inclusive_blacklevel_seals_p_stroke_gap(self):
        """Ath 'p' has a 1-px break in the bottom bowl under Otsu."""
        p_idx = GLYPH_NAMES.index("p")
        box = self.boxes[p_idx]
        otsu = crop_glyph(self.binary, box)
        native_breaks = _horizontal_breaks(otsu)
        self.assertGreater(native_breaks, 0)

        prepared = prepare_glyph_for_trace(self.gray, box)
        ink = np.where(prepared < TRACE_BLACKLEVEL * 255, 255, 0).astype(np.uint8)
        self.assertLess(_horizontal_breaks(ink), native_breaks)


if __name__ == "__main__":
    unittest.main()
