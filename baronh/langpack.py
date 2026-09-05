"""宣言的な言語パック（phonology / morphology / syntax / lexicon）。

アーヴ語の本番翻訳は従来どおり grammar.py / translate.py を使う。
パックは (1) 新規の架空言語を同じ転移翻訳で動かす (2) 読み・IPA・制約付き認識
(3) 文法コンテキストの生成、のための単一の記述形式である。
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from baronh.lexicon import CASES, CASE_JA, CASE_PARTICLE_JA, Entry, Lexicon, load_lexicon, load_lexicon_document
from baronh.paths import LANGS_DIR, ROOT_DIR

_PIVOT_LANGS = {"ja", "en", "auto"}


class LangpackError(ValueError):
    """言語パックが読めない / スキーマを満たさない。"""


@dataclass
class PhonologySpec:
    engine: str = "table"
    vowels: tuple[str, ...] = ()
    consonants: tuple[str, ...] = ()
    digraphs: dict[str, str] = field(default_factory=dict)
    ipa: dict[str, str] = field(default_factory=dict)
    reading_ja_vowels: dict[str, str] = field(default_factory=dict)
    reading_ja_cv: dict[str, str] = field(default_factory=dict)
    reading_ja_coda: dict[str, str] = field(default_factory=dict)
    silent_final: tuple[str, ...] = ()
    syllable: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> PhonologySpec:
        data = raw or {}
        reading = data.get("reading_ja") or {}
        return cls(
            engine=str(data.get("engine") or "table"),
            vowels=tuple(data.get("vowels") or ()),
            consonants=tuple(data.get("consonants") or ()),
            digraphs={str(k): str(v) for k, v in (data.get("digraphs") or {}).items()},
            ipa={str(k): str(v) for k, v in (data.get("ipa") or {}).items()},
            reading_ja_vowels={str(k): str(v) for k, v in (reading.get("vowels") or {}).items()},
            reading_ja_cv={str(k): str(v) for k, v in (reading.get("cv") or {}).items()},
            reading_ja_coda={str(k): str(v) for k, v in (reading.get("coda") or {}).items()},
            silent_final=tuple(data.get("silent_final") or ()),
            syllable=str(data.get("syllable") or ""),
        )


@dataclass
class DeclensionSpec:
    drop_suffix: str = ""
    suffixes: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> DeclensionSpec:
        data = raw or {}
        stem = data.get("stem") or {}
        suffixes = data.get("suffixes") or {}
        return cls(
            drop_suffix=str(stem.get("drop_suffix") or data.get("drop_suffix") or ""),
            suffixes={str(k): str(v) for k, v in suffixes.items()},
        )


@dataclass
class MorphologySpec:
    engine: str = "suffix"
    cases: tuple[str, ...] = CASES
    case_ja: dict[str, str] = field(default_factory=lambda: dict(CASE_JA))
    case_particle_ja: dict[str, str] = field(default_factory=lambda: dict(CASE_PARTICLE_JA))
    default_noun: str = "a"
    declensions: dict[str, DeclensionSpec] = field(default_factory=dict)
    voices: tuple[str, ...] = ("causative", "passive", "negative")
    voice_suffix: dict[str, str] = field(default_factory=dict)
    moods: tuple[str, ...] = ("indicative", "subjunctive", "imperative", "participle")
    aspects: tuple[str, ...] = ("indefinite", "perfect", "progressive", "prospective")
    verb_endings: dict[tuple[str, str], str] = field(default_factory=dict)
    default_verb: str = "v"

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> MorphologySpec:
        data = raw or {}
        endings_raw = data.get("verb_endings") or {}
        endings: dict[tuple[str, str], str] = {}
        for key, value in endings_raw.items():
            if isinstance(key, str) and "|" in key:
                mood, aspect = key.split("|", 1)
            elif isinstance(key, (list, tuple)) and len(key) == 2:
                mood, aspect = str(key[0]), str(key[1])
            else:
                continue
            endings[(mood, aspect)] = str(value)
        declensions = {
            str(name): DeclensionSpec.from_dict(spec)
            for name, spec in (data.get("declensions") or {}).items()
        }
        cases = tuple(data.get("cases") or CASES)
        case_ja = dict(CASE_JA)
        case_ja.update({str(k): str(v) for k, v in (data.get("case_ja") or {}).items()})
        case_particle_ja = dict(CASE_PARTICLE_JA)
        case_particle_ja.update({str(k): str(v) for k, v in (data.get("case_particle_ja") or {}).items()})
        return cls(
            engine=str(data.get("engine") or "suffix"),
            cases=cases,
            case_ja=case_ja,
            case_particle_ja=case_particle_ja,
            default_noun=str(data.get("default_noun") or "a"),
            declensions=declensions,
            voices=tuple(data.get("voices") or ("causative", "passive", "negative")),
            voice_suffix={str(k): str(v) for k, v in (data.get("voice_suffix") or {}).items()},
            moods=tuple(data.get("moods") or ("indicative", "subjunctive", "imperative", "participle")),
            aspects=tuple(data.get("aspects") or ("indefinite", "perfect", "progressive", "prospective")),
            verb_endings=endings,
            default_verb=str(data.get("default_verb") or "v"),
        )


@dataclass
class TopicSpec:
    particle: str = ""
    position: str = "after"
    form: str = "nom"
    pronoun_contract: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> TopicSpec:
        data = raw or {}
        return cls(
            particle=str(data.get("particle") or ""),
            position=str(data.get("position") or "after"),
            form=str(data.get("form") or "nom"),
            pronoun_contract={str(k).casefold(): str(v) for k, v in (data.get("pronoun_contract") or {}).items()},
        )


@dataclass
class ParticleSpec:
    particle: str = ""
    position: str = "after"
    form: str = "nom"

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> ParticleSpec:
        data = raw or {}
        return cls(
            particle=str(data.get("particle") or ""),
            position=str(data.get("position") or "after"),
            form=str(data.get("form") or "nom"),
        )


@dataclass
class CopulaSpec:
    lemma: str = ""
    omit_with_ins: bool = True

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> CopulaSpec:
        data = raw or {}
        return cls(
            lemma=str(data.get("lemma") or ""),
            omit_with_ins=bool(data.get("omit_with_ins", True)),
        )


@dataclass
class SyntaxSpec:
    word_order: str = "SOV"
    constituent_order: tuple[str, ...] = ()
    topic: TopicSpec = field(default_factory=TopicSpec)
    vocative: ParticleSpec = field(default_factory=ParticleSpec)
    question: ParticleSpec = field(default_factory=ParticleSpec)
    copula: CopulaSpec = field(default_factory=CopulaSpec)
    ja_particles: dict[str, str] = field(default_factory=dict)
    en_prep: dict[str, str] = field(default_factory=dict)
    period: str = "."
    question_mark: str = "?"
    modifier_position: str = "before"

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> SyntaxSpec:
        data = raw or {}
        return cls(
            word_order=str(data.get("word_order") or "SOV"),
            constituent_order=tuple(data.get("constituent_order") or ()),
            topic=TopicSpec.from_dict(data.get("topic")),
            vocative=ParticleSpec.from_dict(data.get("vocative")),
            question=ParticleSpec.from_dict(data.get("question")),
            copula=CopulaSpec.from_dict(data.get("copula")),
            ja_particles={str(k): str(v) for k, v in (data.get("ja_particles") or {}).items()},
            en_prep={str(k): str(v) for k, v in (data.get("en_prep") or {}).items()},
            period=str(data.get("period") or "."),
            question_mark=str(data.get("question_mark") or "?"),
            modifier_position=str(data.get("modifier_position") or "before"),
        )


@dataclass
class LanguagePack:
    id: str
    path: Path
    version: int = 1
    names: dict[str, str] = field(default_factory=dict)
    description: str = ""
    script: str = "latin"
    phonology: PhonologySpec = field(default_factory=PhonologySpec)
    morphology: MorphologySpec = field(default_factory=MorphologySpec)
    syntax: SyntaxSpec = field(default_factory=SyntaxSpec)
    lexicon_path: Path | None = None
    closed_forms: tuple[str, ...] = ()
    grammar_notes: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def name_ja(self) -> str:
        return self.names.get("ja") or self.names.get("autonym") or self.id

    @property
    def name_en(self) -> str:
        return self.names.get("en") or self.names.get("autonym") or self.id

    @property
    def autonym(self) -> str:
        return self.names.get("autonym") or self.id

    def load_lexicon(self) -> Lexicon:
        if self.morphology.engine == "baronh" or self.id == "baronh":
            return load_lexicon(None)
        if self.lexicon_path and self.lexicon_path.is_file():
            return load_lexicon_document(self.lexicon_path)
        raise LangpackError(f"language pack {self.id} has no lexicon.json")


def _required(raw: dict[str, Any], key: str, path: Path) -> Any:
    if key not in raw:
        raise LangpackError(f"{path}: missing required field {key}")
    return raw[key]


def load_pack(source: str | Path, *, langs_dir: Path | None = None) -> LanguagePack:
    """id または language.json のパスからパックを読む。"""
    root = Path(langs_dir) if langs_dir else LANGS_DIR
    text = str(source)
    path = Path(text)
    if path.suffix.lower() == ".json" and path.is_file():
        pack_path = path
    elif path.is_dir() and (path / "language.json").is_file():
        pack_path = path / "language.json"
    else:
        pack_path = root / text / "language.json"
    if not pack_path.is_file():
        raise LangpackError(f"language pack not found: {source}")
    raw = json.loads(pack_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise LangpackError(f"{pack_path}: root must be an object")
    pack_id = str(_required(raw, "id", pack_path))
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", pack_id):
        raise LangpackError(f"{pack_path}: id must be lowercase ascii, got {pack_id!r}")
    lexicon_rel = raw.get("lexicon") or "lexicon.json"
    lexicon_path = (pack_path.parent / str(lexicon_rel)).resolve()
    if not lexicon_path.is_file():
        lexicon_path = None
    names = {str(k): str(v) for k, v in (raw.get("names") or {}).items()}
    return LanguagePack(
        id=pack_id,
        path=pack_path,
        version=int(raw.get("version") or 1),
        names=names,
        description=str(raw.get("description") or ""),
        script=str(raw.get("script") or "latin"),
        phonology=PhonologySpec.from_dict(raw.get("phonology")),
        morphology=MorphologySpec.from_dict(raw.get("morphology")),
        syntax=SyntaxSpec.from_dict(raw.get("syntax")),
        lexicon_path=lexicon_path,
        closed_forms=tuple(str(x) for x in (raw.get("closed_forms") or ())),
        grammar_notes=tuple(str(x) for x in (raw.get("grammar_notes") or ())),
        raw=raw,
    )


def list_pack_ids(*, langs_dir: Path | None = None) -> list[str]:
    root = Path(langs_dir) if langs_dir else LANGS_DIR
    if not root.is_dir():
        return []
    ids: list[str] = []
    for child in sorted(root.iterdir()):
        if child.name.startswith("."):
            continue
        if (child / "language.json").is_file():
            ids.append(child.name)
    return ids


def list_packs(*, langs_dir: Path | None = None) -> list[LanguagePack]:
    root = Path(langs_dir) if langs_dir else LANGS_DIR
    packs: list[LanguagePack] = []
    for pack_id in list_pack_ids(langs_dir=root):
        packs.append(load_pack(pack_id, langs_dir=root))
    return packs


def is_pack_lang(lang: str, *, langs_dir: Path | None = None) -> bool:
    if not lang or lang in _PIVOT_LANGS:
        return False
    if lang == "baronh":
        return True
    return lang in set(list_pack_ids(langs_dir=langs_dir))


def uses_builtin_engine(pack: LanguagePack) -> bool:
    return pack.id == "baronh" or pack.morphology.engine == "baronh"


def noun_stem(entry: Entry, pack: LanguagePack) -> str:
    if entry.stem:
        return entry.stem
    kind = entry.declension or pack.morphology.default_noun
    spec = pack.morphology.declensions.get(kind)
    lemma = entry.lemma
    if spec and spec.drop_suffix and lemma.endswith(spec.drop_suffix):
        body = lemma[: -len(spec.drop_suffix)]
        return body if body else lemma
    return lemma


def decline_entry(entry: Entry, pack: LanguagePack) -> dict[str, str]:
    if uses_builtin_engine(pack):
        from baronh.grammar import decline as baronh_decline

        return baronh_decline(entry)
    if entry.paradigm:
        return {case: entry.paradigm.get(case, entry.lemma) for case in pack.morphology.cases}
    kind = entry.declension or pack.morphology.default_noun
    spec = pack.morphology.declensions.get(kind)
    if spec is None:
        return {case: entry.lemma for case in pack.morphology.cases}
    stem = noun_stem(entry, pack)
    forms: dict[str, str] = {}
    for case in pack.morphology.cases:
        suffix = spec.suffixes.get(case, "")
        forms[case] = stem + suffix
    return forms


def conjugate_entry(
    entry: Entry,
    pack: LanguagePack,
    *,
    mood: str = "indicative",
    aspect: str = "indefinite",
    voices: Iterable[str] = (),
) -> str:
    if uses_builtin_engine(pack):
        from baronh.grammar import conjugate as baronh_conjugate

        return baronh_conjugate(entry, mood=mood, aspect=aspect, voices=voices)
    stem = entry.stem or entry.lemma
    wanted = set(voices)
    affix = "".join(pack.morphology.voice_suffix[name] for name in pack.morphology.voices if name in wanted)
    ending = pack.morphology.verb_endings.get((mood, aspect))
    if ending is None:
        ending = pack.morphology.verb_endings.get(("indicative", "indefinite"), "")
    return stem + affix + ending


def all_verb_forms_pack(entry: Entry, pack: LanguagePack) -> list[tuple[str, str, tuple[str, ...], str]]:
    if uses_builtin_engine(pack):
        from baronh.grammar import all_verb_forms

        return all_verb_forms(entry)
    forms: list[tuple[str, str, tuple[str, ...], str]] = []
    voice_sets: list[tuple[str, ...]] = [()]
    for voice in pack.morphology.voices:
        voice_sets.append((voice,))
    if len(pack.morphology.voices) >= 2:
        voice_sets.append(tuple(pack.morphology.voices[:2]))
    if len(pack.morphology.voices) >= 3:
        voice_sets.append(tuple(pack.morphology.voices))
    for voices in voice_sets:
        for mood in pack.morphology.moods:
            for aspect in pack.morphology.aspects:
                if (mood, aspect) not in pack.morphology.verb_endings:
                    continue
                form = conjugate_entry(entry, pack, mood=mood, aspect=aspect, voices=voices)
                forms.append((mood, aspect, voices, form))
    return forms


def topic_form(entry: Entry, pack: LanguagePack) -> str:
    forms = decline_entry(entry, pack)
    nom = forms.get(pack.syntax.topic.form or "nom", entry.lemma)
    if entry.pos == "pronoun":
        contracted = pack.syntax.topic.pronoun_contract.get(nom.casefold())
        if contracted:
            return contracted
    particle = pack.syntax.topic.particle
    if not particle:
        return nom
    if pack.syntax.topic.position == "before":
        return f"{particle} {nom}".strip()
    return f"{nom} {particle}".strip()


def vocative_form(entry: Entry, pack: LanguagePack) -> str:
    forms = decline_entry(entry, pack)
    nom = forms.get(pack.syntax.vocative.form or "nom", entry.lemma)
    particle = pack.syntax.vocative.particle
    if not particle:
        return nom
    if pack.syntax.vocative.position == "before":
        return f"{particle} {nom}".strip()
    return f"{nom} {particle}".strip()


def apply_case(entry: Entry, pack: LanguagePack, case: str) -> str:
    if entry.pos in {"noun", "pronoun"} and case in pack.morphology.case_particle_ja:
        return decline_entry(entry, pack)[case]
    return entry.lemma


def closed_form_set(pack: LanguagePack) -> set[str]:
    items = {form.casefold() for form in pack.closed_forms}
    if pack.syntax.topic.particle:
        items.add(pack.syntax.topic.particle.casefold())
    if pack.syntax.vocative.particle:
        items.add(pack.syntax.vocative.particle.casefold())
    if pack.syntax.question.particle:
        items.add(pack.syntax.question.particle.casefold())
    items.update(value.casefold() for value in pack.syntax.topic.pronoun_contract.values())
    return items


def grammar_context_for(pack: LanguagePack) -> str:
    """生成 AI / 設計メモ向けに、パックから文法コンテキストを組む。"""
    if uses_builtin_engine(pack):
        from baronh.grammar import grammar_context

        return grammar_context()
    morph = pack.morphology
    verb_lines = [
        f"- {mood} / {aspect}: -{ending}"
        for (mood, aspect), ending in morph.verb_endings.items()
    ]
    case_line = " ".join(f"{morph.case_ja.get(case, case)} {case}" for case in morph.cases)
    notes = list(pack.grammar_notes)
    decl_lines = []
    for name, spec in morph.declensions.items():
        bits = ", ".join(f"{case}:{spec.suffixes.get(case, '') or '∅'}" for case in morph.cases)
        decl_lines.append(f"- {name}: {bits}")
    return "\n".join(
        [
            f"# {pack.name_ja}文法",
            f"語順は {pack.syntax.word_order}。",
            f"名詞の格: {case_line}。",
            *decl_lines,
            f"主題は nominative + {pack.syntax.topic.particle or '（無標）'}。",
            "",
            "## 動詞",
            "動詞は語幹+態+語尾。",
            *verb_lines,
            "",
            *notes,
        ]
    )


def init_lang(
    pack_id: str,
    *,
    name_ja: str = "",
    name_en: str = "",
    autonym: str = "",
    langs_dir: Path | None = None,
    template_id: str = "mina",
) -> Path:
    """雛形パックをコピーして新しい言語ディレクトリを作る。"""
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", pack_id):
        raise LangpackError("id must be lowercase ascii [a-z][a-z0-9_-]{0,31}")
    root = Path(langs_dir) if langs_dir else LANGS_DIR
    dest = root / pack_id
    if dest.exists():
        raise LangpackError(f"already exists: {dest}")
    try:
        template = load_pack(template_id, langs_dir=root)
    except LangpackError:
        template = load_pack(template_id, langs_dir=LANGS_DIR)
    shutil.copytree(template.path.parent, dest)
    pack_path = dest / "language.json"
    raw = json.loads(pack_path.read_text(encoding="utf-8"))
    raw["id"] = pack_id
    names = dict(raw.get("names") or {})
    names["autonym"] = autonym or pack_id
    names["ja"] = name_ja or f"{pack_id}語"
    names["en"] = name_en or pack_id.title()
    raw["names"] = names
    raw["description"] = (
        raw.get("description") or ""
    ) + f"\n（{template_id} から複製した雛形。音韻・形態・語彙を書き換えてください。）"
    pack_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lexicon_path = dest / (raw.get("lexicon") or "lexicon.json")
    if lexicon_path.is_file():
        lex = json.loads(lexicon_path.read_text(encoding="utf-8"))
        meta = dict(lex.get("meta") or {})
        meta["language"] = pack_id
        lex["meta"] = meta
        lexicon_path.write_text(json.dumps(lex, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dest


def repo_root() -> Path:
    return ROOT_DIR
