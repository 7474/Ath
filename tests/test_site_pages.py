#!/usr/bin/env python3
"""GitHub Pages is a site about Baronh and Ath, not only a font demo."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class SiteStructureTest(unittest.TestCase):
    def test_pages_exist(self):
        for rel in ("index.html", "ath/index.html", "web/index.html", "site.css"):
            path = ROOT / rel
            self.assertTrue(path.is_file(), f"missing {rel}")

    def test_shared_navigation(self):
        pages = {
            "index.html": ("./", "ath/", "web/"),
            "ath/index.html": ("../", "./", "../web/"),
            "web/index.html": ("../", "../ath/", "./"),
        }
        for rel, hrefs in pages.items():
            text = (ROOT / rel).read_text(encoding="utf-8")
            with self.subTest(page=rel):
                self.assertIn("概要", text)
                self.assertIn("アース", text)
                self.assertIn("翻訳", text)
                self.assertIn('class="site-nav"', text)
                for href in hrefs:
                    self.assertIn(f'href="{href}"', text)

    def test_hub_is_about_language_and_script(self):
        hub = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("アーヴ語とアース", hub)
        self.assertNotIn("Webfont Demo", hub)
        self.assertIn('href="ath/"', hub)
        self.assertIn('href="web/"', hub)
        self.assertIn("字形デモ", hub)
        self.assertIn("翻訳", hub)

    def test_ath_demo_keeps_translate_play(self):
        demo = (ROOT / "ath" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="translate-button"', demo)
        self.assertIn("../aarth.css", demo)
        self.assertIn("../site.css", demo)
        self.assertNotIn("Baronh 翻訳", demo)

    def test_translator_points_to_site_hub(self):
        web = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("../ath/", web)
        self.assertNotIn("フォントデモ", web)
        self.assertIn("../site.css", web)
        self.assertIn("../aarth.css", web)

    def test_translator_font_face_works_on_pages(self):
        css = (ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8")
        self.assertIn("../../aarth.woff2", css)

    def test_readme_describes_site_map(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertTrue(readme.startswith("# アーヴ語とアース"))
        self.assertIn("/ath/", readme)
        self.assertIn("/web/", readme)
        self.assertIn("https://7474.github.io/Ath/", readme)
        self.assertNotIn("公開デモ（GitHub Pages）", readme)

    def test_serve_hosts_whole_site(self):
        cli = (ROOT / "baronh" / "cli.py").read_text(encoding="utf-8")
        self.assertIn("directory=str(ROOT_DIR)", cli)
        self.assertNotIn("directory=str(WEB_DIR)", cli)
        self.assertIn("アーヴ語とアース:", cli)

    def test_pages_workflow_copies_site_files(self):
        workflow = (ROOT / ".github" / "workflows" / "build-font.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("site.css", workflow)
        self.assertIn("ath/**", workflow)
        self.assertIn("cp ath/index.html docs/ath/index.html", workflow)
        self.assertIn("cp site.css docs/site.css", workflow)


if __name__ == "__main__":
    unittest.main()
