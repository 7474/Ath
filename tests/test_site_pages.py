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

    def test_translator_mentions_server_agent(self):
        web = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("サーバエージェント", web)
        self.assertIn("ベクトル検索", web)
        self.assertIn("js/vectordb.js", web)
        self.assertIn("id=\"agent-url\"", web)
        self.assertIn("/api/translate", web)
        self.assertIn("id=\"local-vector-search\"", web)
        self.assertIn("訳語をベクトル検索", web)
        self.assertIn('value="agent"', web)

    def test_translator_page_leads_with_tool_not_construction(self):
        web = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        tool_at = web.find('id="source-text"')
        dict_at = web.find(">辞書<")
        self.assertGreater(tool_at, 0)
        self.assertGreater(dict_at, tool_at)
        self.assertNotIn("使い方", web)
        self.assertNotIn("python -m baronh", web)
        self.assertNotIn("export-web", web)
        self.assertNotIn("GitHub Actions", web)
        self.assertNotIn("DEPLOY.md", web)
        self.assertNotIn("Cloud Run", web)
        css = (ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8")
        self.assertIn("ファーストビュー", css)
        self.assertIn("min-height: 5.25rem", css)

    def test_translator_points_to_site_hub(self):
        web = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("../ath/", web)
        self.assertNotIn("フォントデモ", web)
        self.assertIn("../site.css", web)
        self.assertIn("../aarth.css", web)

    def test_translator_font_face_works_on_pages(self):
        css = (ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8")
        self.assertIn("../../aarth.woff2", css)
        self.assertIn('url("aarth.woff2")', css)
        self.assertIn("textarea {", css)
        self.assertNotIn("<textarea {", css)

    def test_readme_describes_site_map(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertTrue(readme.startswith("# アーヴ語とアース"))
        self.assertIn("/ath/", readme)
        self.assertIn("/web/", readme)
        self.assertIn("https://7474.github.io/Ath/", readme)
        self.assertNotIn("公開デモ（GitHub Pages）", readme)

    def test_readme_documents_mapping_caveats(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("転写とグリフの留意点", readme)
        self.assertIn("fold_fan_romanization", readme)
        self.assertIn("to_ath_keys", readme)
        self.assertIn("bœrh", readme)
        self.assertIn("語末の `oe`", readme)
        architecture = (ROOT / "baronh" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        self.assertIn("アース転写とグリフ", architecture)
        demo = (ROOT / "ath" / "index.html").read_text(encoding="utf-8")
        self.assertIn("4×7 ラベル順", demo)

    def test_serve_hosts_whole_site(self):
        server = (ROOT / "baronh" / "server.py").read_text(encoding="utf-8")
        self.assertIn("directory=str(ROOT_DIR)", server)
        self.assertNotIn("directory=str(WEB_DIR)", server)
        self.assertIn("アーヴ語とアース:", server)
        self.assertIn("/api/translate", server)
        cli = (ROOT / "baronh" / "cli.py").read_text(encoding="utf-8")
        self.assertIn("from baronh.server import serve", cli)

    def test_pages_workflow_copies_site_files(self):
        workflow = (ROOT / ".github" / "workflows" / "build-font.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("site.css", workflow)
        self.assertIn("ath/**", workflow)
        self.assertIn("cp ath/index.html docs/ath/index.html", workflow)
        self.assertIn("cp site.css docs/site.css", workflow)
        self.assertIn("python3 -m baronh export-web --out docs/web/data", workflow)
        self.assertIn("vectors.bin", workflow)
        self.assertIn("vectors.json", workflow)


if __name__ == "__main__":
    unittest.main()
