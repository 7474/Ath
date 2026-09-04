#!/usr/bin/env python3
"""Keyword retrieval over Baronh grammar cards and lexicon (RAG-like, no embeddings)."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KNOWLEDGE = ROOT / "knowledge"


def load_json(name: str):
    return json.loads((KNOWLEDGE / name).read_text(encoding="utf-8"))


def load_phonemes() -> dict:
    return load_json("phonemes.json")


def load_grammar() -> list[dict]:
    return load_json("grammar.json")


def load_lexicon() -> list[dict]:
    return load_json("lexicon.json")


_TOKEN = re.compile(r"[A-Za-zÀ-ÿœŒ0-9ぁ-んァ-ン一-龯ー]+")


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text or "")]


def _blob(item: dict) -> str:
    parts = []
    for key in ("id", "title", "text", "baronh", "ja", "en", "note", "pos"):
        val = item.get(key)
        if val:
            parts.append(str(val))
    tags = item.get("tags") or []
    parts.extend(str(t) for t in tags)
    return " ".join(parts).lower()


def _score(query_tokens: list[str], item: dict) -> int:
    blob = _blob(item)
    score = 0
    for tok in query_tokens:
        if not tok:
            continue
        if tok in blob:
            score += 3 if len(tok) >= 2 else 1
        # extra weight for exact baronh/ja headwords
        if tok == str(item.get("baronh") or "").lower():
            score += 8
        if tok == str(item.get("ja") or "").lower():
            score += 8
    return score


def search_grammar(query: str, *, limit: int = 4) -> list[dict]:
    tokens = _tokens(query)
    ranked = sorted(
        (( _score(tokens, card), card) for card in load_grammar()),
        key=lambda pair: pair[0],
        reverse=True,
    )
    return [card for score, card in ranked if score > 0][:limit]


def search_lexicon(query: str, *, limit: int = 8) -> list[dict]:
    tokens = _tokens(query)
    ranked = sorted(
        (( _score(tokens, entry), entry) for entry in load_lexicon()),
        key=lambda pair: pair[0],
        reverse=True,
    )
    return [entry for score, entry in ranked if score > 0][:limit]


def retrieve(query: str) -> dict:
    """Local retrieval to stuff into the first LLM turn (works without tool-calling)."""
    grammar = search_grammar(query) or search_grammar("概要 格 翻訳 音声")
    return {
        "grammar": grammar[:3],
        "lexicon": search_lexicon(query),
        "phonemes": load_phonemes()["keys"],
    }


def keys_to_ipa(ath_keys: str) -> str:
    table = sorted(load_phonemes()["keys"], key=lambda row: len(row["key"]), reverse=True)
    out: list[str] = []
    i = 0
    text = ath_keys or ""
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            out.append(" ")
            i += 1
            continue
        matched = None
        for row in table:
            key = row["key"]
            if text.startswith(key, i):
                matched = row
                break
        if matched:
            out.append(matched["ipa"])
            i += len(matched["key"])
        else:
            out.append(ch)
            i += 1
    return "".join(out)
