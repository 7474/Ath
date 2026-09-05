#!/usr/bin/env python3
"""Registered Ath webfont faces (faces.json) and extra rasters."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import generate_aarth_font as aarth  # noqa: E402

SIGNPEN = ROOT / "templates" / "faces" / "aarth-koudenpa-signpen.jpg"
FACES_JSON = ROOT / "faces.json"


class FacesCatalogTest(unittest.TestCase):
    def test_catalog_lists_default_and_signpen(self):
        catalog = aarth.load_faces_catalog(FACES_JSON)
        ids = [face["id"] for face in catalog["faces"]]
        self.assertEqual(catalog["default"], "aarth")
        self.assertIn("aarth", ids)
        self.assertIn("aarth-koudenpa-signpen", ids)
        signpen = aarth.get_face(catalog, "aarth-koudenpa-signpen")
        self.assertEqual(signpen["family"], "Aarth Koudenpa Signpen")
        self.assertEqual(signpen["fileStem"], "aarth-koudenpa-signpen")
        image = ROOT / signpen["image"]
        self.assertTrue(image.is_file(), image)

    def test_unknown_face_raises(self):
        catalog = aarth.load_faces_catalog(FACES_JSON)
        with self.assertRaises(KeyError):
            aarth.get_face(catalog, "missing-face")

    def test_write_faces_css_switches_families(self):
        dest = Path(tempfile.mkdtemp(prefix="aarth-css-")) / "aarth.css"
        aarth.write_faces_css(dest)
        css = dest.read_text(encoding="utf-8")
        self.assertIn("--ath-font", css)
        self.assertIn("font-family: 'Aarth';", css)
        self.assertIn("font-family: 'Aarth Koudenpa Signpen';", css)
        self.assertIn("aarth-koudenpa-signpen.woff2", css)
        self.assertIn("html[data-ath-face='aarth-koudenpa-signpen']", css)
        committed = (ROOT / "aarth.css").read_text(encoding="utf-8")
        self.assertIn("--ath-font", committed)
        self.assertIn("Aarth Koudenpa Signpen", committed)


class SignpenRasterTest(unittest.TestCase):
    def test_signpen_sheet_detects_full_inventory(self):
        self.assertTrue(SIGNPEN.is_file(), SIGNPEN)
        binary = aarth.load_and_binarize(SIGNPEN)
        alphabet, digits = aarth.find_alphabet_and_digit_boxes(binary)
        self.assertEqual(len(alphabet), 28)
        self.assertEqual(len(digits), 10)


class SignpenFontTest(unittest.TestCase):
    output_dir: Path

    @classmethod
    def setUpClass(cls):
        cls.output_dir = Path(tempfile.mkdtemp(prefix="aarth-signpen-"))
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "generate_aarth_font.py"),
                "--face",
                "aarth-koudenpa-signpen",
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
                "signpen font generation failed:\n"
                f"{completed.stdout}\n{completed.stderr}"
            )

    def test_named_output_files_exist(self):
        ttf = self.output_dir / "aarth-koudenpa-signpen.ttf"
        woff2 = self.output_dir / "aarth-koudenpa-signpen.woff2"
        self.assertTrue(ttf.is_file(), ttf)
        self.assertTrue(woff2.is_file(), woff2)
        self.assertGreater(ttf.stat().st_size, 0)
        self.assertGreater(woff2.stat().st_size, 0)

    def test_ttf_family_and_cmap(self):
        from fontTools.ttLib import TTFont

        font = TTFont(self.output_dir / "aarth-koudenpa-signpen.ttf")
        cmap = font.getBestCmap()
        self.assertEqual(len(cmap), 38)
        for codepoint in aarth.GLYPH_CODEPOINTS:
            self.assertIn(codepoint, cmap)
        names = " ".join(
            rec.toUnicode() for rec in font["name"].names if rec.toUnicode()
        )
        self.assertIn("Aarth Koudenpa Signpen", names)
        self.assertIn("koudenpa", names.lower())


class FacesJsonOnDiskTest(unittest.TestCase):
    def test_json_is_valid_and_images_exist(self):
        data = json.loads(FACES_JSON.read_text(encoding="utf-8"))
        self.assertIsInstance(data["faces"], list)
        self.assertGreaterEqual(len(data["faces"]), 2)
        for face in data["faces"]:
            with self.subTest(id=face["id"]):
                self.assertTrue(face["id"])
                self.assertTrue(face["family"])
                self.assertTrue(face["fileStem"])
                self.assertTrue(face["label"])
                image = ROOT / face["image"]
                self.assertTrue(image.is_file(), image)


if __name__ == "__main__":
    unittest.main()
