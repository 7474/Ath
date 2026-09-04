"""ローマ字化・アースキー・読み（仮名）変換。"""

from __future__ import annotations

import re
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


def fold_latin1_oelig(text: str) -> str:
    """Latin-1 環境の ``oe`` を、Wikipedia / アース字母の ``œ`` へ畳む。

    Dadh Baronr など Latin-1 / euc-jp の資料は œ (U+0153) を書けないため
    ASCII の ``oe`` で代用する。掻き集め辞書は ``&#339;`` で œ を表す。
    語末の ``oe`` は o 語幹 + 不定詞 -e（``boe`` 思う、``ramgoe`` さまよう）
    のことがあるので畳まない。
    """
    if not text:
        return text
    src = unicodedata.normalize("NFC", text)
    pieces: list[str] = []
    for token in re.split(r"(\s+)", src):
        if not token or token.isspace():
            pieces.append(token)
            continue
        pieces.append(_fold_latin1_oelig_token(token))
    return "".join(pieces)


def _fold_latin1_oelig_token(token: str) -> str:
    tail = ""
    body = token
    if len(body) >= 2 and body[-2:].lower() == "oe":
        tail = body[-2:]
        body = body[:-2]
    out: list[str] = []
    i = 0
    while i < len(body):
        pair = body[i : i + 2]
        if pair.lower() == "oe":
            out.append("Œ" if pair[0].isupper() else "œ")
            i += 2
            continue
        out.append(body[i])
        i += 1
    return "".join(out) + tail


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
            # 語末の黙字（空白・句読点の直前も語末）
            at_word_end = (not nxt) or nxt in " \t\n.,!?;:"
            if drop_silent_final and at_word_end and low in {"c"}:
                i += 1
                continue
            if drop_silent_final and at_word_end and low == "r" and pieces:
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


PHONETIC_NOTE = "発音転記（辞書にない固有名詞）"
PHONETIC_SUMMARY = (
    "辞書にない固有名詞は発音から転記しています。辞書の見出しではありません。"
)

# 仮名モーラ → アーヴ語ローマ字。アースに無い j/k/w/v は使わない。
# ジ行は gh（g+h → [ʒ]）、ヴは bh（b+h → [v]）、ワ行は u の渡り。
# カ行は c=/k/。拗音は cia 型（シャは sia。ヘボンの sha/ja にしない）。
_KANA_BARONH: tuple[tuple[str, str], ...] = (
    ("キャ", "cia"), ("キュ", "ciu"), ("キョ", "cio"),
    ("ギャ", "gia"), ("ギュ", "giu"), ("ギョ", "gio"),
    ("シャ", "sia"), ("シュ", "siu"), ("ショ", "sio"), ("シェ", "sie"),
    ("ジャ", "gha"), ("ジュ", "ghu"), ("ジョ", "gho"), ("ジェ", "ghe"),
    ("チャ", "tia"), ("チュ", "tiu"), ("チョ", "tio"), ("チェ", "tie"),
    ("ニャ", "nia"), ("ニュ", "niu"), ("ニョ", "nio"),
    ("ヒャ", "hia"), ("ヒュ", "hiu"), ("ヒョ", "hio"),
    ("ビャ", "bia"), ("ビュ", "biu"), ("ビョ", "bio"),
    ("ピャ", "pia"), ("ピュ", "piu"), ("ピョ", "pio"),
    ("ミャ", "mia"), ("ミュ", "miu"), ("ミョ", "mio"),
    ("リャ", "ria"), ("リュ", "riu"), ("リョ", "rio"),
    ("ファ", "fa"), ("フィ", "fi"), ("フェ", "fe"), ("フォ", "fo"), ("フュ", "fiu"),
    ("ヴァ", "bha"), ("ヴィ", "bhi"), ("ヴェ", "bhe"), ("ヴォ", "bho"), ("ヴュ", "bhiu"),
    ("ティ", "ti"), ("テュ", "tiu"), ("トゥ", "tu"),
    ("ディ", "di"), ("デュ", "diu"), ("ドゥ", "du"),
    ("ウィ", "ui"), ("ウェ", "ue"), ("ウォ", "uo"),
    ("ア", "a"), ("イ", "i"), ("ウ", "u"), ("エ", "e"), ("オ", "o"),
    ("カ", "ca"), ("キ", "ci"), ("ク", "cu"), ("ケ", "ce"), ("コ", "co"),
    ("サ", "sa"), ("シ", "si"), ("ス", "su"), ("セ", "se"), ("ソ", "so"),
    ("タ", "ta"), ("チ", "ti"), ("ツ", "tu"), ("テ", "te"), ("ト", "to"),
    ("ナ", "na"), ("ニ", "ni"), ("ヌ", "nu"), ("ネ", "ne"), ("ノ", "no"),
    ("ハ", "ha"), ("ヒ", "hi"), ("フ", "fu"), ("ヘ", "he"), ("ホ", "ho"),
    ("マ", "ma"), ("ミ", "mi"), ("ム", "mu"), ("メ", "me"), ("モ", "mo"),
    ("ヤ", "ia"), ("ユ", "iu"), ("ヨ", "io"),
    ("ラ", "ra"), ("リ", "ri"), ("ル", "ru"), ("レ", "re"), ("ロ", "ro"),
    ("ワ", "ua"), ("ヲ", "uo"), ("ン", "n"),
    ("ガ", "ga"), ("ギ", "gi"), ("グ", "gu"), ("ゲ", "ge"), ("ゴ", "go"),
    ("ザ", "za"), ("ジ", "ghi"), ("ズ", "zu"), ("ゼ", "ze"), ("ゾ", "zo"),
    ("ダ", "da"), ("ヂ", "di"), ("ヅ", "du"), ("デ", "de"), ("ド", "do"),
    ("バ", "ba"), ("ビ", "bi"), ("ブ", "bu"), ("ベ", "be"), ("ボ", "bo"),
    ("パ", "pa"), ("ピ", "pi"), ("プ", "pu"), ("ペ", "pe"), ("ポ", "po"),
    ("ヴ", "bhu"),
)

_KANA_BARONH_SORTED = tuple(sorted(_KANA_BARONH, key=lambda item: len(item[0]), reverse=True))

_HONORIFICS = ("さん", "さま", "様", "くん", "君", "ちゃん", "氏")


def hira_to_kata(text: str) -> str:
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if 0x3041 <= code <= 0x3096:
            out.append(chr(code + 0x60))
        else:
            out.append(ch)
    return "".join(out)


def split_honorific(text: str) -> tuple[str, str]:
    for suffix in _HONORIFICS:
        if text.endswith(suffix) and len(text) > len(suffix) + 0:
            core = text[: -len(suffix)]
            if core:
                return core, suffix
    return text, ""


def is_katakana_name(text: str) -> bool:
    core, _hon = split_honorific(text)
    core = core.replace("・", "").replace("＝", "").replace("-", "")
    if len(core) < 2:
        return False
    return all("ァ" <= ch <= "ヶ" or ch in "ー・ヴヵヶ" for ch in core.replace("・", "ア"))


def is_hiragana_span(text: str) -> bool:
    core, _hon = split_honorific(text)
    core = core.replace("ー", "")
    if len(core) < 2:
        return False
    return all("ぁ" <= ch <= "ゖ" or ch in "ー" for ch in core)


def is_latin_name(text: str, *, require_capital: bool = True) -> bool:
    stripped = text.strip(".,!?;:")
    letters = stripped.replace("-", "").replace("'", "")
    if len(stripped) < 2 or not letters.isalpha():
        return False
    if not re.fullmatch(r"[A-Za-zÉéÏïÜüŸÿŒœ][A-Za-zÉéÏïÜüŸÿŒœ''\-]*", stripped):
        return False
    if require_capital:
        return stripped[0].isupper()
    return True


def looks_like_proper_noun(text: str, *, nxt: str = "", copula: bool = False) -> bool:
    core, hon = split_honorific(text)
    if hon:
        text = core
    if is_katakana_name(text):
        return True
    if is_latin_name(text, require_capital=True):
        return True
    if is_hiragana_span(text) and (nxt in {"は", "が", "を", "の", "に", "へ", "と", "も", "よ"} or copula or hon):
        return True
    return False


def kana_to_baronh(text: str) -> str:
    """日本語の発音（仮名）をアーヴ語ローマ字へ転記する。"""
    src = hira_to_kata(unicodedata.normalize("NFKC", text or "")).replace("＝", "・")
    src = src.replace("ヵ", "カ").replace("ヶ", "ケ")
    pieces: list[str] = []
    i = 0
    geminate = False
    while i < len(src):
        ch = src[i]
        if ch in "・･/／":
            pieces.append(" ")
            i += 1
            continue
        if ch in "ーｰ":
            i += 1
            continue
        if ch == "ッ":
            geminate = True
            i += 1
            continue
        matched = None
        for kana, roman in _KANA_BARONH_SORTED:
            if src.startswith(kana, i):
                matched = (kana, roman)
                break
        if not matched:
            i += 1
            continue
        kana, roman = matched
        # トウ / キョウ などの長音のウは落とす
        if roman == "u" and pieces:
            prev = pieces[-1].rstrip()
            if prev.endswith("o"):
                i += len(kana)
                continue
        if geminate and roman and roman[0] not in "aeiouïüÿéœ":
            roman = roman[0] + roman
            geminate = False
        else:
            geminate = False
        pieces.append(roman)
        i += len(kana)
    out = "".join(pieces)
    while "  " in out:
        out = out.replace("  ", " ")
    return fold_to_ath_spelling(out.strip())


def fold_to_ath_spelling(text: str) -> str:
    """アースに無いラテン字を、対応するアーヴ語綴りへ畳む。"""
    out: list[str] = []
    for ch in text:
        low = ch.lower()
        if low == "j":
            out.append("gh")
        elif low == "v":
            out.append("bh")
        elif low == "w":
            out.append("u")
        elif low in {"k", "q"}:
            out.append("c")
        elif low == "x":
            out.append("cs")
        else:
            out.append(ch)
    return "".join(out)


_PROPER_VOWELS = set("aiueoïüÿéœy")


def baronh_proper_noun(stem: str) -> tuple[str, str]:
    """固有名詞の語幹を正規アーヴ語の主格（-c / -h / -n）と型に整える。"""
    stem = fold_to_ath_spelling((stem or "").strip())
    if not stem:
        return "", ""
    last = stem[-1].lower()
    if last == "c":
        return stem, "3"
    if last == "h":
        return stem, "2"
    if last == "n":
        return stem, "1n"
    if last in _PROPER_VOWELS:
        return stem + "c", "3"
    return stem + "h", "2"


def latin_to_baronh(text: str) -> str:
    """ラテン文字の固有名詞をアーヴ語綴りに寄せる（k→c、j→gh など）。"""
    src = unicodedata.normalize("NFC", text.strip().strip(".,!?;:"))
    out: list[str] = []
    i = 0
    while i < len(src):
        pair = src[i : i + 2]
        low_pair = pair.lower()
        if low_pair in {"th", "ch", "ph"}:
            out.append(low_pair)
            i += 2
            continue
        if low_pair == "sh":
            out.append("ch")
            i += 2
            continue
        if low_pair == "wh":
            out.append("u")
            i += 2
            continue
        ch = src[i]
        mapped = {
            "j": "gh", "J": "gh",
            "v": "bh", "V": "bh",
            "w": "u", "W": "u",
            "k": "c", "K": "c",
            "q": "c", "Q": "c",
            "x": "cs", "X": "cs",
        }.get(ch)
        if mapped:
            out.append(mapped)
        elif ch.isalpha() or ch in "'’-":
            out.append(ch.lower() if ch.isalpha() else ch)
        i += 1
    return fold_to_ath_spelling("".join(out))


def transcribe_proper_noun(text: str) -> tuple[str, str]:
    """固有名詞をアーヴ語の主格見出しと変化型にする。"""
    core, _hon = split_honorific(text.strip())
    core = core.strip(".,!?;:")
    if not core:
        return "", ""
    if re.search(r"[A-Za-zÉéÏïÜüŸÿŒœ]", core) and not re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", core):
        stem = latin_to_baronh(core)
    else:
        stem = kana_to_baronh(core)
    return baronh_proper_noun(stem)


def transcribe_proper_to_baronh(text: str) -> str:
    lemma, _kind = transcribe_proper_noun(text)
    return lemma


def transcribe_baronh_to_kana(text: str) -> str:
    """未登録のアーヴ語固有名詞を仮名読みにする。"""
    return reading_ja(text, drop_silent_final=True)


def speakable_text(text: str, lang: str) -> str:
    if lang == "baronh":
        return reading_ja(text)
    return text
