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
    def test_page_edge_stripe_does_not_hide_glyphs(self):
        gray = make_grid_image([7, 7, 7, 7, 7, 3], header=True)
        gray[:, -3:] = 0
        binary = aarth.binarize(gray)
        alphabet, digits = aarth.find_alphabet_and_digit_boxes(binary)
        self.assertEqual(len(alphabet), 28)
        self.assertEqual(len(digits), 10)

    def test_red_sign_pen_ink_is_detected(self):
        gray = make_grid_image([7, 7, 7, 7, 7, 3], header=False)
        bgr = np.full((*gray.shape, 3), 255, dtype=np.uint8)
        bgr[gray < 128] = (18, 22, 190)
        dest = Path(tempfile.mkdtemp(prefix="aarth-red-")) / "red.png"
        cv2.imwrite(str(dest), bgr)
        binary = aarth.load_and_binarize(dest)
        alphabet, digits = aarth.find_alphabet_and_digit_boxes(binary)
        self.assertEqual(len(alphabet), 28)
        self.assertEqual(len(digits), 10)

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

    def test_blank_template_has_no_glyphs(self):
        dest = Path(tempfile.mkdtemp(prefix="aarth-blank-")) / "blank.png"
        aarth.write_source_template(dest, blank=True)
        binary = aarth.load_and_binarize(dest)
        alphabet, digits = aarth.find_alphabet_and_digit_boxes(binary)
        self.assertEqual(alphabet, [], msg="blank sheet must not invent letters")
        self.assertEqual(digits, [], msg="blank sheet must not invent digits")

    def test_write_source_templates_emits_reading_and_blank(self):
        dest = Path(tempfile.mkdtemp(prefix="aarth-both-"))
        paths = aarth.write_source_templates(dest, alphabet_image=SOURCE_PNG)
        filled, blank = paths[0], paths[1]
        self.assertEqual(filled.name, "ath_source_template.png")
        self.assertEqual(blank.name, "ath_blank_template.png")
        self.assertTrue(filled.is_file())
        self.assertTrue(blank.is_file())
        filled_bin = aarth.load_and_binarize(filled)
        blank_bin = aarth.load_and_binarize(blank)
        f_alpha, f_digits = aarth.find_alphabet_and_digit_boxes(filled_bin)
        b_alpha, b_digits = aarth.find_alphabet_and_digit_boxes(blank_bin)
        self.assertEqual(len(f_alpha), 28)
        self.assertEqual(f_digits, [], msg="empty numeral cells must not be detected")
        self.assertEqual(b_alpha, [])
        self.assertEqual(b_digits, [])
        self.assertGreaterEqual(len(paths), 3)
        self.assertEqual(paths[2].name, "ath_source_filled.png")
        self.assertTrue(paths[2].is_file())

    def test_filled_template_detects_ten_digits(self):
        dest = Path(tempfile.mkdtemp(prefix="aarth-filled-")) / "ath_source_filled.png"
        aarth.write_source_template(
            dest, alphabet_image=SOURCE_PNG, fill_digits=True,
        )
        binary = aarth.load_and_binarize(dest)
        alphabet, digits = aarth.find_alphabet_and_digit_boxes(binary)
        self.assertEqual(len(alphabet), 28)
        self.assertEqual(len(digits), 10)
        # Numeral 1 is a horizontal bar — shorter than letter bodies.
        one = digits[1]
        self.assertGreater(one[2], one[3] * 2)

    def test_painted_tron_zero_keeps_counters(self):
        rasters = aarth.load_tron_digit_rasters()
        self.assertIsNotNone(rasters)
        self.assertEqual(len(rasters), 10)
        gray = rasters[0][:, :, 0]
        ink = gray < 128
        h, w = gray.shape
        self.assertTrue(ink.any())
        self.assertFalse(ink[int(h * 0.28), w // 2], msg="upper counter must stay open")
        self.assertFalse(ink[int(h * 0.72), w // 2], msg="lower counter must stay open")
        # Midline bar of Ath 1 must not fill the whole cell.
        one = rasters[1][:, :, 0] < 128
        self.assertLess(one.sum(), one.size * 0.15)

    def test_horizontal_bar_survives_letter_size_filter(self):
        boxes = [(0, 0, 20, 25), (30, 10, 18, 2)]
        kept = aarth._letter_sized_boxes(boxes)
        self.assertEqual(kept, boxes)


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

    def test_filled_template_font_has_digits_and_license(self):
        work = Path(tempfile.mkdtemp(prefix="aarth-filled-font-"))
        sheet = work / "filled.png"
        aarth.write_source_template(
            sheet, alphabet_image=SOURCE_PNG, fill_digits=True,
        )
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "generate_aarth_font.py"),
                "--image",
                str(sheet),
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
                "font generation from filled template failed:\n"
                f"{completed.stdout}\n{completed.stderr}"
            )
        from fontTools.pens.boundsPen import BoundsPen
        from fontTools.pens.recordingPen import RecordingPen
        from fontTools.ttLib import TTFont

        font = TTFont(work / "aarth.ttf")
        cmap = font.getBestCmap()
        self.assertEqual(len(cmap), 38)
        for codepoint in aarth.DIGIT_CODEPOINTS:
            self.assertIn(codepoint, cmap)
        names = {
            rec.toUnicode()
            for rec in font["name"].names
            if rec.toUnicode()
        }
        joined = " ".join(names)
        self.assertIn("Morioka", joined)
        self.assertIn("Akai", joined)
        self.assertIn("CC BY-SA 3.0", joined)

        charstrings = font["CFF "].cff.topDictIndex[0].CharStrings
        one_pen = BoundsPen(None)
        charstrings["one"].draw(one_pen)
        _x0, y0, _x1, y1 = one_pen.bounds
        self.assertGreater(y0, 180, msg="Ath 1 is a midline bar, not an underscore")
        self.assertLess(y1, 520)

        rec = RecordingPen()
        charstrings["zero"].draw(rec)
        n_moves = sum(1 for op, _args in rec.value if op == "moveTo")
        self.assertGreaterEqual(n_moves, 2, msg="Ath 0 must keep its counters")


if __name__ == "__main__":
    unittest.main()
