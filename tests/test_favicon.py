#!/usr/bin/env python3
"""Favicon generation keeps yin-yang gems readable at tab sizes."""

from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from generate_favicon import generate, load_emblem, render_size

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "favicon-source.jpg"


class FaviconFilesTest(unittest.TestCase):
    def test_committed_icons_exist(self):
        expected = {
            ROOT / "favicon.ico": None,
            ROOT / "icons" / "favicon-16.png": (16, 16),
            ROOT / "icons" / "favicon-32.png": (32, 32),
            ROOT / "icons" / "favicon-48.png": (48, 48),
            ROOT / "icons" / "apple-touch-icon.png": (180, 180),
            ROOT / "icons" / "icon-192.png": (192, 192),
            ROOT / "icons" / "icon-512.png": (512, 512),
        }
        for path, size in expected.items():
            self.assertTrue(path.is_file(), f"missing {path.relative_to(ROOT)}")
            if size is not None:
                with Image.open(path) as im:
                    self.assertEqual(im.size, size)
                    self.assertEqual(im.mode, "RGBA")

    def test_source_is_square_photo(self):
        self.assertTrue(SOURCE.is_file())
        with Image.open(SOURCE) as im:
            self.assertEqual(im.size[0], im.size[1])
            self.assertGreaterEqual(im.size[0], 512)

    def test_large_icon_has_transparent_corners(self):
        with Image.open(ROOT / "icons" / "icon-512.png") as im:
            self.assertEqual(im.getpixel((0, 0))[3], 0)
            self.assertEqual(im.getpixel((511, 0))[3], 0)
            cx, cy = im.size[0] // 2, im.size[1] // 2
            self.assertEqual(im.getpixel((cx, cy))[3], 255)

    def test_apple_touch_icon_is_opaque(self):
        with Image.open(ROOT / "icons" / "apple-touch-icon.png") as im:
            alpha = im.getchannel("A")
            self.assertEqual(alpha.getextrema(), (255, 255))

    def test_docs_pages_copy_includes_icons(self):
        self.assertTrue((ROOT / "docs" / "favicon.ico").is_file())
        for name in ("favicon-16.png", "favicon-32.png", "apple-touch-icon.png", "icon-512.png"):
            self.assertTrue((ROOT / "docs" / "icons" / name).is_file(), name)


class FaviconGenerateTest(unittest.TestCase):
    def test_generate_writes_ico_and_png_sizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            written = generate(SOURCE, out)
            ico = written["favicon.ico"]
            self.assertTrue(ico.is_file())
            with ico.open("rb") as fh:
                reserved, kind, count = struct.unpack("<HHH", fh.read(6))
            self.assertEqual((reserved, kind, count), (0, 1, 3))
            with Image.open(ico) as im:
                self.assertGreaterEqual(len(im.ico.sizes()), 3)

            for name, size in (
                ("favicon-16.png", (16, 16)),
                ("favicon-32.png", (32, 32)),
                ("favicon-48.png", (48, 48)),
                ("apple-touch-icon.png", (180, 180)),
                ("icon-192.png", (192, 192)),
                ("icon-512.png", (512, 512)),
            ):
                path = written[name]
                with Image.open(path) as im:
                    self.assertEqual(im.size, size, name)

    def test_small_icon_keeps_red_and_blue_gems(self):
        emblem = load_emblem(SOURCE)
        icon = render_size(emblem, 16)
        arr = __import__("numpy").asarray(icon)
        rgb, alpha = arr[:, :, :3], arr[:, :, 3]
        visible = alpha > 80
        red = visible & (rgb[:, :, 0] > 140) & (rgb[:, :, 0] > rgb[:, :, 1] + 30)
        blue = visible & (rgb[:, :, 2] > 140) & (rgb[:, :, 2] > rgb[:, :, 0] + 30)
        self.assertGreaterEqual(int(red.sum()), 1, "16px favicon lost the red gem")
        self.assertGreaterEqual(int(blue.sum()), 1, "16px favicon lost the blue gem")


if __name__ == "__main__":
    unittest.main()
