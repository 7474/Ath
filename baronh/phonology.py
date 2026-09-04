"""ローマ字化・アースキー・読み（仮名）変換。"""

from __future__ import annotations

import unicodedata

ATH_DIGRAPHS = (("ai", "A"), ("au", "I"), ("eu", "E"))

# 子音字 + h の同化（Wikipedia の記述に基づく近似）。
H_DIGRAPHS = {
    "mh": "フ",
    "bh": "ヴ",
    "ph": "フ",
    "fh": "フ",
    "th": "ス",
    "dh": "ズ",
    "nh": "ニ",
    "rh": "ル",
    "lh": "ル",
    "ch": "シュ",
    "gh": "ジュ",
    "sh": "シュ",
    "zh": "ジュ",
}

VOWEL_KANA = {
    "a": "ア",
    "i": "イ",
    "ï": "イ",
    "u": "ウ",
    "ü": "ウ",
    "e": "エ",
    "é": "エ",
    "o": "オ",
    "œ": "エ",
    "y": "イ",
    "ÿ": "イ",
}

CONSONANT_CV = {
    "c": "カキクケコ",
    "k": "カキクケコ",
    "s": "サシスセソ",
    "t": "タチツテト",
    "n": "ナニヌネノ",
    "h": "ハヒフヘホ",
    "p": "パピプペポ",
    "f": "ファフィフフェフォ",
    "m": "マミムメモ",
    "y": "ヤイユエヨ",
    "r": "ラリルレロ",
    "w": "ワウィウウェウォ",
    "g": "ガギグゲゴ",
    "z": "ザジズゼゾ",
    "d": "ダヂヅデド",
    "b": "バビブベボ",
    "l": "ラリルレロ",
    "j": "ジャジジュジェジョ",
}

VOWEL_INDEX = {"a": 0, "i": 1, "ï": 1, "u": 2, "ü": 2, "e": 3, "é": 3, "œ": 3, "o": 4, "y": 1, "ÿ": 1}


def normalize_baronh(text: str) -> str:
    return unicodedata.normalize("NFC", text.strip())


def to_ath_keys(text: str) -> str:
    """このリポジトリの Aarth フォントが期待する入力キーへ変換する。"""
    src = normalize_baronh(text)
    out: list[str] = []
    i = 0
    while i < len(src):
        pair = src[i : i + 2]
        mapped = None
        for src_digraph, key in ATH_DIGRAPHS:
            if pair.lower() == src_digraph:
                mapped = key
                break
        if mapped:
            out.append(mapped)
            i += 2
            continue
        out.append(src[i])
        i += 1
    return "".join(out)


def _cv(consonant: str, vowel: str) -> str:
    row = CONSONANT_CV.get(consonant)
    idx = VOWEL_INDEX.get(vowel)
    if row and idx is not None:
        if consonant in {"f", "w", "j"} or (consonant == "y" and vowel in {"a", "u", "o"}):
            units = ["ファ", "フィ", "フ", "フェ", "フォ"] if consonant == "f" else None
            if consonant == "f" and units:
                return units[idx]
            if consonant == "w":
                return ["ワ", "ウィ", "ウ", "ウェ", "ウォ"][idx]
            if consonant == "j":
                return ["ジャ", "ジ", "ジュ", "ジェ", "ジョ"][idx]
        if len(row) == 5:
            return row[idx]
    if consonant in H_DIGRAPHS and idx is not None:
        return H_DIGRAPHS[consonant] + ("" if vowel in {"u", "ü"} else VOWEL_KANA[vowel])
    return (CONSONANT_CV.get(consonant, consonant)[:1] if row else consonant) + VOWEL_KANA.get(vowel, vowel)


def reading_ja(text: str, *, drop_silent_final: bool = True) -> str:
    """ローマ字アーヴ語を日本語 TTS 向けの仮名読みに落とす。"""
    src = normalize_baronh(text)
    if not src:
        return ""
    pieces: list[str] = []
    i = 0
    length = len(src)
    while i < length:
        ch = src[i]
        if ch in " \t\n.,!?;:'’\"「」-":
            if ch in "’'":
                i += 1
                continue
            if ch.isspace():
                pieces.append(" ")
            elif ch in ".,!?":
                pieces.append("。")
            i += 1
            continue
        pair = src[i : i + 2].lower()
        if pair in {"ai", "au", "eu"}:
            pieces.append({"ai": "アイ", "au": "アウ", "eu": "エウ"}[pair])
            i += 2
            continue
        if pair in H_DIGRAPHS:
            nxt = src[i + 2].lower() if i + 2 < length else ""
            if nxt in VOWEL_KANA:
                base = H_DIGRAPHS[pair]
                if pair in {"ch", "gh", "sh", "zh", "nh"}:
                    pieces.append(_soft_h(pair, nxt))
                elif nxt == "u":
                    pieces.append(base)
                else:
                    pieces.append(base + VOWEL_KANA[nxt] if base[-1] not in "ァィゥェォャュョ" else base)
                i += 3 if nxt else 2
                continue
            # 語末の mh など
            if drop_silent_final and i + 2 == length and pair in {"mh", "bh"}:
                pieces.append(H_DIGRAPHS[pair])
                i += 2
                continue
            pieces.append(H_DIGRAPHS[pair])
            i += 2
            continue
        low = ch.lower()
        nxt = src[i + 1].lower() if i + 1 < length else ""
        if low in CONSONANT_CV or low in {"k"}:
            if nxt in VOWEL_KANA:
                pieces.append(_cv(low, nxt))
                i += 2
                continue
            # 語末の黙字
            if drop_silent_final and i + 1 == length and low in {"c"}:
                i += 1
                continue
            if drop_silent_final and i + 1 == length and low == "r" and pieces:
                i += 1
                continue
            pieces.append({
                "c": "ク", "k": "ク", "s": "ス", "t": "ト", "n": "ン", "h": "フ",
                "p": "プ", "f": "フ", "m": "ム", "r": "ル", "g": "グ", "z": "ズ",
                "d": "ド", "b": "ブ", "l": "ル", "j": "ジュ", "y": "イ", "w": "ウ",
            }.get(low, ch))
            i += 1
            continue
        if low in VOWEL_KANA:
            pieces.append(VOWEL_KANA[low])
            i += 1
            continue
        pieces.append(ch)
        i += 1
    text_out = "".join(pieces)
    while "  " in text_out:
        text_out = text_out.replace("  ", " ")
    return text_out.strip()


def _soft_h(pair: str, vowel: str) -> str:
    table = {
        "ch": ["シャ", "シ", "シュ", "シェ", "ショ"],
        "sh": ["シャ", "シ", "シュ", "シェ", "ショ"],
        "gh": ["ジャ", "ジ", "ジュ", "ジェ", "ジョ"],
        "zh": ["ジャ", "ジ", "ジュ", "ジェ", "ジョ"],
        "nh": ["ニャ", "ニ", "ニュ", "ニェ", "ニョ"],
    }
    idx = VOWEL_INDEX.get(vowel, 2)
    return table[pair][idx]


def speakable_text(text: str, lang: str) -> str:
    if lang == "baronh":
        return reading_ja(text)
    return text
