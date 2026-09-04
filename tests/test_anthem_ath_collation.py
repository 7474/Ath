#!/usr/bin/env python3
"""写本（アース）と Aarth 組版の単語照合。"""

from __future__ import annotations

import unittest
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from baronh.phonology import to_ath_keys

ROOT = Path(__file__).resolve().parent.parent
MANUSCRIPT = ROOT / "data" / "examples" / "rueoll_ath.png"
ROMAN = ROOT / "data" / "examples" / "rueoll_baronh.txt"
FONT = ROOT / "aarth.ttf"
ATH_PAGE = ROOT / "ath" / "index.html"

# 写本の本文行（ダイアクリティクスは直前ギャップへ最大 4px）。
BODY_BANDS = [
    (3, 15),
    (17, 29),
    (31, 43),
    (45, 57),
    (59, 70),
    (86, 98),
    (100, 112),
    (114, 126),
    (128, 140),
    (156, 168),
    (170, 182),
    (184, 196),
    (198, 209),
    (211, 223),
    (239, 251),
    (253, 265),
    (267, 279),
    (281, 293),
    (309, 320),
    (323, 334),
]


def anthem_roman_lines() -> list[str]:
    lines = []
    for raw in ROMAN.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def ath_keys_line(roman: str) -> str:
    return to_ath_keys(roman.lower())


def exp_words(roman: str) -> list[str]:
    keys = ath_keys_line(roman)
    out = []
    for token in keys.replace(",", " ").replace(".", " ").split():
        token = token.replace("'", "")
        if token:
            out.append(token)
    return out


def render_word(text: str, font_path: Path = FONT, size: int = 72) -> np.ndarray:
    font = ImageFont.truetype(str(font_path), size)
    dummy = Image.new("L", (1, 1), 255)
    draw = ImageDraw.Draw(dummy)
    bbox = draw.textbbox((0, 0), text, font=font)
    img = Image.new(
        "L",
        (max(8, bbox[2] - bbox[0] + 6), max(8, bbox[3] - bbox[1] + 8)),
        255,
    )
    ImageDraw.Draw(img).text((3 - bbox[0], 4 - bbox[1]), text, font=font, fill=0)
    arr = np.array(img)
    ink = arr < 200
    ys, xs = np.where(ink)
    return arr[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]


def ncc_word(src_gray: np.ndarray, tmpl_gray: np.ndarray) -> float:
    src = (src_gray < 190).astype(np.float32)
    tmpl = (tmpl_gray < 190).astype(np.float32)
    a = cv2.resize(src, (48, 24), interpolation=cv2.INTER_AREA)
    b = cv2.resize(tmpl, (48, 24), interpolation=cv2.INTER_AREA)
    if a.std() < 1e-3 or b.std() < 1e-3:
        return -1.0
    a = (a - a.mean()) / (a.std() + 1e-6)
    b = (b - b.mean()) / (b.std() + 1e-6)
    return float((a * b).mean())


def split_words(gray: np.ndarray) -> list[list[int]]:
    ink = (gray < 190).astype(np.uint8)
    col = ink.sum(axis=0)
    words: list[list[int]] = []
    inside = False
    start = 0
    for x, value in enumerate(col):
        if value > 0 and not inside:
            inside = True
            start = x
        elif value == 0 and inside:
            inside = False
            if x - start >= 3 and int(ink[:, start:x].sum()) >= 8:
                words.append([start, x])
    if inside:
        end = gray.shape[1]
        if end - start >= 3 and int(ink[:, start:end].sum()) >= 8:
            words.append([start, end])
    return words


def fit_word_count(words: list[list[int]], count: int) -> list[list[int]]:
    """写本のインク塊を期待語数へ畳む。

    行末の狭い塊はカンマ／ピリオド。ギャップ 1px 前後の狭い塊は
    ``i`` / ``e`` / ダイアクリティクスの分裂なので隣接語へマージする。
    1 字母の ``a`` は語間ギャップのあとに残るので、行末句読点だけ先に落とす。
    """
    fitted = [list(box) for box in words]
    while len(fitted) > count:
        last_w = fitted[-1][1] - fitted[-1][0]
        if last_w < 12:
            fitted.pop()
            continue
        best: tuple[float, int] | None = None
        for i in range(len(fitted) - 1):
            gap = fitted[i + 1][0] - fitted[i][1]
            if best is None or gap < best[0]:
                best = (float(gap), i)
        assert best is not None
        i = best[1]
        fitted[i] = [fitted[i][0], fitted[i + 1][1]]
        del fitted[i + 1]
    return fitted


def crop_line(src: np.ndarray, index: int) -> np.ndarray:
    y0, y1 = BODY_BANDS[index]
    prev_end = BODY_BANDS[index - 1][1] if index else 0
    y0p = max(prev_end + 1, y0 - 4)
    crop = src[y0p : y1 + 1]
    ink = crop < 190
    xs = np.where(ink.any(axis=0))[0]
    ys = np.where(ink.any(axis=1))[0]
    return crop[ys[0] : ys[-1] + 1, xs[0] : xs[-1] + 1]


class AnthemAthCollationTest(unittest.TestCase):
    def test_manuscript_has_twenty_lines(self):
        self.assertTrue(MANUSCRIPT.is_file())
        roman = anthem_roman_lines()
        self.assertEqual(len(roman), 20)
        self.assertEqual(len(BODY_BANDS), 20)

    def test_html_uses_ath_keys_from_romanization(self):
        html = ATH_PAGE.read_text(encoding="utf-8")
        for roman in anthem_roman_lines():
            keys = " ".join(
                ath_keys_line(roman).replace("'", "").replace(",", "").replace(".", "").split()
            )
            self.assertIn(keys, html, msg=roman)

    def test_manuscript_words_match_aarth_render(self):
        src = cv2.imread(str(MANUSCRIPT), cv2.IMREAD_GRAYSCALE)
        self.assertIsNotNone(src)
        roman_lines = anthem_roman_lines()
        vocab = sorted({word for line in roman_lines for word in exp_words(line)})
        templates = {word: render_word(word) for word in vocab}
        accepted = 0
        total = 0
        misses: list[str] = []
        for i, roman in enumerate(roman_lines):
            words = exp_words(roman)
            gray = crop_line(src, i)
            boxes = fit_word_count(split_words(gray), len(words))
            self.assertEqual(len(boxes), len(words), msg=f"L{i:02d} {roman}")
            for word, (x0, x1) in zip(words, boxes):
                total += 1
                crop = gray[:, x0:x1]
                ranked = sorted(
                    ((ncc_word(crop, templates[cand]), cand) for cand in vocab),
                    reverse=True,
                )
                top = [name for _score, name in ranked[:3]]
                if word in top:
                    accepted += 1
                else:
                    misses.append(f"L{i:02d} {word} top={top}")
        # 12px 写本では bale/fade/dar、ullote/farh、loréïl/lomi が近接する。
        self.assertGreaterEqual(accepted, 69, msg="\n".join(misses) or "no misses")
        self.assertLessEqual(len(misses), 2)


if __name__ == "__main__":
    unittest.main()
