"""アーヴ語辞書の簡易ベクトル索引。

外部のベクトル DB は使わず、numpy のハッシュ n-gram 埋め込みと余弦類似度だけにする。
語釈・見出し・類義語ブリッジを同じ文書に載せ、生成 AI が search_lexicon で引けるようにする。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from baronh.grammar import conjugate, decline
from baronh.lexicon import Entry, Lexicon, _split_ja_aliases
from baronh.synonyms import PARAPHRASE_KEYS

VECTOR_DIM = 512
INDEX_HASH = "blake2b-8"
VECTORS_BIN = "vectors.bin"
VECTORS_JSON = "vectors.json"
_INDEX_CACHE: dict[int, "LexiconIndex"] = {}


@dataclass
class VectorHit:
    entry: Entry
    score: float
    document: str


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").casefold()).strip()


def _parts(text: str) -> list[str]:
    src = _fold(text)
    if not src:
        return []
    parts: list[str] = []
    seen: set[str] = set()
    for part in (src, *re.split(r"[\s/・,，、]+", src)):
        if not part or part in seen:
            continue
        seen.add(part)
        parts.append(part)
    return parts


def _ngrams(text: str) -> list[str]:
    """語単位で n-gram を切る。長い複合語の 1 文字（光 ⊂ 凝集光銃）は索引しない。"""
    grams: list[str] = []
    for part in _parts(text):
        grams.append(part)
        compact = part.replace(" ", "")
        min_size = 1 if len(compact) <= 2 else 2
        for size in range(min_size, 4):
            if len(compact) < size:
                continue
            grams.extend(compact[i : i + size] for i in range(len(compact) - size + 1))
    return grams


def _token_boost(query: str, document: str) -> float:
    q = _fold(query)
    if not q:
        return 0.0
    tokens = {part for part in re.split(r"[\s/・,，、]+", _fold(document)) if part}
    if q in tokens:
        return 1.0
    return 0.0


def embed_text(text: str, *, dim: int = VECTOR_DIM) -> np.ndarray:
    """文字 n-gram をハッシュして L2 正規化する。追加の埋め込みモデルは使わない。"""
    vec = np.zeros(dim, dtype=np.float32)
    for gram in _ngrams(text):
        digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(digest[:4], "little") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        weight = 1.0 + (digest[5] / 255.0)
        vec[idx] += sign * weight
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec /= norm
    return vec


def _bridge_terms(entry: Entry) -> list[str]:
    aliases = set(_split_ja_aliases(entry.gloss_ja))
    aliases.update(_split_ja_aliases(entry.gloss_en or ""))
    aliases.add(entry.lemma)
    aliases.add(entry.gloss_ja)
    terms: list[str] = []
    for query, keys in PARAPHRASE_KEYS.items():
        if any(key in aliases for key in keys):
            terms.append(query)
    return terms


def entry_document(entry: Entry) -> str:
    parts = [
        entry.lemma,
        entry.pos,
        entry.gloss_ja,
        entry.gloss_en or "",
        " ".join(_split_ja_aliases(entry.gloss_ja)),
        " ".join(_bridge_terms(entry)),
    ]
    return " ".join(part for part in parts if part)


def format_entry_line(entry: Entry, *, score: float | None = None) -> str:
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
    if score is not None:
        line += f" score={score:.3f}"
    return line


class LexiconIndex:
    def __init__(self, lexicon: Lexicon, *, dim: int = VECTOR_DIM):
        self.lexicon = lexicon
        self.dim = dim
        self.entries = list(lexicon.entries)
        self.documents = [entry_document(entry) for entry in self.entries]
        matrix = np.stack([embed_text(doc, dim=dim) for doc in self.documents], axis=0)
        self.matrix = matrix.astype(np.float32)

    def search(self, query: str, *, limit: int = 8, min_score: float = 0.08) -> list[VectorHit]:
        text = (query or "").strip()
        if not text or not self.entries:
            return []
        q = embed_text(text, dim=self.dim)
        cosine = self.matrix @ q
        boosts = np.array(
            [_token_boost(text, doc) for doc in self.documents],
            dtype=np.float32,
        )
        scores = cosine + boosts
        order = np.argsort(-scores)
        hits: list[VectorHit] = []
        seen: set[str] = set()
        for idx in order:
            score = float(scores[int(idx)])
            if score < min_score:
                break
            entry = self.entries[int(idx)]
            key = f"{entry.lemma}|{entry.pos}"
            if key in seen:
                continue
            seen.add(key)
            hits.append(VectorHit(entry=entry, score=score, document=self.documents[int(idx)]))
            if len(hits) >= limit:
                break
        return hits

    def search_many(self, queries: list[str], *, limit: int = 16, min_score: float = 0.08) -> list[VectorHit]:
        best: dict[str, VectorHit] = {}
        for query in queries:
            if not (query or "").strip():
                continue
            for hit in self.search(query, limit=limit, min_score=min_score):
                key = f"{hit.entry.lemma}|{hit.entry.pos}"
                prev = best.get(key)
                if prev is None or hit.score > prev.score:
                    best[key] = hit
        ranked = sorted(best.values(), key=lambda item: -item.score)
        return ranked[:limit]


def _entry_key(entry: Entry) -> str:
    return f"{entry.lemma}|{entry.pos}"


def write_index(lexicon: Lexicon, dest_dir: Path | str, *, dim: int = VECTOR_DIM) -> dict:
    """GitHub Actions / export-web がブラウザへ配る Flat 索引を書く。"""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    index = LexiconIndex(lexicon, dim=dim)
    matrix = np.ascontiguousarray(index.matrix, dtype=np.float32)
    (dest / VECTORS_BIN).write_bytes(matrix.tobytes())
    meta = {
        "dim": int(index.dim),
        "count": int(matrix.shape[0]),
        "hash": INDEX_HASH,
        "endian": "little",
        "keys": [_entry_key(entry) for entry in index.entries],
        "documents": index.documents,
    }
    (dest / VECTORS_JSON).write_text(json.dumps(meta, ensure_ascii=False) + "\n", encoding="utf-8")
    return meta


def load_index(lexicon: Lexicon, dest_dir: Path | str) -> LexiconIndex:
    """write_index の成果物を読み、辞書の現在のエントリに合わせて載せる。"""
    dest = Path(dest_dir)
    meta = json.loads((dest / VECTORS_JSON).read_text(encoding="utf-8"))
    dim = int(meta["dim"])
    count = int(meta["count"])
    raw = np.frombuffer((dest / VECTORS_BIN).read_bytes(), dtype=np.float32).copy()
    if raw.size != count * dim:
        raise ValueError(f"{VECTORS_BIN} の要素数 {raw.size} が count*dim={count * dim} と違う")
    if meta.get("hash") not in (None, INDEX_HASH):
        raise ValueError(f"未対応の埋め込み hash: {meta.get('hash')}")
    matrix_src = raw.reshape(count, dim)
    by_pre: dict[str, tuple[str, np.ndarray]] = {}
    for i, key in enumerate(meta["keys"]):
        by_pre[key] = (meta["documents"][i], matrix_src[i])
    entries = list(lexicon.entries)
    documents: list[str] = []
    rows: list[np.ndarray] = []
    for entry in entries:
        key = _entry_key(entry)
        doc = entry_document(entry)
        pre = by_pre.get(key)
        if pre is not None and pre[0] == doc:
            documents.append(pre[0])
            rows.append(pre[1])
        else:
            documents.append(doc)
            rows.append(embed_text(doc, dim=dim))
    index = LexiconIndex.__new__(LexiconIndex)
    index.lexicon = lexicon
    index.dim = dim
    index.entries = entries
    index.documents = documents
    index.matrix = np.stack(rows, axis=0).astype(np.float32) if rows else np.zeros((0, dim), dtype=np.float32)
    return index


def get_index(lexicon: Lexicon) -> LexiconIndex:
    key = id(lexicon)
    cached = _INDEX_CACHE.get(key)
    if cached is not None and cached.lexicon is lexicon and len(cached.entries) == len(lexicon.entries):
        return cached
    index = LexiconIndex(lexicon)
    _INDEX_CACHE[key] = index
    return index


def hit_to_dict(hit: VectorHit) -> dict[str, object]:
    return {
        "lemma": hit.entry.lemma,
        "pos": hit.entry.pos,
        "gloss_ja": hit.entry.gloss_ja,
        "gloss_en": hit.entry.gloss_en,
        "score": round(hit.score, 3),
        "line": format_entry_line(hit.entry, score=hit.score),
    }


def search_context(queries: list[str], lexicon: Lexicon, *, limit: int = 16) -> str:
    hits = get_index(lexicon).search_many(queries, limit=limit)
    if not hits:
        return "(ヒットなし。search_lexicon で追加検索してください)"
    return "\n".join(format_entry_line(hit.entry, score=hit.score) for hit in hits)
