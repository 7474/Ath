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

    def test_pages_link_favicon(self):
        pages = {
            "index.html": ("favicon.ico", "icons/favicon-32.png", "icons/favicon-16.png", "icons/apple-touch-icon.png"),
            "ath/index.html": ("../favicon.ico", "../icons/favicon-32.png", "../icons/favicon-16.png", "../icons/apple-touch-icon.png"),
            "web/index.html": ("../favicon.ico", "../icons/favicon-32.png", "../icons/favicon-16.png", "../icons/apple-touch-icon.png"),
        }
        for rel, hrefs in pages.items():
            text = (ROOT / rel).read_text(encoding="utf-8")
            with self.subTest(page=rel):
                self.assertIn('rel="icon"', text)
                self.assertIn('rel="apple-touch-icon"', text)
                for href in hrefs:
                    self.assertIn(f'href="{href}"', text)

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

    def test_ath_demo_sets_empire_anthem_in_ath_keys(self):
        demo = (ROOT / "ath" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="frybarec"', demo)
        self.assertIn("frybarec gloer gor bari", demo)
        self.assertIn("bar frybarec", demo)
        self.assertIn("gerElacr", demo)
        self.assertIn("nahAnlace", demo)
        self.assertIn("sIsnée", demo)
        self.assertIn("tymbAdel", demo)
        self.assertIn("alsAma", demo)
        self.assertIn("üAponéra", demo)
        self.assertIn("farh a lomi zacsantto loréïl", demo)
        self.assertIn("class=\"ath-keys", demo)
        self.assertIn("text-transform: none", demo)
        self.assertNotIn("f'a ", demo)
        self.assertNotIn("我ら、ともに永遠を抱かん", demo)
        self.assertNotIn("Sausnée surepuce", demo)
        self.assertNotIn("Anthem (Baronh romanization)", demo)
        self.assertNotIn("empire-gloss", demo)
        self.assertNotIn("lotr atosr nea rhoibhe", demo)

    def test_hub_shows_empire_name_in_ath(self):
        hub = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("frybarec gloer gor bari", hub)
        self.assertIn("国歌をアースで組版", hub)

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
        self.assertIn('aria-live="polite"', web)
        self.assertIn('id="busy-row"', web)
        self.assertIn('id="translator"', web)
        css = (ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8")
        self.assertIn("busy-spinner", css)
        self.assertIn(".busy-spinner[hidden]", css)
        self.assertIn(".translator.is-busy .busy-spinner", css)
        self.assertIn("prefers-reduced-motion", css)
        js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("stream: true", js)
        self.assertIn("readNdjsonStream", js)
        self.assertIn("下書き（生成中）", js)

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
        self.assertIn("cp favicon.ico docs/favicon.ico", workflow)
        self.assertIn("cp -r icons docs/icons", workflow)
        self.assertIn("python3 -m baronh export-web --out docs/web/data", workflow)
        self.assertIn("vectors.bin", workflow)
        self.assertIn("vectors.json", workflow)


if __name__ == "__main__":
    unittest.main()
