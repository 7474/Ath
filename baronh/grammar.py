"""アーヴ語の格変化・動詞活用・形態解析。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from baronh.lexicon import CASES, Entry, Lexicon

VOICES = ("causative", "passive", "negative")
VOICE_SUFFIX = {
    "causative": "as",
    "passive": "ar",
    "negative": "ad",
}

MOODS = ("indicative", "subjunctive", "imperative", "participle")
ASPECTS = ("indefinite", "perfect", "progressive", "prospective")

# Wikipedia「アーヴ語」の動詞語尾表。
VERB_ENDINGS: dict[tuple[str, str], str] = {
    ("indicative", "indefinite"): "e",
    ("indicative", "perfect"): "le",
    ("indicative", "progressive"): "lér",
    ("indicative", "prospective"): "to",
    ("subjunctive", "indefinite"): "éme",
    ("subjunctive", "perfect"): "lar",
    ("subjunctive", "progressive"): "lérm",
    ("subjunctive", "prospective"): "dar",
    ("imperative", "indefinite"): "é",
    ("participle", "indefinite"): "a",
    ("participle", "perfect"): "la",
    ("participle", "progressive"): "léra",
    ("participle", "prospective"): "naur",
}

MOOD_JA = {
    "indicative": "直説法",
    "subjunctive": "仮定法",
    "imperative": "命令法",
    "participle": "分詞",
}
ASPECT_JA = {
    "indefinite": "不定相",
    "perfect": "完了相",
    "progressive": "進行相",
    "prospective": "未然相",
}
VOICE_JA = {
    "causative": "使役",
    "passive": "受動",
    "negative": "否定",
}


def type1_guess(lemma: str) -> dict[str, str]:
    """第1型の規則的類推。既知の不規則は paradigm を優先する。"""
    if lemma.endswith("h") and len(lemma) >= 3:
        body = lemma[:-1]
        cons = body[1:]
        gen = cons + "ar"
        return {
            "nom": lemma,
            "acc": body + "e",
            "gen": gen,
            "dat": gen + "i",
            "all": gen + "é",
            "abl": lemma + "ar",
            "ins": cons + "ale",
        }
    if lemma.endswith("n"):
        body = lemma[:-1]
        return {
            "nom": lemma,
            "acc": body + "e",
            "gen": body + "r",
            "dat": body + "ri",
            "all": body + "ré",
            "abl": lemma + "ar",
            "ins": body + "le",
        }
    if len(lemma) >= 3:
        body = lemma[:-1] if lemma[-1] == lemma[-2] else lemma
        cons = body[1:]
        gen = cons + "ar"
        return {
            "nom": lemma,
            "acc": body[:2] + "e" if len(body) > 2 else body + "e",
            "gen": gen,
            "dat": gen + "i",
            "all": gen + "é",
            "abl": lemma + "ar",
            "ins": cons + "ale",
        }
    return {case: lemma for case in CASES}


def type2_forms(stem: str) -> dict[str, str]:
    return {
        "nom": stem + "h",
        "acc": stem + "e",
        "gen": stem + "r",
        "dat": stem + "i",
        "all": stem + "é",
        "abl": stem + "har",
        "ins": stem + "hle",
    }


def type3_forms(stem: str) -> dict[str, str]:
    return {
        "nom": stem + "c",
        "acc": stem + "l",
        "gen": stem + "r",
        "dat": stem + "ri",
        "all": stem + "gh",
        "abl": stem + "sar",
        "ins": stem + "le",
    }


def type4_forms(base: str, kind: str = "iac") -> dict[str, str]:
    if kind == "gac":
        return {
            "nom": base + "gac",
            "acc": base + "l",
            "gen": base + "r",
            "dat": base + "ri",
            "all": base + "gh",
            "abl": base + "sar",
            "ins": base + "le",
        }
    return {
        "nom": base + "iac",
        "acc": base + "él",
        "gen": base + "ér",
        "dat": base + "éri",
        "all": base + "égh",
        "abl": base + "iasar",
        "ins": base + "éle",
    }


def noun_stem(entry: Entry) -> str:
    if entry.stem:
        return entry.stem
    lemma = entry.lemma
    kind = entry.declension
    if kind == "2" and lemma.endswith("h"):
        return lemma[:-1]
    if kind == "3" and lemma.endswith("c"):
        return lemma[:-1]
    if kind == "4" and lemma.endswith("iac"):
        return lemma[:-3]
    if kind == "4g" and lemma.endswith("gac"):
        return lemma[:-3]
    if kind in {"1", "1n"}:
        return lemma[:-1] if lemma.endswith(("h", "n")) else lemma
    return lemma


def decline(entry: Entry) -> dict[str, str]:
    if entry.paradigm:
        forms = {case: entry.paradigm.get(case, entry.lemma) for case in CASES}
        return forms
    kind = entry.declension
    stem = noun_stem(entry)
    if kind == "1" or kind == "1n":
        return type1_guess(entry.lemma)
    if kind == "2":
        return type2_forms(stem)
    if kind == "3":
        return type3_forms(stem)
    if kind == "4":
        return type4_forms(stem, "iac")
    if kind == "4g":
        return type4_forms(stem, "gac")
    return {case: entry.lemma for case in CASES}


def voice_affix(voices: Iterable[str]) -> str:
    order = [name for name in VOICES if name in set(voices)]
    return "".join(VOICE_SUFFIX[name] for name in order)


def verb_ending(mood: str, aspect: str, stem: str = "") -> str:
    ending = VERB_ENDINGS.get((mood, aspect))
    if ending is None:
        raise ValueError(f"unsupported mood/aspect: {mood}/{aspect}")
    if mood == "imperative" and aspect == "indefinite" and stem and stem[-1] in "aiuééoœïüÿy":
        return "éno"
    return ending


def conjugate(
    entry: Entry,
    *,
    mood: str = "indicative",
    aspect: str = "indefinite",
    voices: Iterable[str] = (),
) -> str:
    stem = entry.stem or entry.lemma
    return stem + voice_affix(voices) + verb_ending(mood, aspect, stem)


def all_verb_forms(entry: Entry) -> list[tuple[str, str, tuple[str, ...], str]]:
    forms: list[tuple[str, str, tuple[str, ...], str]] = []
    voice_sets: list[tuple[str, ...]] = [()]
    for voice in VOICES:
        voice_sets.append((voice,))
    voice_sets.append(("causative", "passive"))
    voice_sets.append(("causative", "negative"))
    voice_sets.append(("passive", "negative"))
    voice_sets.append(("causative", "passive", "negative"))
    for voices in voice_sets:
        for mood in MOODS:
            for aspect in ASPECTS:
                if (mood, aspect) not in VERB_ENDINGS:
                    continue
                form = conjugate(entry, mood=mood, aspect=aspect, voices=voices)
                forms.append((mood, aspect, voices, form))
    return forms


@dataclass
class FormAnalysis:
    form: str
    entry: Entry
    kind: str
    case: str = ""
    mood: str = ""
    aspect: str = ""
    voices: tuple[str, ...] = ()
    extras: list[str] = field(default_factory=list)

    def summary_ja(self) -> str:
        bits = [f"{self.entry.lemma}「{self.entry.gloss_ja}」"]
        if self.case:
            from baronh.lexicon import CASE_JA

            bits.append(CASE_JA.get(self.case, self.case))
        if self.mood:
            bits.append(MOOD_JA.get(self.mood, self.mood))
        if self.aspect:
            bits.append(ASPECT_JA.get(self.aspect, self.aspect))
        if self.voices:
            bits.append("・".join(VOICE_JA[v] for v in self.voices))
        if self.extras:
            bits.extend(self.extras)
        return " / ".join(bits)


def _norm(text: str) -> str:
    return text.casefold()


class FormIndex:
    def __init__(self, lexicon: Lexicon):
        self.lexicon = lexicon
        self._exact: dict[str, list[FormAnalysis]] = {}
        self._rebuild()

    def _add(self, analysis: FormAnalysis) -> None:
        self._exact.setdefault(_norm(analysis.form), []).append(analysis)

    def _rebuild(self) -> None:
        self._exact.clear()
        for entry in self.lexicon.entries:
            if entry.pos in {"noun", "pronoun"}:
                for case, form in decline(entry).items():
                    self._add(FormAnalysis(form, entry, entry.pos, case=case))
            elif entry.pos == "verb":
                self._add(FormAnalysis(entry.lemma, entry, "verb", mood="indicative", aspect="indefinite"))
                if entry.stem and entry.stem != entry.lemma:
                    self._add(FormAnalysis(entry.stem, entry, "verb-stem"))
                for mood, aspect, voices, form in all_verb_forms(entry):
                    self._add(FormAnalysis(form, entry, "verb", mood=mood, aspect=aspect, voices=voices))
            else:
                self._add(FormAnalysis(entry.lemma, entry, entry.pos))

    def lookup(self, form: str) -> list[FormAnalysis]:
        return list(self._exact.get(_norm(form), []))


def analyze_form(form: str, lexicon: Lexicon, index: FormIndex | None = None) -> list[FormAnalysis]:
    idx = index or FormIndex(lexicon)
    hits = idx.lookup(form)
    if hits:
        return hits
    # 後置詞が付いたままの語 (例: F'a は別処理)
    return []


def topic_contract(form: str) -> str:
    """代名詞主格 + 主題後置詞 a → F'a のような縮約。"""
    if not form:
        return "a"
    contracted = {"fe": "F'a", "de": "D'a", "se": "S'a"}
    return contracted.get(form.casefold(), f"{form} a")


def grammar_context() -> str:
    """生成 AI のシステムプロンプトに載せる文法の全文。ツールで分割取得しない。"""
    verb_lines = []
    for (mood, aspect), ending in VERB_ENDINGS.items():
        verb_lines.append(f"- {MOOD_JA[mood]} / {ASPECT_JA[aspect]}: -{ending}")
    return "\n".join(
        [
            "# アーヴ語文法",
            "名詞は7格: 主格 nom（が）対格 acc（を）生格 gen（の）与格 dat（に）向格 all（へ）奪格 abl（から）具格 ins（で）。",
            "第1型 abh/abe/bar/bari/baré/abhar/bale。第2型 -h: lamh/lame/lamr/lami/lamé/lamhar/lamhle。",
            "第3型 -c: duc/dul/dur/duri/dugh/dusar/dule。第4型 -iac: saidiac/saidél/saidér/saidéri/saidégh/saidiasar/saidéle。",
            "主題は代名詞で F'a / D'a / S'a（Fe+a の縮約）。普通名詞の主題は lemma a。",
            "",
            "## 動詞",
            "動詞は語幹+態+語尾。態接辞は語幹と語尾の間に使役 -as- 受動 -ar- 否定 -ad- の順。",
            "命令は母音語幹なら -éno。例: sac → sace / sacle / sacasé。",
            *verb_lines,
            "",
            "## 代名詞",
            "fe 私, de あなた, se 彼/彼女, farh 私たち, darh あなたたち, cnac 彼ら, so これ, re それ, ai あれ。",
            "fe の格: fe/fal/far/feri/feré/fasar/fale。",
            "",
            "## 統語",
            "語順は SOV または SVO。修飾語は被修飾語の後ろ。",
            "後置詞: a は, éü よ, sa か, te と（引用）, le/lo と（並列）。",
            "「AはBだ」は A(主題) + B(具格)。コピュラ ane は省略することが多い。疑問は sa を文末に置く。",
            "",
            "## 音韻・正書法",
            "c は /k/。ch は摩擦音。Ath キー: ai→A, au→I, eu→E。",
            "辞書にない固有名詞はアーヴ語正書法で発音転記する。",
            "カ行は ca/ci/cu/ce/co。ジ行は gh（g+h=[ʒ]）。ヴは bh。アースに無い j/k/w/v は使わない。",
            "名詞の主格は -c / -h / -n で終わる。",
        ]
    )
