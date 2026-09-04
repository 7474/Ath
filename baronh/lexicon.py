"""辞書エントリと読み込み。

検索の点数付け・表記ゆれ・部分一致をしない理由は baronh/ARCHITECTURE.md を参照。
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

from baronh.paths import SEED_LEXICON_PATH, default_lexicon_paths
from baronh.phonology import hira_to_kata

CASES = ("nom", "acc", "gen", "dat", "all", "abl", "ins")
CASE_JA = {
    "nom": "主格",
    "acc": "対格",
    "gen": "生格",
    "dat": "与格",
    "all": "向格",
    "abl": "奪格",
    "ins": "具格",
}
CASE_PARTICLE_JA = {
    "nom": "が",
    "acc": "を",
    "gen": "の",
    "dat": "に",
    "all": "へ",
    "abl": "から",
    "ins": "で",
}


@dataclass
class Entry:
    lemma: str
    pos: str
    gloss_ja: str
    gloss_en: str = ""
    declension: str = ""
    stem: str = ""
    reading_ja: str = ""
    paradigm: dict[str, str] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    source: str = "seed"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["paradigm"]:
            data.pop("paradigm")
        if not data["tags"]:
            data.pop("tags")
        if not data["notes"]:
            data.pop("notes")
        if not data["reading_ja"]:
            data.pop("reading_ja")
        if not data["stem"]:
            data.pop("stem")
        if not data["declension"]:
            data.pop("declension")
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Entry:
        known = {k: raw[k] for k in cls.__dataclass_fields__ if k in raw}
        if "tags" in known and isinstance(known["tags"], str):
            known["tags"] = [part.strip() for part in known["tags"].split(",") if part.strip()]
        return cls(**known)


def _e(
    lemma: str,
    pos: str,
    gloss_ja: str,
    gloss_en: str = "",
    declension: str = "",
    stem: str = "",
    reading_ja: str = "",
    paradigm: dict[str, str] | None = None,
    tags: list[str] | None = None,
    notes: str = "",
) -> Entry:
    return Entry(
        lemma=lemma,
        pos=pos,
        gloss_ja=gloss_ja,
        gloss_en=gloss_en or gloss_ja,
        declension=declension,
        stem=stem,
        reading_ja=reading_ja,
        paradigm=paradigm or {},
        tags=tags or ["wikipedia"],
        notes=notes,
        source="seed",
    )


def seed_entries() -> list[Entry]:
    """Wikipedia「アーヴ語」ほか公開資料に基づくシード語彙。"""
    pronouns = [
        _e("fe", "pronoun", "私", "I", paradigm=_pron("fe", "fal", "far", "feri", "feré", "fasar", "fale"), reading_ja="フェ", tags=["wikipedia", "pronoun"]),
        _e("de", "pronoun", "あなた", "you", paradigm=_pron("de", "dal", "dar", "deri", "deré", "dasar", "dale"), reading_ja="デ", tags=["wikipedia", "pronoun"]),
        _e("se", "pronoun", "彼/彼女", "he/she", paradigm=_pron("se", "sal", "sar", "seri", "seré", "sasar", "sale"), reading_ja="セ", tags=["wikipedia", "pronoun"]),
        _e("farh", "pronoun", "私たち", "we", paradigm=_pron("farh", "fare", "farer", "fari", "faré", "farhar", "farle"), reading_ja="ファール", tags=["wikipedia", "pronoun"]),
        _e("darh", "pronoun", "あなたたち", "you (pl.)", paradigm=_pron("darh", "dare", "darer", "dari", "daré", "darhar", "darle"), reading_ja="ダール", tags=["wikipedia", "pronoun"]),
        _e("cnac", "pronoun", "彼ら", "they", paradigm=_pron("cnac", "cnal", "cnar", "cnari", "cnaré", "cnasar", "cnal"), reading_ja="クナ", tags=["wikipedia", "pronoun"]),
        _e("so", "pronoun", "これ", "this", paradigm=_pron("so", "sol", "sor", "sori", "soré", "sosar", "sole"), reading_ja="ソ", tags=["wikipedia", "pronoun"]),
        _e("re", "pronoun", "それ", "that", paradigm=_pron("re", "rol", "ror", "rori", "roré", "rosar", "role"), reading_ja="レ", tags=["wikipedia", "pronoun"]),
        _e("ai", "pronoun", "あれ", "that (distal)", paradigm=_pron("ai", "al", "ar", "ari", "aré", "asar", "ale"), reading_ja="アイ", tags=["wikipedia", "pronoun"]),
    ]
    nouns = [
        _e("abh", "noun", "アーヴ", "Abh", "1", "ab", "アーヴ",
           _pron("abh", "abe", "bar", "bari", "baré", "abhar", "bale")),
        _e("ath", "noun", "アース（文字）", "Ath (letter)", "1", "at", "アース",
           _pron("ath", "ate", "tar", "tari", "taré", "athar", "tale")),
        _e("azz", "noun", "敵", "enemy", "1", "az", "アズ",
           _pron("azz", "aze", "zar", "zari", "zaré", "azzar", "zale")),
        _e("lorann", "noun", "父", "father", "1n", "loran", "ロラン", tags=["wikipedia"]),
        _e("sarann", "noun", "母", "mother", "1n", "saran", "サラン", tags=["wikipedia"]),
        _e("aronn", "noun", "あそん", "ason", "1n", "aron", "アロン", tags=["wikipedia"]),
        _e("lamh", "noun", "真珠", "pearl", "2", "lam", "ラーフ"),
        _e("éboth", "noun", "微笑", "smile", "2", "ébot", "エボス"),
        _e("ïomh", "noun", "恋人", "lover", "2", "ïom", "イオム"),
        _e("laimh", "noun", "国民", "people / nation", "2", "laim", "ライム"),
        _e("saurh", "noun", "家族", "family", "2", "saur", "サウル", tags=["wikipedia"]),
        _e("sath", "noun", "方", "direction", "2", "sat", "サス"),
        _e("duc", "noun", "紅玉", "ruby", "3", "du", "デュー"),
        _e("greuc", "noun", "星", "star", "3", "greu", "グレウ"),
        _e("goc", "noun", "時空", "spacetime", "3", "go", "ゴー"),
        _e("nuïc", "noun", "耳", "ear", "3", "nuï", "ヌイ"),
        _e("dreuc", "noun", "伯爵", "count", "3", "dreu", "ドリュー"),
        _e("bœrh", "noun", "子爵", "viscount", "2", "bœr", "ベール"),
        _e("nimh", "noun", "男爵", "baron", "2", "nim", "ニム"),
        _e("saidiac", "noun", "操舵士", "helmsman", "4", "said", "サイディア"),
        _e("izomiac", "noun", "挑戦者", "challenger", "4", "izom", "イゾミア"),
        _e("rinusiac", "noun", "記事", "article", "4", "rinus", "リヌシア"),
        _e("useriac", "noun", "移民", "immigrant", "4", "user", "ウセリア"),
        _e("cilugiac", "noun", "皇太子/皇太女", "crown prince/princess", "4", "cilug", "シルギア"),
        _e("belységac", "noun", "管制官", "controller", "4g", "belysé", "ベリュセガ"),
        _e("gereulach", "noun", "星たち", "stars", "2", "gereulac", "ゲレウラ", tags=["wikipedia"]),
        _e("gosucelach", "noun", "家臣団", "retinue", "2", "gosucelac", "ゴスセラ"),
        _e("cairhoth", "noun", "入学", "entering school", "2", "cairhot", "カイルホス"),
        _e("dozzoth", "noun", "望み", "wish", "2", "dozzot", "ドゾス"),
        _e("cimecoth", "noun", "秘密", "secret", "2", "cimecot", "シメコス"),
        _e("sacoth", "noun", "買い物", "shopping", "2", "sacot", "サコス"),
        _e("ménragh", "noun", "平面宇宙航行機能", "plane-space navigation", "2", "ménrag", "メンラグ"),
        _e("baronh", "noun", "アーヴ語", "Baronh", "2", "baron", "バロン"),
        _e("lonh", "noun", "閣下", "excellency", "2", "lon", "ロン"),
        _e("fïac", "noun", "皇子/皇女", "imperial child", "3", "fïa", "フィア"),
        _e("frymec", "noun", "娘", "daughter", "3", "fryme", "フリュメ"),
        _e("lartnéc", "noun", "公子", "prince", "3", "lartné", "ラルトネ"),
        _e("laburec", "noun", "艦", "warship", "3", "labure", "ラブーレ"),
        _e("lonid", "noun", "門", "gate", "", "lonid", "ロニド", tags=["public"]),
        _e("gaftonosh", "noun", "紋章", "crest", "2", "gaftonos", "ガフトノーシュ", tags=["public"]),
        _e("frybarec", "noun", "帝国", "empire", "3", "frybare", "フリューバレ"),
        _e("lébh", "noun", "レーフ（帝国国民）", "imperial citizen", "2", "léb", "レーフ"),
        _e("ablïarsec", "noun", "アブリアル", "Ablïarsec", "3", "ablïarse", "アブリアル", tags=["public"]),
        _e("lacmhacarh", "noun", "ラクファカール", "Lacmhacarh", "2", "lacmhacar", "ラクファカール", tags=["wikipedia"]),
        _e("gatharsec", "noun", "ガサルス", "Gatharsec", "3", "gatharse", "ガサルス", tags=["wikipedia"]),
        _e("sarrych", "noun", "サリューシュ", "Sarrych", "2", "sarryc", "サリューシュ", tags=["wikipedia"]),
        _e("spaurh", "noun", "スポール", "Spaurh", "2", "spaur", "スポール", tags=["wikipedia"]),
        _e("lamhirh", "noun", "ラーフィール", "Lamhirh", "2", "lamhir", "ラーフィール", tags=["public"]),
        _e("parhynh", "noun", "パリューニュ", "Parhynh", "2", "parhyn", "パリューニュ", tags=["wikipedia"]),
        _e("haïdec", "noun", "ハイド", "Haïdec", "3", "haïde", "ハイド", tags=["wikipedia"]),
        _e("aith", "noun", "邦国", "kingdom", "2", "ait", "アイス"),
        _e("alïca", "noun", "頭環", "circlet", "", "alïca", "アリーカ"),
    ]
    verbs = [
        _e("ane", "verb", "である", "be", stem="an", reading_ja="アネ"),
        _e("user", "verb", "移民する/移る", "immigrate / move", stem="user", reading_ja="ウセル"),
        _e("sac", "verb", "書く", "write", stem="sac", reading_ja="サク"),
        _e("fac", "verb", "分かる", "understand", stem="fac", reading_ja="ファク"),
        _e("dor", "verb", "乗る", "board / ride", stem="dor", reading_ja="ドル"),
        _e("gob", "verb", "呼ぶ", "call", stem="gob", reading_ja="ゴブ"),
        _e("cilug", "verb", "皇位を継承する", "succeed to the throne", stem="cilug", reading_ja="シルグ"),
        _e("belysé", "verb", "管制する", "control", stem="belysé", reading_ja="ベリュセ"),
        _e("cair", "verb", "入る", "enter", stem="cair", reading_ja="カイル"),
        _e("doz", "verb", "望む", "wish", stem="doz", reading_ja="ドズ"),
        _e("cime", "verb", "秘密にする", "keep secret", stem="cime", reading_ja="シメ"),
        _e("sa", "verb", "買う", "buy", stem="sa", reading_ja="サ"),
        _e("lom", "verb", "幸せである", "be happy", stem="lom", reading_ja="ロム"),
        _e("samad", "verb", "構う", "mind", stem="samad", reading_ja="サマド"),
        _e("sot", "verb", "同席する", "sit together", stem="sot", reading_ja="ソト"),
        _e("zain", "verb", "だよね", "right?", stem="zain", reading_ja="ザイン"),
        _e("ïku", "verb", "行く", "go", stem="ïku", reading_ja="イク", tags=["public"]),
        _e("lar", "verb", "来る", "come", stem="lar", reading_ja="ラル", tags=["public"]),
        _e("mire", "verb", "見る", "see", stem="mire", reading_ja="ミレ", tags=["public"]),
        _e("banas", "verb", "話す", "speak", stem="banas", reading_ja="バナス", tags=["public"]),
        _e("om", "verb", "思う", "think", stem="om", reading_ja="オム", tags=["public"]),
        _e("as", "verb", "する", "do", stem="as", reading_ja="アス", tags=["public"]),
        _e("ar", "verb", "ある/いる", "exist", stem="ar", reading_ja="アル", tags=["public"]),
    ]
    other = [
        _e("a", "postposition", "は", "topic", reading_ja="ア"),
        _e("éü", "postposition", "よ", "vocative", reading_ja="エウ"),
        _e("sa", "postposition", "か", "question", reading_ja="サ"),
        _e("te", "postposition", "と（引用）", "quotative", reading_ja="テ"),
        _e("le", "postposition", "と（並列）", "and", reading_ja="レ"),
        _e("lo", "postposition", "と（並列）", "and", reading_ja="ロ"),
        _e("réfaiseni", "adverb", "一緒", "together", reading_ja="レファイセニ", tags=["wikipedia"]),
        _e("sote", "adverb", "ここに", "here", reading_ja="ソテ", tags=["wikipedia"]),
        _e("amata", "adjective", "多い", "many", reading_ja="アマタ"),
        _e("arata", "adjective", "新しい", "new", reading_ja="アラタ"),
        _e("dara", "interjection", "はい", "yes", reading_ja="ダラ", tags=["public"]),
        _e("ada", "interjection", "いいえ", "no", reading_ja="アダ", tags=["public"]),
        _e("zom", "interjection", "ありがとう", "thanks", reading_ja="ゾム", tags=["public"]),
    ]
    return pronouns + nouns + verbs + other


def _pron(nom: str, acc: str, gen: str, dat: str, allative: str, abl: str, ins: str) -> dict[str, str]:
    return {
        "nom": nom,
        "acc": acc,
        "gen": gen,
        "dat": dat,
        "all": allative,
        "abl": abl,
        "ins": ins,
    }


def seed_document() -> dict[str, Any]:
    return {
        "meta": {
            "version": 1,
            "language": "baronh",
            "license": "CC BY-SA 4.0 for Wikipedia-derived entries; fan compilation otherwise",
            "sources": [
                {
                    "name": "Wikipedia アーヴ語",
                    "url": "https://ja.wikipedia.org/wiki/%E3%82%A2%E3%83%BC%E3%83%B4%E8%AA%9E",
                    "license": "CC BY-SA 4.0",
                }
            ],
            "notes": (
                "公式の公開辞書は存在しない。文法の骨格は Wikipedia「アーヴ語」に依る。"
                "語彙はファンサイトを走査して拡充し、スペシャルサンクスに記す。"
            ),
        },
        "entries": [entry.to_dict() for entry in seed_entries()],
    }


def write_seed_lexicon(path: Path | None = None) -> Path:
    target = path or SEED_LEXICON_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(seed_document(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def _normalize_key(text: str) -> str:
    return "".join(text.casefold().split())


class Lexicon:
    def __init__(self, entries: Iterable[Entry]):
        self.entries: list[Entry] = []
        self._by_lemma: dict[str, list[Entry]] = {}
        self._by_gloss_ja: dict[str, list[Entry]] = {}
        self._by_gloss_en: dict[str, list[Entry]] = {}
        for entry in entries:
            self.add(entry)

    def add(self, entry: Entry, *, replace: bool = False) -> None:
        key = _normalize_key(entry.lemma)
        existing = self._by_lemma.get(key, [])
        if replace:
            self.entries = [item for item in self.entries if _normalize_key(item.lemma) != key or item.pos != entry.pos]
            existing = [item for item in existing if item.pos != entry.pos]
        else:
            for item in existing:
                if item.pos == entry.pos:
                    self._enrich(item, entry)
                    return
        self.entries.append(entry)
        self._by_lemma.setdefault(key, existing).append(entry)
        self._index_glosses(entry)

    def _index_glosses(self, entry: Entry) -> None:
        self._by_gloss_ja.setdefault(_normalize_key(entry.gloss_ja), []).append(entry)
        if " / " in entry.gloss_ja:
            for part in entry.gloss_ja.split("/"):
                self._by_gloss_ja.setdefault(_normalize_key(part), []).append(entry)
        for ja in _split_ja_aliases(entry.gloss_ja):
            self._by_gloss_ja.setdefault(_normalize_key(ja), []).append(entry)
        if entry.gloss_en:
            self._by_gloss_en.setdefault(_normalize_key(entry.gloss_en), []).append(entry)
            for part in entry.gloss_en.replace("/", ",").split(","):
                self._by_gloss_en.setdefault(_normalize_key(part), []).append(entry)

    def _enrich(self, existing: Entry, incoming: Entry) -> None:
        if incoming.gloss_ja and incoming.gloss_ja not in existing.gloss_ja:
            existing.gloss_ja = f"{existing.gloss_ja} / {incoming.gloss_ja}"
            self._index_glosses(existing)
        if incoming.reading_ja and not existing.reading_ja:
            existing.reading_ja = incoming.reading_ja
        if incoming.stem and not existing.stem:
            existing.stem = incoming.stem
        for tag in incoming.tags:
            if tag not in existing.tags:
                existing.tags.append(tag)
        if incoming.notes and incoming.notes not in existing.notes:
            existing.notes = (existing.notes + " " + incoming.notes).strip()

    def merge_document(self, document: dict[str, Any], *, replace: bool = True) -> int:
        count = 0
        for raw in document.get("entries", []):
            if not raw.get("lemma"):
                continue
            self.add(Entry.from_dict(raw), replace=replace)
            count += 1
        return count

    def lookup(self, query: str, *, lang: str = "auto") -> list[Entry]:
        key = _normalize_key(query)
        if not key:
            return []
        found: list[Entry] = []
        seen: set[int] = set()

        def take(items: Iterable[Entry]) -> None:
            for item in items:
                ident = id(item)
                if ident not in seen:
                    seen.add(ident)
                    found.append(item)

        if lang in ("auto", "baronh"):
            take(self._by_lemma.get(key, []))
        if lang in ("auto", "ja"):
            take(self._by_gloss_ja.get(key, []))
        if lang in ("auto", "en"):
            take(self._by_gloss_en.get(key, []))
        if not found and len(key) >= 3:
            # 日本語の部分一致は「ジント」⊂「サイ・ジント様」のように固有名詞を壊す
            if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", query):
                return found
            for entry in self.entries:
                blob = _normalize_key(" ".join([entry.lemma, entry.gloss_en]))
                if key in blob:
                    take([entry])
        return found

    def search(self, query: str, *, lang: str = "auto", limit: int = 8) -> list[Entry]:
        """短いクエリで全エントリを点数付けする。完全一致を優先し、無ければ活用語尾を剥がして探す。"""
        exact = self.lookup(query, lang=lang)
        if exact:
            return exact[:limit]
        tokens = list(dict.fromkeys(ja_query_variants(query) + en_query_variants(query)))
        return self.rank(query, tokens=tokens, limit=limit)

    def rank(
        self,
        haystack: str,
        *,
        tokens: Iterable[str] | None = None,
        fuzzy_tokens: Iterable[str] | None = None,
        limit: int = 40,
        min_score: int = 150,
    ) -> list[Entry]:
        """文や下訳に対して辞書を全件スキャンし、関連する見出しだけを返す。"""
        token_list = [part.strip() for part in (tokens or []) if part and str(part).strip()]
        expanded: list[str] = []
        seen_tok: set[str] = set()
        for token in token_list:
            for variant in (*ja_query_variants(token), *en_query_variants(token), token):
                if variant and variant not in seen_tok:
                    seen_tok.add(variant)
                    expanded.append(variant)
        fuzzy_src = [part.strip() for part in (fuzzy_tokens if fuzzy_tokens is not None else token_list) if part and str(part).strip()]
        fuzzy_expanded: list[str] = []
        seen_fuzzy: set[str] = set()
        for token in fuzzy_src:
            for variant in (*ja_query_variants(token), *en_query_variants(token), token):
                if variant and variant not in seen_fuzzy:
                    seen_fuzzy.add(variant)
                    fuzzy_expanded.append(variant)
        folded = {tok: fold_for_match(tok) for tok in set(expanded) | set(fuzzy_expanded)}
        scored: list[tuple[int, str, Entry]] = []
        for entry in self.entries:
            points = score_entry(
                entry,
                haystack=haystack,
                tokens=expanded,
                folded_tokens=folded,
                fuzzy_tokens=fuzzy_expanded,
            )
            if points >= min_score:
                scored.append((points, entry.lemma, entry))
        scored.sort(key=lambda item: (-item[0], item[1]))
        picked: list[Entry] = []
        seen_lemma: set[str] = set()
        for _points, lemma, entry in scored:
            key = _normalize_key(lemma)
            if key in seen_lemma:
                continue
            seen_lemma.add(key)
            picked.append(entry)
            if len(picked) >= limit:
                break
        return picked

    def iter_pos(self, *pos: str) -> Iterator[Entry]:
        wanted = set(pos)
        for entry in self.entries:
            if entry.pos in wanted:
                yield entry

    def to_document(self) -> dict[str, Any]:
        from baronh.fanlex import SPECIAL_THANKS

        doc = seed_document()
        sources = list(doc["meta"]["sources"])
        seen_urls = {item.get("url") for item in sources}
        for item in SPECIAL_THANKS:
            if item["url"] not in seen_urls:
                sources.append(item)
        doc["meta"]["sources"] = sources
        doc["meta"]["thanks"] = [item["thanks"] for item in SPECIAL_THANKS]
        doc["entries"] = [entry.to_dict() for entry in self.entries]
        doc["meta"]["entry_count"] = len(self.entries)
        return doc


_JA_STRIP_SUFFIXES = (
    "でしたか",
    "であります",
    "ました",
    "ません",
    "ました",
    "ますか",
    "でした",
    "だった",
    "である",
    "します",
    "ました",
    "する",
    "した",
    "して",
    "ます",
    "です",
    "だ",
)

_EN_STOP = {
    "a", "an", "the", "of", "to", "from", "with", "by", "in", "on", "at",
    "is", "are", "was", "were", "be", "and", "or", "i", "you", "we", "they",
}


def ja_query_variants(query: str) -> list[str]:
    """見ます→見る、移民します→移民する のように、辞書見出しと突き合わせる候補を増やす。"""
    text = (query or "").strip()
    if not text:
        return []
    out: list[str] = [text]
    for suf in _JA_STRIP_SUFFIXES:
        if text.endswith(suf) and len(text) > len(suf):
            stem = text[: -len(suf)]
            out.append(stem)
            if suf in {"ます", "ますか", "ました", "ません", "します"}:
                out.append(stem + "る")
            if suf in {"ます", "ますか", "ました", "ません", "します", "だ", "です", "した", "して"}:
                out.append(stem + "する")
    seen: set[str] = set()
    uniq: list[str] = []
    for item in out:
        item = item.strip()
        if item and item not in seen:
            seen.add(item)
            uniq.append(item)
    return uniq


def en_query_variants(query: str) -> list[str]:
    text = (query or "").strip()
    if not text:
        return []
    low = text.casefold()
    out = [text, low]
    if low.endswith("ing") and len(low) > 5:
        stem = low[:-3]
        out.extend([stem, stem + "e"])
    if low.endswith("ies") and len(low) > 4:
        out.append(low[:-3] + "y")
    elif low.endswith("es") and len(low) > 4:
        out.append(low[:-2])
    elif low.endswith("s") and len(low) > 3:
        out.append(low[:-1])
    seen: set[str] = set()
    uniq: list[str] = []
    for item in out:
        if item and item not in seen:
            seen.add(item)
            uniq.append(item)
    return uniq


def fold_for_match(text: str) -> str:
    """誤字検索用。ひらがな/カタカナ・ヴ/ブ・長音・全角を畳む。部分文字列検索には使わない。"""
    s = hira_to_kata(unicodedata.normalize("NFKC", text or ""))
    s = s.replace("ヴ", "ブ").replace("ヷ", "バ").replace("ヺ", "ボ")
    for mark in ("ー", "ｰ", "〜", "~", "・", "･", " ", "\u3000"):
        s = s.replace(mark, "")
    return s.casefold()


def within_edit_distance(left: str, right: str, limit: int = 1) -> bool:
    if left == right:
        return True
    if abs(len(left) - len(right)) > limit:
        return False
    if len(left) > len(right):
        left, right = right, left
    prev = list(range(len(right) + 1))
    for i, ca in enumerate(left, 1):
        curr = [i]
        row_min = i
        for j, cb in enumerate(right, 1):
            val = min(curr[-1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb))
            curr.append(val)
            if val < row_min:
                row_min = val
        if row_min > limit:
            return False
        prev = curr
    return prev[-1] <= limit


def fuzzy_points_folded(folded_token: str, folded_alias: str) -> int:
    if not folded_token or not folded_alias:
        return 0
    if folded_token == folded_alias:
        return 300
    if min(len(folded_token), len(folded_alias)) < 4:
        return 0
    # 日本語の1文字差は「ジントは」と「ジント様」を結んでしまうので、ラテン綴りだけに限る
    if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", folded_token + folded_alias):
        return 0
    if within_edit_distance(folded_token, folded_alias, 1):
        return 170
    return 0


def fuzzy_points(token: str, alias: str) -> int:
    """表記ゆれ・1文字タイポ。意味の近い別語や部分一致は採らない。"""
    if not token or not alias or token == alias:
        return 0
    folded_a = fold_for_match(token)
    folded_b = fold_for_match(alias)
    if folded_a == folded_b:
        return 300
    return fuzzy_points_folded(folded_a, folded_b)


def _en_aliases(gloss: str) -> list[str]:
    aliases: list[str] = []
    for part in (gloss or "").replace("/", ",").split(","):
        item = part.strip()
        if item:
            aliases.append(item)
    return aliases


def score_entry(
    entry: Entry,
    *,
    haystack: str,
    tokens: Iterable[str],
    folded_tokens: dict[str, str] | None = None,
    fuzzy_tokens: Iterable[str] | None = None,
) -> int:
    """完全一致の語釈・見出しを強く、1文字の部分一致は採らない。"""
    token_list = [str(token) for token in tokens if token]
    token_set = set(token_list)
    token_cf = {token.casefold() for token in token_list}
    folds = folded_tokens or {token: fold_for_match(token) for token in token_list}
    fuzzy_list = [str(token) for token in (fuzzy_tokens if fuzzy_tokens is not None else token_list) if token]
    hay = haystack or ""
    best = 0
    lemma = entry.lemma
    if lemma:
        if lemma in token_set or lemma.casefold() in token_cf:
            best = max(best, 500)
        elif len(lemma) >= 2 and re.search(
            rf"(?i)(?<![A-Za-zÉéÏïÜüŸÿŒœ]){re.escape(lemma)}(?![A-Za-zÉéÏïÜüŸÿŒœ])",
            hay,
        ):
            best = max(best, 280)
        folded_lemma = fold_for_match(lemma)
        for token in fuzzy_list:
            if token == lemma:
                continue
            best = max(best, fuzzy_points_folded(folds.get(token, ""), folded_lemma))
    aliases = _split_ja_aliases(entry.gloss_ja)
    primary = (aliases[0] if aliases else entry.gloss_ja).strip()
    for alias in aliases:
        alias = alias.strip()
        if not alias:
            continue
        n = len(alias)
        if n < 2 and alias != primary:
            continue
        if alias in token_set:
            best = max(best, 450 + n * 10)
        elif n >= 2 and alias in hay:
            best = max(best, 200 + n * 10)
        else:
            folded_alias = fold_for_match(alias)
            for token in token_list:
                if len(token) < 2:
                    continue
                if n >= 2 and (token.startswith(alias) or alias.startswith(token)):
                    best = max(best, 90 + min(n, len(token)) * 6)
            for token in fuzzy_list:
                if token != alias:
                    best = max(best, fuzzy_points_folded(folds.get(token, ""), folded_alias))
    for alias in _en_aliases(entry.gloss_en):
        low = alias.casefold()
        if not low or low in _EN_STOP:
            continue
        if alias in token_set or low in token_cf:
            best = max(best, 400 + len(alias) * 4)
        elif len(low) >= 3 and re.search(rf"(?i)\b{re.escape(alias)}\b", hay):
            best = max(best, 180 + len(alias) * 4)
        else:
            folded_alias = fold_for_match(alias)
            for token in fuzzy_list:
                if token != alias:
                    best = max(best, fuzzy_points_folded(folds.get(token, ""), folded_alias))
    return best


def _split_ja_aliases(gloss: str) -> list[str]:
    text = gloss.replace("（", "(").replace("）", ")")
    aliases = [text]
    if "(" in text:
        aliases.append(text.split("(", 1)[0])
        inner = text[text.find("(") + 1 : text.rfind(")")]
        if inner:
            aliases.append(inner)
    for sep in ("/", "・", "。", "、"):
        expanded: list[str] = []
        for alias in aliases:
            expanded.extend(part.strip() for part in alias.split(sep) if part.strip())
        aliases = expanded
    return aliases


def load_lexicon(paths: Iterable[Path] | None = None) -> Lexicon:
    from baronh.paths import INGESTED_PATH, default_lexicon_paths

    lexicon = Lexicon(seed_entries())
    for path in paths if paths is not None else default_lexicon_paths():
        if path == SEED_LEXICON_PATH and path.is_file():
            continue
        if path.is_file():
            document = json.loads(path.read_text(encoding="utf-8"))
            replace = path != INGESTED_PATH
            lexicon.merge_document(document, replace=replace)
    return lexicon
