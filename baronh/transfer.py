"""言語パックによる転移翻訳（日本語/英語 ⇄ 目標言語）。

日本語・英語を格役割のスロット列に落とし、パックの形態・統語で表層化する。
アーヴ語の本番経路（translate.py）は置き換えない。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from baronh.g2p import g2p_reading_ja
from baronh.grammar import FormAnalysis, FormIndex
from baronh.langpack import (
    LanguagePack,
    apply_case,
    conjugate_entry,
    decline_entry,
    topic_form,
    uses_builtin_engine,
    vocative_form,
)
from baronh.lexicon import Entry, Lexicon
from baronh.translate import (
    EN_PREP,
    JA_COPULA,
    JA_COPULA_RE,
    JA_PARTICLES,
    JA_QUESTION_RE,
    LANGS,
    TokenGloss,
    TranslationResult,
    _lookup_ja,
    _tokenize_en,
    _tokenize_ja,
    _verb_features_ja,
    detect_lang as detect_pivot_lang,
    translate as translate_builtin,
)

LATIN_TOKEN_RE = re.compile(r"[A-Za-zÉéÏïÜüŸÿŒœ']+|[^\s]")


@dataclass
class Slot:
    source: str
    role: str
    entry: Entry | None = None
    mood: str = "indicative"
    aspect: str = "indefinite"
    voices: tuple[str, ...] = ()
    extra: str = ""


@dataclass
class PackFormIndex:
    pack: LanguagePack
    lexicon: Lexicon
    _exact: dict[str, list[FormAnalysis]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self._exact:
            self._rebuild()

    def _add(self, analysis: FormAnalysis) -> None:
        key = (analysis.form or "").casefold()
        self._exact.setdefault(key, []).append(analysis)

    def _rebuild(self) -> None:
        self._exact.clear()
        for entry in self.lexicon.entries:
            if entry.pos in {"noun", "pronoun"}:
                for case, form in decline_entry(entry, self.pack).items():
                    self._add(FormAnalysis(form, entry, entry.pos, case=case))
                self._add(
                    FormAnalysis(
                        topic_form(entry, self.pack),
                        entry,
                        entry.pos,
                        extras=["topic"],
                    )
                )
            elif entry.pos == "verb":
                self._add(FormAnalysis(entry.lemma, entry, "verb", mood="indicative", aspect="indefinite"))
                if entry.stem and entry.stem != entry.lemma:
                    self._add(FormAnalysis(entry.stem, entry, "verb-stem"))
                from baronh.langpack import all_verb_forms_pack

                for mood, aspect, voices, form in all_verb_forms_pack(entry, self.pack):
                    self._add(FormAnalysis(form, entry, "verb", mood=mood, aspect=aspect, voices=voices))
            else:
                self._add(FormAnalysis(entry.lemma, entry, entry.pos))
        for form in self.pack.closed_forms:
            dummy = Entry(lemma=form, pos="particle", gloss_ja=form, gloss_en=form)
            self._add(FormAnalysis(form, dummy, "particle"))

    def lookup(self, form: str) -> list[FormAnalysis]:
        return list(self._exact.get((form or "").casefold(), []))


def form_index_for(pack: LanguagePack, lexicon: Lexicon) -> FormIndex | PackFormIndex:
    if uses_builtin_engine(pack):
        return FormIndex(lexicon)
    return PackFormIndex(pack, lexicon)


def _tokenize_pack(text: str) -> list[str]:
    return [part for part in LATIN_TOKEN_RE.findall(text) if not part.isspace()]


def detect_pack_lang(text: str, packs: list[LanguagePack]) -> str | None:
    """ラテン文がどのパックの語形に近いか。"""
    tokens = _tokenize_pack(text)
    if not tokens:
        return None
    best_id = None
    best_ratio = 0.0
    for pack in packs:
        try:
            lexicon = pack.load_lexicon()
        except Exception:
            continue
        index = form_index_for(pack, lexicon)
        hits = 0
        for tok in tokens:
            form = tok.rstrip(".,!?;:")
            if not form:
                continue
            if index.lookup(form) or form.casefold() in {
                pack.syntax.topic.particle.casefold(),
                pack.syntax.question.particle.casefold(),
                pack.syntax.vocative.particle.casefold(),
            }:
                hits += 1
        ratio = hits / max(len(tokens), 1)
        if ratio > best_ratio:
            best_ratio = ratio
            best_id = pack.id
    if best_ratio >= 0.4:
        return best_id
    return None


def _ja_particles(pack: LanguagePack) -> dict[str, str]:
    mapping = dict(JA_PARTICLES)
    mapping.update(pack.syntax.ja_particles)
    return mapping


def _en_prep(pack: LanguagePack) -> dict[str, str]:
    mapping = dict(EN_PREP)
    mapping.update(pack.syntax.en_prep)
    return mapping


def analyze_ja(text: str, lexicon: Lexicon, pack: LanguagePack) -> tuple[list[Slot], list[str]]:
    tokens = _tokenize_ja(text, lexicon)
    particles = _ja_particles(pack)
    question = bool(JA_QUESTION_RE.search(text.strip())) or "か" in tokens
    vocative = "よ" in tokens
    slots: list[Slot] = []
    unknown: list[str] = []
    pending: Entry | None = None
    pending_src = ""

    def flush(role: str) -> None:
        nonlocal pending, pending_src
        if pending is None:
            return
        slots.append(Slot(pending_src, role, pending))
        pending = None
        pending_src = ""

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in "、。！？!?.,":
            i += 1
            continue
        if tok in JA_COPULA:
            if pending is not None:
                flush("ins")
            i += 1
            continue
        if tok in particles:
            role = particles[tok]
            if pending is not None:
                flush(role)
            elif role == "question":
                question = True
            elif role == "vocative":
                vocative = True
            i += 1
            continue
        entries = _lookup_ja(lexicon, tok)
        if not entries:
            unknown.append(tok)
            slots.append(Slot(tok, "unknown"))
            i += 1
            continue
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        nounish = next((e for e in entries if e.pos in {"noun", "pronoun", "adjective"}), None)
        verbish = next((e for e in entries if e.pos == "verb"), None)
        other = next((e for e in entries if e.pos in {"interjection", "adverb", "postposition"}), None)
        if nounish and nxt in particles:
            pending = nounish
            pending_src = tok
            i += 1
            continue
        if verbish:
            flush("nom")
            _stem, mood, voices, aspect = _verb_features_ja(tok)
            slots.append(Slot(tok, "verb", verbish, mood=mood, aspect=aspect, voices=tuple(voices)))
            i += 1
            continue
        if other and nxt not in particles:
            slots.append(Slot(tok, other.pos, other))
            i += 1
            continue
        if nounish:
            pending = nounish
            pending_src = tok
            i += 1
            continue
        unknown.append(tok)
        i += 1

    if pending is not None:
        if JA_COPULA_RE.search(text.strip()) or text.strip().endswith(("です", "だ", "である")):
            flush("ins")
        elif vocative:
            flush("vocative")
        else:
            flush("nom")
    if question and not any(s.role == "question" for s in slots):
        slots.append(Slot("か", "question"))
    if vocative and not any(s.role == "vocative" for s in slots):
        if slots:
            last = slots[-1]
            if last.role in {"nom", "ins"} and last.entry is not None:
                last.role = "vocative"
    return slots, unknown


def analyze_en(text: str, lexicon: Lexicon, pack: LanguagePack) -> tuple[list[Slot], list[str]]:
    tokens = _tokenize_en(text)
    prep = _en_prep(pack)
    question = text.strip().endswith("?") or (tokens and tokens[0].lower() in {"is", "are", "do", "does", "can"})
    slots: list[Slot] = []
    unknown: list[str] = []
    pending: Entry | None = None
    pending_src = ""
    seen_verb = False

    def flush(role: str) -> None:
        nonlocal pending, pending_src
        if pending is None:
            return
        slots.append(Slot(pending_src, role, pending))
        pending = None
        pending_src = ""

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        low = tok.lower()
        if low in {",", ".", "!", "?", "the", "a", "an"}:
            i += 1
            continue
        if low in prep:
            flush(prep[low])
            i += 1
            continue
        entries = lexicon.lookup(low, lang="en")
        if not entries and low.endswith("s"):
            entries = lexicon.lookup(low[:-1], lang="en")
        if not entries:
            unknown.append(tok)
            slots.append(Slot(tok, "unknown"))
            i += 1
            continue
        nxt = tokens[i + 1].lower() if i + 1 < len(tokens) else ""
        nounish = next((e for e in entries if e.pos in {"noun", "pronoun"}), None)
        verbish = next((e for e in entries if e.pos == "verb"), None)
        if nounish and nxt in prep:
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
            if pending is not None:
                flush("topic")
            i += 1
            continue
        if verbish:
            flush("nom")
            seen_verb = True
            aspect = "indefinite"
            if low.endswith("ed"):
                aspect = "perfect"
            if low.endswith("ing"):
                aspect = "progressive"
            slots.append(Slot(tok, "verb", verbish, aspect=aspect))
            i += 1
            continue
        if nounish:
            pending = nounish
            pending_src = tok
            i += 1
            continue
        slots.append(Slot(tok, entries[0].pos, entries[0]))
        i += 1
    if pending is not None:
        if any(t.lower() in {"is", "am", "are"} for t in tokens):
            flush("ins")
        elif seen_verb:
            flush("acc")
        else:
            flush("nom")
    if question:
        slots.append(Slot("?", "question"))
    return slots, unknown


def realize(slots: list[Slot], pack: LanguagePack, source_lang: str, source_text: str, unknown: list[str]) -> TranslationResult:
    pieces: list[str] = []
    analysis: list[TokenGloss] = []
    question = False
    for slot in slots:
        if slot.role == "question":
            question = True
            continue
        if slot.entry is None:
            pieces.append(slot.source)
            analysis.append(TokenGloss(slot.source, slot.source, "未登録"))
            continue
        if slot.role == "topic":
            surface = topic_form(slot.entry, pack)
            note = "主題"
        elif slot.role == "vocative":
            surface = vocative_form(slot.entry, pack)
            note = "呼びかけ"
        elif slot.role == "verb":
            surface = conjugate_entry(
                slot.entry,
                pack,
                mood=slot.mood,
                aspect=slot.aspect,
                voices=slot.voices,
            )
            note = slot.entry.gloss_ja
        elif slot.role == "cite":
            surface = apply_case(slot.entry, pack, "acc")
            note = "引用対象"
        elif slot.role in pack.morphology.case_particle_ja:
            surface = apply_case(slot.entry, pack, slot.role)
            note = pack.morphology.case_particle_ja.get(slot.role, slot.role)
        else:
            surface = slot.entry.lemma
            note = slot.entry.pos
        pieces.append(surface)
        analysis.append(TokenGloss(slot.source, surface, note))

    if question and pack.syntax.question.particle:
        particle = pack.syntax.question.particle
        if not any(p == particle or p.endswith(particle) for p in pieces):
            pieces.append(particle)
            analysis.append(TokenGloss("か", particle, "疑問"))

    surface = " ".join(p for p in pieces if p)
    mark = pack.syntax.question_mark if question else pack.syntax.period
    if surface and mark and not surface.endswith((".", "!", "?", pack.syntax.period, pack.syntax.question_mark)):
        if question:
            surface = surface.rstrip() + mark
        else:
            surface = surface + mark
    notes = []
    if unknown:
        notes.append("未登録の語は原文のまま残しています。言語パックの lexicon.json に足せます。")
    return TranslationResult(
        source_lang=source_lang,
        target_lang=pack.id,
        source_text=source_text,
        text=surface,
        engine="transfer",
        ath_keys="",
        reading_ja=g2p_reading_ja(surface, pack),
        analysis=analysis,
        notes=notes,
        unknown=unknown,
    )


def _translate_out(text: str, pack: LanguagePack, lexicon: Lexicon, target: str) -> TranslationResult:
    index = form_index_for(pack, lexicon)
    tokens = _tokenize_pack(text)
    pieces: list[str] = []
    analysis: list[TokenGloss] = []
    unknown: list[str] = []
    question = False
    topic_particle = pack.syntax.topic.particle.casefold()
    voc_particle = pack.syntax.vocative.particle.casefold()
    q_particle = pack.syntax.question.particle.casefold()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in {".", ",", "!", "?"}:
            if tok in {"?", "？"}:
                question = True
            i += 1
            continue
        low = tok.casefold()
        if q_particle and low == q_particle:
            question = True
            analysis.append(TokenGloss(tok, "か" if target == "ja" else "?", "question"))
            i += 1
            continue
        if voc_particle and low == voc_particle:
            pieces.append("よ" if target == "ja" else "O")
            analysis.append(TokenGloss(tok, "よ" if target == "ja" else "O", "vocative"))
            i += 1
            continue
        if topic_particle and low == topic_particle:
            if pieces:
                if target == "ja":
                    for suffix in ("が", "を", "の", "に", "へ", "から", "で"):
                        if pieces[-1].endswith(suffix):
                            pieces[-1] = pieces[-1][: -len(suffix)] + "は"
                            break
                    else:
                        if not pieces[-1].endswith("は"):
                            pieces[-1] += "は"
                elif not pieces[-1].endswith(" (topic)"):
                    pieces[-1] += " (topic)"
            i += 1
            continue
        nxt = tokens[i + 1].casefold() if i + 1 < len(tokens) else ""
        hits = index.lookup(tok)
        if not hits:
            unknown.append(tok)
            pieces.append(tok)
            analysis.append(TokenGloss(tok, tok, "unknown"))
            i += 1
            continue
        hit = hits[0]
        extras = set(hit.extras)
        if topic_particle and nxt == topic_particle:
            extras.add("topic")
            i += 1
        if target == "ja":
            word = hit.entry.gloss_ja.split("/")[0]
            if "topic" in extras:
                word += "は"
            elif hit.case:
                word += pack.morphology.case_particle_ja.get(hit.case, "")
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
            if "topic" in extras:
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
        surface = surface.replace("はが", "は").replace("がは", "は")
        if question and not surface.endswith(("か", "？")):
            surface += "か"
        if surface and not surface.endswith(("。", "？", "！", "か")):
            surface += "。"
    return TranslationResult(
        source_lang=pack.id,
        target_lang=target,
        source_text=text,
        text=surface,
        engine="transfer",
        ath_keys="",
        reading_ja=g2p_reading_ja(text, pack),
        analysis=analysis,
        notes=["規則ベースの直訳です。語順は原文に近い語釈の連結です。"],
        unknown=unknown,
    )


def translate_pack(
    text: str,
    pack: LanguagePack,
    lexicon: Lexicon | None = None,
    *,
    source_lang: str = "auto",
    target_lang: str = "auto",
) -> TranslationResult:
    text = text.strip()
    lexicon = lexicon if lexicon is not None else pack.load_lexicon()
    src = source_lang
    if src in {"", "auto"}:
        src = detect_pivot_lang(text, lexicon)
        if src in {"baronh", pack.id} or (src not in {"ja", "en"} and src != pack.id):
            src = pack.id
    tgt = target_lang
    if tgt in {"", "auto"}:
        tgt = "ja" if src == pack.id else pack.id
    if src == tgt:
        return TranslationResult(
            src,
            tgt,
            text,
            text,
            engine="transfer",
            reading_ja=g2p_reading_ja(text, pack) if src == pack.id else "",
        )
    if src in {"ja", "en"} and tgt == pack.id:
        slots, unknown = analyze_ja(text, lexicon, pack) if src == "ja" else analyze_en(text, lexicon, pack)
        return realize(slots, pack, src, text, unknown)
    if src == pack.id and tgt in {"ja", "en"}:
        return _translate_out(text, pack, lexicon, tgt)
    if src in {"ja", "en"} and tgt in {"ja", "en"}:
        mid_slots, mid_unknown = analyze_ja(text, lexicon, pack) if src == "ja" else analyze_en(text, lexicon, pack)
        mid = realize(mid_slots, pack, src, text, mid_unknown)
        back = _translate_out(mid.text, pack, lexicon, tgt)
        back.source_lang = src
        back.source_text = text
        back.notes.append(f"{src}→{pack.id}→{tgt} の二段翻訳です。")
        return back
    raise ValueError(f"no transfer route for {src}->{tgt} (pack {pack.id})")


def translate_auto(
    text: str,
    *,
    source_lang: str = "auto",
    target_lang: str = "auto",
    lexicon: Lexicon | None = None,
    pack: LanguagePack | None = None,
    vector_search: bool = False,
) -> TranslationResult:
    """パック言語なら転移翻訳、ja/en/baronh なら従来エンジン。"""
    src = source_lang
    tgt = target_lang
    pack_langs = {pack.id} if pack else set()
    if pack is None:
        from baronh.langpack import list_packs

        try:
            packs = list_packs()
        except Exception:
            packs = []
        pack_langs = {item.id for item in packs}
        if src in pack_langs:
            pack = next(item for item in packs if item.id == src)
        elif tgt in pack_langs:
            pack = next(item for item in packs if item.id == tgt)
        elif src in {"", "auto"} and tgt not in LANGS and tgt in pack_langs:
            pack = next(item for item in packs if item.id == tgt)

    if pack is not None and not uses_builtin_engine(pack):
        return translate_pack(text, pack, lexicon, source_lang=src, target_lang=tgt)

    if lexicon is None:
        from baronh.lexicon import load_lexicon

        lexicon = load_lexicon(None)
    return translate_builtin(
        text,
        lexicon,
        source_lang=src if src else "auto",
        target_lang=tgt if tgt else "auto",
        vector_search=vector_search,
    )
