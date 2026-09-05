"""制約付き認識（仮名読み / IPA / 正書法 → 言語の表層）。

音響モデルは持たない。Whisper 等の出力を、パックの語形と G2P の逆引きで
語彙に落とす層である。低資源・架空言語ではこの制約が本体になる。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from baronh.g2p import compact_reading, g2p_ipa, g2p_reading_ja
from baronh.langpack import LanguagePack, closed_form_set
from baronh.lexicon import Lexicon
from baronh.transfer import form_index_for


@dataclass
class RecognitionHit:
    form: str
    reading: str
    note: str = ""


@dataclass
class RecognitionResult:
    lang: str
    spoken_text: str
    text: str
    engine: str = "lexicon-fst"
    reading_ja: str = ""
    ipa: str = ""
    path: list[RecognitionHit] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "lang": self.lang,
            "spoken_text": self.spoken_text,
            "text": self.text,
            "engine": self.engine,
            "reading_ja": self.reading_ja,
            "ipa": self.ipa,
            "path": [hit.__dict__ for hit in self.path],
            "unknown": self.unknown,
            "notes": self.notes,
        }


def _form_inventory(pack: LanguagePack, lexicon: Lexicon) -> list[tuple[str, str, str]]:
    """(form, compact_kana, compact_ipa) を長い読み優先で返す。"""
    index = form_index_for(pack, lexicon)
    seen: set[str] = set()
    rows: list[tuple[str, str, str]] = []
    forms: list[str] = []
    if hasattr(index, "_exact"):
        forms.extend(index._exact.keys())  # type: ignore[attr-defined]
    for form in pack.closed_forms:
        forms.append(form)
    for form in closed_form_set(pack):
        forms.append(form)
    for form in forms:
        if not form or " " in form:
            # 主題の "na ya" は単語ごとで見る
            for part in form.split():
                if part and part.casefold() not in seen:
                    seen.add(part.casefold())
                    kana = compact_reading(g2p_reading_ja(part, pack))
                    ipa = compact_reading(g2p_ipa(part, pack))
                    rows.append((part, kana, ipa))
            continue
        key = form.casefold()
        if key in seen:
            continue
        seen.add(key)
        kana = compact_reading(g2p_reading_ja(form, pack))
        ipa = compact_reading(g2p_ipa(form, pack))
        rows.append((form, kana, ipa))
    rows.sort(key=lambda item: (-max(len(item[1]), len(item[2])), -len(item[0])))
    return rows


def _match_compact(compact: str, rows: list[tuple[str, str, str]], field: int) -> tuple[list[RecognitionHit], list[str]]:
    hits: list[RecognitionHit] = []
    unknown: list[str] = []
    i = 0
    while i < len(compact):
        matched = None
        for form, kana, ipa in rows:
            needle = kana if field == 1 else ipa
            if needle and compact.startswith(needle, i):
                matched = RecognitionHit(form, needle, "reading" if field == 1 else "ipa")
                i += len(needle)
                break
        if matched is None:
            unknown.append(compact[i])
            i += 1
            continue
        hits.append(matched)
    return hits, unknown


def recognize(
    spoken: str,
    pack: LanguagePack,
    lexicon: Lexicon | None = None,
) -> RecognitionResult:
    """仮名・IPA・正書法のいずれかを、パックの語形へ落とす。"""
    spoken = (spoken or "").strip()
    lexicon = lexicon if lexicon is not None else pack.load_lexicon()
    index = form_index_for(pack, lexicon)
    notes: list[str] = []

    tokens = [part for part in spoken.replace("。", " ").replace("、", " ").split() if part]
    latinish = tokens and all(
        all(ch.isascii() and (ch.isalpha() or ch in ".'-?") for ch in tok) or tok in {".", "?", "!"}
        for tok in tokens
    )
    if latinish:
        kept: list[str] = []
        unknown: list[str] = []
        path: list[RecognitionHit] = []
        for tok in tokens:
            form = tok.rstrip(".,!?;:")
            punct = tok[len(form) :]
            if not form:
                continue
            hits = index.lookup(form) if hasattr(index, "lookup") else []
            closed = form.casefold() in closed_form_set(pack)
            if hits or closed:
                kept.append(form)
                path.append(RecognitionHit(form, form, "orthography"))
            else:
                unknown.append(form)
                kept.append(form)
            if punct:
                kept[-1] = kept[-1] + punct
        surface = " ".join(kept)
        if surface and not surface.endswith((".", "!", "?")):
            surface += pack.syntax.period
        if unknown:
            notes.append("正書法として読めない語をそのまま残しています。")
        return RecognitionResult(
            lang=pack.id,
            spoken_text=spoken,
            text=surface,
            reading_ja=g2p_reading_ja(surface, pack),
            ipa=g2p_ipa(surface, pack),
            path=path,
            unknown=unknown,
            notes=notes or ["正書法入力を語形索引で正規化しました。"],
        )

    rows = _form_inventory(pack, lexicon)
    compact = compact_reading(spoken)
    path, unknown = _match_compact(compact, rows, 1)
    field_note = "仮名読み"
    if (not path or unknown) and any(row[2] for row in rows):
        ipa_compact = compact_reading(spoken)
        alt_path, alt_unknown = _match_compact(ipa_compact, rows, 2)
        if len(alt_unknown) < len(unknown):
            path, unknown = alt_path, alt_unknown
            field_note = "IPA"

    surface = " ".join(hit.form for hit in path)
    if surface and not surface.endswith((".", "!", "?")):
        if pack.syntax.question.particle and path and path[-1].form.casefold() == pack.syntax.question.particle.casefold():
            surface += pack.syntax.question_mark
        else:
            surface += pack.syntax.period
    if unknown:
        notes.append(f"{field_note}の一部を語形に落とせませんでした。")
    else:
        notes.append(f"{field_note}を語彙・形態の制約で表層に落としました。")
    notes.append("音響モデルは使っていません。Whisper 等の出力をこの層へ渡せます。")
    return RecognitionResult(
        lang=pack.id,
        spoken_text=spoken,
        text=surface,
        reading_ja=g2p_reading_ja(surface, pack) if surface else "",
        ipa=g2p_ipa(surface, pack) if surface else "",
        path=path,
        unknown=unknown,
        notes=notes,
    )
