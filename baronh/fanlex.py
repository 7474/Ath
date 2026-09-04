"""ファンサイト辞書の出典メタデータと走査。"""

from __future__ import annotations

import html as html_lib
import re
from html.parser import HTMLParser
from typing import Any

from baronh.lexicon import Entry

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
    "名": "noun",
    "代名": "pronoun",
    "動": "verb",
    "形": "adjective",
    "副": "adverb",
    "感": "interjection",
    "接続": "conjunction",
    "後": "postposition",
    "連語": "phrase",
    "動詞接尾": "suffix",
    "接頭": "prefix",
    "接尾": "suffix",
}

LEMMA_RE = re.compile(
    r"^\*?-?[A-Za-zÉéÏïÜüŸÿŒœ][A-Za-zÉéÏïÜüŸÿŒœ''\-]*(?:[ 　][A-Za-zÉéÏïÜüŸÿŒœ][A-Za-zÉéÏïÜüŸÿŒœ''\-]*){0,6}$"
)
POS_MARK_RE = re.compile(r"[【《]([^】》]+)[】》]")
GEN_RE = re.compile(r"gen\.\s*([A-Za-zÉéÏïÜüŸÿŒœ]+)\.?", re.I)


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
            out.append(lemma)
            continue
        if LEMMA_RE.match(lemma):
            out.append(lemma.casefold())
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


def _gloss_ja_from_dadh(gloss: str) -> str:
    text = POS_MARK_RE.sub("", gloss, count=1)
    text = GEN_RE.sub("", text)
    text = re.sub(r"\[jp\.[^\]]*\]", "", text)
    text = re.sub(r"\[[^\]]*\]", "", text)
    text = re.sub(r"→.*$", "", text)
    text = text.replace("。", "。 ").split("。")[0]
    text = re.sub(r"\s+", " ", text).strip(" .。;；")
    if len(text) > 40:
        text = text[:40].rsplit(" ", 1)[0] or text[:40]
    return text


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
        for lemma in _clean_lemma(roman):
            pos = _guess_pos(lemma, ja, note)
            stem = lemma[:-1] if pos == "verb" and lemma.endswith("e") and len(lemma) > 2 else ""
            key = (lemma, pos)
            existing = grouped.get(key)
            if existing:
                if ja not in existing.gloss_ja:
                    existing.gloss_ja = existing.gloss_ja + " / " + ja
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
                notes=note.strip(),
            )
    return list(grouped.values())


def entries_from_dadh_pairs(pairs: list[tuple[str, str]], *, source: str) -> list[Entry]:
    out: list[Entry] = []
    seen: set[tuple[str, str]] = set()
    for raw_lemma, gloss in pairs:
        reconstructed = raw_lemma.strip().startswith("*")
        for lemma in _clean_lemma(raw_lemma):
            pos = _pos_from_dadh_gloss(gloss)
            ja = _gloss_ja_from_dadh(gloss)
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
                paradigm = {"nom": lemma, "gen": gen.group(1).casefold()}
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
