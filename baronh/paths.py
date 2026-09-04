"""リポジトリ内のパス解決。"""

from __future__ import annotations

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT_DIR = PACKAGE_DIR.parent
DATA_DIR = ROOT_DIR / "data"
WEB_DIR = ROOT_DIR / "web"
SEED_LEXICON_PATH = DATA_DIR / "lexicon.json"
USER_LEXICON_PATH = DATA_DIR / "user_lexicon.json"


def default_lexicon_paths() -> list[Path]:
    paths = [SEED_LEXICON_PATH, USER_LEXICON_PATH]
    home_overlay = Path.home() / ".config" / "ath-translate" / "lexicon.json"
    paths.append(home_overlay)
    return paths
