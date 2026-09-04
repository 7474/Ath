"""サーバサイドのアーヴ語翻訳エージェント。

クライアントからの単発 Chat Completions ではなく、辞書の類義語探索 →
言い換え → 生成 → 語形検証 をサーバで回す。LLM が無くても類義語の
局所置換は行う。モデル呼び出しは OpenAI 互換（Vertex / Bedrock / ローカル）に載せる。
"""

from __future__ import annotations

import json
import os
from typing import Any

from baronh.grammar import FormIndex
from baronh.lexicon import Lexicon
from baronh.openai_backend import (
    DEFAULT_CHAT_MODEL,
    GRAMMAR_TOPICS,
    api_url,
    clean_model_text,
    dispatch_tool as openai_dispatch_tool,
    invented_baronh_forms,
    normalize_api_base,
    resolve_api_key,
    retrieve_lexicon_context,
    run_chat_tool_loop,
    system_prompt as openai_system_prompt,
)
from baronh.phonology import reading_ja, to_ath_keys
from baronh.synonyms import (
    coverage_plan,
    find_synonyms,
    format_hits,
    format_plan,
    paraphrase_source,
    uncovered_tokens,
)
from baronh.translate import TokenGloss, TranslationResult, translate

AGENT_BRIEF = """
あなたはアーヴ語 (Baronh) の翻訳エージェントです。公式の完全辞書は公開されていないため、
与えられた辞書・文法だけを根拠にします。

目標言語がアーヴ語のとき、最優先は「辞書にある語で意味が通ること」です。
辞書にない普通名詞は造語せず、find_synonyms で辞書語釈の類義語・言い換えを探し、
その見出しの格変化・活用で訳してください。意味がややずれても、未登録語を残すより
辞書の類義語を使います。どうしても見つからなければ原文の語を残します。
固有名詞は発音転記（ジ行 gh、カ行 c、主格 -c/-h/-n。j/k/w/v は使わない）を維持します。
下訳は規則ベースで抜けがあります。類義語表と辞書で直してください。
訳文だけを出力し、解説や引用符は付けないでください。
"""

FEW_SHOT_SYNONYM = """
例（類義語で辞書に寄せる）:
- 星たちの光を見ます → 光は辞書に無いので 輝くもの (sairiac) に寄せ、gereulachr sairial mire.
- 私はアーヴです → F'a bale.
- ジントはアーヴです → ghintoc a bale.（ジントは固有名詞の発音転記）
"""

AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "lookup_lexicon",
            "description": "アーヴ語・日本語・英語でローカル辞書を引く。誤字や表記ゆれでも近い見出しを返す。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "lang": {
                        "type": "string",
                        "enum": ["auto", "baronh", "ja", "en"],
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_synonyms",
            "description": "辞書にない語を、語釈の類義語・言い換えで辞書見出しへ寄せる。普通名詞向け。固有名詞には使わない。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "原文の未登録語、または言い換え候補"},
                    "extra_keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "モデルが考えた類義語・言い換え。辞書照合に使う",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grammar_note",
            "description": "アーヴ語文法の詳細トピックを取り出す。",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "enum": list(GRAMMAR_TOPICS.keys()),
                    },
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_baronh",
            "description": "生成したアーヴ語のうち、辞書語形でも発音転記でもない語を列挙する。",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "検証するアーヴ語"},
                },
                "required": ["text"],
            },
        },
    },
]


def dispatch_agent_tool(
    name: str,
    arguments: dict[str, Any],
    lexicon: Lexicon,
    *,
    local: TranslationResult | None = None,
) -> str:
    if name == "find_synonyms":
        query = str(arguments.get("query") or "").strip()
        extra = arguments.get("extra_keys") or []
        if not isinstance(extra, list):
            extra = [str(extra)]
        extra_keys = [str(item).strip() for item in extra if str(item).strip()]
        hits = find_synonyms(query, lexicon, extra_keys=extra_keys)
        return json.dumps(
            {"query": query, "hits": format_hits(hits)},
            ensure_ascii=False,
        )
    if name == "validate_baronh":
        text = str(arguments.get("text") or "")
        invented = invented_baronh_forms(text, lexicon, local=local)
        return json.dumps({"text": text, "invented": invented}, ensure_ascii=False)
    return openai_dispatch_tool(name, arguments, lexicon)


def agent_system_prompt(target_lang: str) -> str:
    topics = "\n".join(f"- {name}: {body}" for name, body in GRAMMAR_TOPICS.items())
    shot = FEW_SHOT_SYNONYM if target_lang == "baronh" else openai_system_prompt(target_lang)
    if target_lang == "baronh":
        return f"{AGENT_BRIEF.strip()}\n\n文法の詳細:\n{topics}\n{shot.strip()}"
    return openai_system_prompt(target_lang)


def build_agent_user_prompt(
    text: str,
    lexicon: Lexicon,
    *,
    local: TranslationResult,
    target_lang: str,
    paraphrased: str,
    plan_text: str,
) -> str:
    retrieved = retrieve_lexicon_context(text, lexicon, local=local)
    extra = ""
    if paraphrased and paraphrased != text:
        extra = f"\n\n類義語で言い換えた原文:\n{paraphrased}\n"
    return (
        f"翻訳方向: {local.source_lang} → {target_lang}\n"
        f"原文:\n{text}\n"
        f"{extra}"
        f"規則ベースの下訳（誤り・抜けあり。類義語で直してよい）:\n{local.text}\n\n"
        f"類義語カバレッジ:\n{plan_text}\n\n"
        f"関連辞書（全文ではない）:\n{retrieved}\n\n"
        "訳文だけを出力してください。"
        "足りない普通名詞は find_synonyms、見出しの確認は lookup_lexicon、"
        "格は grammar_note、書き上がったら validate_baronh を使ってください。"
    )


def _apply_result(
    text: str,
    lexicon: Lexicon,
    *,
    local: TranslationResult,
    out: str,
    notes: list[str],
    substitutions: list[dict[str, str]],
    engine: str,
) -> TranslationResult:
    target_lang = local.target_lang
    analysis = list(local.analysis)
    seen = {item.source for item in analysis}
    for item in substitutions:
        src = item.get("from") or ""
        lemma = item.get("lemma") or ""
        gloss = item.get("gloss") or ""
        via = item.get("via") or ""
        if not src or src in seen:
            continue
        analysis.append(TokenGloss(src, lemma, f"類義語 {gloss}" + (f"（{via}）" if via else "")))
        seen.add(src)
    return TranslationResult(
        source_lang=local.source_lang,
        target_lang=target_lang,
        source_text=text,
        text=out,
        engine=engine,
        ath_keys=to_ath_keys(out) if target_lang == "baronh" else "",
        reading_ja=reading_ja(out) if target_lang == "baronh" else local.reading_ja,
        analysis=analysis,
        notes=notes,
        unknown=[word for word in local.unknown if word not in {item.get("from") for item in substitutions}],
        substitutions=substitutions,
    )


def _local_synonym_translate(
    text: str,
    lexicon: Lexicon,
    *,
    source_lang: str,
    target_lang: str,
) -> tuple[TranslationResult, str, list[dict[str, str]], str]:
    local = translate(text, lexicon, source_lang=source_lang, target_lang=target_lang)
    if target_lang != "baronh" or local.source_lang == "baronh":
        return local, text, [], format_plan(coverage_plan(local, lexicon))
    plan = coverage_plan(local, lexicon)
    paraphrased, substitutions = paraphrase_source(text, plan, source_lang=local.source_lang)
    if paraphrased != text and substitutions:
        rewritten = translate(paraphrased, lexicon, source_lang=local.source_lang, target_lang=target_lang)
        rewritten.source_text = text
        rewritten.notes = [
            note for note in rewritten.notes if "未登録の語は原文のまま" not in note
        ] + [
            "未登録の普通名詞を辞書の類義語・言い換えに寄せてから規則翻訳しました。"
        ]
        rewritten.unknown = [word for word in rewritten.unknown if word not in {item["from"] for item in substitutions}]
        rewritten.substitutions = substitutions
        rewritten.analysis = list(rewritten.analysis)
        for item in substitutions:
            from baronh.translate import TokenGloss

            rewritten.analysis.append(
                TokenGloss(item["from"], item["lemma"], f"類義語 {item['gloss']}（{item['via']}）")
            )
        return rewritten, paraphrased, substitutions, format_plan(plan)
    return local, paraphrased, substitutions, format_plan(plan)


def translate_agent(
    text: str,
    lexicon: Lexicon,
    *,
    source_lang: str = "auto",
    target_lang: str = "auto",
    api_key: str | None = None,
    api_base: str | None = None,
    model: str | None = None,
    use_model: bool | None = None,
    chat_once: Any = None,
    max_rounds: int = 10,
) -> TranslationResult:
    """類義語制約の翻訳。use_model=False またはキー無しなら局所置換のみ。"""
    draft, paraphrased, substitutions, plan_text = _local_synonym_translate(
        text, lexicon, source_lang=source_lang, target_lang=target_lang
    )
    notes = list(draft.notes)
    if substitutions:
        summary = "、".join(f"{item['from']}→{item['lemma']}「{item['gloss']}」" for item in substitutions)
        notes.append("類義語置換: " + summary + "。")

    want_model = use_model
    if want_model is None:
        if chat_once is not None:
            want_model = True
        elif api_key or os.environ.get("OPENAI_API_KEY"):
            want_model = True
        else:
            want_model = bool(
                api_base or os.environ.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_API_BASE")
            )

    if not want_model or draft.target_lang != "baronh":
        draft.engine = "agent"
        draft.notes = notes or draft.notes
        draft.substitutions = substitutions
        return draft

    base = normalize_api_base(api_base)
    key = "no-key" if chat_once is not None else resolve_api_key(api_key, api_base=base)
    chat_model = model or os.environ.get("OPENAI_CHAT_MODEL") or DEFAULT_CHAT_MODEL
    user = build_agent_user_prompt(
        text,
        lexicon,
        local=draft,
        target_lang=draft.target_lang,
        paraphrased=paraphrased,
        plan_text=plan_text,
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": agent_system_prompt(draft.target_lang)},
        {"role": "user", "content": user},
    ]
    url = api_url("chat/completions", api_base=base)
    notes.append(f"サーバエージェント（{base}）。類義語探索と語形検証をサーバ側で回します。")

    def _dispatch(name: str, arguments: dict[str, Any], lex: Lexicon) -> str:
        return dispatch_agent_tool(name, arguments, lex, local=draft)

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
            notes.append(f"ツール非対応のため単発に切り替え（{rounds} 回）。")
        else:
            notes.append(f"モデル呼び出しに失敗したため類義語付き下訳を使います: {exc}")
            draft.engine = "agent"
            draft.notes = notes
            return draft

    out = clean_model_text(out)
    if not out:
        out = draft.text
        notes.append("生成結果が空のため類義語付き下訳を使いました。")

    if draft.target_lang == "baronh":
        index = FormIndex(lexicon)
        invented = invented_baronh_forms(out, lexicon, local=draft, index=index)
        if invented and out != draft.text:
            critique = (
                f"次の語は辞書の語形でも発音転記でも類義語の格変化でもありません: {', '.join(invented)}。"
                "造語せず、find_synonyms で辞書の類義語に寄せて書き直してください。"
                "訳文だけを出力してください。"
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
                    again = invented_baronh_forms(rewritten, lexicon, local=draft, index=index)
                    if len(again) <= len(invented):
                        out = rewritten
                        invented = again
            except RuntimeError:
                notes.append("語形の再生成に失敗したため、最初の生成を使います。")
        if invented:
            notes.append("辞書にない語形: " + ", ".join(invented) + "。")
            if draft.text and not invented_baronh_forms(draft.text, lexicon, local=draft, index=index):
                if len(invented) >= 2:
                    notes.append("生成文の未登録語が多いため類義語付き下訳を使いました。")
                    out = draft.text

    return _apply_result(
        text,
        lexicon,
        local=draft,
        out=out,
        notes=notes,
        substitutions=substitutions,
        engine="agent",
    )
