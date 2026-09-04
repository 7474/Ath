"""辞書と文法規則によるアーヴ語⇄日本語/英語の翻訳。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from baronh.grammar import FormIndex, conjugate, decline, topic_contract
from baronh.lexicon import CASE_PARTICLE_JA, Entry, Lexicon, _split_ja_aliases
from baronh.phonology import (
    PHONETIC_NOTE,
    PHONETIC_SUMMARY,
    is_latin_name,
    looks_like_proper_noun,
    reading_ja,
    split_honorific,
    to_ath_keys,
    transcribe_baronh_to_kana,
    transcribe_proper_noun,
    normalize_baronh,
)

LANGS = ("baronh", "ja", "en")

JA_PARTICLES = {
    "から": "abl",
    "まで": "all",
    "より": "abl",
    "は": "topic",
    "が": "nom",
    "を": "acc",
    "の": "gen",
    "に": "dat",
    "へ": "all",
    "で": "ins",
    "と": "cite",
    "よ": "vocative",
    "か": "question",
    "も": "also",
}

# 先に食べる複音節。で/か より先に です/ます を切る。
JA_ATOMIC = (
    "から", "まで", "より", "である", "であります", "でした", "だった",
    "です", "だ",
)
JA_FINAL_ONLY = {"か", "よ", "ね"}

EN_PREP = {
    "of": "gen",
    "to": "dat",
    "toward": "all",
    "towards": "all",
    "into": "all",
    "from": "abl",
    "with": "ins",
    "by": "ins",
    "at": "all",
    "in": "all",
}

JA_COPULA_RE = re.compile(r"(です|だ|である|であります)(か)?$")
JA_QUESTION_RE = re.compile(r"[か？?]$")
JA_COPULA = {"です", "だ", "である", "であります", "でした", "だった"}


@dataclass
class TokenGloss:
    source: str
    target: str
    note: str = ""


@dataclass
class TranslationResult:
    source_lang: str
    target_lang: str
    source_text: str
    text: str
    engine: str = "local"
    ath_keys: str = ""
    reading_ja: str = ""
    analysis: list[TokenGloss] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    substitutions: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source_lang": self.source_lang,
            "target_lang": self.target_lang,
            "source_text": self.source_text,
            "text": self.text,
            "engine": self.engine,
            "ath_keys": self.ath_keys,
            "reading_ja": self.reading_ja,
            "analysis": [item.__dict__ for item in self.analysis],
            "notes": self.notes,
            "unknown": self.unknown,
            "substitutions": self.substitutions,
        }


def detect_lang(text: str, lexicon: Lexicon | None = None) -> str:
    stripped = text.strip()
    if not stripped:
        return "ja"
    if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", stripped):
        return "ja"
    tokens = _tokenize_baronh(stripped)
    if lexicon is not None:
        index = FormIndex(lexicon)
        hits = sum(1 for tok in tokens if index.lookup(tok.rstrip(".,!?;:")))
        if tokens and hits / max(len(tokens), 1) >= 0.4:
            return "baronh"
    if re.search(r"[éïüÿœÉÏÜŸŒ]|'", stripped):
        return "baronh"
    if re.search(r"\b(the|is|are|you|i|we|they|this|that)\b", stripped, re.I):
        return "en"
    return "baronh"


def _tokenize_baronh(text: str) -> list[str]:
    text = normalize_baronh(text)
    text = text.replace("’", "'")
    return [part for part in re.findall(r"[A-Za-zÉéÏïÜüŸÿŒœ']+|[^\s]", text) if not part.isspace()]


def _tokenize_en(text: str) -> list[str]:
    return re.findall(r"[A-Za-z']+|[0-9]+|[^\s\w]", text)


def _is_ja_boundary_marker(src: str, index: int) -> str | None:
    if index >= len(src):
        return None
    for atom in JA_ATOMIC:
        if src.startswith(atom, index):
            return atom
    for particle in sorted(JA_PARTICLES, key=len, reverse=True):
        if not src.startswith(particle, index):
            continue
        after = index + len(particle)
        if particle in JA_FINAL_ONLY:
            rest = src[after:]
            if rest == "" or rest[0] in "、。！？!?., \t":
                return particle
            continue
        return particle
    return None


def _ja_match_phrases(lexicon: Lexicon | None) -> list[str]:
    if lexicon is None:
        return []
    skip = set(JA_PARTICLES) | set(JA_ATOMIC)
    phrases: set[str] = set()
    for entry in lexicon.entries:
        for alias in _split_ja_aliases(entry.gloss_ja):
            text = alias.strip()
            if len(text) < 2 or text in skip:
                continue
            phrases.add(text)
    return sorted(phrases, key=len, reverse=True)


def _longest_ja_phrase(src: str, index: int, phrases: list[str]) -> str | None:
    for phrase in phrases:
        if src.startswith(phrase, index):
            return phrase
    return None


def _tokenize_ja(text: str, lexicon: Lexicon | None = None) -> list[str]:
    tokens: list[str] = []
    i = 0
    src = text.strip()
    phrases = _ja_match_phrases(lexicon)
    while i < len(src):
        ch = src[i]
        if ch.isspace():
            i += 1
            continue
        if ch in "、。！？!?.,":
            tokens.append(ch)
            i += 1
            continue
        particle = _is_ja_boundary_marker(src, i)
        phrase = _longest_ja_phrase(src, i, phrases)
        if particle and (phrase is None or len(phrase) <= len(particle)):
            tokens.append(particle)
            i += len(particle)
            continue
        j = i + 1
        while j < len(src) and not src[j].isspace() and src[j] not in "、。！？!?.,":
            if _is_ja_boundary_marker(src, j):
                break
            j += 1
        leftover = src[i:j]
        if phrase and len(phrase) > len(leftover):
            tokens.append(phrase)
            i += len(phrase)
            continue
        if leftover:
            tokens.append(leftover)
            i = j
            continue
        if phrase:
            tokens.append(phrase)
            i += len(phrase)
            continue
        tokens.append(src[i])
        i += 1
    return tokens


def _verb_features_ja(word: str) -> tuple[str, str, list[str], str]:
    """日本語動詞っぽい語尾から法・相・態を取る。戻り値: (語幹候補, mood, voices, aspect)."""
    voices: list[str] = []
    mood = "indicative"
    aspect = "indefinite"
    core = word
    if core.endswith("か"):
        core = core[:-1]
    for suffix, feat in (
        ("させられない", ("causative", "passive", "negative")),
        ("させない", ("causative", "negative")),
        ("されない", ("passive", "negative")),
        ("させる", ("causative",)),
        ("される", ("passive",)),
        ("しない", ("negative",)),
        ("ない", ("negative",)),
        ("ません", ("negative",)),
    ):
        if core.endswith(suffix):
            voices.extend(feat)
            core = core[: -len(suffix)] + ("する" if suffix in {"しない", "ません"} else "")
            break
    if core.endswith(("している", "しています", "つつある")):
        aspect = "progressive"
        core = re.sub(r"(している|しています|つつある)$", "", core)
    elif core.endswith(("した", "しました", "た")):
        aspect = "perfect"
        core = re.sub(r"(しました|した|た)$", "", core)
    elif core.endswith(("だろう", "でしょう", "う")):
        aspect = "prospective"
        core = re.sub(r"(でしょう|だろう)$", "", core)
    elif core.endswith(("しろ", "せよ", "ください")):
        mood = "imperative"
        core = re.sub(r"(してください|ください|しろ|せよ)$", "", core)
    elif core.endswith(("すれば", "なら", "ならば")):
        mood = "subjunctive"
        core = re.sub(r"(すれば|ならば|なら)$", "", core)
    core = re.sub(r"(します|する|です|だ)$", "", core)
    return core or word, mood, voices, aspect


def _lookup_ja(lexicon: Lexicon, word: str) -> list[Entry]:
    if word.endswith("します") or word.endswith("する"):
        as_suru = word[:-3] + "する" if word.endswith("します") else word
        suru_hits = [e for e in lexicon.lookup(as_suru, lang="ja") if e.pos == "verb"]
        if suru_hits:
            return suru_hits
        stem_hits = [e for e in lexicon.lookup(word[:-3] if word.endswith("します") else word[:-2], lang="ja") if e.pos == "verb"]
        if stem_hits:
            return stem_hits
    direct = lexicon.lookup(word, lang="ja")
    if direct:
        return direct
    stem, *_ = _verb_features_ja(word)
    if stem != word:
        found = lexicon.lookup(stem, lang="ja")
        if found:
            return found
    candidates = [word]
    if word.endswith("ます") and len(word) > 2:
        i_stem = word[:-2]
        godan = i_stem[:-1] + i_stem[-1].translate(str.maketrans("きぎしちにびみり", "くぐすつぬぶむる")) if i_stem else i_stem
        candidates.extend([i_stem + "る", godan, i_stem])
    for suffix in ("します", "しました", "する", "した", "です", "だ", "たち"):
        if word.endswith(suffix) and len(word) > len(suffix):
            candidates.append(word[: -len(suffix)])
    seen: set[str] = set()
    for cand in candidates:
        if not cand or cand in seen:
            continue
        seen.add(cand)
        found = lexicon.lookup(cand, lang="ja")
        if found:
            return found
    return []


def _phonetic_noun_entry(source: str, lemma: str, declension: str = "") -> Entry:
    return Entry(
        lemma=lemma,
        pos="noun",
        gloss_ja=source,
        gloss_en=source,
        declension=declension,
        tags=["phonetic", "proper"],
        notes=PHONETIC_NOTE,
        source="phonetic",
    )


def _try_phonetic_noun(tok: str, nxt: str) -> Entry | None:
    if not looks_like_proper_noun(tok, nxt=nxt, copula=nxt in JA_COPULA):
        return None
    core, _hon = split_honorific(tok)
    lemma, declension = transcribe_proper_noun(core)
    if not lemma:
        return None
    return _phonetic_noun_entry(tok, lemma, declension)


def _apply_case(entry: Entry, case: str) -> str:
    if entry.pos in {"noun", "pronoun"} and case in CASE_PARTICLE_JA:
        return decline(entry)[case]
    return entry.lemma


def _translate_ja_to_baronh(text: str, lexicon: Lexicon) -> TranslationResult:
    tokens = _tokenize_ja(text, lexicon)
    question = bool(JA_QUESTION_RE.search(text.strip())) or "か" in tokens
    vocative = "よ" in tokens
    pieces: list[str] = []
    analysis: list[TokenGloss] = []
    unknown: list[str] = []
    phonetic_pairs: list[str] = []
    pending_noun: Entry | None = None
    pending_src = ""
    used_topic = False

    def flush_noun(case: str, extra: str = "") -> None:
        nonlocal pending_noun, pending_src, used_topic
        if pending_noun is None:
            return
        phonetic = "phonetic" in pending_noun.tags
        mark = f" / {PHONETIC_NOTE}" if phonetic else ""
        if case == "topic":
            form = decline(pending_noun)["nom"] if pending_noun.pos in {"noun", "pronoun"} else pending_noun.lemma
            if pending_noun.pos == "pronoun":
                surface = topic_contract(form)
                used_topic = True
            else:
                surface = form + " a"
                used_topic = True
            pieces.append(surface)
            analysis.append(TokenGloss(pending_src + "は", surface, "主題" + mark))
        elif case == "vocative":
            form = decline(pending_noun)["nom"] if pending_noun.pos in {"noun", "pronoun"} else pending_noun.lemma
            surface = f"{form} éü"
            pieces.append(surface)
            analysis.append(TokenGloss(pending_src + "よ", surface, "呼びかけ" + mark))
        elif case == "cite":
            form = decline(pending_noun)["acc"] if pending_noun.pos in {"noun", "pronoun"} else pending_noun.lemma
            pieces.append(form)
            analysis.append(TokenGloss(pending_src, form, (extra or "引用対象") + mark))
        else:
            form = _apply_case(pending_noun, case if case in CASE_PARTICLE_JA else "nom")
            pieces.append(form)
            analysis.append(TokenGloss(pending_src, form, (extra or CASE_PARTICLE_JA.get(case, "")) + mark))
        pending_noun = None
        pending_src = ""

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in "、。！？!?.,":
            i += 1
            continue
        if tok in {"です", "だ", "である", "であります", "でした", "だった"}:
            if pending_noun is not None:
                flush_noun("ins")
            i += 1
            continue
        if tok in JA_PARTICLES:
            role = JA_PARTICLES[tok]
            if pending_noun is not None:
                flush_noun(role)
            elif role == "question":
                question = True
            elif role == "vocative":
                vocative = True
            i += 1
            continue
        entries = _lookup_ja(lexicon, tok)
        if not entries:
            core, hon = split_honorific(tok)
            if hon:
                entries = _lookup_ja(lexicon, core)
        if not entries:
            nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
            phonetic = _try_phonetic_noun(tok, nxt)
            if phonetic:
                phonetic_pairs.append(f"{tok}→{phonetic.lemma}")
                pending_noun = phonetic
                pending_src = tok
                i += 1
                continue
            unknown.append(tok)
            pieces.append(tok)
            analysis.append(TokenGloss(tok, tok, "未登録"))
            i += 1
            continue
        # 助詞が後続する名詞を優先
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        nounish = next((e for e in entries if e.pos in {"noun", "pronoun", "adjective"}), None)
        verbish = next((e for e in entries if e.pos == "verb"), None)
        interj = next((e for e in entries if e.pos in {"interjection", "adverb", "postposition"}), None)
        if nounish and nxt in JA_PARTICLES:
            pending_noun = nounish
            pending_src = tok
            i += 1
            continue
        if verbish and (nxt in JA_PARTICLES or nxt in {"", "。", "！", "？", "!", "?"} or i == len(tokens) - 1 or nxt in JA_PARTICLES):
            flush_noun("nom")
            _stem, mood, voices, aspect = _verb_features_ja(tok)
            form = conjugate(verbish, mood=mood, aspect=aspect, voices=voices)
            pieces.append(form)
            analysis.append(TokenGloss(tok, form, verbish.gloss_ja))
            i += 1
            continue
        if interj and nxt not in JA_PARTICLES:
            pieces.append(interj.lemma)
            analysis.append(TokenGloss(tok, interj.lemma, interj.pos))
            i += 1
            continue
        if nounish:
            pending_noun = nounish
            pending_src = tok
            i += 1
            continue
        if verbish:
            _stem, mood, voices, aspect = _verb_features_ja(tok)
            form = conjugate(verbish, mood=mood, aspect=aspect, voices=voices)
            pieces.append(form)
            analysis.append(TokenGloss(tok, form, verbish.gloss_ja))
            i += 1
            continue
        if interj:
            pieces.append(interj.lemma)
            analysis.append(TokenGloss(tok, interj.lemma, interj.pos))
            i += 1
            continue
        unknown.append(tok)
        i += 1

    if pending_noun is not None:
        # 「AはBです」の B は具格
        if JA_COPULA_RE.search(text.strip()) or text.strip().endswith(("です", "だ", "である")):
            flush_noun("ins")
        elif vocative:
            flush_noun("vocative")
        else:
            flush_noun("nom")

    # コピュラ省略: 「私はアーヴです」→ F'a bale
    # 明示的な「である」がある場合は ane を残す
    if any(t in text for t in ("です", "だ", "である")) and not any(
        item.target.startswith("an") and "である" in (item.note or "") for item in analysis
    ):
        # 具格補語があれば ane は省略してよい（F'a bale）
        pass

    if question and not any(p.endswith("sa") or p == "sa" for p in pieces):
        pieces.append("sa")
        analysis.append(TokenGloss("か", "sa", "疑問"))
    if vocative and not any("éü" in p for p in pieces):
        if pieces:
            pieces[-1] = pieces[-1] + " éü"

    surface = " ".join(p for p in pieces if p)
    if surface and not surface.endswith((".", "!", "?")) and question:
        surface = surface.rstrip() + "?"
    elif surface and not surface.endswith((".", "!", "?")):
        surface = surface + "."
    notes = []
    if phonetic_pairs:
        notes.append(PHONETIC_SUMMARY + " " + "、".join(phonetic_pairs) + "。")
    if unknown:
        notes.append("未登録の語は原文のまま残しています。ingest で辞書を足せます。")
    return TranslationResult(
        source_lang="ja",
        target_lang="baronh",
        source_text=text,
        text=surface,
        ath_keys=to_ath_keys(surface),
        reading_ja=reading_ja(surface),
        analysis=analysis,
        notes=notes,
        unknown=unknown,
    )


def _translate_en_to_baronh(text: str, lexicon: Lexicon) -> TranslationResult:
    tokens = _tokenize_en(text)
    question = text.strip().endswith("?") or (tokens and tokens[0].lower() in {"is", "are", "do", "does", "can"})
    pieces: list[str] = []
    analysis: list[TokenGloss] = []
    unknown: list[str] = []
    phonetic_pairs: list[str] = []
    pending: Entry | None = None
    pending_src = ""
    skip_next_prep = False

    def flush(case: str) -> None:
        nonlocal pending, pending_src
        if pending is None:
            return
        form = _apply_case(pending, case if case in CASE_PARTICLE_JA else "nom")
        if case == "topic" and pending.pos == "pronoun":
            form = topic_contract(decline(pending)["nom"])
        mark = f" / {PHONETIC_NOTE}" if "phonetic" in pending.tags else ""
        pieces.append(form)
        analysis.append(TokenGloss(pending_src, form, case + mark))
        pending = None
        pending_src = ""

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        low = tok.lower()
        if low in {",", ".", "!", "?", "the", "a", "an"}:
            i += 1
            continue
        if low in EN_PREP:
            flush(EN_PREP[low])
            skip_next_prep = False
            i += 1
            continue
        entries = lexicon.lookup(low, lang="en")
        if not entries and low.endswith("s"):
            entries = lexicon.lookup(low[:-1], lang="en")
        if not entries:
            if is_latin_name(tok, require_capital=True):
                lemma, declension = transcribe_proper_noun(tok)
                phonetic = _phonetic_noun_entry(tok, lemma, declension)
                phonetic_pairs.append(f"{tok}→{lemma}")
                pending = phonetic
                pending_src = tok
                i += 1
                continue
            unknown.append(tok)
            pieces.append(tok)
            analysis.append(TokenGloss(tok, tok, "unknown"))
            i += 1
            continue
        nxt = tokens[i + 1].lower() if i + 1 < len(tokens) else ""
        nounish = next((e for e in entries if e.pos in {"noun", "pronoun"}), None)
        verbish = next((e for e in entries if e.pos == "verb"), None)
        if nounish and nxt in EN_PREP:
            pending = nounish
            pending_src = tok
            i += 1
            continue
        if nounish and nxt in {"is", "am", "are"}:
            pending = nounish
            pending_src = tok
            i += 1
            continue
        if low in {"is", "am", "are", "was", "were", "be"}:
            # 次の補語を具格に
            if pending is not None:
                flush("topic")
            i += 1
            continue
        if verbish:
            flush("nom")
            aspect = "indefinite"
            mood = "indicative"
            voices: list[str] = []
            if low.endswith("ed") or low in {"was", "were"}:
                aspect = "perfect"
            if low.endswith("ing"):
                aspect = "progressive"
            form = conjugate(verbish, mood=mood, aspect=aspect, voices=voices)
            pieces.append(form)
            analysis.append(TokenGloss(tok, form, verbish.gloss_en))
            i += 1
            continue
        if nounish:
            pending = nounish
            pending_src = tok
            i += 1
            continue
        pieces.append(entries[0].lemma)
        analysis.append(TokenGloss(tok, entries[0].lemma, entries[0].pos))
        i += 1
        _ = skip_next_prep

    if pending is not None:
        if any(t.lower() in {"is", "am", "are"} for t in tokens):
            flush("ins")
        else:
            flush("nom")
    if question:
        pieces.append("sa")
    surface = " ".join(p for p in pieces if p)
    if surface and not surface.endswith((".", "!", "?")):
        surface += "?" if question else "."
    return TranslationResult(
        source_lang="en",
        target_lang="baronh",
        source_text=text,
        text=surface,
        ath_keys=to_ath_keys(surface),
        reading_ja=reading_ja(surface),
        analysis=analysis,
        notes=[item for item in [
            (PHONETIC_SUMMARY + " " + "、".join(phonetic_pairs) + "。") if phonetic_pairs else "",
            "英語は語順の解析が粗いため、短い句向けです。" if unknown else "",
        ] if item],
        unknown=unknown,
    )


def _translate_baronh_out(text: str, lexicon: Lexicon, target: str) -> TranslationResult:
    index = FormIndex(lexicon)
    tokens = _tokenize_baronh(text)
    pieces: list[str] = []
    analysis: list[TokenGloss] = []
    unknown: list[str] = []
    phonetic_pairs: list[str] = []
    question = False
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in {".", ",", "!", "?"}:
            if tok in {"?", "？"}:
                question = True
            i += 1
            continue
        extras: list[str] = []
        surface = tok
        if tok.endswith("a") and "'" in tok:
            extras.append("topic")
            surface = tok.split("'")[0] + "e"  # F'a → Fe
            if surface.lower() == "fe":
                pass
            # F'a: F + a → fe
            letter = tok[0].lower()
            surface = {"f": "fe", "d": "de", "s": "se"}.get(letter, surface)
        if tok.lower() == "sa":
            question = True
            analysis.append(TokenGloss(tok, "か" if target == "ja" else "?", "question"))
            i += 1
            continue
        if tok.lower() in {"éü", "eu"}:
            pieces.append("よ" if target == "ja" else "O")
            analysis.append(TokenGloss(tok, "よ" if target == "ja" else "O", "vocative"))
            i += 1
            continue
        hits = index.lookup(surface)
        if not hits and tok.endswith("'a"):
            hits = index.lookup({"f": "fe", "d": "de", "s": "se"}.get(tok[0].lower(), tok))
            extras.append("topic")
        if not hits:
            if is_latin_name(tok, require_capital=False) or re.fullmatch(
                r"[A-Za-zÉéÏïÜüŸÿŒœ][A-Za-zÉéÏïÜüŸÿŒœ''\-]*", tok
            ):
                if target == "ja":
                    kana = transcribe_baronh_to_kana(tok)
                    pieces.append(kana)
                    analysis.append(TokenGloss(tok, kana, PHONETIC_NOTE))
                    phonetic_pairs.append(f"{tok}→{kana}")
                else:
                    pieces.append(tok)
                    analysis.append(TokenGloss(tok, tok, PHONETIC_NOTE))
                    phonetic_pairs.append(tok)
                i += 1
                continue
            unknown.append(tok)
            pieces.append(tok)
            analysis.append(TokenGloss(tok, tok, "unknown"))
            i += 1
            continue
        hit = hits[0]
        if target == "ja":
            word = hit.entry.gloss_ja.split("/")[0]
            if extras == ["topic"]:
                word += "は"
            elif hit.case:
                word += CASE_PARTICLE_JA.get(hit.case, "")
            if hit.mood == "imperative":
                word += "（命令）"
            elif hit.aspect == "perfect":
                word += "した"
            elif hit.aspect == "progressive":
                word += "している"
            elif hit.voices:
                if "negative" in hit.voices:
                    word += "ない"
                if "causative" in hit.voices:
                    word += "（使役）"
                if "passive" in hit.voices:
                    word += "（受動）"
        else:
            word = hit.entry.gloss_en.split("/")[0]
            if extras == ["topic"]:
                word = word + " (topic)"
            elif hit.case:
                word = f"{word}[{hit.case}]"
        pieces.append(word)
        analysis.append(TokenGloss(tok, word, hit.summary_ja()))
        i += 1

    if question:
        pieces.append("か" if target == "ja" else "?")
    surface = "".join(pieces) if target == "ja" else " ".join(pieces)
    if target == "ja":
        surface = surface.replace("はが", "は")
        if question and not surface.endswith(("か", "？")):
            surface += "か"
        if surface and not surface.endswith(("。", "？", "！", "か")):
            surface += "。"
    return TranslationResult(
        source_lang="baronh",
        target_lang=target,
        source_text=text,
        text=surface,
        ath_keys=to_ath_keys(text),
        reading_ja=reading_ja(text),
        analysis=analysis,
        notes=[item for item in [
            "規則ベースの直訳です。語順は原文に近い語釈の連結です。",
            (PHONETIC_SUMMARY + " " + "、".join(phonetic_pairs) + "。") if phonetic_pairs else "",
        ] if item],
        unknown=unknown,
    )


def translate(
    text: str,
    lexicon: Lexicon,
    *,
    source_lang: str = "auto",
    target_lang: str = "auto",
) -> TranslationResult:
    text = text.strip()
    src = detect_lang(text, lexicon) if source_lang in {"", "auto"} else source_lang
    if src not in LANGS:
        raise ValueError(f"unsupported source language: {src}")
    if target_lang in {"", "auto"}:
        tgt = "ja" if src == "baronh" else "baronh"
    else:
        tgt = target_lang
    if tgt not in LANGS:
        raise ValueError(f"unsupported target language: {tgt}")
    if src == tgt:
        result = TranslationResult(src, tgt, text, text, ath_keys=to_ath_keys(text), reading_ja=reading_ja(text) if src == "baronh" else "")
        return result
    if src == "ja" and tgt == "baronh":
        return _translate_ja_to_baronh(text, lexicon)
    if src == "en" and tgt == "baronh":
        return _translate_en_to_baronh(text, lexicon)
    if src == "baronh" and tgt in {"ja", "en"}:
        return _translate_baronh_out(text, lexicon, tgt)
    # ja↔en は辞書グロッスの橋渡し
    if src == "ja" and tgt == "en":
        mid = _translate_ja_to_baronh(text, lexicon)
        back = _translate_baronh_out(mid.text, lexicon, "en")
        back.source_lang = "ja"
        back.source_text = text
        back.notes.append("日本語→アーヴ語→英語の二段翻訳です。")
        return back
    if src == "en" and tgt == "ja":
        mid = _translate_en_to_baronh(text, lexicon)
        back = _translate_baronh_out(mid.text, lexicon, "ja")
        back.source_lang = "en"
        back.source_text = text
        back.notes.append("英語→アーヴ語→日本語の二段翻訳です。")
        return back
    raise ValueError(f"no local route for {src}->{tgt}")
