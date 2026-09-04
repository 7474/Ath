"""文法・辞書の取り込み。Wikipedia / HTML / CSV / JSON。"""

from __future__ import annotations

import csv
import io
import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from baronh.fanlex import (
    DADH_DIC_PAGES,
    DADH_ONDIC_URL,
    MULE_JISYO_URL,
    entries_from_dadh_pairs,
    entries_from_mule_table,
    parse_dadh_html,
    thanks_document,
)
from baronh.lexicon import Entry, Lexicon
from baronh.paths import INGESTED_PATH
from baronh.phonology import fold_fan_romanization

WIKI_API = "https://{lang}.wikipedia.org/w/api.php"
USER_AGENT = "Ath-Baronh-Translator/0.1 (https://github.com/7474/Ath; educational fan tool)"

# Wikipedia 本文に頻出する「lemma（日本語）」パターン。
LEMMA_JA_RE = re.compile(
    r"([A-Za-zÉéÏïÜüŸÿŒœ][A-Za-zÉéÏïÜüŸÿŒœ''-]{1,24})（([^）]{1,20})）"
)


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._capture = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
            self._capture = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(re.sub(r"\s+", " ", "".join(self._cell)).strip())
            self._cell = None
            self._capture = False
        elif tag == "tr" and self._row is not None and self._table is not None:
            if any(self._row):
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None

    def handle_data(self, data: str) -> None:
        if self._capture and self._cell is not None:
            self._cell.append(data)


def fetch_url(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_text(url: str, encoding: str | None = None) -> str:
    raw = fetch_url(url)
    if encoding:
        return raw.decode(encoding, errors="replace")
    # Wikipedia は UTF-8。古いファンサイトは euc-jp のことがある。
    for enc in ("utf-8", "euc-jp", "shift_jis", "cp932"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def fetch_wikipedia(title: str = "アーヴ語", lang: str = "ja") -> dict[str, Any]:
    api = WIKI_API.format(lang=lang)
    query = (
        f"{api}?action=parse&page={urllib.parse.quote(title)}"
        "&prop=text|wikitext&format=json&formatversion=2"
    )
    data = json.loads(fetch_text(query))
    if "error" in data:
        raise RuntimeError(data["error"])
    parsed = data["parse"]
    return {
        "title": parsed.get("title", title),
        "html": parsed.get("text", ""),
        "wikitext": parsed.get("wikitext", ""),
        "url": f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(title)}",
    }


def _guess_pos(lemma: str, ja: str) -> tuple[str, str]:
    if lemma.endswith("e") and ja.endswith(("る", "す", "む", "く", "ぐ", "つ")):
        return "verb", ""
    if lemma in {"a", "éü", "sa", "te", "le", "lo"}:
        return "postposition", ""
    if lemma.endswith("iac") or lemma.endswith("gac"):
        return "noun", "4" if lemma.endswith("iac") else "4g"
    if lemma.endswith("c"):
        return "noun", "3"
    if lemma.endswith("h"):
        return "noun", "2"
    return "noun", ""


def entries_from_pairs(pairs: list[tuple[str, str]], *, source: str) -> list[Entry]:
    out: list[Entry] = []
    seen: set[str] = set()
    for lemma, ja in pairs:
        lemma = lemma.strip().strip(".,;:「」『』")
        ja = ja.strip().strip(".,;:「」『』")
        if not lemma or not ja or lemma in seen:
            continue
        lemma = fold_fan_romanization(lemma)
        if not re.fullmatch(r"[A-Za-zÉéÏïÜüŸÿŒœ][A-Za-zÉéÏïÜüŸÿŒœ''-]*", lemma):
            continue
        if len(ja) > 24:
            continue
        seen.add(lemma)
        pos, decl = _guess_pos(lemma, ja)
        stem = lemma[:-1] if pos == "verb" and lemma.endswith("e") else lemma
        if pos == "verb" and lemma.endswith("e"):
            lemma = stem
        out.append(
            Entry(
                lemma=lemma,
                pos=pos,
                gloss_ja=ja,
                gloss_en=ja,
                declension=decl,
                stem=stem if pos == "verb" else "",
                source=source,
                tags=["ingested"],
            )
        )
    return out


def extract_pairs_from_text(text: str) -> list[tuple[str, str]]:
    pairs = [(m.group(1), m.group(2)) for m in LEMMA_JA_RE.finditer(text)]
    # 「アーヴ語 / 日本語」の単純行
    for line in text.splitlines():
        if "\t" in line:
            left, right = line.split("\t", 1)
            pairs.append((left.strip(), right.strip()))
        elif re.match(r"^[A-Za-zÉéÏïÜüŸÿŒœ].+[,，/／]\s*\S+", line):
            left, right = re.split(r"[,，/／]", line, maxsplit=1)
            pairs.append((left.strip(), right.strip()))
    return pairs


def extract_pairs_from_html(html_text: str) -> list[tuple[str, str]]:
    parser = _TableParser()
    parser.feed(html_text)
    pairs = extract_pairs_from_text(re.sub(r"<[^>]+>", " ", html_text))
    for table in parser.tables:
        if not table:
            continue
        header = [cell.lower() for cell in table[0]]
        baronh_idx = next((i for i, h in enumerate(header) if any(k in h for k in ("アーヴ", "baronh", "ath", "lemma", "語"))), None)
        ja_idx = next((i for i, h in enumerate(header) if any(k in h for k in ("日本", "意味", "ja", "gloss", "和"))), None)
        rows = table[1:] if baronh_idx is not None else table
        if baronh_idx is None:
            # 変化表: 先頭列が格名、残りが語形
            if table[0] and any(x in "".join(table[0]) for x in ("主格", "対格")):
                for row in table:
                    if row and row[0] == "主格":
                        for form in row[1:]:
                            if re.fullmatch(r"[A-Za-zÉéÏïÜüŸÿŒœ]+", form or ""):
                                pairs.append((form, form))
                continue
            baronh_idx, ja_idx = 0, 1 if table[0] and len(table[0]) > 1 else 0
        for row in rows:
            if baronh_idx < len(row) and ja_idx is not None and ja_idx < len(row):
                pairs.append((row[baronh_idx], row[ja_idx]))
    return pairs


def ingest_wikipedia(title: str = "アーヴ語", lang: str = "ja") -> dict[str, Any]:
    page = fetch_wikipedia(title, lang)
    html_text = page["html"]
    # parse API の text は HTML フラグメント
    pairs = extract_pairs_from_html(html_text)
    pairs += extract_pairs_from_text(page["wikitext"])
    entries = entries_from_pairs(pairs, source=page["url"])
    return {
        "source": page["url"],
        "title": page["title"],
        "entries": [e.to_dict() for e in entries],
        "count": len(entries),
    }


def ingest_html_url(url: str) -> dict[str, Any]:
    text = fetch_text(url)
    if "<html" in text.lower() or "<table" in text.lower():
        pairs = extract_pairs_from_html(text)
    else:
        pairs = extract_pairs_from_text(text)
    entries = entries_from_pairs(pairs, source=url)
    return {"source": url, "entries": [e.to_dict() for e in entries], "count": len(entries)}


def ingest_file(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        document = json.loads(raw)
        if isinstance(document, list):
            document = {"entries": document}
        return {"source": str(path), "entries": document.get("entries", []), "count": len(document.get("entries", []))}
    if suffix in {".csv", ".tsv"}:
        dialect = csv.excel_tab if suffix == ".tsv" else csv.excel
        reader = csv.DictReader(io.StringIO(raw), dialect=dialect)
        entries = []
        if reader.fieldnames and {"lemma", "gloss_ja"} <= {name.strip() for name in reader.fieldnames if name}:
            for row in reader:
                cleaned = {k.strip(): (v or "").strip() for k, v in row.items() if k}
                if cleaned.get("lemma"):
                    entries.append(cleaned)
        else:
            simple = csv.reader(io.StringIO(raw), delimiter="\t" if suffix == ".tsv" else ",")
            for row in simple:
                if len(row) >= 2 and row[0] and not row[0].startswith("#"):
                    entries.append({"lemma": row[0].strip(), "gloss_ja": row[1].strip(), "gloss_en": row[1].strip(), "pos": "noun"})
        return {"source": str(path), "entries": entries, "count": len(entries)}
    pairs = extract_pairs_from_text(raw)
    entries = [e.to_dict() for e in entries_from_pairs(pairs, source=str(path))]
    return {"source": str(path), "entries": entries, "count": len(entries)}


def ingest_mule_jisyo(url: str = MULE_JISYO_URL) -> dict[str, Any]:
    html_text = fetch_text(url)
    parser = _TableParser()
    parser.feed(html_text)
    rows = parser.tables[0] if parser.tables else []
    entries = entries_from_mule_table(rows, source=url)
    document = thanks_document(entries)
    document["source"] = url
    document["title"] = "アーヴ語掻き集め アーヴ語辞書"
    document["count"] = len(entries)
    document["entries"] = [e.to_dict() for e in entries]
    return document


def ingest_dadh_ondic() -> dict[str, Any]:
    entries = []
    for url in DADH_DIC_PAGES:
        html_text = fetch_text(url)
        pairs = parse_dadh_html(html_text)
        entries.extend(entries_from_dadh_pairs(pairs, source=url))
    document = thanks_document(entries)
    document["source"] = DADH_ONDIC_URL
    document["title"] = "Sidrÿac Borgh=Racair Mauch 私家版アーヴ語辞書"
    document["count"] = len(entries)
    document["entries"] = [e.to_dict() for e in entries]
    return document


def ingest_known_sources(*, out: Path | None = None) -> dict[str, Any]:
    mule = ingest_mule_jisyo()
    dadh = ingest_dadh_ondic()
    lexicon = Lexicon([])
    lexicon.merge_document(dadh, replace=False)
    lexicon.merge_document(mule, replace=False)
    document = thanks_document(lexicon.entries)
    document["count"] = len(lexicon.entries)
    document["sources_ingested"] = [mule["source"], dadh["source"]]
    target = out or INGESTED_PATH
    write_lexicon_document(document, target)
    return document


def write_lexicon_document(document: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def merge_into_lexicon(lexicon: Lexicon, document: dict[str, Any], *, replace: bool = True) -> int:
    return lexicon.merge_document(document, replace=replace)


def write_lexicon(lexicon: Lexicon, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(lexicon.to_document(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ingest_auto(target: str) -> dict[str, Any]:
    parsed = urlparse(target)
    key = target.strip().lower()
    if key in {"wikipedia", "wiki", "wp"}:
        return ingest_wikipedia()
    if key in {"mule", "jisyo", "掻き集め"}:
        return ingest_mule_jisyo()
    if key in {"dadh", "ondic", "baronhdic"}:
        return ingest_dadh_ondic()
    if key in {"known", "thanks", "fan"}:
        return ingest_known_sources()
    if parsed.scheme in {"http", "https"}:
        if "wikipedia.org" in parsed.netloc:
            title = parsed.path.rsplit("/", 1)[-1]
            lang = parsed.netloc.split(".")[0]
            title = urllib.parse.unquote(title)
            return ingest_wikipedia(title=title or "アーヴ語", lang=lang or "ja")
        if "mule.s59.xrea.com" in parsed.netloc and "jisyo" in parsed.path:
            return ingest_mule_jisyo(target)
        if "dadh-baronr" in parsed.netloc:
            return ingest_dadh_ondic()
        return ingest_html_url(target)
    path = Path(target)
    if path.is_file():
        return ingest_file(path)
    raise FileNotFoundError(f"取り込み先が見つかりません: {target}")
