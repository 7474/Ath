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

    def test_ath_demo_leads_with_empire_name(self):
        demo = (ROOT / "ath" / "index.html").read_text(encoding="utf-8")
        anthem = (
            "F'a rume catmé gereulacr, Ullote izomél, Lanote dige césati, "
            "Lüamse nahainlace. F'a Bale, scuréle Frybarer. Frybarec éü, "
            "Sicé léssote dar scurér alsaima. Farer Léssoth, R'a sotle botnasa "
            "dari éïrace lona. F'a flare rycmal gereulacr, Sausnée surepuce, "
            "Issae dade lo fade, Froce tymbaidel gol. F'a Bale, carsarh gereulacr. "
            "Gereulach éü, Sicé dozzote dar carsarr factina. Farer dozzoth, "
            "R'a sotle nilora rÿal dar üaiponéra. Frybarec éü, gereulach éü, "
            "Farh a lomi zacsantto loréïl."
        )
        self.assertNotIn("Hero text", demo)
        self.assertNotIn("Sample text (romanised Ath phonetics)", demo)
        self.assertNotIn("lotr atosr nea rhoibhe", demo)
        self.assertNotIn("fhemainr tlaicr suanaer", demo)
        self.assertIn("Humankind Empire of Abh", demo)
        self.assertIn(anthem, demo)
        self.assertEqual(demo.count('class="aarth-hero"'), 1)
        main_at = demo.find("<main")
        title_at = demo.find("Humankind Empire of Abh")
        anthem_at = demo.find("F'a rume catmé gereulacr")
        close_at = demo.find("Farh a lomi zacsantto loréïl.")
        h1_at = demo.find("<h1>")
        self.assertGreater(main_at, 0)
        self.assertGreater(title_at, main_at)
        self.assertGreater(anthem_at, title_at)
        self.assertGreater(close_at, anthem_at)
        self.assertGreater(h1_at, close_at)
        hero_html = demo[demo.find('<p class="aarth-hero">') : h1_at]
        self.assertNotIn("<p class=\"aarth-hero\">", hero_html[1:])

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

    def test_translator_ai_settings_is_modal_beside_examples(self):
        web = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        nav = web[web.find('class="site-nav"') : web.find("</nav>")]
        actions_at = web.find('class="actions"')
        examples_at = web.find('id="examples-btn"')
        settings_btn_at = web.find('id="open-settings"')
        dialog_at = web.find('id="settings-panel"')
        self.assertGreater(actions_at, 0)
        self.assertGreater(examples_at, actions_at)
        self.assertGreater(settings_btn_at, examples_at)
        self.assertGreater(dialog_at, settings_btn_at)
        self.assertIn("生成AI設定", web)
        self.assertNotIn("open-settings", nav)
        self.assertNotIn("生成AI設定", nav)
        self.assertIn("<dialog", web[max(0, dialog_at - 120) : dialog_at + 40])
        self.assertIn('id="close-settings"', web)
        css = (ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8")
        self.assertIn("settings-modal", css)
        self.assertIn("::backdrop", css)
        js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("showModal", js)
        self.assertIn("closeSettings", js)

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
