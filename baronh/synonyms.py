"""辞書語釈から類義語・言い換え見出しを探す。

ベクトル検索は使わない。未登録の普通名詞だけを対象にし、
語釈の短い別名・形態変化・少数の言い換え表で辞書内の lemma に寄せる。
固有名詞や長い複合語（「光」⊂「凝集光銃」）は結ばない。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from baronh.lexicon import (
    Entry,
    Lexicon,
    _normalize_key,
    _split_ja_aliases,
    en_query_variants,
    ja_query_variants,
)
from baronh.phonology import looks_like_proper_noun
from baronh.translate import JA_PARTICLES, TranslationResult

# 辞書に無い概念を、実際に語釈として存在する短い別名へ橋渡しする。
# 値は lemma ではなく lookup 用の日本語・英語。ヒットしなければ無視する。
PARAPHRASE_KEYS: dict[str, tuple[str, ...]] = {
    "光": ("輝くもの", "輝く者", "輝き", "光る", "shine", "light", "glow"),
    "明かり": ("輝くもの", "輝く者", "light"),
    "輝き": ("輝くもの", "輝く者"),
    "光線": ("輝くもの", "凝集光"),
    "light": ("輝くもの", "輝く者", "shine", "glow"),
    "lights": ("輝くもの", "輝く者"),
    "shine": ("輝くもの", "輝く者"),
    "glow": ("輝くもの", "輝く者"),
    "bright": ("輝くもの", "輝く者"),
    "brightness": ("輝くもの", "輝く者"),
    "火": ("点火", "火照る"),
    "炎": ("点火",),
    "fire": ("点火",),
    "flame": ("点火",),
    "死": ("死ぬ",),
    "death": ("死ぬ",),
    "die": ("死ぬ",),
    "生": ("生きる",),
    "life": ("生きる",),
    "live": ("生きる",),
    "赤": ("赤い", "真っ赤に"),
    "red": ("赤い",),
    "白": ("真白",),
    "white": ("真白",),
    "愛": ("愛する",),
    "love": ("愛する",),
    "空": ("通常空間", "真空世界"),
    "sky": ("通常空間",),
    "space": ("通常空間", "真空世界"),
    "声": ("口",),
    "voice": ("口", "言う"),
    "食べる": ("口",),
    "eat": ("口",),
    "悪い": ("敵",),
    "bad": ("敵",),
    "友": ("人",),
    "friend": ("人",),
    "時間": ("〔物理〕時間",),
    "time": ("〔物理〕時間",),
}

_JA_MORPH = (
    "するもの",
    "すること",
    "すること",
    "もの",
    "こと",
    "する",
    "した",
    "して",
    "します",
    "される",
    "られる",
    "れる",
    "い",
    "な",
    "る",
    "り",
    "み",
    "き",
    "く",
    "ん",
)

_COMPOUND_MARKERS = ("の", "・", "／", "/", "（", "(", "〔", "[", "、")


@dataclass
class SynonymHit:
    query: str
    entry: Entry
    via: str
    relation: str
    score: int

    def to_dict(self) -> dict[str, str | int]:
        return {
            "query": self.query,
            "lemma": self.entry.lemma,
            "pos": self.entry.pos,
            "gloss_ja": self.entry.gloss_ja,
            "gloss_en": self.entry.gloss_en,
            "via": self.via,
            "relation": self.relation,
            "score": self.score,
        }


@dataclass
class CoverageItem:
    source: str
    status: str
    lemma: str = ""
    gloss: str = ""
    via: str = ""
    relation: str = ""


def _kanji(text: str) -> str:
    return "".join(re.findall(r"[\u4e00-\u9fff]", text or ""))


def _is_simple_alias(alias: str) -> bool:
    text = (alias or "").strip()
    if not text or len(text) > 8:
        return False
    if any(mark in text for mark in _COMPOUND_MARKERS):
        return False
    if len(_kanji(text)) > 3:
        return False
    return True


def _too_specific(query: str, alias: str) -> bool:
    q = (query or "").strip()
    a = (alias or "").strip()
    if not q or not a:
        return True
    if q == a:
        return False
    if q in a and len(a) >= len(q) + 3:
        return True
    qk, ak = _kanji(q), _kanji(a)
    if qk and ak and qk in ak and len(ak) >= len(qk) + 2:
        return True
    return False


def _morph_keys(query: str) -> list[str]:
    text = (query or "").strip()
    if not text:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for variant in (text, *ja_query_variants(text), *en_query_variants(text)):
        if variant and variant not in seen:
            seen.add(variant)
            out.append(variant)
        if not variant:
            continue
        for suf in _JA_MORPH:
            if variant.endswith(suf) and len(variant) > len(suf):
                stem = variant[: -len(suf)]
                if stem and stem not in seen:
                    seen.add(stem)
                    out.append(stem)
            grown = variant + suf
            if grown not in seen:
                seen.add(grown)
                out.append(grown)
    return out


def _alias_candidates(entry: Entry) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    for raw in (entry.gloss_ja, entry.gloss_en, entry.lemma):
        for alias in _split_ja_aliases(raw or ""):
            text = alias.strip()
            if not text:
                continue
            key = _normalize_key(text)
            if key in seen:
                continue
            seen.add(key)
            aliases.append(text)
        if raw:
            for part in re.split(r"[,/;]", raw):
                text = part.strip()
                if not text:
                    continue
                key = _normalize_key(text)
                if key in seen:
                    continue
                seen.add(key)
                aliases.append(text)
    return aliases


def find_synonyms(
    query: str,
    lexicon: Lexicon,
    *,
    limit: int = 6,
    extra_keys: Iterable[str] | None = None,
) -> list[SynonymHit]:
    """未登録語を辞書の短い語釈へ寄せる。完全一致があればそれを最優先する。"""
    text = (query or "").strip()
    if not text or text in JA_PARTICLES:
        return []
    hits: list[SynonymHit] = []
    seen: set[str] = set()

    def take(entry: Entry, via: str, relation: str, score: int) -> None:
        key = _normalize_key(entry.lemma) + "|" + entry.pos
        if key in seen:
            return
        seen.add(key)
        hits.append(SynonymHit(query=text, entry=entry, via=via, relation=relation, score=score))

    exact = lexicon.lookup(text, lang="auto")
    for entry in exact:
        take(entry, text, "exact", 1000)

    paraphrase_keys = list(dict.fromkeys((*PARAPHRASE_KEYS.get(text, ()), *PARAPHRASE_KEYS.get(text.casefold(), ()))))
    for offset, key in enumerate(paraphrase_keys):
        for entry in lexicon.lookup(key, lang="auto"):
            take(entry, key, "paraphrase", 760 - offset)

    keys: list[str] = []
    for item in (*_morph_keys(text), *(extra_keys or ())):
        if item and item not in keys and item != text:
            keys.append(item)

    for key in keys:
        for entry in lexicon.lookup(key, lang="auto"):
            take(entry, key, "morph", 820)

    folded_keys = {_normalize_key(k) for k in keys}
    folded_keys.add(_normalize_key(text))
    folded_keys.update(_normalize_key(k) for k in paraphrase_keys)
    for entry in lexicon.entries:
        if _normalize_key(entry.lemma) + "|" + entry.pos in seen:
            continue
        for alias in _alias_candidates(entry):
            if not _is_simple_alias(alias):
                continue
            if _too_specific(text, alias):
                continue
            alias_key = _normalize_key(alias)
            if alias_key in folded_keys:
                relation = "paraphrase" if alias in paraphrase_keys else "morph"
                take(entry, alias, relation, 640)
                break
            qk = _kanji(text)
            ak = _kanji(alias)
            if qk and ak == qk and len(alias) <= len(text) + 2:
                take(entry, alias, "stem", 520)
                break

    hits.sort(key=lambda item: (-item.score, item.entry.lemma))
    return hits[:limit]


def uncovered_tokens(local: TranslationResult) -> list[str]:
    """規則下訳で残った未登録の普通名詞。固有名詞の発音転記は含めない。"""
    out: list[str] = []
    seen: set[str] = set()
    for item in local.analysis:
        note = item.note or ""
        if "発音転記" in note:
            continue
        if "未登録" not in note:
            continue
        src = (item.source or "").strip()
        if not src or src in seen or src in JA_PARTICLES:
            continue
        if looks_like_proper_noun(src):
            continue
        seen.add(src)
        out.append(src)
    for word in local.unknown:
        if word in seen or word in JA_PARTICLES:
            continue
        if looks_like_proper_noun(word):
            continue
        seen.add(word)
        out.append(word)
    return out


def coverage_plan(local: TranslationResult, lexicon: Lexicon) -> list[CoverageItem]:
    plan: list[CoverageItem] = []
    seen: set[str] = set()
    for item in local.analysis:
        src = (item.source or "").strip()
        if not src or src in seen:
            continue
        seen.add(src)
        note = item.note or ""
        if "発音転記" in note:
            plan.append(CoverageItem(src, "phonetic", lemma=item.target, gloss=note, relation="phonetic"))
            continue
        if "未登録" in note:
            hits = find_synonyms(src, lexicon)
            if hits:
                top = hits[0]
                plan.append(
                    CoverageItem(
                        src,
                        "synonym",
                        lemma=top.entry.lemma,
                        gloss=top.entry.gloss_ja,
                        via=top.via,
                        relation=top.relation,
                    )
                )
            else:
                plan.append(CoverageItem(src, "unknown"))
            continue
        plan.append(CoverageItem(src, "exact", lemma=item.target, gloss=note, relation="exact"))
    for word in uncovered_tokens(local):
        if word in seen:
            continue
        seen.add(word)
        hits = find_synonyms(word, lexicon)
        if hits:
            top = hits[0]
            plan.append(
                CoverageItem(
                    word,
                    "synonym",
                    lemma=top.entry.lemma,
                    gloss=top.entry.gloss_ja,
                    via=top.via,
                    relation=top.relation,
                )
            )
        else:
            plan.append(CoverageItem(word, "unknown"))
    return plan


def paraphrase_source(text: str, plan: list[CoverageItem], *, source_lang: str) -> tuple[str, list[dict[str, str]]]:
    """未登録語を辞書語釈の短い別名に置き換えて、規則翻訳が拾えるようにする。"""
    substitutions: list[dict[str, str]] = []
    rewritten = text
    # 長い語から置換して部分一致で壊さない
    items = sorted(
        [item for item in plan if item.status == "synonym" and item.via],
        key=lambda item: len(item.source),
        reverse=True,
    )
    for item in items:
        replacement = item.via
        if source_lang == "en":
            replacement = item.via if re.search(r"[A-Za-z]", item.via) else (item.gloss.split("/")[0].strip() or item.via)
        if not replacement or replacement == item.source:
            continue
        if item.source not in rewritten:
            continue
        rewritten = rewritten.replace(item.source, replacement)
        substitutions.append(
            {
                "from": item.source,
                "to": replacement,
                "lemma": item.lemma,
                "gloss": item.gloss,
                "relation": item.relation,
                "via": item.via,
            }
        )
    return rewritten, substitutions


def format_hits(hits: list[SynonymHit]) -> list[dict[str, str | int]]:
    return [hit.to_dict() for hit in hits]


def format_plan(plan: list[CoverageItem]) -> str:
    if not plan:
        return "(対象なし)"
    lines: list[str] = []
    for item in plan:
        if item.status == "synonym":
            lines.append(f"- {item.source} → {item.lemma}「{item.gloss}」（言い換え {item.via} / {item.relation}）")
        elif item.status == "unknown":
            lines.append(f"- {item.source}（辞書にも類義語にも無い。造語せず原文を残す）")
        elif item.status == "phonetic":
            lines.append(f"- {item.source} → {item.lemma}（固有名詞の発音転記）")
    return "\n".join(lines) if lines else "(辞書で足りている)"
