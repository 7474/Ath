#!/usr/bin/env python3
"""Raster template + optional Ath numerals."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import generate_aarth_font as aarth  # noqa: E402

SOURCE_PNG = ROOT / "Ath_alphabet.png"


def _draw_glyph_cell(img: np.ndarray, x: int, y: int, w: int, h: int, kind: int) -> None:
    """Paint a tall ink blob so it survives the letter-size filter."""
    cv2.rectangle(img, (x, y), (x + w, y + h), 0, thickness=-1)
    if kind % 3 == 1:
        cv2.rectangle(img, (x + 4, y + 4), (x + w - 5, y + h - 5), 255, thickness=-1)
        cv2.rectangle(img, (x + 8, y + 8), (x + w - 9, y + h - 9), 0, thickness=-1)
    elif kind % 3 == 2:
        cv2.ellipse(
            img, (x + w // 2, y + h // 2), (w // 3, h // 3), 0, 0, 360, 255, thickness=-1,
        )


def make_grid_image(
    row_widths: list[int],
    cell: int = 36,
    gap: int = 18,
    margin: int = 24,
    header: bool = False,
    label_h: int = 8,
) -> np.ndarray:
    """White page with black glyph rectangles in a row-major grid."""
    n_rows = len(row_widths) + (1 if header else 0)
    n_cols = max(row_widths) if row_widths else 1
    width = margin * 2 + n_cols * cell + (n_cols - 1) * gap
    row_pitch = cell + label_h + 12 + gap
    height = margin * 2 + n_rows * row_pitch
    img = np.full((height, width), 255, dtype=np.uint8)
    row_i = 0
    if header:
        for c in range(5):
            x = margin + c * (cell + gap)
            y = margin
            _draw_glyph_cell(img, x, y, cell - 4, cell - 4, c)
        row_i = 1
    kind = 0
    for widths in row_widths:
        for c in range(widths):
            x = margin + c * (cell + gap)
            y = margin + row_i * row_pitch
            _draw_glyph_cell(img, x, y, cell - 4, cell - 4, kind)
            # Short Latin-style label under the glyph (must be dropped).
            cv2.rectangle(
                img,
                (x + 6, y + cell + 2),
                (x + 16, y + cell + 2 + label_h),
                0,
                thickness=-1,
            )
            kind += 1
        row_i += 1
    return img


class DigitGridDetectionTest(unittest.TestCase):
    def test_wikipedia_sheet_has_no_digits(self):
        binary = aarth.load_and_binarize(SOURCE_PNG)
        alphabet, digits = aarth.find_alphabet_and_digit_boxes(binary)
        self.assertEqual(len(alphabet), len(aarth.ALPHABET_CODEPOINTS))
        self.assertEqual(digits, [])

    def test_combined_7_plus_3_digit_rows(self):
        gray = make_grid_image([7, 7, 7, 7, 7, 3], header=True)
        binary = aarth.binarize(gray)
        alphabet, digits = aarth.find_alphabet_and_digit_boxes(binary)
        self.assertEqual(len(alphabet), 28)
        self.assertEqual(len(digits), 10)

    def test_combined_10_wide_digit_row(self):
        gray = make_grid_image([7, 7, 7, 7, 10], header=False)
        binary = aarth.binarize(gray)
        alphabet, digits = aarth.find_alphabet_and_digit_boxes(binary)
        self.assertEqual(len(alphabet), 28)
        self.assertEqual(len(digits), 10)

    def test_digits_only_7_plus_3(self):
        gray = make_grid_image([7, 3])
        binary = aarth.binarize(gray)
        self.assertEqual(len(aarth.find_digit_boxes(binary)), 10)
        alphabet, digits = aarth.find_alphabet_and_digit_boxes(binary)
        self.assertEqual(alphabet, [])
        self.assertEqual(len(digits), 10)

    def test_empty_template_does_not_invent_digits(self):
        dest = Path(tempfile.mkdtemp(prefix="aarth-tpl-")) / "tpl.png"
        aarth.write_source_template(dest, alphabet_image=SOURCE_PNG)
        binary = aarth.load_and_binarize(dest)
        alphabet, digits = aarth.find_alphabet_and_digit_boxes(binary)
        self.assertEqual(len(alphabet), 28, msg="prefilled letters must still detect")
        self.assertEqual(digits, [], msg="empty numeral cells must not be detected")


class DigitsInFontTest(unittest.TestCase):
    def test_digits_image_lands_in_cmap(self):
        work = Path(tempfile.mkdtemp(prefix="aarth-digits-"))
        digits_png = work / "digits.png"
        cv2.imwrite(str(digits_png), make_grid_image([7, 3]))
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "generate_aarth_font.py"),
                "--image",
                str(SOURCE_PNG),
                "--digits-image",
                str(digits_png),
                "--output-dir",
                str(work),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise AssertionError(
                "font generation with digits failed:\n"
                f"{completed.stdout}\n{completed.stderr}"
            )
        from fontTools.ttLib import TTFont

        font = TTFont(work / "aarth.ttf")
        cmap = font.getBestCmap()
        self.assertIsNotNone(cmap)
        for codepoint, name in zip(aarth.ALPHABET_CODEPOINTS, aarth.ALPHABET_NAMES):
            self.assertIn(codepoint, cmap)
            self.assertEqual(cmap[codepoint], name)
        for codepoint, name in zip(aarth.DIGIT_CODEPOINTS, aarth.DIGIT_NAMES):
            self.assertIn(codepoint, cmap)
            self.assertEqual(cmap[codepoint], name)
        self.assertEqual(len(cmap), 38)


if __name__ == "__main__":
    unittest.main()
