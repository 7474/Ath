"""サーバサイドのアーヴ語翻訳エージェント。

規則ベースの下訳を直すのではなく、生成 AI がベクトル検索した辞書と文法コンテキストで訳す。
辞書 lookup・類義語・発音転記・語形検証はツールとして提供し、文の組み立てはモデルが行う。
モデル（OpenAI 互換 / Vertex / Bedrock 等）が無いときは動かない。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from baronh.grammar import FormIndex, decline, grammar_context
from baronh.lexicon import Entry, Lexicon
from baronh.openai_backend import (
    DEFAULT_CHAT_MODEL,
    GRAMMAR_TOPICS,
    api_url,
    clean_model_text,
    collect_lookup_queries,
    collect_tool_strings,
    dispatch_tool as openai_dispatch_tool,
    invented_baronh_forms,
    normalize_api_base,
    resolve_api_key,
    run_chat_tool_loop,
    system_prompt as openai_system_prompt,
    _json_single_or_results,
)
from baronh.phonology import looks_like_proper_noun, reading_ja, to_ath_keys, transcribe_proper_noun
from baronh.synonyms import find_synonyms, format_hits
from baronh.translate import (
    JA_PARTICLES,
    TokenGloss,
    TranslationResult,
    _tokenize_baronh,
    _tokenize_en,
    _tokenize_ja,
    detect_lang,
)
from baronh.vectordb import get_index, hit_to_dict, search_context

AGENT_BRIEF = """
あなたはアーヴ語 (Baronh) の翻訳エージェントです。公式の完全辞書は公開されていないため、
与えられた文法コンテキストと、ベクトル検索した辞書だけを根拠に、自分で訳文を組み立てます。
規則ベースの下訳は渡しません。なぞらないでください。

目標言語がアーヴ語のとき、最優先は「辞書にある語で意味が通ること」です。
辞書にない普通名詞は造語せず、search_lexicon（ベクトル検索）や find_synonyms で
語釈の類義語・言い換えを探し、その見出しの格変化・活用で訳してください。
意味がややずれても、未登録語を残すより辞書の類義語を使います。
固有名詞は transcribe_name でアーヴ語正書法へ発音転記します
（ジ行 gh、カ行 c、主格 -c/-h/-n。j/k/w/v は使わない）。
文法は下のコンテキストに全文があります。grammar_note は確認用で、使うなら topics にまとめて1回だけ。
足りない語は search_lexicon / find_synonyms / lookup_lexicon の queries（固有名詞は transcribe_name の names）にすべて入れて1回で引く。
1語ずつの連続呼び出しは禁止。関連辞書で足りるならツールは使わず訳文だけを出す。
validate_baronh は訳文が書けてから1回だけ。
訳文だけを出力し、解説や引用符は付けないでください。
"""

FEW_SHOT_SYNONYM = """
例（類義語で辞書に寄せる。文はモデルが組む）:
- 星たちの光を見ます → 光は辞書に無いので 輝くもの (sairiac) に寄せ、gereulacr sairiac mire.
- 私はアーヴです → F'a bale.
- ジントはアーヴです → ghintoc a bale.（ジントは固有名詞の発音転記）
"""

AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_lexicon",
            "description": (
                "アーヴ語辞書のベクトル検索。足りない語はすべて queries に入れて1回だけ呼ぶ。"
                "1語ずつの連続呼び出しは禁止。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "queries": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "原文の語・言い換え・短い句をすべて入れる",
                    },
                    "limit": {"type": "integer", "description": "各語の返す件数。既定 8"},
                },
                "required": ["queries"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_lexicon",
            "description": (
                "辞書の厳密検索。lemma / gloss / alias の近い一致。"
                "足りない語はすべて queries に入れて1回だけ呼ぶ。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "queries": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "検索語をすべて入れる",
                    },
                    "lang": {
                        "type": "string",
                        "enum": ["auto", "baronh", "ja", "en"],
                    },
                },
                "required": ["queries"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_synonyms",
            "description": (
                "未登録の普通名詞を辞書語釈の類義語へ寄せる。固有名詞には使わない。"
                "足りない語はすべて queries に入れて1回だけ呼ぶ。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "queries": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "寄せたい概念をすべて入れる。例: 光、見る",
                    },
                    "extra_keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "モデルが考えた類義語・言い換え。辞書照合に使う",
                    },
                },
                "required": ["queries"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "transcribe_name",
            "description": (
                "固有名詞をアーヴ語音写する。ジ行は gh、カ行は c、ヴは bh。"
                "複数なら names にまとめて1回だけ呼ぶ。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "カタカナ・欧文などの固有名詞をすべて入れる",
                    },
                    "kind": {
                        "type": "string",
                        "enum": ["person", "place", "other"],
                        "description": "人名なら person、地名なら place",
                    },
                },
                "required": ["names"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grammar_note",
            "description": "文法トピックを取り出す。要点は既出なので原則不要。使うなら topics にまとめて1回だけ。",
            "parameters": {
                "type": "object",
                "properties": {
                    "topics": {
                        "type": "array",
                        "items": {"type": "string", "enum": list(GRAMMAR_TOPICS.keys())},
                    }
                },
                "required": ["topics"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_baronh",
            "description": "訳文の各語が辞書 lemma か、許容する固有名詞音写かを検査する。訳文が書けてから1回だけ。",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "検査するアーヴ語テキスト"}
                },
                "required": ["text"],
            },
        },
    },
]


class AgentModelRequired(RuntimeError):
    """エージェントは生成 AI が必須。"""

    def __init__(self) -> None:
        super().__init__(
            "サーバエージェントは生成 AI が必要です。"
            "OPENAI_API_KEY または OPENAI_BASE_URL を設定するか、--api-key / --api-base を渡してください。"
            "規則ベースだけ使うときは --engine local です。"
        )


@dataclass
class AgentTrace:
    substitutions: list[dict[str, str]] = field(default_factory=list)
    names: list[tuple[str, str]] = field(default_factory=list)

    def phonetic_local(self, *, source_lang: str, target_lang: str, source_text: str) -> TranslationResult:
        analysis = [
            TokenGloss(name, lemma, "発音転記（辞書にない固有名詞）") for name, lemma in self.names
        ]
        return TranslationResult(
            source_lang=source_lang,
            target_lang=target_lang,
            source_text=source_text,
            text="",
            analysis=analysis,
        )


def model_configured(
    *,
    api_key: str | None = None,
    api_base: str | None = None,
    chat_once: Any = None,
) -> bool:
    if chat_once is not None:
        return True
    if (api_key or os.environ.get("OPENAI_API_KEY") or "").strip():
        return True
    return bool(
        (api_base or os.environ.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_API_BASE") or "").strip()
    )


def _source_tokens(text: str, lexicon: Lexicon, source_lang: str) -> list[str]:
    if source_lang == "en":
        return _tokenize_en(text)
    if source_lang == "baronh":
        return _tokenize_baronh(text)
    return _tokenize_ja(text, lexicon)


def dictionary_hints(text: str, lexicon: Lexicon, source_lang: str) -> str:
    """原文トークンを辞書・類義語で注記する。アーヴ語の文は組まない。"""
    lines: list[str] = []
    seen: set[str] = set()
    for tok in _source_tokens(text, lexicon, source_lang):
        word = tok.strip(".,!?;:。？！")
        if not word or word in seen or word in JA_PARTICLES:
            continue
        if word in "、。！？!?.":
            continue
        seen.add(word)
        exact = lexicon.lookup(word, lang="auto")
        if exact:
            top = exact[0]
            lines.append(f"- {word}: 辞書 {top.lemma} [{top.pos}] 「{top.gloss_ja}」")
            continue
        syn = find_synonyms(word, lexicon, limit=3)
        if syn:
            bits = " / ".join(f"{hit.entry.lemma}「{hit.entry.gloss_ja}」（{hit.via}）" for hit in syn[:3])
            lines.append(f"- {word}: 未登録の普通名詞。類義語候補 {bits}")
            continue
        if looks_like_proper_noun(word):
            lines.append(f"- {word}: 固有名詞の可能性。transcribe_name で発音転記")
            continue
        lines.append(f"- {word}: 未登録。search_lexicon / find_synonyms で辞書内の言い換えを探す")
    return "\n".join(lines) if lines else "(ヒントなし。search_lexicon で引いてください)"


def dispatch_agent_tool(
    name: str,
    arguments: dict[str, Any],
    lexicon: Lexicon,
    *,
    local: TranslationResult | None = None,
    trace: AgentTrace | None = None,
) -> str:
    if name == "search_lexicon":
        queries = collect_lookup_queries(arguments)
        try:
            limit = int(arguments.get("limit") or 8)
        except (TypeError, ValueError):
            limit = 8
        limit = max(1, min(limit, 16))
        packed = []
        for query in queries:
            hits = get_index(lexicon).search(query, limit=limit)
            packed.append({"query": query, "hits": [hit_to_dict(hit) for hit in hits]})
        return _json_single_or_results(packed)
    if name == "find_synonyms":
        queries = collect_lookup_queries(arguments)
        extra = arguments.get("extra_keys") or []
        if not isinstance(extra, list):
            extra = [str(extra)]
        extra_keys = [str(item).strip() for item in extra if str(item).strip()]
        packed = []
        for query in queries:
            hits = find_synonyms(query, lexicon, extra_keys=extra_keys)
            if trace is not None and hits:
                top = hits[0]
                if not any(item.get("from") == query for item in trace.substitutions):
                    trace.substitutions.append(
                        {
                            "from": query,
                            "to": top.via,
                            "lemma": top.entry.lemma,
                            "gloss": top.entry.gloss_ja,
                            "relation": top.relation,
                            "via": top.via,
                        }
                    )
            packed.append({"query": query, "hits": format_hits(hits)})
        return _json_single_or_results(packed)
    if name == "transcribe_name":
        names = collect_tool_strings(arguments, "names", "name")
        packed = []
        for raw_name in names:
            lemma, kind = transcribe_proper_noun(raw_name)
            if not lemma:
                packed.append({"name": raw_name, "error": "empty name"})
                continue
            entry = Entry(lemma=lemma, pos="noun", gloss_ja=raw_name, declension=kind or "")
            forms = decline(entry) if entry.pos == "noun" else {}
            if trace is not None:
                trace.names.append((raw_name, lemma))
            packed.append(
                {
                    "name": raw_name,
                    "lemma": lemma,
                    "declension": kind,
                    "forms": forms,
                    "note": "固有名詞の発音転記。辞書の見出しではない。",
                }
            )
        if not packed:
            return json.dumps({"error": "empty name"}, ensure_ascii=False)
        if len(packed) == 1:
            return json.dumps(packed[0], ensure_ascii=False)
        return json.dumps({"results": packed}, ensure_ascii=False)
    if name == "validate_baronh":
        text = str(arguments.get("text") or "")
        invented = invented_baronh_forms(text, lexicon, local=local)
        return json.dumps({"text": text, "invented": invented}, ensure_ascii=False)
    return openai_dispatch_tool(name, arguments, lexicon)


def agent_system_prompt(target_lang: str) -> str:
    grammar = grammar_context()
    if target_lang == "baronh":
        return f"{AGENT_BRIEF.strip()}\n\n{grammar}\n\n{FEW_SHOT_SYNONYM.strip()}"
    return f"{openai_system_prompt(target_lang)}\n\n{grammar}"


def build_agent_user_prompt(
    text: str,
    lexicon: Lexicon,
    *,
    source_lang: str,
    target_lang: str,
) -> str:
    queries = [text, *_source_tokens(text, lexicon, source_lang)]
    retrieved = search_context(queries, lexicon, limit=16)
    hints = dictionary_hints(text, lexicon, source_lang)
    return (
        f"翻訳方向: {source_lang} → {target_lang}\n"
        f"原文:\n{text}\n\n"
        f"辞書ヒント（文ではない。訳は自分で組む）:\n{hints}\n\n"
        f"ベクトル検索した関連辞書（全文ではない）:\n{retrieved}\n\n"
        "訳文だけを出力してください。規則ベースの下訳はありません。"
        "足りない語は search_lexicon / find_synonyms / lookup_lexicon の queries にまとめて1回で引く。"
        "1語ずつの連続呼び出しは禁止。固有名詞は transcribe_name の names にまとめる。"
        "文法はシステムプロンプトにある。validate_baronh は訳文が書けてから1回だけ。"
    )


def _infer_substitutions(
    text: str,
    generated: str,
    lexicon: Lexicon,
    source_lang: str,
    existing: list[dict[str, str]],
) -> list[dict[str, str]]:
    out = list(existing)
    seen = {item.get("from") for item in out}
    hay = generated.casefold()
    for tok in _source_tokens(text, lexicon, source_lang):
        word = tok.strip(".,!?;:。？！")
        if not word or word in seen or word in JA_PARTICLES:
            continue
        if lexicon.lookup(word, lang="auto"):
            continue
        if looks_like_proper_noun(word):
            continue
        for hit in find_synonyms(word, lexicon, limit=4):
            lemma = hit.entry.lemma
            if lemma and lemma.casefold() in hay:
                out.append(
                    {
                        "from": word,
                        "to": hit.via,
                        "lemma": lemma,
                        "gloss": hit.entry.gloss_ja,
                        "relation": hit.relation,
                        "via": hit.via,
                    }
                )
                seen.add(word)
                break
    return out


def translate_agent(
    text: str,
    lexicon: Lexicon,
    *,
    source_lang: str = "auto",
    target_lang: str = "auto",
    api_key: str | None = None,
    api_base: str | None = None,
    model: str | None = None,
    chat_once: Any = None,
    max_rounds: int = 3,
) -> TranslationResult:
    """生成 AI が辞書ツールで訳す。モデルが無ければ AgentModelRequired。"""
    if not model_configured(api_key=api_key, api_base=api_base, chat_once=chat_once):
        raise AgentModelRequired()

    src = source_lang if source_lang != "auto" else detect_lang(text, lexicon)
    tgt = target_lang if target_lang != "auto" else ("ja" if src == "baronh" else "baronh")
    trace = AgentTrace()
    stub = trace.phonetic_local(source_lang=src, target_lang=tgt, source_text=text)
    notes = [
        "サーバエージェントは生成 AI がベクトル辞書と文法コンテキストで訳します。規則ベースの下訳は使いません。",
    ]

    base = normalize_api_base(api_base)
    key = "no-key" if chat_once is not None else resolve_api_key(api_key, api_base=base)
    chat_model = model or os.environ.get("OPENAI_CHAT_MODEL") or DEFAULT_CHAT_MODEL
    user = build_agent_user_prompt(text, lexicon, source_lang=src, target_lang=tgt)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": agent_system_prompt(tgt)},
        {"role": "user", "content": user},
    ]
    url = api_url("chat/completions", api_base=base)
    notes.append(f"モデル {chat_model}（{base}）。")

    def _dispatch(name: str, arguments: dict[str, Any], lex: Lexicon) -> str:
        stub.analysis = trace.phonetic_local(source_lang=src, target_lang=tgt, source_text=text).analysis
        return dispatch_agent_tool(name, arguments, lex, local=stub, trace=trace)

    try:
        out, rounds = run_chat_tool_loop(
            url=url,
            api_key=key,
            model=chat_model,
            messages=list(messages),
            lexicon=lexicon,
            use_tools=True,
            max_rounds=max_rounds,
            tools=AGENT_TOOLS,
            dispatch=_dispatch,
            chat_once=chat_once,
        )
        notes.append(f"チャット往復 {rounds} 回。")
    except RuntimeError as exc:
        if "tool" in str(exc).lower() or "400" in str(exc):
            out, rounds = run_chat_tool_loop(
                url=url,
                api_key=key,
                model=chat_model,
                messages=list(messages),
                lexicon=lexicon,
                use_tools=False,
                max_rounds=3,
                chat_once=chat_once,
            )
            notes.append(f"ツール非対応のため生成の単発に切り替え（{rounds} 回）。規則下訳には戻しません。")
        else:
            raise

    out = clean_model_text(out)
    if not out:
        raise RuntimeError("生成結果が空でした。規則ベースへはフォールバックしません。")

    stub = trace.phonetic_local(source_lang=src, target_lang=tgt, source_text=text)
    if tgt == "baronh":
        index = FormIndex(lexicon)
        invented = invented_baronh_forms(out, lexicon, local=stub, index=index)
        if invented:
            critique = (
                f"次の語は辞書の語形でも発音転記でもありません: {', '.join(invented)}。"
                "造語せず、search_lexicon / find_synonyms の queries にまとめて辞書の類義語へ寄せて書き直してください。"
                "規則ベースの下訳は無いので、自分で訳してください。訳文だけを出力してください。"
            )
            retry_messages = list(messages) + [
                {"role": "assistant", "content": out},
                {"role": "user", "content": critique},
            ]
            try:
                rewritten, extra = run_chat_tool_loop(
                    url=url,
                    api_key=key,
                    model=chat_model,
                    messages=retry_messages,
                    lexicon=lexicon,
                    use_tools=True,
                    max_rounds=4,
                    tools=AGENT_TOOLS,
                    dispatch=_dispatch,
                    chat_once=chat_once,
                )
                rewritten = clean_model_text(rewritten)
                notes.append(f"辞書にない語形 {', '.join(invented)} を検出し、再生成しました（+{extra} 回）。")
                if rewritten:
                    again = invented_baronh_forms(rewritten, lexicon, local=stub, index=index)
                    if len(again) <= len(invented):
                        out = rewritten
                        invented = again
            except RuntimeError:
                notes.append("語形の再生成に失敗したため、最初の生成を使います。規則下訳には戻しません。")
        if invented:
            notes.append("辞書にない語形: " + ", ".join(invented) + "。")

    substitutions = _infer_substitutions(text, out, lexicon, src, trace.substitutions)
    analysis: list[TokenGloss] = []
    seen: set[str] = set()
    for name, lemma in trace.names:
        analysis.append(TokenGloss(name, lemma, "発音転記（辞書にない固有名詞）"))
        seen.add(name)
    for item in substitutions:
        src_word = item.get("from") or ""
        if not src_word or src_word in seen:
            continue
        analysis.append(
            TokenGloss(
                src_word,
                item.get("lemma") or "",
                f"類義語 {item.get('gloss') or ''}" + (f"（{item.get('via')}）" if item.get("via") else ""),
            )
        )
        seen.add(src_word)

    return TranslationResult(
        source_lang=src,
        target_lang=tgt,
        source_text=text,
        text=out,
        engine="agent",
        ath_keys=to_ath_keys(out) if tgt == "baronh" else "",
        reading_ja=reading_ja(out) if tgt == "baronh" else "",
        analysis=analysis,
        notes=notes,
        unknown=[],
        substitutions=substitutions,
    )
