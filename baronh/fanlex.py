"""ファンサイト辞書の出典メタデータと走査。"""

from __future__ import annotations

import html as html_lib
import re
from html.parser import HTMLParser
from typing import Any

from baronh.lexicon import Entry
from baronh.phonology import fold_fan_romanization

MULE_JISYO_URL = "http://mule.s59.xrea.com/seikai/jisyo/"
DADH_ONDIC_URL = "http://dadh-baronr.s5.xrea.com/etc/ondic.html"
DADH_DIC_PAGES = [
    f"http://dadh-baronr.s5.xrea.com/doc/baronhdic-{i}.html" for i in range(1, 9)
]

SPECIAL_THANKS: list[dict[str, str]] = [
    {
        "name": "アーヴ語掻き集め アーヴ語辞書",
        "url": MULE_JISYO_URL,
        "thanks": (
            "スペシャルサンクス: アーヴ語掻き集め『アーヴ語辞書』"
            "（http://mule.s59.xrea.com/seikai/jisyo/ 、2005-01-23 版）。"
            "語彙表を走査して辞書を拡充しました。"
        ),
    },
    {
        "name": "Sidrÿac Borgh=Racair Mauch 私家版アーヴ語辞書",
        "url": DADH_ONDIC_URL,
        "thanks": (
            "スペシャルサンクス: Dadh Baronr — アーヴ語の世界"
            "『Sidrÿac Borgh=Racair Mauch の私家版アーヴ語辞書』"
            "（http://dadh-baronr.s5.xrea.com/etc/ondic.html）。"
            "見出し語と品詞・語釈を走査して辞書を拡充しました。"
            "語源・語釈は編者の再構成であり、森岡浩之氏は関知していません。"
        ),
    },
]

POS_FROM_MARK: dict[str, str] = {
    "代名": "pronoun",
    "動詞接尾": "suffix",
    "接続": "conjunction",
    "連語": "phrase",
    "接頭": "prefix",
    "接尾": "suffix",
    "名": "noun",
    "動": "verb",
    "形": "adjective",
    "副": "adverb",
    "感": "interjection",
    "後": "postposition",
}

LEMMA_RE = re.compile(
    r"^\*?-?[A-Za-zÉéÏïÜüŸÿŒœ][A-Za-zÉéÏïÜüŸÿŒœ''\-]*(?:[ 　][A-Za-zÉéÏïÜüŸÿŒœ][A-Za-zÉéÏïÜüŸÿŒœ''\-]*){0,6}$"
)
POS_MARK_RE = re.compile(r"[【《]([^】》]+)[】》]")
GEN_RE = re.compile(r"gen\.\s*\*?([A-Za-zÉéÏïÜüŸÿŒœ]+)\.?", re.I)


class _DefinitionListParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.pairs: list[tuple[str, str]] = []
        self._in_dt = False
        self._in_dd = False
        self._dt: list[str] = []
        self._dd: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "dt":
            self._in_dt = True
            self._dt = []
        elif tag == "dd":
            self._in_dd = True
            self._dd = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "dt":
            self._in_dt = False
        elif tag == "dd":
            self._in_dd = False
            lemma = html_lib.unescape(re.sub(r"\s+", " ", "".join(self._dt))).strip()
            gloss = html_lib.unescape(re.sub(r"\s+", " ", "".join(self._dd))).strip()
            if lemma:
                self.pairs.append((lemma, gloss))

    def handle_data(self, data: str) -> None:
        if self._in_dt:
            self._dt.append(data)
        elif self._in_dd:
            self._dd.append(data)


def _clean_lemma(raw: str) -> list[str]:
    text = html_lib.unescape(raw or "").strip()
    text = text.replace("〜", "～").replace("*", "")
    text = re.sub(r"\s+", " ", text)
    if not text:
        return []
    parts = re.split(r"[、,/／]", text)
    out: list[str] = []
    for part in parts:
        lemma = part.strip().strip("。．")
        if lemma.startswith("-") and len(lemma) > 1:
            out.append(fold_fan_romanization(lemma))
            continue
        if LEMMA_RE.match(lemma):
            out.append(fold_fan_romanization(lemma.casefold()))
    return out


_GREETINGS = {
    "はい", "いいえ", "ああ", "うーん", "やあ",
    "おはよう", "こんにちは", "こんばんは", "さようなら", "さよなら",
}


def _guess_pos(lemma: str, ja: str, note: str = "") -> str:
    blob = f"{ja} {note}"
    if "後置詞" in blob:
        return "postposition"
    if lemma.startswith("-") or lemma.endswith("-"):
        return "suffix" if lemma.startswith("-") else "prefix"
    if " " in lemma:
        return "phrase"
    parts = [part.strip() for part in re.split(r"[。、/／]", ja) if part.strip()]
    head = parts[0] if parts else ja
    if head in _GREETINGS or ja in _GREETINGS:
        return "interjection"
    verb_like = ("する", "る", "す", "む", "く", "ぐ", "つ", "ぬ", "ぶ")
    if any(part.endswith(verb_like) and len(part) <= 12 for part in (parts or [ja])):
        return "verb"
    if head.endswith(("しい", "い")) and len(head) <= 8:
        return "adjective"
    return "noun"


def _pos_from_dadh_gloss(gloss: str) -> str:
    match = POS_MARK_RE.search(gloss)
    if not match:
        return "noun"
    mark = match.group(1).replace(" ", "")
    for key, pos in POS_FROM_MARK.items():
        if key in mark:
            return pos
    return "noun"


_LENTICULAR_RE = re.compile(r"〔([^〕]*)〕")
_QUOTE_RE = re.compile(r"「([^」]+)」")
_LATIN_TOKEN_RE = re.compile(r"[A-Za-zÉéÏïÜüŸÿŒœ*]{2,}")
_LEADING_META_PAREN = re.compile(
    r"^[（(]("
    r"特に|"
    r"あるいは|"
    r"または|"
    r"多くは?|"
    r"主に|"
    r"不変化|"
    r"品詞不詳|"
    r"pl\.[^）)]*|"
    r"[Rr]ü[eé]\s*-?|"
    r"nom\.[^）)]*|acc\.[^）)]*|gen\.[^）)]*|"
    r"職業としての|"
    r"アーヴ帝国の|"
    r"勧誘[^）)]*|"
    r"目的語なし[^）)]*|"
    r"-[^）)]*"
    r")[）)]\s*"
)
_LEADING_EQ_PAREN = re.compile(r"^\(=([^)]+)\)\s*")
_LEADING_QUALIFIER_PAREN = re.compile(
    r"^[（(]([^）)]+(?:を|に|としての|のように|の))[）)]\s+"
)
_LEADING_QUALIFIER_PAREN_TIGHT = re.compile(
    r"^[（(]([^）)]+(?:を|に|としての|のように|の))[）)]"
)
_LEADING_ANY_PAREN = re.compile(r"^[（(]([^）)]+)[）)]\s*(.+)$")
_TRAIL_CASE_PAREN = re.compile(r"[（(][はをがにへとでのも][）)]$")
_TRAIL_NOTE_PAREN = re.compile(r"[（(]([^）)]+)[）)]$")
_MID_NADO_PAREN = re.compile(r"^(.+?)[（(](など|などに|等)[）)](.+)$")
_GENDER_PAREN = re.compile(r"([\u3040-\u30ff\u4e00-\u9fff]*子)\(女\)")
_USAGE_LABEL_RE = re.compile(
    r"^(?:並列|引用|感嘆詞|感動詞|副詞|後置詞|前置詞|前置型|生格|正格|正格扱い|"
    r"単位|長さの単位|人数を表す|呼びかけ|歓迎の言葉|文字|帝国国民|"
    r".+詞|.+格|.+扱い|.+単位|.+を表す|.+の言葉|.+の称号)$"
)
_NOTE_PHRASE_RE = re.compile(
    r"(?:爵位|姓称号)の[１1一]つ?|の美称|と同じ|の略$|の意か$|の[１1一]つ$|の上$|の下$|の称号$|の別がある$"
)
_GRAMMAR_DESC_RE = re.compile(
    r"(を表わ?す|を現わ?す|を示[す]|を意味する|文末に|人称代名詞|接頭語|接尾)"
)
_DEFINITION_NOTE_RE = re.compile(
    r"(において|を取り|を用い|であると|について|をもつ|を領地|するもの$|すること$)"
)
_LEADING_BARONH_RE = re.compile(
    r"^[A-Za-zÉéÏïÜüŸÿŒœ*][A-Za-zÉéÏïÜüŸÿŒœ*''\-]*(?:\s+[A-Za-zÉéÏïÜüŸÿŒœ*][A-Za-zÉéÏïÜüŸÿŒœ*''\-]*)*"
)


def _ja_char_count(text: str) -> int:
    return len(re.findall(r"[\u3040-\u30ff\u4e00-\u9fff]", text or ""))


def _latin_char_count(text: str) -> int:
    return sum(len(match) for match in _LATIN_TOKEN_RE.findall(text or ""))


def _strip_trail_case_paren(text: str) -> str:
    prev = None
    while prev != text:
        prev = text
        text = _TRAIL_CASE_PAREN.sub("", text).strip()
    return text


def _looks_grammar_desc(text: str) -> bool:
    if _QUOTE_RE.search(text):
        return False
    if re.search(r"(文末|人称代名詞|接頭語)", text):
        return True
    return bool(re.search(r"(を表わ?す|を現わ?す|を示[す]|を意味する)$", text))


def _looks_furigana(inner: str, head: str) -> bool:
    if not re.fullmatch(r"[\u3040-\u309f\u30a0-\u30ffー]+", inner or ""):
        return False
    return _ja_char_count(inner) <= max(6, _ja_char_count(head) + 2)


def _looks_usage_label(inner: str) -> bool:
    item = (inner or "").strip()
    if not item:
        return False
    if item.endswith(("?", "？")):
        return True
    if "具体的" in item or "不詳" in item:
        return True
    return bool(_USAGE_LABEL_RE.match(item))


_DICT_PASSIVE_RE = re.compile(r"^〜?\(ら\)れる$")
_DICT_CAUSATIVE_RE = re.compile(r"^〜?\(さ\)せる$")
_DICT_PASSIVE_PLAIN_RE = re.compile(r"^〜される$")


def _normalize_dict_aux(text: str, notes: list[str]) -> str:
    """辞書の活用表記 `〜(ら)れる` は訳語にせず、受け身・使役だけを残す。"""
    if _DICT_PASSIVE_RE.fullmatch(text):
        notes.append("〜(ら)れる")
        return "受け身"
    if _DICT_CAUSATIVE_RE.fullmatch(text):
        notes.append("〜(さ)せる")
        return "使役"
    if _DICT_PASSIVE_PLAIN_RE.fullmatch(text):
        notes.append(text)
        return "受け身"
    return text


def _peel_any_leading_paren(text: str, notes: list[str]) -> str:
    """残った先頭カッコは用法・修飾として notes へ。活用表記は後で辞書形として分ける。"""
    while text:
        match = _LEADING_ANY_PAREN.match(text)
        if not match:
            break
        inner, rest = match.group(1).strip(), match.group(2).strip()
        if inner in {"ら", "さ"} and rest.startswith(("れる", "せる", "られる", "させる")):
            break
        if not rest or _ja_char_count(rest) < 1:
            break
        notes.append(inner)
        text = rest
    return text


def _split_sense_parts(text: str) -> list[str]:
    """`;` `。` `/` で語義を割る。括弧の中の `/` は切らない。"""
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for char in text:
        if char in "(（":
            depth += 1
            buf.append(char)
        elif char in ")）":
            depth = max(0, depth - 1)
            buf.append(char)
        elif depth == 0 and char in ";；。/／":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(char)
    parts.append("".join(buf))
    return parts


def _expand_compact_parens(text: str, notes: list[str]) -> list[str]:
    """皇太子(女) や 打撃(隊) のように、実義を畳んだカッコは見出しへ展開する。"""
    suffix = re.search(r"(の称号|の別がある)$", text)
    if suffix and _GENDER_PAREN.search(text):
        notes.append(suffix.group(1))
        text = text[: suffix.start()].rstrip()
    if _GENDER_PAREN.search(text):
        expanded = _GENDER_PAREN.sub(
            lambda match: f"{match.group(1)} / {match.group(1)[:-1]}女",
            text,
        )
        return [bit.strip() for bit in expanded.split(" / ") if bit.strip()]
    compact = re.fullmatch(r"(.+)\((隊|するもの|輸送艦)\)$", text)
    if compact:
        head, inner = compact.group(1), compact.group(2)
        if inner == "するもの":
            return [f"{head}するもの"]
        if inner == "輸送艦":
            return [f"{head}{inner}"]
        return [head, f"{head}{inner}"]
    return [text]


def _peel_mid_nado_paren(text: str, notes: list[str]) -> str:
    match = _MID_NADO_PAREN.match(text)
    if not match:
        return text
    left, mark, rest = match.group(1).strip(), match.group(2), match.group(3).strip()
    if rest and _ja_char_count(rest) >= 2:
        notes.append(f"{left}{mark}")
        return rest
    return text


def _peel_mid_synonym_paren(text: str, notes: list[str]) -> str:
    """物質燃料(推進剤)採取基地 のような複合語中の言い換えを notes へ。"""
    match = re.fullmatch(r"(.+?)[（(]([^）)]{1,12})[）)](.+)", text)
    if not match:
        return text
    left, inner, right = match.group(1), match.group(2).strip(), match.group(3)
    if inner in {"ら", "さ", "女", "隊"}:
        return text
    if _looks_usage_label(inner) or _looks_furigana(inner, left):
        notes.append(inner)
        return (left + right).strip()
    if (
        _ja_char_count(inner) <= 6
        and _ja_char_count(left) >= 2
        and _ja_char_count(right) >= 2
        and "あるいは" not in inner
    ):
        notes.append(inner)
        return (left + right).strip()
    return text


def _peel_trailing_note_paren(text: str, notes: list[str]) -> str:
    """`と（並列）` `ええと(感嘆詞)` `明日(あした)` の末尾補足を notes へ。"""
    match = _TRAIL_NOTE_PAREN.search(text)
    if not match:
        return text
    inner = match.group(1).strip()
    head = text[: match.start()].rstrip()
    if not head or inner in {"ら", "さ", "女", "隊", "するもの", "輸送艦"}:
        return text
    if _looks_furigana(inner, head) or _looks_usage_label(inner) or _ja_char_count(inner) > 6:
        notes.append(inner)
        return head
    return text


def _looks_definition_note(text: str) -> bool:
    if not _DEFINITION_NOTE_RE.search(text):
        return False
    return _ja_char_count(text) > 12


def _is_note_segment(text: str) -> bool:
    item = text.strip()
    if not item:
        return True
    if item in {"語義不詳", "未詳", "不詳", "品詞不詳"}:
        return False
    if item.startswith("→") or item.startswith("-"):
        return True
    if re.search(r"は\s+[A-Za-zÉéÏïÜüŸÿŒœ*]", item):
        return True
    if _NOTE_PHRASE_RE.search(item) and _ja_char_count(item) <= 16:
        return True
    if item.startswith(("gen.", "nom.", "acc.", "pl.")):
        return True
    if _LEADING_BARONH_RE.match(item) and _latin_char_count(item) >= 2 and _ja_char_count(item) > 0:
        return True
    if _looks_grammar_desc(item):
        return True
    if _looks_definition_note(item):
        return True
    return False


_LEADING_LATIN_PAREN = re.compile(
    r"^[（(]([^）)]*[A-Za-zÉéÏïÜüŸÿŒœ*][^）)]*)[）)]\s*"
)


def _peel_leading_meta(text: str, notes: list[str]) -> tuple[str, bool]:
    """先頭の用法・文法カッコを notes へ。`(特に)` なら残りは例示。"""
    usage_example = False
    while text:
        meta = _LEADING_META_PAREN.match(text)
        if meta:
            notes.append(meta.group(0).strip())
            if meta.group(1).startswith("特に") and meta.group(1) == "特に":
                usage_example = True
            text = text[meta.end() :].lstrip()
            continue
        eq_paren = _LEADING_EQ_PAREN.match(text)
        if eq_paren:
            notes.append(f"={eq_paren.group(1)}")
            text = text[eq_paren.end() :].lstrip()
            continue
        latin_paren = _LEADING_LATIN_PAREN.match(text)
        if latin_paren:
            notes.append(latin_paren.group(1).strip())
            text = text[latin_paren.end() :].lstrip()
            continue
        break
    return text, usage_example


def _peel_qualifier_paren(text: str, notes: list[str]) -> str:
    """`(楽器を)演奏する` や `(地上世界の行政単位としての)市` から見出し語を残す。"""
    match = _LEADING_QUALIFIER_PAREN.match(text) or _LEADING_QUALIFIER_PAREN_TIGHT.match(text)
    if not match:
        return text
    rest = text[match.end() :].strip()
    if not rest or _LEADING_BARONH_RE.match(rest):
        return text
    notes.append(match.group(1).strip())
    return rest


def clean_ja_gloss(raw: str) -> tuple[str, str]:
    """語釈から単語だけを残し、`;` 以降の用法・括弧注などを notes へ分ける。"""
    text = POS_MARK_RE.sub("", raw or "")
    text = text.replace("（", "(").replace("）", ")")
    notes: list[str] = []
    for match in _LENTICULAR_RE.finditer(text):
        inner = match.group(1).strip()
        if inner:
            notes.append(inner)
    text = _LENTICULAR_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" \t.。;；")

    senses: list[str] = []
    unknown: list[str] = []
    for raw_part in _split_sense_parts(text):
        part = raw_part.strip(" /／、, ")
        if not part:
            continue
        part, usage_example = _peel_leading_meta(part, notes)
        if usage_example:
            if part:
                notes.append(part)
            continue
        part = _peel_qualifier_paren(part, notes)
        part = _peel_any_leading_paren(part, notes)
        pieces = _expand_compact_parens(part, notes)
        for part in pieces:
            part = _peel_mid_nado_paren(part, notes)
            part = _peel_mid_synonym_paren(part, notes)
            part = _peel_trailing_note_paren(part, notes)
            part = _strip_trail_case_paren(part)
            part = _normalize_dict_aux(part, notes)
            if not part:
                continue
            if re.fullmatch(r"[（(][^）)]+[）)]", part):
                notes.append(part.strip("（）()"))
                continue
            _collect_sense(part, senses, notes, unknown)

    seen: set[str] = set()
    unique: list[str] = []
    for sense in senses:
        sense = sense.strip(" /")
        key = re.sub(r"\s+", "", sense)
        if not sense or key in seen:
            continue
        seen.add(key)
        unique.append(sense)
    if not unique and unknown:
        unique.append(unknown[0])
    short = [item for item in unique if _ja_char_count(item) <= 10]
    long_defs = [item for item in unique if _ja_char_count(item) > 18]
    if short and long_defs:
        unique = [item for item in unique if item not in long_defs]
        notes.extend(long_defs)
    gloss = " / ".join(unique)
    note_parts = [item for item in notes if item and item not in unique and item != gloss]
    return gloss, " ".join(dict.fromkeys(note_parts))


def _collect_sense(part: str, senses: list[str], notes: list[str], unknown: list[str]) -> None:
    quotes = _QUOTE_RE.findall(part)
    if quotes and _GRAMMAR_DESC_RE.search(_QUOTE_RE.sub("", part)):
        for quote in quotes:
            quote = quote.replace("…", "").strip()
            if quote:
                senses.append(quote)
        notes.append(part)
        return
    if part in {"語義不詳", "未詳", "不詳", "品詞不詳"}:
        unknown.append(part)
        return
    speculation = re.fullmatch(r"(.+?)(?:、あるいは(.+?))?の意か", part)
    if speculation and not _looks_grammar_desc(part):
        for group in speculation.groups():
            if group:
                senses.append(group.strip())
        notes.append("の意か")
        return
    if _latin_char_count(part) >= 3:
        head = re.match(r"^([\u3040-\u30ff\u4e00-\u9fff〜ー]{1,4})(?=\s|[A-Za-zÉéÏïÜüŸÿŒœ*（(]|$)", part)
        if head:
            senses.append(head.group(1))
        notes.append(part)
        return
    etym = re.fullmatch(
        r"([\u3040-\u30ff\u4e00-\u9fff〜ー]{1,6})\s*の意(?:[、,].+)?$",
        part,
    )
    if etym and _ja_char_count(part) > 10:
        senses.append(etym.group(1))
        notes.append(part)
        return
    if _is_note_segment(part):
        notes.append(part)
        return
    if "、" in part or "," in part:
        bits = [bit.strip() for bit in re.split(r"[、,]", part) if bit.strip()]
        if bits and all(_ja_char_count(bit) <= 8 and not _is_note_segment(bit) for bit in bits):
            senses.extend(_strip_trail_case_paren(bit) for bit in bits)
            return
    senses.append(part)


def _gloss_ja_from_dadh(gloss: str) -> tuple[str, str]:
    text = GEN_RE.sub("", gloss)
    text = re.sub(r"\[[^\]]*\]", "", text)
    return clean_ja_gloss(text)


def _reading_from_kana(kana: str) -> str:
    kana = html_lib.unescape(kana or "").strip()
    kana = re.sub(r"[＜＞<>]", "", kana)
    return kana


def entries_from_mule_table(rows: list[list[str]], *, source: str) -> list[Entry]:
    grouped: dict[tuple[str, str], Entry] = {}
    body = rows[1:] if rows and "ローマ字" in "".join(rows[0]) else rows
    for row in body:
        if len(row) < 3:
            continue
        roman, kana, ja = row[0], row[1], row[2]
        note = row[4] if len(row) > 4 else ""
        ja = html_lib.unescape(ja).strip()
        if not ja or ja in {"ピッカージュ"}:
            continue
        ja, extra_notes = clean_ja_gloss(ja)
        if not ja:
            continue
        notes = " ".join(part for part in (note.strip(), extra_notes) if part)
        for lemma in _clean_lemma(roman):
            pos = _guess_pos(lemma, ja, notes)
            stem = lemma[:-1] if pos == "verb" and lemma.endswith("e") and len(lemma) > 2 else ""
            key = (lemma, pos)
            existing = grouped.get(key)
            if existing:
                if ja not in existing.gloss_ja:
                    existing.gloss_ja = existing.gloss_ja + " / " + ja
                if extra_notes and extra_notes not in existing.notes:
                    existing.notes = (existing.notes + " " + extra_notes).strip()
                if kana and not existing.reading_ja:
                    existing.reading_ja = _reading_from_kana(kana)
                continue
            grouped[key] = Entry(
                lemma=lemma,
                pos=pos,
                gloss_ja=ja,
                gloss_en=ja,
                stem=stem,
                reading_ja=_reading_from_kana(kana),
                source=source,
                tags=["mule-jisyo", "ingested"],
                notes=notes,
            )
    return list(grouped.values())


def entries_from_dadh_pairs(pairs: list[tuple[str, str]], *, source: str) -> list[Entry]:
    out: list[Entry] = []
    seen: set[tuple[str, str]] = set()
    for raw_lemma, gloss in pairs:
        reconstructed = raw_lemma.strip().startswith("*")
        for lemma in _clean_lemma(raw_lemma):
            pos = _pos_from_dadh_gloss(gloss)
            ja, extra_notes = _gloss_ja_from_dadh(gloss)
            if not ja:
                continue
            key = (lemma, pos)
            if key in seen:
                continue
            seen.add(key)
            stem = lemma[:-1] if pos == "verb" and lemma.endswith("e") and len(lemma) > 2 else ""
            paradigm: dict[str, str] = {}
            gen = GEN_RE.search(gloss)
            if pos == "noun" and gen:
                paradigm = {"nom": lemma, "gen": fold_fan_romanization(gen.group(1).casefold())}
            tags = ["dadh-baronr", "ingested"]
            if reconstructed:
                tags.append("reconstructed")
            out.append(
                Entry(
                    lemma=lemma,
                    pos=pos,
                    gloss_ja=ja,
                    gloss_en=ja,
                    stem=stem,
                    paradigm=paradigm,
                    source=source,
                    tags=tags,
                    notes=extra_notes,
                )
            )
    return out


def parse_dadh_html(html_text: str) -> list[tuple[str, str]]:
    parser = _DefinitionListParser()
    parser.feed(html_text)
    return parser.pairs


def thanks_document(entries: list[Entry], *, extra_sources: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {
        "meta": {
            "version": 1,
            "kind": "ingested",
            "license": "fan compilation; see source sites for their terms",
            "sources": extra_sources or SPECIAL_THANKS,
            "thanks": [item["thanks"] for item in SPECIAL_THANKS],
            "notes": (
                "公式辞書ではない二次資料の走査結果です。語釈は各サイト編者の再構成を含み、誤りがあり得ます。"
            ),
        },
        "entries": [entry.to_dict() for entry in entries],
    }
