"""アーヴ語 (Baronh) の辞書・文法・翻訳ライブラリ。"""

from __future__ import annotations

__version__ = "0.1.0"

from baronh.grammar import conjugate, decline, analyze_form
from baronh.lexicon import Lexicon, load_lexicon
from baronh.phonology import reading_ja, to_ath_keys
from baronh.translate import TranslationResult, translate

__all__ = [
    "Lexicon",
    "TranslationResult",
    "analyze_form",
    "conjugate",
    "decline",
    "load_lexicon",
    "reading_ja",
    "to_ath_keys",
    "translate",
    "__version__",
]
