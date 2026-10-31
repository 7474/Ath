"""音声合成。ローカルは読み上げエンジン、任意で OpenAI TTS。"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from baronh.g2p import speakable_for_pack
from baronh.langpack import LanguagePack
from baronh.phonology import reading_ja, speakable_text


@dataclass
class SpeechResult:
    engine: str
    spoken_text: str
    audio_path: str | None = None
    command: list[str] | None = None
    note: str = ""


def _espeak_cmd() -> str | None:
    return shutil.which("espeak-ng") or shutil.which("espeak")


def synthesize_local(
    text: str,
    *,
    lang: str = "baronh",
    output: Path | None = None,
    play: bool = False,
    pack: LanguagePack | None = None,
) -> SpeechResult:
    spoken = speakable_for_pack(text, pack, lang) if pack is not None else speakable_text(text, lang)
    espeak = _espeak_cmd()
    if espeak:
        voice = "en" if lang == "en" else "ja"
        cmd = [espeak, "-v", voice, spoken]
        if output:
            wav = output.with_suffix(".wav") if output.suffix.lower() not in {".wav"} else output
            cmd.extend(["-w", str(wav)])
            subprocess.run(cmd, check=True)
            return SpeechResult("espeak", spoken, audio_path=str(wav), command=cmd)
        if play:
            subprocess.run(cmd, check=True)
            return SpeechResult("espeak", spoken, command=cmd, note="再生しました")
        # 音声ファイルなしでも読みを返す
        return SpeechResult("espeak", spoken, command=cmd, note="--play または --out で音声化できます")
    if play:
        raise RuntimeError("ローカル TTS には espeak-ng が必要です。OpenAI TTS を使うか、読みだけを利用してください。")
    if output:
        output.write_text(spoken + "\n", encoding="utf-8")
        return SpeechResult(
            "reading",
            spoken,
            audio_path=str(output),
            note="espeak-ng が無いため読み仮名テキストを書きました",
        )
    return SpeechResult("reading", spoken, note="espeak-ng 未検出。読み仮名のみです")


def print_reading(text: str, lang: str = "baronh", file=None) -> str:
    spoken = speakable_text(text, lang)
    stream = file or sys.stdout
    print(spoken, file=stream)
    return spoken


def baronh_reading(text: str) -> str:
    return reading_ja(text)
