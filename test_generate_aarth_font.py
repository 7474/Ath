#!/usr/bin/env python3
"""Tests for Ath glyph detection and the stroke-trace preprocessing."""

import unittest
from pathlib import Path

import numpy as np

from generate_aarth_font import (
    ALPHABET_CODEPOINTS,
    ALPHABET_NAMES,
    SOURCE_INK_LEVEL,
    TRACE_BLACKLEVEL,
    TRACE_SCALE,
    binarize,
    crop_glyph,
    find_glyph_boxes,
    load_grayscale,
    prepare_glyph_for_trace,
    split_ink_components,
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
        self.assertEqual(len(self.boxes), len(ALPHABET_CODEPOINTS))

    def test_trace_canvases_are_upscaled_silhouettes(self):
        box = self.boxes[0]
        native = crop_glyph(self.gray, box)
        canvases = prepare_glyph_for_trace(self.gray, self.binary, box)
        self.assertGreaterEqual(len(canvases), 1)
        h, w = native.shape
        for canvas in canvases:
            self.assertEqual(canvas.shape, (h * TRACE_SCALE, w * TRACE_SCALE))
            # Thin Ath strokes only reach ~2px into the SDF; that still
            # maps well below the 0.5 blacklevel used by potrace.
            self.assertLess(int(canvas.min()), 110)
            self.assertGreater(int(canvas.max()), 200)

    def test_inclusive_ink_level_seals_p_stroke_gap(self):
        """Ath 'p' has a 1-px break in the bottom bowl under Otsu."""
        p_idx = ALPHABET_NAMES.index("p")
        box = self.boxes[p_idx]
        otsu = crop_glyph(self.binary, box)  # white = ink
        native_breaks = _horizontal_breaks(otsu)
        self.assertGreater(native_breaks, 0)

        gray_crop = crop_glyph(self.gray, box)
        loose = np.where(gray_crop < SOURCE_INK_LEVEL * 255, 255, 0).astype(np.uint8)
        self.assertLess(_horizontal_breaks(loose), native_breaks)

    def test_diacritics_stay_separate_components(self):
        """Umlaut dots / overlines must not be welded to the letter body."""
        expected = {
            "h": 1,
            "p": 1,
            "idieresis": 2,
            "z": 3,
            "d": 3,
            "b": 3,
            "g": 3,
        }
        for name, n in expected.items():
            idx = ALPHABET_NAMES.index(name)
            box = self.boxes[idx]
            masks = split_ink_components(
                crop_glyph(self.gray, box),
                crop_glyph(self.binary, box),
            )
            self.assertEqual(len(masks), n, msg=name)

    def test_blurred_silhouette_blacklevel_is_mid_ramp(self):
        self.assertAlmostEqual(TRACE_BLACKLEVEL, 0.5)


if __name__ == "__main__":
    unittest.main()
