#!/usr/bin/env python3
"""GitHub Pages is a site about Baronh and Ath, not only a font demo."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class SiteStructureTest(unittest.TestCase):
    def test_pages_exist(self):
        for rel in (
            "index.html",
            "ath/index.html",
            "web/index.html",
            "site.css",
            "theme.js",
            "ath-face.js",
            "faces.json",
        ):
            path = ROOT / rel
            self.assertTrue(path.is_file(), f"missing {rel}")

    def test_pages_load_font_face_switcher(self):
        pages = {
            "index.html": "faces.json",
            "ath/index.html": "../faces.json",
            "web/index.html": "../faces.json",
        }
        for rel, faces_href in pages.items():
            text = (ROOT / rel).read_text(encoding="utf-8")
            with self.subTest(page=rel):
                self.assertIn('localStorage.getItem("ath-face")', text)
                self.assertIn("data-ath-face", text)
                self.assertIn("ath-face.js", text)
                self.assertIn(faces_href, text)
        css = (ROOT / "site.css").read_text(encoding="utf-8")
        self.assertIn("var(--ath-font)", css)
        self.assertIn(".ath-face-switch", css)
        app = (ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8")
        self.assertIn("var(--ath-font)", app)

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
                self.assertIn('id="theme-toggle"', text)
                self.assertIn("viewport-fit=cover", text)
                self.assertIn('name="color-scheme"', text)
                self.assertIn("ath-theme", text)
                for href in hrefs:
                    self.assertIn(f'href="{href}"', text)

    def test_shared_header_has_mobile_touch_rules(self):
        css = (ROOT / "site.css").read_text(encoding="utf-8")
        self.assertIn("min-height: 2.75rem", css)
        self.assertIn(".site-meta { display: none; }", css)
        self.assertIn("safe-area-inset-top", css)
        self.assertIn(".site-nav a:focus-visible", css)
        self.assertIn(".site-card:active", css)
        app = (ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8")
        self.assertNotIn(".site-meta { display: none; }", app)

    def test_hub_is_about_language_and_script(self):
        hub = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("アーヴ語とアース", hub)
        self.assertNotIn("Webfont Demo", hub)
        self.assertIn('href="ath/"', hub)
        self.assertIn('href="web/"', hub)
        self.assertIn("字形デモ", hub)
        self.assertIn("翻訳", hub)

    def test_ath_demo_mobile_glyph_grid_and_mapping(self):
        demo = (ROOT / "ath" / "index.html").read_text(encoding="utf-8")
        self.assertIn("repeat(4, minmax(0, 1fr))", demo)
        self.assertIn("clamp(2.4rem, 12vw, 5rem)", demo)
        self.assertIn(".mapping-table .unicode { display: none; }", demo)
        self.assertIn("var(--heading)", demo)
        hub = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn(".teaser-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }", hub)

    def test_ath_demo_keeps_translate_play(self):
        demo = (ROOT / "ath" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="translate-button"', demo)
        self.assertIn('class="translate-play"', demo)
        self.assertIn("ラテンで読む", demo)
        self.assertIn("アースで見る", demo)
        nav = demo[demo.find('class="site-nav"') : demo.find("</nav>")]
        self.assertNotIn("translate-button", nav)
        play_at = demo.find('class="translate-play"')
        main_at = demo.find("<main")
        self.assertGreater(play_at, 0)
        self.assertGreater(main_at, play_at)
        self.assertIn('id="ath-face-select"', demo)
        self.assertIn("ath-face.js", demo)
        self.assertIn("faces.json", demo)
        self.assertIn("光電波サインペン", demo)
        self.assertIn("../site.css", demo)
        self.assertNotIn("Baronh 翻訳", demo)
        css = (ROOT / "site.css").read_text(encoding="utf-8")
        self.assertIn(".translate-play", css)
        self.assertIn("min-height: 2.75rem", css)

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
        btn_at = web.find('id="translate-btn"')
        self.assertGreater(btn_at, 0)
        self.assertNotIn("busy-spinner", web[btn_at:web.find("</button>", btn_at)])
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

    def test_translator_ai_settings_is_modal(self):
        web = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        nav = web[web.find('class="site-nav"') : web.find("</nav>")]
        details = web[web.find('class="engine-details"') : web.find("</details>")]
        actions = web[web.find('class="actions"') : web.find("</div>", web.find('class="actions"'))]
        settings_btn_at = web.find('id="open-settings"')
        dialog_at = web.find('id="settings-panel"')
        self.assertNotIn('id="examples-btn"', web)
        self.assertIn('class="engine-details"', web)
        self.assertIn('id="engine-summary"', web)
        self.assertIn("engine-details-title", web)
        self.assertIn('enterkeyhint="go"', web)
        css = (ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8")
        self.assertIn(".engine-details summary::after", css)
        self.assertIn("border: 1px solid var(--control)", css)
        js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("syncEngineSummary", js)
        self.assertIn("open-settings", details)
        self.assertNotIn("open-settings", actions)
        self.assertNotIn("生成AI設定", actions)
        self.assertGreater(dialog_at, settings_btn_at)
        self.assertIn("生成AI設定", web)
        self.assertNotIn("open-settings", nav)
        self.assertNotIn("生成AI設定", nav)
        self.assertIn("<dialog", web[max(0, dialog_at - 120) : dialog_at + 40])
        self.assertIn('id="close-settings"', web)
        self.assertNotIn("<pre", web)
        css = (ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8")
        self.assertIn("settings-modal", css)
        self.assertIn("::backdrop", css)
        self.assertIn("100dvh", css)
        self.assertIn(".entry-card", css)
        js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("showModal", js)
        self.assertIn("closeSettings", js)
        self.assertIn("renderEntryCard", js)
        self.assertIn("openaiNeedsSetup", js)
        self.assertIn("索引が無くても語釈と格変化は出す", js)
        self.assertNotIn("examples-btn", js)

    def test_translator_points_to_site_hub(self):
        web = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("../ath/", web)
        self.assertNotIn("フォントデモ", web)
        self.assertIn("../site.css", web)
        self.assertIn("../aarth.css", web)

    def test_translator_font_face_works_on_pages(self):
        app = (ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8")
        self.assertNotIn("@font-face", app)
        self.assertIn("textarea {", app)
        self.assertNotIn("<textarea {", app)
        web = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="../aarth.css"', web)
        self.assertIn('href="../aarth.woff2"', web)
        self.assertIn('rel="preload"', web)
        aarth = (ROOT / "aarth.css").read_text(encoding="utf-8")
          self.assertIn("@font-face", aarth)
          self.assertIn("aarth.woff2", aarth)
          self.assertIn("--ath-font", aarth)
          self.assertIn("aarth-koudenpa-signpen", aarth)
          self.assertIn("Aarth Koudenpa Signpen", aarth)

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

    def test_dark_mode_follows_system_by_default(self):
        css = (ROOT / "site.css").read_text(encoding="utf-8")
        js = (ROOT / "theme.js").read_text(encoding="utf-8")
        self.assertIn("prefers-color-scheme: dark", css)
        self.assertIn('data-theme="light"', css)
        self.assertIn('data-theme="dark"', css)
        self.assertIn("color-scheme: light dark", css)
        self.assertIn(".theme-toggle", css)
        self.assertIn("--bg:", css)
        self.assertIn("--ink:", css)
        self.assertIn("ジントの礼服", css)
        self.assertIn("ラフィールの軍服", css)
        self.assertIn("サイト向けに調整", css)
        self.assertIn("#f7f3ee", css)
        self.assertIn("#3c322a", css)
        self.assertIn("#c04538", css)
        self.assertIn("#121820", css)
        self.assertIn("#8eadd8", css)
        self.assertIn("#d1564c", css)
        self.assertIn("--trim:", css)
        self.assertIn("ath-theme", js)
        self.assertIn("removeAttribute(\"data-theme\")", js)
        self.assertIn("system", js)
        for rel in ("index.html", "ath/index.html", "web/index.html"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            with self.subTest(page=rel):
                self.assertNotIn('data-theme="', text.split("<body", 1)[0].split("<script", 1)[0])
                self.assertIn('id="theme-toggle"', text)
                self.assertIn("theme.js", text)

    def test_pages_workflow_copies_site_files(self):
        workflow = (ROOT / ".github" / "workflows" / "build-font.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("cp faces.json docs/faces.json", workflow)
        self.assertIn("cp ath-face.js docs/ath-face.js", workflow)
        self.assertIn("--all-faces", workflow)
        self.assertIn("site.css", workflow)
        self.assertIn("ath/**", workflow)
        self.assertIn("cp ath/index.html docs/ath/index.html", workflow)
        self.assertIn("cp site.css docs/site.css", workflow)
        self.assertIn("cp theme.js docs/theme.js", workflow)
        self.assertIn("cp favicon.ico docs/favicon.ico", workflow)
        self.assertIn("cp -r icons docs/icons", workflow)
        self.assertIn("python3 -m baronh export-web --out docs/web/data", workflow)
        self.assertIn("vectors.bin", workflow)
        self.assertIn("vectors.json", workflow)


if __name__ == "__main__":
    unittest.main()
