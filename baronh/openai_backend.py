"""OpenAI 互換 Chat Completions / TTS。キーとベース URL は引数または環境変数。"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from baronh.grammar import conjugate, decline
from baronh.lexicon import Lexicon
from baronh.phonology import reading_ja, to_ath_keys
from baronh.translate import TranslationResult, _tokenize_baronh, _tokenize_en, _tokenize_ja, translate

DEFAULT_CHAT_MODEL = "gpt-4o-mini"
DEFAULT_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_TTS_VOICE = "alloy"
DEFAULT_API_BASE = "https://api.openai.com/v1"

GRAMMAR_BRIEF = """
あなたはアーヴ語 (Baronh) の翻訳者です。公式の完全辞書は公開されていないため、
与えられた辞書・文法を根拠にします。普通名詞など辞書にない語は造語せず残します。
辞書にない固有名詞は発音に基づいてローマ字転記し、その語が転記であることを示します。
辞書と文法の全文は渡しません。必要な語は lookup_lexicon、文法の詳細は grammar_note で引いてください。

文法の要点:
- 名詞は7格: 主格(-h/-c が), 対格(-e/-l を), 生格(-r の), 与格(-i/-ri に), 向格(-ré/-é/-gh へ), 奪格(-har/-sar から), 具格(-le で)
- 第1型 abh/abe/bar/bari/baré/abhar/bale、第2型 lamh/lame/lamr/lami/lamé/lamhar/lamhle
- 第3型 duc/dul/dur/duri/dugh/dusar/dule、第4型 saidiac/saidél/saidér/saidéri/saidégh/saidiasar/saidéle
- 代名詞: fe/de/se, farh/darh/cnac, so/re/ai。Fe+a → F'a（主題）
- 後置詞: a は, éü よ, sa か, te と（引用）
- 動詞語尾 直説法: 不定 -e, 完了 -le, 進行 -lér, 未然 -to
- 仮定法: -éme -lar -lérm -dar / 命令 -é / 分詞 -a -la -léra -naur
- 態接辞は語幹と語尾の間に -as- -ar- -ad- の順
- コピュラ ane。F'a bale. のように具格補語で「AはBだ」とも言う
- 語順は SOV または SVO。修飾語は被修飾語の後ろ
- ローマ字化は Nine Lives / 本リポジトリの Aarth キー (ai→A, au→I, eu→E) に従う
"""

GRAMMAR_TOPICS: dict[str, str] = {
    "cases": (
        "7格: 主格 nom（が）対格 acc（を）生格 gen（の）与格 dat（に）"
        "向格 all（へ）奪格 abl（から）具格 ins（で）。"
        "第1型 abh/abe/bar/bari/baré/abhar/bale。"
        "第2型 -h: lamh/lame/lamr/lami/lamé/lamhar/lamhle。"
        "第3型 -c: duc/dul/dur/duri/dugh/dusar/dule。"
        "第4型 -iac: saidiac/saidél/saidér/saidéri/saidégh/saidiasar/saidéle。"
        "主題は代名詞で F'a / D'a / S'a（Fe+a の縮約）。普通名詞は lemma a。"
    ),
    "verbs": (
        "動詞は語幹+態+語尾。直説法: 不定 -e, 完了 -le, 進行 -lér, 未然 -to。"
        "仮定法: -éme -lar -lérm -dar。命令 -é（母音語幹は -éno）。"
        "分詞 -a -la -léra -naur。態は語幹と語尾の間に使役 -as- 受動 -ar- 否定 -ad-。"
        "例: sac → sace / sacle / sacasé。"
    ),
    "pronouns": (
        "fe 私, de あなた, se 彼/彼女, farh 私たち, darh あなたたち, cnac 彼ら,"
        " so これ, re それ, ai あれ。"
        "fe の格: fe/fal/far/feri/feré/fasar/fale。主題 F'a。"
    ),
    "syntax": (
        "語順は SOV または SVO。修飾語は被修飾語の後ろ。"
        "後置詞: a は, éü よ, sa か, te と（引用）, le/lo と（並列）。"
        "「AはBだ」は A(主題) + B(具格)。コピュラ ane は省略することが多い。"
        "疑問は sa を文末に置く。"
    ),
    "phonology": (
        "c は /k/。ch/sh は摩擦音。Ath キー: ai→A, au→I, eu→E。"
        "辞書にない固有名詞は発音転記（カタカナ カ行は ca/ci/cu/ce/co）。"
        "読み上げはローマ字を仮名に落として日本語 TTS に渡す。"
    ),
}

CHAT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "lookup_lexicon",
            "description": "アーヴ語・日本語・英語でローカル辞書を引く。名詞なら7格も返す。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "見出し、語形、日本語または英語"},
                    "lang": {
                        "type": "string",
                        "enum": ["auto", "baronh", "ja", "en"],
                        "description": "検索言語。不明なら auto",
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
                        "description": "cases / verbs / pronouns / syntax / phonology",
                    },
                },
                "required": ["topic"],
            },
        },
    },
]


def normalize_api_base(url: str | None = None) -> str:
    raw = (
        (url or os.environ.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_API_BASE") or DEFAULT_API_BASE)
        .strip()
        .rstrip("/")
    )
    if not raw:
        raw = DEFAULT_API_BASE
    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https"} and parsed.netloc and parsed.path in {"", "/"}:
        raw = raw.rstrip("/") + "/v1"
    return raw


def api_url(path: str, *, api_base: str | None = None) -> str:
    base = normalize_api_base(api_base)
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def resolve_api_key(explicit: str | None = None, *, api_base: str | None = None) -> str:
    key = (explicit or os.environ.get("OPENAI_API_KEY") or "").strip()
    base = normalize_api_base(api_base)
    if key:
        return key
    if "api.openai.com" in base:
        raise RuntimeError("OpenAI API キーがありません。OPENAI_API_KEY か --api-key を設定してください。")
    return "no-key"


def _request(url: str, api_key: str, payload: dict, *, accept: str = "application/json") -> bytes:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": accept,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API error {exc.code}: {detail}") from exc


def _format_entry(entry) -> str:
    line = f"- {entry.lemma} [{entry.pos}] ja:{entry.gloss_ja} en:{entry.gloss_en}"
    if entry.pos in {"noun", "pronoun"}:
        forms = decline(entry)
        line += " " + "/".join(forms[c] for c in ("nom", "acc", "gen", "dat", "all", "abl", "ins"))
    return line


def retrieve_lexicon_context(
    text: str,
    lexicon: Lexicon,
    *,
    local: TranslationResult | None = None,
    limit: int = 36,
) -> str:
    """原文と下訳から関連語だけを拾う。辞書全文は渡さない。"""
    queries: list[str] = []
    queries.extend(_tokenize_ja(text, lexicon))
    queries.extend(_tokenize_baronh(text))
    queries.extend(_tokenize_en(text))
    queries.extend(part for part in text.replace("、", " ").replace(",", " ").split() if part)
    if local:
        queries.extend(item.source for item in local.analysis)
        queries.extend(item.target for item in local.analysis)
        queries.append(local.text)
    picked: list[str] = []
    seen: set[str] = set()
    for word in queries:
        word = word.strip(".,!?;:。")
        if not word:
            continue
        for entry in lexicon.lookup(word, lang="auto"):
            if entry.lemma in seen:
                continue
            seen.add(entry.lemma)
            picked.append(_format_entry(entry))
            if len(picked) >= limit:
                return "\n".join(picked)
    return "\n".join(picked) if picked else "(該当なし。lookup_lexicon で追加検索してください)"


def dispatch_tool(name: str, arguments: dict[str, Any], lexicon: Lexicon) -> str:
    if name == "lookup_lexicon":
        query = str(arguments.get("query") or "").strip()
        lang = str(arguments.get("lang") or "auto")
        if lang not in {"auto", "baronh", "ja", "en"}:
            lang = "auto"
        hits = lexicon.lookup(query, lang=lang)[:8]
        if not hits:
            return json.dumps({"query": query, "hits": []}, ensure_ascii=False)
        return json.dumps(
            {"query": query, "hits": [_format_entry(entry) for entry in hits]},
            ensure_ascii=False,
        )
    if name == "grammar_note":
        topic = str(arguments.get("topic") or "").strip()
        note = GRAMMAR_TOPICS.get(topic)
        if not note:
            return json.dumps({"error": "unknown topic", "topics": list(GRAMMAR_TOPICS)}, ensure_ascii=False)
        return json.dumps({"topic": topic, "note": note}, ensure_ascii=False)
    return json.dumps({"error": f"unknown tool: {name}"}, ensure_ascii=False)


def _chat_once(
    url: str,
    api_key: str,
    payload: dict,
) -> dict[str, Any]:
    raw = _request(url, api_key, payload)
    data = json.loads(raw.decode("utf-8"))
    return data


def _run_tool_loop(
    *,
    url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    lexicon: Lexicon,
    use_tools: bool,
    max_rounds: int = 6,
) -> tuple[str, int]:
    rounds = 0
    for _ in range(max_rounds):
        rounds += 1
        payload: dict[str, Any] = {
            "model": model,
            "temperature": 0.2,
            "messages": messages,
        }
        if use_tools:
            payload["tools"] = CHAT_TOOLS
            payload["tool_choice"] = "auto"
        data = _chat_once(url, api_key, payload)
        message = (data.get("choices") or [{}])[0].get("message") or {}
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            return (message.get("content") or "").strip(), rounds
        messages.append(message)
        for call in tool_calls:
            fn = call.get("function") or {}
            name = fn.get("name") or ""
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            result = dispatch_tool(name, args if isinstance(args, dict) else {}, lexicon)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id") or name,
                    "content": result,
                }
            )
    return "", rounds


def translate_openai(
    text: str,
    lexicon: Lexicon,
    *,
    source_lang: str,
    target_lang: str,
    api_key: str | None = None,
    api_base: str | None = None,
    model: str = DEFAULT_CHAT_MODEL,
    use_tools: bool = True,
) -> TranslationResult:
    base = normalize_api_base(api_base)
    key = resolve_api_key(api_key, api_base=base)
    local = translate(text, lexicon, source_lang=source_lang, target_lang=target_lang)
    retrieved = retrieve_lexicon_context(text, lexicon, local=local)
    user = (
        f"翻訳方向: {local.source_lang} → {target_lang}\n"
        f"原文:\n{text}\n\n"
        f"規則ベースの下訳:\n{local.text}\n\n"
        f"関連辞書（自動検索、全文ではない）:\n{retrieved}\n\n"
        "訳文だけを出力してください。解説は不要です。"
        "足りない語や格は lookup_lexicon / grammar_note で引いてから訳してください。"
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": GRAMMAR_BRIEF.strip()},
        {"role": "user", "content": user},
    ]
    url = api_url("chat/completions", api_base=base)
    notes = [
        f"OpenAI 互換 Chat Completions（{base}）。下訳と検索した辞書を渡し、必要ならツールで追加検索します。",
    ]
    used_tools = False
    try:
        out, rounds = _run_tool_loop(
            url=url, api_key=key, model=model, messages=list(messages), lexicon=lexicon, use_tools=use_tools
        )
        used_tools = use_tools and rounds > 1
        notes.append(f"チャット往復 {rounds} 回。")
    except RuntimeError as exc:
        if use_tools and ("tool" in str(exc).lower() or "400" in str(exc)):
            out, rounds = _run_tool_loop(
                url=url, api_key=key, model=model, messages=list(messages), lexicon=lexicon, use_tools=False
            )
            notes.append(f"ツール非対応のため単発に切り替え（{rounds} 回）。")
        else:
            raise
    if not out:
        out = local.text
        notes.append("生成結果が空のため下訳を使いました。")
    if used_tools:
        notes.append("モデルが lookup_lexicon / grammar_note を呼び出しています。")
    return TranslationResult(
        source_lang=local.source_lang,
        target_lang=target_lang,
        source_text=text,
        text=out,
        engine="openai",
        ath_keys=to_ath_keys(out) if target_lang == "baronh" else "",
        reading_ja=reading_ja(out) if target_lang == "baronh" else local.reading_ja,
        analysis=local.analysis,
        notes=notes,
        unknown=local.unknown,
    )


def synthesize_openai(
    text: str,
    *,
    lang: str = "baronh",
    api_key: str | None = None,
    api_base: str | None = None,
    model: str = DEFAULT_TTS_MODEL,
    voice: str = DEFAULT_TTS_VOICE,
    output: Path,
) -> Path:
    """翻訳とは別呼び出し。アーヴ語は先に仮名読みへ落としてから /audio/speech へ渡す。"""
    base = normalize_api_base(api_base)
    key = resolve_api_key(api_key, api_base=base)
    spoken = reading_ja(text) if lang == "baronh" else text
    payload = {
        "model": model,
        "voice": voice,
        "input": spoken,
        "format": "mp3",
    }
    raw = _request(api_url("audio/speech", api_base=base), key, payload, accept="audio/mpeg")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(raw)
    return output
