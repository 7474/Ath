"""言語パックの G2P（正書法 → 仮名読み / IPA）。"""

from __future__ import annotations

import re
import unicodedata

from baronh.langpack import LanguagePack, uses_builtin_engine
from baronh.phonology import reading_ja as baronh_reading_ja

_VOWEL_INDEX = {"a": 0, "i": 1, "u": 2, "e": 3, "o": 4}


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text or "")


def _longest_keys(mapping: dict[str, str]) -> list[str]:
    return sorted((key for key in mapping if key), key=len, reverse=True)


def g2p_reading_ja(text: str, pack: LanguagePack) -> str:
    """TTS 向けの仮名読み。アーヴ語パックは従来の reading_ja に委譲する。"""
    if uses_builtin_engine(pack) or pack.phonology.engine == "baronh":
        return baronh_reading_ja(text)
    src = _nfc(text)
    if not src:
        return ""
    vowels = pack.phonology.reading_ja_vowels
    cv = pack.phonology.reading_ja_cv
    coda = pack.phonology.reading_ja_coda
    digraphs = pack.phonology.digraphs
    silent = {item.casefold() for item in pack.phonology.silent_final}
    pieces: list[str] = []
    i = 0
    length = len(src)
    while i < length:
        ch = src[i]
        if ch in " \t\n":
            pieces.append(" ")
            i += 1
            continue
        if ch in ".,!?;:":
            pieces.append("。")
            i += 1
            continue
        if ch in "'’\"-":
            i += 1
            continue
        matched = False
        for key in _longest_keys(digraphs):
            if src[i : i + len(key)].casefold() == key.casefold():
                ipa_or_kana = digraphs[key]
                pieces.append(vowels.get(ipa_or_kana, ipa_or_kana))
                i += len(key)
                matched = True
                break
        if matched:
            continue
        cons = ch.casefold()
        nxt = src[i + 1].casefold() if i + 1 < length else ""
        row = cv.get(cons)
        if row and nxt in _VOWEL_INDEX and nxt in vowels:
            idx = _VOWEL_INDEX[nxt]
            if len(row) >= 5:
                # 5 モーラ列（カキクケコ）または明示的なカンマ区切り
                units = row.split(",") if "," in row else list(row)
                if len(units) == 5 and all(len(item) == 1 for item in units):
                    # 全角1文字×5（カキクケコ）
                    pieces.append(row[idx] if len(row) == 5 else units[idx])
                elif len(units) == 5:
                    pieces.append(units[idx])
                elif len(row) == 5:
                    pieces.append(row[idx])
                else:
                    pieces.append(units[idx] if idx < len(units) else row)
            else:
                pieces.append(row)
            i += 2
            continue
        if cons in coda:
            at_coda = (not nxt) or nxt in " \t\n.,!?;:" or nxt in silent
            if at_coda or nxt in cv or nxt in vowels:
                pieces.append(coda[cons])
                i += 1
                continue
        if cons in vowels:
            pieces.append(vowels[cons])
            i += 1
            continue
        at_word_end = (not nxt) or nxt in " \t\n.,!?;:"
        if at_word_end and cons in silent:
            i += 1
            continue
        if row:
            pieces.append(row[0])
            i += 1
            continue
        pieces.append(ch)
        i += 1
    out = "".join(pieces)
    while "  " in out:
        out = out.replace("  ", " ")
    return out.strip()


def g2p_ipa(text: str, pack: LanguagePack) -> str:
    """単語区切りの IPA（簡易）。辞書に無い連音は正書法の字ごと。"""
    src = _nfc(text)
    if not src:
        return ""
    mapping = dict(pack.phonology.ipa)
    mapping.update(pack.phonology.digraphs)
    silent = {item.casefold() for item in pack.phonology.silent_final}
    keys = _longest_keys(mapping)
    pieces: list[str] = []
    i = 0
    length = len(src)
    while i < length:
        ch = src[i]
        if ch.isspace():
            pieces.append(" ")
            i += 1
            continue
        if ch in ".,!?;:'’\"-":
            i += 1
            continue
        matched = False
        for key in keys:
            span = src[i : i + len(key)]
            if span.casefold() == key.casefold():
                nxt = src[i + len(key) : i + len(key) + 1]
                at_end = (not nxt) or nxt.isspace() or nxt in ".,!?;:"
                if key.casefold() in silent and at_end:
                    i += len(key)
                    matched = True
                    break
                pieces.append(mapping[key])
                i += len(key)
                matched = True
                break
        if matched:
            continue
        low = ch.casefold()
        nxt = src[i + 1] if i + 1 < length else ""
        at_end = (not nxt) or nxt.isspace() or nxt in ".,!?;:"
        if at_end and low in silent:
            i += 1
            continue
        pieces.append(mapping.get(low, low))
        i += 1
    out = "".join(pieces)
    while "  " in out:
        out = out.replace("  ", " ")
    return out.strip()


def compact_reading(text: str) -> str:
    """認識照合用に空白・句読点を落とし、仮名をカタカナへ揃える。"""
    from baronh.phonology import hira_to_kata

    src = hira_to_kata(unicodedata.normalize("NFKC", text or ""))
    return re.sub(r"[\s。．，、！？!?・･'’\"-]", "", src)


def speakable_for_pack(text: str, pack: LanguagePack | None, lang: str) -> str:
    if lang in {"ja", "en"}:
        return text
    if pack is not None:
        return g2p_reading_ja(text, pack)
    if lang == "baronh":
        return baronh_reading_ja(text)
    return text
