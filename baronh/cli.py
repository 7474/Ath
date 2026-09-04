"""CLI: 翻訳・辞書・取り込み・音声・Web。"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from baronh import __version__
from baronh.grammar import FormIndex, all_verb_forms, analyze_form, conjugate, decline
from baronh.ingest import ingest_auto, merge_into_lexicon, write_lexicon
from baronh.lexicon import CASE_JA, Lexicon, load_lexicon, write_seed_lexicon
from baronh.paths import DATA_DIR, ROOT_DIR, USER_LEXICON_PATH, WEB_DIR
from baronh.phonology import reading_ja, to_ath_keys
from baronh.translate import translate
from baronh.tts import synthesize_local


def _lexicon(args: argparse.Namespace) -> Lexicon:
    extra = [Path(p) for p in getattr(args, "lexicon", []) or []]
    return load_lexicon(None) if not extra else _load_with_extra(extra)


def _load_with_extra(extra: list[Path]) -> Lexicon:
    from baronh.paths import default_lexicon_paths

    lexicon = load_lexicon(default_lexicon_paths() + extra)
    return lexicon


def cmd_translate(args: argparse.Namespace) -> int:
    lexicon = _lexicon(args)
    text = args.text if args.text is not None else sys.stdin.read()
    engine = args.engine
    if engine in {"openai", "auto"} and (args.api_key or engine == "openai"):
        from baronh.openai_backend import translate_openai

        result = translate_openai(
            text,
            lexicon,
            source_lang=args.source,
            target_lang=args.target,
            api_key=args.api_key,
            model=args.model,
        )
        if engine == "auto" and not result.text:
            result = translate(text, lexicon, source_lang=args.source, target_lang=args.target)
    elif engine == "auto":
        result = translate(text, lexicon, source_lang=args.source, target_lang=args.target)
    else:
        result = translate(text, lexicon, source_lang=args.source, target_lang=args.target)
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0
    print(result.text)
    if args.show_analysis:
        if result.reading_ja:
            print(f"# 読み: {result.reading_ja}", file=sys.stderr)
        if result.ath_keys and result.target_lang == "baronh":
            print(f"# Ath: {result.ath_keys}", file=sys.stderr)
        for item in result.analysis:
            print(f"# {item.source} → {item.target} ({item.note})", file=sys.stderr)
        for note in result.notes:
            print(f"# {note}", file=sys.stderr)
    return 0


def cmd_lookup(args: argparse.Namespace) -> int:
    lexicon = _lexicon(args)
    hits = lexicon.lookup(args.query, lang=args.lang)
    if not hits:
        print("見つかりませんでした", file=sys.stderr)
        return 1
    for entry in hits:
        print(f"{entry.lemma}\t{entry.pos}\t{entry.gloss_ja}\t{entry.gloss_en}")
        if entry.pos in {"noun", "pronoun"}:
            forms = decline(entry)
            print("  " + "  ".join(f"{CASE_JA[c]}:{forms[c]}" for c in forms))
        if args.json:
            pass
    if args.json:
        print(json.dumps([e.to_dict() for e in hits], ensure_ascii=False, indent=2))
    return 0


def cmd_decline(args: argparse.Namespace) -> int:
    lexicon = _lexicon(args)
    hits = lexicon.lookup(args.lemma, lang="baronh") or lexicon.lookup(args.lemma, lang="ja")
    entry = next((e for e in hits if e.pos in {"noun", "pronoun"}), None)
    if entry is None:
        print("名詞/代名詞が見つかりません", file=sys.stderr)
        return 1
    forms = decline(entry)
    if args.json:
        print(json.dumps({"lemma": entry.lemma, "forms": forms}, ensure_ascii=False, indent=2))
        return 0
    print(f"{entry.lemma} ({entry.gloss_ja}) 第{entry.declension or '?'}型")
    for case, form in forms.items():
        print(f"  {CASE_JA[case]:<4} {form}")
    return 0


def cmd_conjugate(args: argparse.Namespace) -> int:
    lexicon = _lexicon(args)
    hits = lexicon.lookup(args.lemma, lang="baronh") or lexicon.lookup(args.lemma, lang="ja")
    entry = next((e for e in hits if e.pos == "verb"), None)
    if entry is None:
        print("動詞が見つかりません", file=sys.stderr)
        return 1
    voices = [v for v in ("causative", "passive", "negative") if getattr(args, v)]
    if args.all:
        if args.json:
            rows = [
                {"mood": m, "aspect": a, "voices": list(vs), "form": form}
                for m, a, vs, form in all_verb_forms(entry)
            ]
            print(json.dumps(rows, ensure_ascii=False, indent=2))
            return 0
        for mood, aspect, vs, form in all_verb_forms(entry):
            tag = "+".join(vs) if vs else "-"
            print(f"{mood:12} {aspect:12} {tag:24} {form}")
        return 0
    form = conjugate(entry, mood=args.mood, aspect=args.aspect, voices=voices)
    print(form)
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    lexicon = _lexicon(args)
    index = FormIndex(lexicon)
    hits = analyze_form(args.form, lexicon, index)
    if not hits:
        print("解析できませんでした", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps([h.summary_ja() for h in hits], ensure_ascii=False, indent=2))
        return 0
    for hit in hits:
        print(hit.summary_ja())
    return 0


def cmd_speak(args: argparse.Namespace) -> int:
    text = args.text
    lang = args.lang
    if lang == "auto":
        from baronh.translate import detect_lang

        lang = detect_lang(text, _lexicon(args))
    if args.engine == "openai":
        from baronh.openai_backend import synthesize_openai

        out = Path(args.out) if args.out else Path("speech.mp3")
        path = synthesize_openai(text, lang=lang, api_key=args.api_key, output=out)
        print(path)
        return 0
    result = synthesize_local(
        text,
        lang=lang,
        output=Path(args.out) if args.out else None,
        play=args.play,
    )
    print(result.spoken_text)
    if result.audio_path:
        print(result.audio_path, file=sys.stderr)
    if result.note:
        print(f"# {result.note}", file=sys.stderr)
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    document = ingest_auto(args.source)
    lexicon = _lexicon(args)
    added = merge_into_lexicon(lexicon, document, replace=not args.keep)
    out = Path(args.out) if args.out else USER_LEXICON_PATH
    write_lexicon(lexicon, out)
    print(f"{document.get('source', args.source)} から {document.get('count', added)} 件を取り込み、{out} に書きました")
    if args.json:
        print(json.dumps({"source": document.get("source"), "count": document.get("count")}, ensure_ascii=False))
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    lexicon = _lexicon(args)
    by_pos: dict[str, int] = {}
    for entry in lexicon.entries:
        by_pos[entry.pos] = by_pos.get(entry.pos, 0) + 1
    print(f"ath-translate {__version__}")
    print(f"entries: {len(lexicon.entries)}")
    for pos, count in sorted(by_pos.items()):
        print(f"  {pos}: {count}")
    return 0


def cmd_export_web(args: argparse.Namespace) -> int:
    lexicon = _lexicon(args)
    dest = Path(args.out) if args.out else WEB_DIR / "data"
    dest.mkdir(parents=True, exist_ok=True)
    write_seed_lexicon(DATA_DIR / "lexicon.json")
    write_lexicon(lexicon, dest / "lexicon.json")
    print(dest / "lexicon.json")
    return 0


def cmd_reading(args: argparse.Namespace) -> int:
    print(reading_ja(args.text))
    if args.ath:
        print(to_ath_keys(args.text))
    return 0


class _TranslatorHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def log_message(self, fmt: str, *log_args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % log_args))

    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        rel = unquote(parsed.path)
        if rel in {"/", "/index.html"}:
            return str(WEB_DIR / "index.html")
        if rel.startswith("/data/"):
            target = (DATA_DIR / rel[len("/data/") :]).resolve()
            if str(target).startswith(str(DATA_DIR.resolve())) and target.is_file():
                return str(target)
        if rel.startswith("/font/"):
            name = rel[len("/font/") :]
            target = (ROOT_DIR / name).resolve()
            if str(target).startswith(str(ROOT_DIR.resolve())) and target.is_file():
                return str(target)
        mapped = super().translate_path(path)
        return mapped


def cmd_serve(args: argparse.Namespace) -> int:
    WEB_DIR.mkdir(parents=True, exist_ok=True)
    write_seed_lexicon()
    if not (WEB_DIR / "data" / "lexicon.json").is_file():
        write_lexicon(load_lexicon(), WEB_DIR / "data" / "lexicon.json")
    server = ThreadingHTTPServer((args.host, args.port), _TranslatorHandler)
    url = f"http://{args.host}:{args.port}/"
    print(f"アーヴ語翻訳 UI: {url}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--lexicon", action="append", default=[], help="追加の lexicon.json")
    parser = argparse.ArgumentParser(
        prog="python -m baronh",
        description="アーヴ語 (Baronh) と日本語・英語を翻訳する CLI / Web ツール",
        parents=[shared],
    )
    parser.add_argument("--version", action="version", version=f"ath-translate {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("translate", help="翻訳する", parents=[shared])
    p.add_argument("text", nargs="?", help="原文。省略時は標準入力")
    p.add_argument("--from", dest="source", default="auto", choices=["auto", "baronh", "ja", "en"])
    p.add_argument("--to", dest="target", default="auto", choices=["auto", "baronh", "ja", "en"])
    p.add_argument("--engine", default="local", choices=["local", "openai", "auto"])
    p.add_argument("--api-key", default=None)
    p.add_argument("--model", default="gpt-4o-mini")
    p.add_argument("--json", action="store_true")
    p.add_argument("--show-analysis", action="store_true")
    p.set_defaults(func=cmd_translate)

    p = sub.add_parser("lookup", help="辞書を引く", parents=[shared])
    p.add_argument("query")
    p.add_argument("--lang", default="auto", choices=["auto", "baronh", "ja", "en"])
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_lookup)

    p = sub.add_parser("decline", help="名詞・代名詞を格変化する", parents=[shared])
    p.add_argument("lemma")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_decline)

    p = sub.add_parser("conjugate", help="動詞を活用する", parents=[shared])
    p.add_argument("lemma")
    p.add_argument("--mood", default="indicative", choices=["indicative", "subjunctive", "imperative", "participle"])
    p.add_argument("--aspect", default="indefinite", choices=["indefinite", "perfect", "progressive", "prospective"])
    p.add_argument("--causative", action="store_true")
    p.add_argument("--passive", action="store_true")
    p.add_argument("--negative", action="store_true")
    p.add_argument("--all", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_conjugate)

    p = sub.add_parser("analyze", help="語形を解析する", parents=[shared])
    p.add_argument("form")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("speak", help="音声合成する", parents=[shared])
    p.add_argument("text")
    p.add_argument("--lang", default="auto", choices=["auto", "baronh", "ja", "en"])
    p.add_argument("--engine", default="local", choices=["local", "openai"])
    p.add_argument("--api-key", default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--play", action="store_true")
    p.set_defaults(func=cmd_speak)

    p = sub.add_parser("ingest", help="サイトまたはファイルから辞書を取り込む", parents=[shared])
    p.add_argument("source", help="wikipedia / URL / ファイルパス")
    p.add_argument("--out", default=None, help="書き出し先 JSON (既定: data/user_lexicon.json)")
    p.add_argument("--keep", action="store_true", help="既存エントリを上書きしない")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("serve", help="ブラウザ向け UI を起動する")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("export-web", help="Web 用 lexicon.json を書き出す", parents=[shared])
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_export_web)

    p = sub.add_parser("info", help="辞書の統計を表示する", parents=[shared])
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("reading", help="アーヴ語の仮名読み / Ath キー")
    p.add_argument("text")
    p.add_argument("--ath", action="store_true")
    p.set_defaults(func=cmd_reading)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
