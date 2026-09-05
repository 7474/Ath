"""CLI: 翻訳・辞書・取り込み・音声・Web。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from baronh import __version__
from baronh.grammar import FormIndex, all_verb_forms, analyze_form, conjugate, decline
from baronh.ingest import ingest_auto, merge_into_lexicon, write_lexicon, write_lexicon_document
from baronh.langpack import LangpackError, grammar_context_for, init_lang, is_pack_lang, list_packs, load_pack, uses_builtin_engine
from baronh.lexicon import CASE_JA, Lexicon, load_lexicon, write_seed_lexicon
from baronh.paths import USER_LEXICON_PATH, WEB_DIR
from baronh.phonology import reading_ja, to_ath_keys
from baronh.translate import translate
from baronh.tts import synthesize_local


def _lang_choices() -> list[str]:
    from baronh.langpack import list_pack_ids

    ids = ["auto", "ja", "en"]
    for pack_id in ["baronh", *list_pack_ids()]:
        if pack_id not in ids:
            ids.append(pack_id)
    return ids


def _pack_for_lang(lang: str):
    if not lang or lang in {"auto", "ja", "en"}:
        return None
    if not is_pack_lang(lang):
        return None
    pack = load_pack(lang)
    if uses_builtin_engine(pack):
        return None
    return pack


def _lexicon(args: argparse.Namespace) -> Lexicon:
    extra = [Path(p) for p in getattr(args, "lexicon", []) or []]
    return load_lexicon(None) if not extra else _load_with_extra(extra)


def _load_with_extra(extra: list[Path]) -> Lexicon:
    from baronh.paths import default_lexicon_paths

    lexicon = load_lexicon(default_lexicon_paths() + extra)
    return lexicon


def cmd_translate(args: argparse.Namespace) -> int:
    text = args.text if args.text is not None else sys.stdin.read()
    engine = args.engine
    pack = _pack_for_lang(args.source) or _pack_for_lang(args.target)
    if pack is not None:
        if engine not in {"local", "auto"}:
            print("言語パックの翻訳は --engine local のみです", file=sys.stderr)
            return 2
        from baronh.transfer import translate_pack

        result = translate_pack(
            text,
            pack,
            source_lang=args.source,
            target_lang=args.target,
        )
    else:
        lexicon = _lexicon(args)
        if engine == "agent":
            from baronh.agent import AgentModelRequired, translate_agent

            try:
                result = translate_agent(
                    text,
                    lexicon,
                    source_lang=args.source,
                    target_lang=args.target,
                    api_key=args.api_key,
                    api_base=getattr(args, "api_base", None),
                    model=args.model,
                )
            except AgentModelRequired as exc:
                print(str(exc), file=sys.stderr)
                return 2
        elif engine in {"openai", "auto"} and (args.api_key or engine == "openai"):
            from baronh.openai_backend import translate_openai

            result = translate_openai(
                text,
                lexicon,
                source_lang=args.source,
                target_lang=args.target,
                api_key=args.api_key,
                api_base=getattr(args, "api_base", None),
                model=args.model,
            )
            if engine == "auto" and not result.text:
                result = translate(
                    text,
                    lexicon,
                    source_lang=args.source,
                    target_lang=args.target,
                    vector_search=getattr(args, "vector_search", False),
                )
        elif engine == "auto":
            result = translate(text, lexicon, source_lang=args.source, target_lang=args.target, vector_search=getattr(args, "vector_search", False))
        else:
            result = translate(text, lexicon, source_lang=args.source, target_lang=args.target, vector_search=getattr(args, "vector_search", False))
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
    pack = None
    if lang == "auto":
        from baronh.translate import detect_lang

        lang = detect_lang(text, _lexicon(args))
    if lang not in {"ja", "en"}:
        try:
            pack = load_pack(lang)
        except LangpackError:
            pack = None
    if args.engine == "openai":
        from baronh.openai_backend import synthesize_openai

        out = Path(args.out) if args.out else Path("speech.mp3")
        path = synthesize_openai(
            text,
            lang=lang,
            api_key=args.api_key,
            api_base=getattr(args, "api_base", None),
            model=getattr(args, "tts_model", None) or "gpt-4o-mini-tts",
            output=out,
        )
        print(path)
        return 0
    result = synthesize_local(
        text,
        lang=lang,
        output=Path(args.out) if args.out else None,
        play=args.play,
        pack=pack,
    )
    print(result.spoken_text)
    if result.audio_path:
        print(result.audio_path, file=sys.stderr)
    if result.note:
        print(f"# {result.note}", file=sys.stderr)
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    from baronh.fanlex import SPECIAL_THANKS
    from baronh.paths import INGESTED_PATH

    document = ingest_auto(args.source)
    kind = (document.get("meta") or {}).get("kind")
    if kind == "ingested" or args.source.lower() in {"known", "thanks", "fan", "mule", "dadh", "ondic", "jisyo"}:
        out = Path(args.out) if args.out else INGESTED_PATH
        write_lexicon_document(document, out)
        print(f"{document.get('source', args.source)} から {document.get('count', 0)} 件を取り込み、{out} に書きました")
        for line in document.get("meta", {}).get("thanks") or [item["thanks"] for item in SPECIAL_THANKS]:
            print(line)
        if args.json:
            print(json.dumps({"source": document.get("source"), "count": document.get("count")}, ensure_ascii=False))
        return 0
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
    from baronh.fanlex import SPECIAL_THANKS

    print("special thanks:")
    for item in SPECIAL_THANKS:
        print(f"  - {item['thanks']}")
    return 0


def cmd_export_web(args: argparse.Namespace) -> int:
    from baronh.vectordb import write_index

    lexicon = _lexicon(args)
    dest = Path(args.out) if args.out else WEB_DIR / "data"
    dest.mkdir(parents=True, exist_ok=True)
    write_lexicon(lexicon, dest / "lexicon.json")
    write_index(lexicon, dest)
    print(dest / "lexicon.json")
    print(dest / "vectors.json")
    print(dest / "vectors.bin")
    return 0


def cmd_reading(args: argparse.Namespace) -> int:
    lang = getattr(args, "lang", "baronh")
    pack = None
    if lang not in {"ja", "en"}:
        try:
            pack = load_pack(lang)
        except LangpackError:
            pack = None
    if pack is not None:
        from baronh.g2p import g2p_ipa, g2p_reading_ja

        print(g2p_reading_ja(args.text, pack))
        if getattr(args, "ipa", False):
            print(g2p_ipa(args.text, pack))
        if args.ath and pack.id == "baronh":
            print(to_ath_keys(args.text))
        return 0
    print(reading_ja(args.text))
    if args.ath:
        print(to_ath_keys(args.text))
    return 0


def cmd_languages(args: argparse.Namespace) -> int:
    rows = []
    for pack in list_packs():
        rows.append(
            {
                "id": pack.id,
                "name_ja": pack.name_ja,
                "name_en": pack.name_en,
                "engine": pack.morphology.engine,
                "path": str(pack.path.parent),
            }
        )
        if not args.json:
            print(f"{pack.id}\t{pack.name_ja}\t{pack.morphology.engine}\t{pack.path.parent}")
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


def cmd_init_lang(args: argparse.Namespace) -> int:
    try:
        dest = init_lang(
            args.id,
            name_ja=args.name_ja or "",
            name_en=args.name_en or "",
            autonym=args.autonym or "",
            template_id=args.template,
        )
    except LangpackError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(dest)
    return 0


def cmd_g2p(args: argparse.Namespace) -> int:
    from baronh.g2p import g2p_ipa, g2p_reading_ja

    try:
        pack = load_pack(args.lang)
    except LangpackError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    reading = g2p_reading_ja(args.text, pack)
    ipa = g2p_ipa(args.text, pack)
    if args.json:
        print(json.dumps({"lang": pack.id, "text": args.text, "reading_ja": reading, "ipa": ipa}, ensure_ascii=False, indent=2))
        return 0
    if args.ipa:
        print(ipa)
    else:
        print(reading)
    return 0


def cmd_recognize(args: argparse.Namespace) -> int:
    from baronh.asr import recognize

    try:
        pack = load_pack(args.lang)
    except LangpackError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    result = recognize(args.text, pack)
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0
    print(result.text)
    if args.show_analysis:
        print(f"# 読み: {result.reading_ja}", file=sys.stderr)
        print(f"# IPA: {result.ipa}", file=sys.stderr)
        for note in result.notes:
            print(f"# {note}", file=sys.stderr)
        for hit in result.path:
            print(f"# {hit.form} ({hit.note})", file=sys.stderr)
    return 0


def cmd_grammar(args: argparse.Namespace) -> int:
    try:
        pack = load_pack(args.lang)
    except LangpackError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(grammar_context_for(pack))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from baronh.server import serve

    host = args.host
    port = args.port if args.port is not None else int(os.environ.get("PORT", "8765"))
    serve(host, port)
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
    p.add_argument("--from", dest="source", default="auto", choices=_lang_choices())
    p.add_argument("--to", dest="target", default="auto", choices=_lang_choices())
    p.add_argument("--engine", default="local", choices=["local", "openai", "agent", "auto"])
    p.add_argument("--vector-search", action="store_true", help="ローカル辞書で未登録語をベクトル検索して寄せる")
    p.add_argument("--api-key", default=None, help="API キー。OPENAI_API_KEY でも可")
    p.add_argument("--api-base", default=None, help="OpenAI 互換ベース URL（例: https://api.openai.com/v1）")
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
    p.add_argument("--lang", default="auto", choices=_lang_choices())
    p.add_argument("--engine", default="local", choices=["local", "openai"])
    p.add_argument("--api-key", default=None, help="API キー。OPENAI_API_KEY でも可")
    p.add_argument("--api-base", default=None, help="OpenAI 互換ベース URL")
    p.add_argument("--tts-model", default="gpt-4o-mini-tts")
    p.add_argument("--out", default=None)
    p.add_argument("--play", action="store_true")
    p.set_defaults(func=cmd_speak)

    p = sub.add_parser("ingest", help="サイトまたはファイルから辞書を取り込む", parents=[shared])
    p.add_argument("source", help="known / mule / dadh / wikipedia / URL / ファイルパス")
    p.add_argument("--out", default=None, help="書き出し先 JSON (既定: data/user_lexicon.json)")
    p.add_argument("--keep", action="store_true", help="既存エントリを上書きしない")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("serve", help="概要・アース・翻訳のサイトとエージェント API を起動する")
    p.add_argument("--host", default="0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
    p.add_argument("--port", type=int, default=None, help="既定 8765。PORT 環境変数があればそれを使う（Cloud Run）")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("export-web", help="Web 用 lexicon.json とベクトル索引を書き出す", parents=[shared])
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_export_web)

    p = sub.add_parser("info", help="辞書の統計を表示する", parents=[shared])
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("reading", help="仮名読み / Ath キー / IPA")
    p.add_argument("text")
    p.add_argument("--lang", default="baronh", choices=_lang_choices())
    p.add_argument("--ath", action="store_true")
    p.add_argument("--ipa", action="store_true")
    p.set_defaults(func=cmd_reading)

    p = sub.add_parser("languages", help="言語パックを列挙する")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_languages)

    p = sub.add_parser("init-lang", help="雛形から新しい言語パックを作る")
    p.add_argument("id", help="小文字の言語 id（ディレクトリ名）")
    p.add_argument("--name-ja", default="", help="日本語名")
    p.add_argument("--name-en", default="", help="英語名")
    p.add_argument("--autonym", default="", help="自称")
    p.add_argument("--template", default="mina", help="複製元パック id")
    p.set_defaults(func=cmd_init_lang)

    p = sub.add_parser("g2p", help="正書法を仮名読みまたは IPA にする")
    p.add_argument("text")
    p.add_argument("--lang", default="baronh", choices=_lang_choices())
    p.add_argument("--ipa", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_g2p)

    p = sub.add_parser("recognize", help="仮名読み / IPA / 正書法を語形制約で認識する")
    p.add_argument("text")
    p.add_argument("--lang", default="baronh", choices=_lang_choices())
    p.add_argument("--json", action="store_true")
    p.add_argument("--show-analysis", action="store_true")
    p.set_defaults(func=cmd_recognize)

    p = sub.add_parser("grammar", help="言語パックの文法コンテキストを出す")
    p.add_argument("--lang", default="baronh", choices=_lang_choices())
    p.set_defaults(func=cmd_grammar)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
