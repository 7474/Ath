"""OpenAI 互換 Chat Completions / TTS。キーとベース URL は引数または環境変数。

アーキテクチャ上の特性と制約は baronh/ARCHITECTURE.md を参照。
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from baronh.grammar import FormIndex, conjugate, decline
from baronh.lexicon import Entry, Lexicon
from baronh.phonology import reading_ja, to_ath_keys
from baronh.translate import (
    JA_PARTICLES,
    TranslationResult,
    _tokenize_baronh,
    _tokenize_en,
    _tokenize_ja,
    translate,
)

DEFAULT_CHAT_MODEL = "gpt-4o-mini"
DEFAULT_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_TTS_VOICE = "alloy"
DEFAULT_API_BASE = "https://api.openai.com/v1"

GRAMMAR_BRIEF = """
あなたはアーヴ語 (Baronh) の翻訳者です。公式の完全辞書は公開されていないため、
与えられた辞書・文法だけを根拠にします。
下訳は規則ベースで、抜けや誤りがあります。辞書と文法で直してください。
原文の誤字・仮名漢字・ヴ/ブ・長音の表記ゆれは、辞書の近い見出しに寄せてよい。
普通名詞など辞書にない語は造語せず、原文の語を残します。
辞書にない固有名詞はアーヴ語の正書法で発音転記して構いません（ジ行は gh、カ行は c、主格は -c/-h/-n。j/k/w/v は使わない）。ただし辞書に近い見出しがあるなら転記より辞書を優先します。
必要な語は lookup_lexicon、文法の確認は grammar_note で追加検索できます。
訳文だけを出力し、解説や引用符は付けないでください。

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

FEW_SHOT_TO_BARONH = """
例（ja/en → baronh）:
- 私は移民します → F'a usere.
- 私はアーヴです → F'a bale.
- 分かりますか → face sa?
- ありがとう → zom.
- ジントはアーヴです → ghintoc a bale.
"""

FEW_SHOT_FROM_BARONH = """
例（baronh → ja/en）:
- F'a usere. → 私は移民する / I immigrate.
- F'a bale. → 私はアーヴだ / I am Abh.
- face sa? → 分かりますか / Do you understand?
- zom. → ありがとう / Thanks.
"""

CLOSED_BARONH = frozenset({"a", "éü", "sa", "te", "le", "lo", "f'a", "d'a", "s'a"})

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
        "c は /k/。ch は摩擦音。Ath キー: ai→A, au→I, eu→E。"
        "辞書にない固有名詞はアーヴ語正書法で発音転記する。"
        "カ行は ca/ci/cu/ce/co。ジ行は gh（g+h=[ʒ]）。ヴは bh。アースに無い j/k/w/v は使わない。"
        "名詞の主格は -c / -h / -n で終わる。"
        "読み上げはローマ字を仮名に落として日本語 TTS に渡す。"
    ),
}

CHAT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "lookup_lexicon",
            "description": "アーヴ語・日本語・英語でローカル辞書を引く。誤字や表記ゆれでも近い見出しを返す。名詞なら7格も返す。",
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
    elif entry.pos == "verb":
        forms = [
            conjugate(entry, mood="indicative", aspect="indefinite"),
            conjugate(entry, mood="indicative", aspect="perfect"),
            conjugate(entry, mood="indicative", aspect="progressive"),
            conjugate(entry, mood="imperative", aspect="indefinite"),
        ]
        line += " 活用:" + "/".join(forms)
    return line


def _is_searchable_note(note: str) -> bool:
    text = (note or "").strip()
    if not text or text in JA_PARTICLES or text == "主題":
        return False
    if "未登録" in text or "発音転記" in text:
        return False
    return True


def _prompt_tokens(text: str, lexicon: Lexicon, local: TranslationResult | None) -> list[str]:
    tokens: list[str] = []
    tokens.extend(_tokenize_ja(text, lexicon))
    tokens.extend(_tokenize_en(text))
    if re.search(r"[A-Za-zÉéÏïÜüŸÿŒœ']", text):
        tokens.extend(_tokenize_baronh(text))
    if local:
        tokens.extend(_tokenize_baronh(local.text))
        if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", local.text):
            tokens.extend(_tokenize_ja(local.text, lexicon))
        for item in local.analysis:
            tokens.append(item.source)
            tokens.append(item.target)
            if _is_searchable_note(item.note):
                tokens.extend(part.strip() for part in item.note.replace("/", " ").split() if part.strip())
        tokens.extend(local.unknown)
    cleaned: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        word = str(token or "").strip(".,!?;:。？！")
        if not word or word in seen:
            continue
        if len(word) == 1 and word not in JA_PARTICLES and word not in {"a", "I"}:
            if not re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", word):
                continue
        seen.add(word)
        cleaned.append(word)
    return cleaned


def retrieve_lexicon_entries(
    text: str,
    lexicon: Lexicon,
    *,
    local: TranslationResult | None = None,
    limit: int = 36,
) -> list:
    """辞書を全件スキャンして関連語だけを返す。ベクトルは使わない。"""
    tokens = _prompt_tokens(text, lexicon, local)
    source_tokens = _prompt_tokens(text, lexicon, None)
    parts = [text]
    if local:
        parts.append(local.text)
        parts.extend(item.note for item in local.analysis if _is_searchable_note(item.note))
    haystack = "\n".join(parts)
    return lexicon.rank(haystack, tokens=tokens, fuzzy_tokens=source_tokens, limit=limit)


def retrieve_lexicon_context(
    text: str,
    lexicon: Lexicon,
    *,
    local: TranslationResult | None = None,
    limit: int = 36,
) -> str:
    """原文と下訳から関連語だけを拾う。辞書全文は渡さない。"""
    picked = [_format_entry(entry) for entry in retrieve_lexicon_entries(text, lexicon, local=local, limit=limit)]
    return "\n".join(picked) if picked else "(該当なし。lookup_lexicon で追加検索してください)"


def describe_gaps(local: TranslationResult | None, lexicon: Lexicon | None = None) -> str:
    if local is None:
        return ""
    lines: list[str] = []
    seen: set[str] = set()
    for item in local.analysis:
        src = item.source
        if src in seen:
            continue
        note = item.note or ""
        close = lexicon.search(src, limit=3) if lexicon is not None else []
        if close and ("発音転記" in note or "未登録" in note):
            seen.add(src)
            top = close[0]
            lines.append(
                f"- {src} は表記ゆれの可能性。辞書の {top.lemma}「{top.gloss_ja}」を優先"
                + (f"（発音転記 {item.target} より）" if "発音転記" in note else "")
            )
            continue
        if "発音転記" in note:
            seen.add(src)
            lines.append(f"- {src} → {item.target}（固有名詞の発音転記。この語形は使ってよい）")
        elif "未登録" in note:
            seen.add(src)
            lines.append(f"- {src}（辞書にない。造語せず原文の語を残す）")
    for word in local.unknown:
        if word in seen:
            continue
        close = lexicon.search(word, limit=3) if lexicon is not None else []
        seen.add(word)
        if close:
            top = close[0]
            lines.append(f"- {word} は表記ゆれの可能性。辞書の {top.lemma}「{top.gloss_ja}」を優先")
        else:
            lines.append(f"- {word}（辞書にない。造語せず原文の語を残す）")
    return "\n".join(lines)


def system_prompt(target_lang: str) -> str:
    shot = FEW_SHOT_FROM_BARONH if target_lang in {"ja", "en"} else FEW_SHOT_TO_BARONH
    topics = "\n".join(f"- {name}: {body}" for name, body in GRAMMAR_TOPICS.items())
    return f"{GRAMMAR_BRIEF.strip()}\n\n文法の詳細:\n{topics}\n{shot.strip()}"


def build_user_prompt(
    text: str,
    lexicon: Lexicon,
    *,
    local: TranslationResult,
    target_lang: str,
) -> str:
    retrieved = retrieve_lexicon_context(text, lexicon, local=local)
    gaps = describe_gaps(local, lexicon)
    gap_block = f"\n\n辞書にない語:\n{gaps}" if gaps else ""
    return (
        f"翻訳方向: {local.source_lang} → {target_lang}\n"
        f"原文:\n{text}\n\n"
        f"規則ベースの下訳（誤り・抜けあり。辞書で直してよい）:\n{local.text}\n\n"
        f"関連辞書（全文スキャンの上位。全文ではない）:\n{retrieved}"
        f"{gap_block}\n\n"
        "訳文だけを出力してください。解説は不要です。"
        "足りない語や格は lookup_lexicon / grammar_note で引いてから訳してください。"
    )


def _phonetic_declined_forms(lemma: str) -> set[str]:
    lemma = lemma.strip(".,!?;:'")
    if not lemma or not re.search(r"[A-Za-zÉéÏïÜüŸÿŒœ]", lemma):
        return set()
    last = lemma[-1].lower()
    kind = "3" if last == "c" else "2" if last == "h" else "1n" if last == "n" else ""
    entry = Entry(lemma=lemma, pos="noun", gloss_ja=lemma, declension=kind)
    forms = {lemma.casefold()}
    for form in decline(entry).values():
        forms.add(form.casefold())
    return forms


def phonetic_allowed_forms(local: TranslationResult | None) -> set[str]:
    allowed: set[str] = set()
    if local is None:
        return allowed
    for item in local.analysis:
        if "発音転記" in (item.note or ""):
            for token in _tokenize_baronh(item.target):
                allowed.add(token.casefold())
                allowed.update(_phonetic_declined_forms(token))
    for note in local.notes or []:
        for lemma in re.findall(r"→([A-Za-zÉéÏïÜüŸÿŒœ']+)", note):
            allowed.update(_phonetic_declined_forms(lemma))
    return allowed


def invented_baronh_forms(
    text: str,
    lexicon: Lexicon,
    *,
    local: TranslationResult | None = None,
    index: FormIndex | None = None,
) -> list[str]:
    """生成したアーヴ語のうち、辞書語形でも発音転記でもないラテン語を列挙する。"""
    idx = index or FormIndex(lexicon)
    allowed = phonetic_allowed_forms(local)
    invented: list[str] = []
    for token in _tokenize_baronh(text):
        surface = token.strip(".,!?;:")
        if not surface:
            continue
        key = surface.casefold()
        if key in CLOSED_BARONH or key in allowed:
            continue
        if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", surface):
            continue
        if not re.search(r"[A-Za-zÉéÏïÜüŸÿŒœ]", surface):
            continue
        if idx.lookup(surface):
            continue
        invented.append(surface)
    return invented


def clean_model_text(text: str) -> str:
    out = (text or "").strip()
    if out.startswith("```"):
        lines = out.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        out = "\n".join(lines).strip()
    return out.strip().strip('"').strip("「」")


def dispatch_tool(name: str, arguments: dict[str, Any], lexicon: Lexicon) -> str:
    if name == "lookup_lexicon":
        query = str(arguments.get("query") or "").strip()
        lang = str(arguments.get("lang") or "auto")
        if lang not in {"auto", "baronh", "ja", "en"}:
            lang = "auto"
        hits = lexicon.search(query, lang=lang, limit=8)
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
    user = build_user_prompt(text, lexicon, local=local, target_lang=target_lang)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt(target_lang)},
        {"role": "user", "content": user},
    ]
    url = api_url("chat/completions", api_base=base)
    notes = [
        f"OpenAI 互換 Chat Completions（{base}）。辞書は全文スキャンして関連語だけ渡し、生成後に語形を検証します。",
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
    out = clean_model_text(out)
    if not out:
        out = local.text
        notes.append("生成結果が空のため下訳を使いました。")
    if used_tools:
        notes.append("モデルが lookup_lexicon / grammar_note を呼び出しています。")
    if target_lang == "baronh":
        index = FormIndex(lexicon)
        invented = invented_baronh_forms(out, lexicon, local=local, index=index)
        if invented and out != local.text:
            critique = (
                f"次の語は辞書の語形でも発音転記でもありません: {', '.join(invented)}。"
                "造語せず、関連辞書または lookup_lexicon の見出し・活用形だけで書き直してください。"
                "普通名詞が見つからなければ原文の語を残してください。訳文だけを出力してください。"
            )
            retry_messages = list(messages) + [
                {"role": "assistant", "content": out},
                {"role": "user", "content": critique},
            ]
            try:
                rewritten, extra = _run_tool_loop(
                    url=url,
                    api_key=key,
                    model=model,
                    messages=retry_messages,
                    lexicon=lexicon,
                    use_tools=use_tools,
                    max_rounds=3,
                )
                rewritten = clean_model_text(rewritten)
                notes.append(f"辞書にない語形 {', '.join(invented)} を検出し、再生成しました（+{extra} 回）。")
                if rewritten:
                    again = invented_baronh_forms(rewritten, lexicon, local=local, index=index)
                    if len(again) <= len(invented):
                        out = rewritten
                        invented = again
            except RuntimeError:
                notes.append("語形の再生成に失敗したため、最初の生成を使います。")
        if invented:
            notes.append("辞書にない語形: " + ", ".join(invented) + "。規則下訳の語を優先してもよいです。")
            if local.text and invented_baronh_forms(local.text, lexicon, local=local, index=index) == []:
                if len(invented) >= 2:
                    notes.append("生成文の未登録語が多いため下訳を使いました。")
                    out = local.text
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
