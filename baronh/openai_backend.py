"""OpenAI API による翻訳と音声合成。キーは環境変数または引数のみ。"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from baronh.grammar import decline
from baronh.lexicon import Lexicon
from baronh.phonology import reading_ja
from baronh.translate import TranslationResult, translate

DEFAULT_CHAT_MODEL = "gpt-4o-mini"
DEFAULT_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_TTS_VOICE = "alloy"
API_BASE = "https://api.openai.com/v1"

GRAMMAR_BRIEF = """
あなたはアーヴ語 (Baronh) の翻訳者です。公式の完全辞書は公開されていないため、
与えられた辞書・文法を根拠にします。普通名詞など辞書にない語は造語せず残します。
辞書にない固有名詞は発音に基づいてローマ字転記し、その語が転記であることを示します。

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


def resolve_api_key(explicit: str | None = None) -> str:
    key = (explicit or os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("OpenAI API キーがありません。OPENAI_API_KEY か --api-key を設定してください。")
    return key


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


def _lexicon_context(text: str, lexicon: Lexicon, limit: int = 40) -> str:
    words = [part for part in text.replace("、", " ").replace(",", " ").split() if part]
    picked: list[str] = []
    seen: set[str] = set()
    for word in words:
        for entry in lexicon.lookup(word, lang="auto"):
            if entry.lemma in seen:
                continue
            seen.add(entry.lemma)
            line = f"- {entry.lemma} [{entry.pos}] ja:{entry.gloss_ja} en:{entry.gloss_en}"
            if entry.pos in {"noun", "pronoun"}:
                forms = decline(entry)
                line += " " + "/".join(forms[c] for c in ("nom", "acc", "gen", "dat", "all", "abl", "ins"))
            picked.append(line)
            if len(picked) >= limit:
                return "\n".join(picked)
    if len(picked) < 12:
        for entry in lexicon.entries[: max(0, 12 - len(picked))]:
            if entry.lemma in seen:
                continue
            picked.append(f"- {entry.lemma} [{entry.pos}] ja:{entry.gloss_ja} en:{entry.gloss_en}")
    return "\n".join(picked)


def translate_openai(
    text: str,
    lexicon: Lexicon,
    *,
    source_lang: str,
    target_lang: str,
    api_key: str | None = None,
    model: str = DEFAULT_CHAT_MODEL,
) -> TranslationResult:
    key = resolve_api_key(api_key)
    local = translate(text, lexicon, source_lang=source_lang, target_lang=target_lang)
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": GRAMMAR_BRIEF},
            {
                "role": "user",
                "content": (
                    f"翻訳方向: {local.source_lang} → {target_lang}\n"
                    f"原文:\n{text}\n\n"
                    f"規則ベースの下訳:\n{local.text}\n\n"
                    f"関連辞書:\n{_lexicon_context(text, lexicon)}\n\n"
                    "訳文だけを出力してください。解説は不要です。"
                ),
            },
        ],
    }
    raw = _request(f"{API_BASE}/chat/completions", key, payload)
    data = json.loads(raw.decode("utf-8"))
    out = data["choices"][0]["message"]["content"].strip()
    return TranslationResult(
        source_lang=local.source_lang,
        target_lang=target_lang,
        source_text=text,
        text=out,
        engine="openai",
        ath_keys=local.ath_keys if target_lang == "baronh" else "",
        reading_ja=reading_ja(out) if target_lang == "baronh" else local.reading_ja,
        analysis=local.analysis,
        notes=["OpenAI API による生成。下訳と辞書をプロンプトに渡しています。"],
        unknown=local.unknown,
    )


def synthesize_openai(
    text: str,
    *,
    lang: str = "baronh",
    api_key: str | None = None,
    model: str = DEFAULT_TTS_MODEL,
    voice: str = DEFAULT_TTS_VOICE,
    output: Path,
) -> Path:
    key = resolve_api_key(api_key)
    spoken = reading_ja(text) if lang == "baronh" else text
    payload = {
        "model": model,
        "voice": voice,
        "input": spoken,
        "format": "mp3",
    }
    raw = _request(f"{API_BASE}/audio/speech", key, payload, accept="audio/mpeg")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(raw)
    return output
