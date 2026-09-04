/* アーヴ語 規則ベース翻訳エンジン（Python baronh パッケージと対になる）。
 * 生成 AI 経路の特性と制約は baronh/ARCHITECTURE.md を参照。
 */
(function (global) {
  "use strict";

  var CASES = ["nom", "acc", "gen", "dat", "all", "abl", "ins"];
  var CASE_JA = { nom: "主格", acc: "対格", gen: "生格", dat: "与格", all: "向格", abl: "奪格", ins: "具格" };
  var CASE_PARTICLE = { nom: "が", acc: "を", gen: "の", dat: "に", all: "へ", abl: "から", ins: "で" };
  var VOICES = ["causative", "passive", "negative"];
  var VOICE_SUFFIX = { causative: "as", passive: "ar", negative: "ad" };
  var VERB_ENDINGS = {
    "indicative|indefinite": "e",
    "indicative|perfect": "le",
    "indicative|progressive": "lér",
    "indicative|prospective": "to",
    "subjunctive|indefinite": "éme",
    "subjunctive|perfect": "lar",
    "subjunctive|progressive": "lérm",
    "subjunctive|prospective": "dar",
    "imperative|indefinite": "é",
    "participle|indefinite": "a",
    "participle|perfect": "la",
    "participle|progressive": "léra",
    "participle|prospective": "naur"
  };
  var JA_PARTICLES = {
    "から": "abl", "まで": "all", "より": "abl", "は": "topic", "が": "nom",
    "を": "acc", "の": "gen", "に": "dat", "へ": "all", "で": "ins",
    "と": "cite", "よ": "vocative", "か": "question", "も": "also"
  };
  var PHONETIC_NOTE = "発音転記（辞書にない固有名詞）";
  var PHONETIC_SUMMARY = "辞書にない固有名詞は発音から転記しています。辞書の見出しではありません。";
  var JA_COPULA = { "です": 1, "だ": 1, "である": 1, "であります": 1, "でした": 1, "だった": 1 };
  var HONORIFICS = ["さん", "さま", "様", "くん", "君", "ちゃん", "氏"];
  var KANA_BARONH = [
    ["キャ", "cia"], ["キュ", "ciu"], ["キョ", "cio"],
    ["ギャ", "gia"], ["ギュ", "giu"], ["ギョ", "gio"],
    ["シャ", "sia"], ["シュ", "siu"], ["ショ", "sio"], ["シェ", "sie"],
    ["ジャ", "gha"], ["ジュ", "ghu"], ["ジョ", "gho"], ["ジェ", "ghe"],
    ["チャ", "tia"], ["チュ", "tiu"], ["チョ", "tio"], ["チェ", "tie"],
    ["ニャ", "nia"], ["ニュ", "niu"], ["ニョ", "nio"],
    ["ヒャ", "hia"], ["ヒュ", "hiu"], ["ヒョ", "hio"],
    ["ビャ", "bia"], ["ビュ", "biu"], ["ビョ", "bio"],
    ["ピャ", "pia"], ["ピュ", "piu"], ["ピョ", "pio"],
    ["ミャ", "mia"], ["ミュ", "miu"], ["ミョ", "mio"],
    ["リャ", "ria"], ["リュ", "riu"], ["リョ", "rio"],
    ["ファ", "fa"], ["フィ", "fi"], ["フェ", "fe"], ["フォ", "fo"], ["フュ", "fiu"],
    ["ヴァ", "bha"], ["ヴィ", "bhi"], ["ヴェ", "bhe"], ["ヴォ", "bho"], ["ヴュ", "bhiu"],
    ["ティ", "ti"], ["テュ", "tiu"], ["トゥ", "tu"],
    ["ディ", "di"], ["デュ", "diu"], ["ドゥ", "du"],
    ["ウィ", "ui"], ["ウェ", "ue"], ["ウォ", "uo"],
    ["ア", "a"], ["イ", "i"], ["ウ", "u"], ["エ", "e"], ["オ", "o"],
    ["カ", "ca"], ["キ", "ci"], ["ク", "cu"], ["ケ", "ce"], ["コ", "co"],
    ["サ", "sa"], ["シ", "si"], ["ス", "su"], ["セ", "se"], ["ソ", "so"],
    ["タ", "ta"], ["チ", "ti"], ["ツ", "tu"], ["テ", "te"], ["ト", "to"],
    ["ナ", "na"], ["ニ", "ni"], ["ヌ", "nu"], ["ネ", "ne"], ["ノ", "no"],
    ["ハ", "ha"], ["ヒ", "hi"], ["フ", "fu"], ["ヘ", "he"], ["ホ", "ho"],
    ["マ", "ma"], ["ミ", "mi"], ["ム", "mu"], ["メ", "me"], ["モ", "mo"],
    ["ヤ", "ia"], ["ユ", "iu"], ["ヨ", "io"],
    ["ラ", "ra"], ["リ", "ri"], ["ル", "ru"], ["レ", "re"], ["ロ", "ro"],
    ["ワ", "ua"], ["ヲ", "uo"], ["ン", "n"],
    ["ガ", "ga"], ["ギ", "gi"], ["グ", "gu"], ["ゲ", "ge"], ["ゴ", "go"],
    ["ザ", "za"], ["ジ", "ghi"], ["ズ", "zu"], ["ゼ", "ze"], ["ゾ", "zo"],
    ["ダ", "da"], ["ヂ", "di"], ["ヅ", "du"], ["デ", "de"], ["ド", "do"],
    ["バ", "ba"], ["ビ", "bi"], ["ブ", "bu"], ["ベ", "be"], ["ボ", "bo"],
    ["パ", "pa"], ["ピ", "pi"], ["プ", "pu"], ["ペ", "pe"], ["ポ", "po"],
    ["ヴ", "bhu"]
  ].sort(function (a, b) { return b[0].length - a[0].length; });

  function hiraToKata(text) {
    return String(text || "").replace(/[\u3041-\u3096]/g, function (ch) {
      return String.fromCharCode(ch.charCodeAt(0) + 0x60);
    });
  }

  function splitHonorific(text) {
    var i, suf, src = String(text || "");
    for (i = 0; i < HONORIFICS.length; i++) {
      suf = HONORIFICS[i];
      if (src.length > suf.length && src.slice(-suf.length) === suf) {
        return { core: src.slice(0, -suf.length), hon: suf };
      }
    }
    return { core: src, hon: "" };
  }

  function isKatakanaName(text) {
    var core = splitHonorific(text).core.replace(/[・＝\-]/g, "");
    if (core.length < 2) return false;
    return /^[ァ-ヶーヴ]+$/.test(core);
  }

  function isHiraganaSpan(text) {
    var core = splitHonorific(text).core.replace(/ー/g, "");
    if (core.length < 2) return false;
    return /^[ぁ-ゖー]+$/.test(core);
  }

  function isLatinName(text, requireCapital) {
    var stripped = String(text || "").replace(/[.,!?;:]/g, "");
    if (stripped.length < 2 || !/^[A-Za-zÉéÏïÜüŸÿŒœ][A-Za-zÉéÏïÜüŸÿŒœ''\-]*$/.test(stripped)) return false;
    if (requireCapital !== false) return stripped.charAt(0) === stripped.charAt(0).toUpperCase() && /[A-ZÉÏÜŸŒ]/.test(stripped.charAt(0));
    return true;
  }

  function looksLikeProperNoun(text, nxt, copula) {
    var split = splitHonorific(text);
    var core = split.hon ? split.core : text;
    if (isKatakanaName(core)) return true;
    if (isLatinName(core, true)) return true;
    if (isHiraganaSpan(core) && (JA_PARTICLES[nxt] || copula || split.hon)) return true;
    return false;
  }

  function kanaToBaronh(text) {
    var src = hiraToKata(String(text || "").normalize("NFKC")).replace(/＝/g, "・").replace(/ヵ/g, "カ").replace(/ヶ/g, "ケ");
    var pieces = [];
    var i = 0;
    var geminate = false;
    while (i < src.length) {
      var ch = src.charAt(i);
      if ("・･/／".indexOf(ch) >= 0) { pieces.push(" "); i++; continue; }
      if (ch === "ー" || ch === "ｰ") { i++; continue; }
      if (ch === "ッ") { geminate = true; i++; continue; }
      var matched = null;
      var k;
      for (k = 0; k < KANA_BARONH.length; k++) {
        if (src.slice(i, i + KANA_BARONH[k][0].length) === KANA_BARONH[k][0]) { matched = KANA_BARONH[k]; break; }
      }
      if (!matched) { i++; continue; }
      var roman = matched[1];
      if (roman === "u" && pieces.length) {
        var prev = pieces[pieces.length - 1].replace(/\s+$/g, "");
        if (/o$/.test(prev)) { i += matched[0].length; continue; }
      }
      if (geminate && roman && "aeiouïüÿéœ".indexOf(roman.charAt(0)) < 0) {
        roman = roman.charAt(0) + roman;
        geminate = false;
      } else geminate = false;
      pieces.push(roman);
      i += matched[0].length;
    }
    return foldToAthSpelling(pieces.join("").replace(/\s+/g, " ").trim());
  }

  function foldToAthSpelling(text) {
    return String(text || "").replace(/./g, function (ch) {
      var low = ch.toLowerCase();
      if (low === "j") return "gh";
      if (low === "v") return "bh";
      if (low === "w") return "u";
      if (low === "k" || low === "q") return "c";
      if (low === "x") return "cs";
      return ch;
    });
  }

  function baronhProperNoun(stem) {
    stem = foldToAthSpelling(String(stem || "").trim());
    if (!stem) return { lemma: "", declension: "" };
    var last = stem.charAt(stem.length - 1).toLowerCase();
    if (last === "c") return { lemma: stem, declension: "3" };
    if (last === "h") return { lemma: stem, declension: "2" };
    if (last === "n") return { lemma: stem, declension: "1n" };
    if ("aiueoïüÿéœy".indexOf(last) >= 0) return { lemma: stem + "c", declension: "3" };
    return { lemma: stem + "h", declension: "2" };
  }

  function latinToBaronh(text) {
    var src = String(text || "").trim().replace(/[.,!?;:]+$/g, "");
    var out = "";
    var i = 0;
    while (i < src.length) {
      var pair = src.slice(i, i + 2).toLowerCase();
      if (pair === "th" || pair === "ch" || pair === "ph") { out += pair; i += 2; continue; }
      if (pair === "sh") { out += "ch"; i += 2; continue; }
      if (pair === "wh") { out += "u"; i += 2; continue; }
      var ch = src.charAt(i);
      var low = ch.toLowerCase();
      if (low === "j") out += "gh";
      else if (low === "v") out += "bh";
      else if (low === "w") out += "u";
      else if (low === "k" || low === "q") out += "c";
      else if (low === "x") out += "cs";
      else if (/[A-Za-zÉéÏïÜüŸÿŒœ]/.test(ch)) out += low;
      else if ("'-".indexOf(ch) >= 0) out += ch;
      i++;
    }
    return foldToAthSpelling(out);
  }

  function transcribeProperNoun(text) {
    var core = splitHonorific(String(text || "").trim()).core.replace(/[.,!?;:]+$/g, "");
    if (!core) return { lemma: "", declension: "" };
    var stem = (/[A-Za-zÉéÏïÜüŸÿŒœ]/.test(core) && !/[\u3040-\u30ff\u4e00-\u9fff]/.test(core))
      ? latinToBaronh(core)
      : kanaToBaronh(core);
    return baronhProperNoun(stem);
  }

  function transcribeProperToBaronh(text) {
    return transcribeProperNoun(text).lemma;
  }

  function phoneticNounEntry(source, lemma, declension) {
    return { lemma: lemma, pos: "noun", gloss_ja: source, gloss_en: source, tags: ["phonetic", "proper"], notes: PHONETIC_NOTE, source: "phonetic", declension: declension || "", paradigm: {} };
  }

  function tryPhoneticNoun(tok, nxt) {
    if (!looksLikeProperNoun(tok, nxt, !!JA_COPULA[nxt])) return null;
    var transcribed = transcribeProperNoun(splitHonorific(tok).core);
    if (!transcribed.lemma) return null;
    return phoneticNounEntry(tok, transcribed.lemma, transcribed.declension);
  }

  function isPhonetic(entry) {
    return entry && ((entry.tags || []).indexOf("phonetic") >= 0 || entry.source === "phonetic");
  }
  var JA_ATOMIC = ["から", "まで", "より", "である", "であります", "でした", "だった", "です", "だ"];
  var JA_FINAL_ONLY = { "か": 1, "よ": 1, "ね": 1 };
  var EN_PREP = { of: "gen", to: "dat", toward: "all", towards: "all", into: "all", from: "abl", with: "ins", by: "ins", at: "all", in: "all" };

  function norm(s) {
    return String(s || "").normalize("NFC").toLowerCase().replace(/\s+/g, "");
  }

  function type1Guess(lemma) {
    if (lemma.endsWith("h") && lemma.length >= 3) {
      var body = lemma.slice(0, -1);
      var cons = body.slice(1);
      var gen = cons + "ar";
      return { nom: lemma, acc: body + "e", gen: gen, dat: gen + "i", all: gen + "é", abl: lemma + "ar", ins: cons + "ale" };
    }
    return { nom: lemma, acc: lemma, gen: lemma, dat: lemma, all: lemma, abl: lemma, ins: lemma };
  }

  function type2(stem) {
    return { nom: stem + "h", acc: stem + "e", gen: stem + "r", dat: stem + "i", all: stem + "é", abl: stem + "har", ins: stem + "hle" };
  }

  function type3(stem) {
    return { nom: stem + "c", acc: stem + "l", gen: stem + "r", dat: stem + "ri", all: stem + "gh", abl: stem + "sar", ins: stem + "le" };
  }

  function type4(base, kind) {
    if (kind === "gac") {
      return { nom: base + "gac", acc: base + "l", gen: base + "r", dat: base + "ri", all: base + "gh", abl: base + "sar", ins: base + "le" };
    }
    return { nom: base + "iac", acc: base + "él", gen: base + "ér", dat: base + "éri", all: base + "égh", abl: base + "iasar", ins: base + "éle" };
  }

  function nounStem(entry) {
    if (entry.stem) return entry.stem;
    var lemma = entry.lemma;
    var kind = entry.declension || "";
    if (kind === "2" && lemma.endsWith("h")) return lemma.slice(0, -1);
    if (kind === "3" && lemma.endsWith("c")) return lemma.slice(0, -1);
    if (kind === "4" && lemma.endsWith("iac")) return lemma.slice(0, -3);
    if (kind === "4g" && lemma.endsWith("gac")) return lemma.slice(0, -3);
    return lemma;
  }

  function decline(entry) {
    if (entry.paradigm && Object.keys(entry.paradigm).length) {
      var out = {};
      CASES.forEach(function (c) { out[c] = entry.paradigm[c] || entry.lemma; });
      return out;
    }
    var kind = entry.declension || "";
    var stem = nounStem(entry);
    if (kind === "1" || kind === "1n") return type1Guess(entry.lemma);
    if (kind === "2") return type2(stem);
    if (kind === "3") return type3(stem);
    if (kind === "4") return type4(stem, "iac");
    if (kind === "4g") return type4(stem, "gac");
    var same = {};
    CASES.forEach(function (c) { same[c] = entry.lemma; });
    return same;
  }

  function voiceAffix(voices) {
    return VOICES.filter(function (v) { return voices.indexOf(v) >= 0; })
      .map(function (v) { return VOICE_SUFFIX[v]; }).join("");
  }

  function conjugate(entry, mood, aspect, voices) {
    var stem = entry.stem || entry.lemma;
    var ending = VERB_ENDINGS[mood + "|" + aspect];
    if (!ending) throw new Error("unsupported " + mood + "/" + aspect);
    if (mood === "imperative" && aspect === "indefinite" && /[aiuééoœïüÿy]$/i.test(stem)) ending = "éno";
    return stem + voiceAffix(voices || []) + ending;
  }

  function allVerbForms(entry) {
    var sets = [[]];
    VOICES.forEach(function (v) { sets.push([v]); });
    sets.push(["causative", "passive"]);
    sets.push(["causative", "negative"]);
    sets.push(["passive", "negative"]);
    sets.push(["causative", "passive", "negative"]);
    var rows = [];
    Object.keys(VERB_ENDINGS).forEach(function (key) {
      var parts = key.split("|");
      sets.forEach(function (vs) {
        rows.push({ mood: parts[0], aspect: parts[1], voices: vs, form: conjugate(entry, parts[0], parts[1], vs) });
      });
    });
    return rows;
  }

  function topicContract(form) {
    var map = { fe: "F'a", de: "D'a", se: "S'a" };
    return map[form.toLowerCase()] || (form + " a");
  }

  function toAthKeys(text) {
    var src = String(text || "").normalize("NFC");
    var out = "";
    for (var i = 0; i < src.length; ) {
      var pair = src.slice(i, i + 2).toLowerCase();
      if (pair === "ai") { out += "A"; i += 2; }
      else if (pair === "au") { out += "I"; i += 2; }
      else if (pair === "eu") { out += "E"; i += 2; }
      else { out += src[i]; i += 1; }
    }
    return out;
  }

  var VOWEL_KANA = { a: "ア", i: "イ", ï: "イ", u: "ウ", ü: "ウ", e: "エ", é: "エ", o: "オ", œ: "エ", y: "イ", ÿ: "イ" };
  var VOWEL_INDEX = { a: 0, i: 1, ï: 1, u: 2, ü: 2, e: 3, é: 3, œ: 3, o: 4, y: 1, ÿ: 1 };
  var CV = {
    c: "カキクケコ", k: "カキクケコ", s: "サシスセソ", t: "タチツテト", n: "ナニヌネノ",
    h: "ハヒフヘホ", p: "パピプペポ", m: "マミムメモ", r: "ラリルレロ", g: "ガギグゲゴ",
    z: "ザジズゼゾ", d: "ダヂヅデド", b: "バビブベボ", l: "ラリルレロ"
  };
  var H_DIG = { mh: "フ", bh: "ヴ", ph: "フ", th: "ス", dh: "ズ", nh: "ニ", rh: "ル", lh: "ル", ch: "シュ", gh: "ジュ", sh: "シュ" };

  function readingJa(text) {
    var src = String(text || "").normalize("NFC");
    var pieces = [];
    var i = 0;
    while (i < src.length) {
      var ch = src[i];
      if (/\s/.test(ch)) { pieces.push(" "); i++; continue; }
      if ("’'".indexOf(ch) >= 0) { i++; continue; }
      if (".,!?。".indexOf(ch) >= 0) { pieces.push("。"); i++; continue; }
      var pair = src.slice(i, i + 2).toLowerCase();
      if (pair === "ai" || pair === "au" || pair === "eu") {
        pieces.push({ ai: "アイ", au: "アウ", eu: "エウ" }[pair]);
        i += 2; continue;
      }
      if (H_DIG[pair]) {
        var nxt = (src[i + 2] || "").toLowerCase();
        if (VOWEL_KANA[nxt]) {
          if (pair === "ch" || pair === "sh") pieces.push(["シャ", "シ", "シュ", "シェ", "ショ"][VOWEL_INDEX[nxt]]);
          else if (pair === "gh") pieces.push(["ジャ", "ジ", "ジュ", "ジェ", "ジョ"][VOWEL_INDEX[nxt]]);
          else if (pair === "nh") pieces.push(["ニャ", "ニ", "ニュ", "ニェ", "ニョ"][VOWEL_INDEX[nxt]]);
          else pieces.push(H_DIG[pair] + (nxt === "u" ? "" : VOWEL_KANA[nxt]));
          i += 3; continue;
        }
        pieces.push(H_DIG[pair]);
        i += 2; continue;
      }
      var low = ch.toLowerCase();
      var n2 = (src[i + 1] || "").toLowerCase();
      if (CV[low] && VOWEL_KANA[n2]) {
        pieces.push(CV[low][VOWEL_INDEX[n2]]);
        i += 2; continue;
      }
      if (low === "f" && VOWEL_KANA[n2]) {
        pieces.push(["ファ", "フィ", "フ", "フェ", "フォ"][VOWEL_INDEX[n2]]);
        i += 2; continue;
      }
      if (VOWEL_KANA[low]) { pieces.push(VOWEL_KANA[low]); i++; continue; }
      if (low === "c" && (!n2 || /[\s.,!?;:]/.test(n2))) { i++; continue; }
      pieces.push({ c: "ク", s: "ス", t: "ト", n: "ン", r: "ル", l: "ル", m: "ム", b: "ブ", g: "グ", d: "ド", z: "ズ", h: "フ", p: "プ", f: "フ" }[low] || ch);
      i++;
    }
    return pieces.join("").replace(/\s+/g, " ").trim();
  }

  function splitJaAliases(gloss) {
    var text = String(gloss || "").replace(/（/g, "(").replace(/）/g, ")");
    var aliases = [text];
    if (text.indexOf("(") >= 0) {
      aliases.push(text.split("(")[0]);
      var inner = text.slice(text.indexOf("(") + 1, text.lastIndexOf(")"));
      if (inner) aliases.push(inner);
    }
    ["/", "・", "。", "、"].forEach(function (sep) {
      var expanded = [];
      aliases.forEach(function (alias) {
        alias.split(sep).forEach(function (part) {
          part = part.trim();
          if (part) expanded.push(part);
        });
      });
      aliases = expanded;
    });
    return aliases;
  }

  function Lexicon(entries) {
    this.entries = [];
    this.byLemma = {};
    this.byJa = {};
    this.byEn = {};
    this.generation = 0;
    var self = this;
    (entries || []).forEach(function (e) { self.add(e); });
  }

  Lexicon.prototype.add = function (entry, replace) {
    var key = norm(entry.lemma);
    if (replace) {
      this.entries = this.entries.filter(function (e) { return !(norm(e.lemma) === key && e.pos === entry.pos); });
    }
    this.entries.push(entry);
    this.byLemma[key] = (this.byLemma[key] || []).concat([entry]);
    var self = this;
    splitJaAliases(entry.gloss_ja || "").forEach(function (alias) {
      var k = norm(alias);
      self.byJa[k] = (self.byJa[k] || []).concat([entry]);
    });
    String(entry.gloss_en || "").split(/[\/,]/).forEach(function (alias) {
      var k = norm(alias);
      if (k) self.byEn[k] = (self.byEn[k] || []).concat([entry]);
    });
  };

  Lexicon.prototype.mergeDocument = function (doc) {
    var self = this;
    (doc.entries || []).forEach(function (raw) {
      if (raw.lemma) self.add(raw, true);
    });
    this.generation = (this.generation || 0) + 1;
    if (global.BaronhVectorDB) global.BaronhVectorDB.invalidateIndex();
  };

  Lexicon.prototype.lookup = function (query, lang) {
    var key = norm(query);
    if (!key) return [];
    var found = [];
    var seen = {};
    function take(arr) {
      (arr || []).forEach(function (e) {
        var id = e.lemma + "|" + e.pos + "|" + e.gloss_ja;
        if (!seen[id]) { seen[id] = true; found.push(e); }
      });
    }
    lang = lang || "auto";
    if (lang === "auto" || lang === "baronh") take(this.byLemma[key]);
    if (lang === "auto" || lang === "ja") take(this.byJa[key]);
    if (lang === "auto" || lang === "en") take(this.byEn[key]);
    if (!found.length && key.length >= 3 && !/[\u3040-\u30ff\u4e00-\u9fff]/.test(query)) {
      this.entries.forEach(function (e) {
        if ((e.lemma + " " + e.gloss_en).toLowerCase().indexOf(String(query).toLowerCase()) >= 0) take([e]);
      });
    }
    return found;
  };

  function jaQueryVariants(query) {
    var text = String(query || "").trim();
    if (!text) return [];
    var sufs = ["でしたか", "であります", "ました", "ません", "ますか", "でした", "だった", "である", "します", "する", "した", "して", "ます", "です", "だ"];
    var out = [text];
    sufs.forEach(function (suf) {
      if (text.length > suf.length && text.slice(-suf.length) === suf) {
        var stem = text.slice(0, -suf.length);
        out.push(stem);
        if (["ます", "ますか", "ました", "ません", "します"].indexOf(suf) >= 0) out.push(stem + "る");
        if (["ます", "ますか", "ました", "ません", "します", "だ", "です", "した", "して"].indexOf(suf) >= 0) out.push(stem + "する");
      }
    });
    return uniqStrings(out);
  }

  function enQueryVariants(query) {
    var text = String(query || "").trim();
    if (!text) return [];
    var low = text.toLowerCase();
    var out = [text, low];
    if (low.length > 5 && low.slice(-3) === "ing") {
      out.push(low.slice(0, -3), low.slice(0, -3) + "e");
    }
    if (low.length > 4 && low.slice(-3) === "ies") out.push(low.slice(0, -3) + "y");
    else if (low.length > 4 && low.slice(-2) === "es") out.push(low.slice(0, -2));
    else if (low.length > 3 && low.slice(-1) === "s") out.push(low.slice(0, -1));
    return uniqStrings(out);
  }

  function uniqStrings(items) {
    var seen = {};
    var out = [];
    items.forEach(function (item) {
      item = String(item || "").trim();
      if (item && !seen[item]) { seen[item] = 1; out.push(item); }
    });
    return out;
  }

  var EN_STOP = { a: 1, an: 1, the: 1, of: 1, to: 1, from: 1, with: 1, by: 1, in: 1, on: 1, at: 1, is: 1, are: 1, was: 1, were: 1, be: 1, and: 1, or: 1, i: 1, you: 1, we: 1, they: 1 };

  function foldForMatch(text) {
    var s = hiraToKata(String(text || "").normalize("NFKC"));
    s = s.replace(/ヴ/g, "ブ").replace(/ヷ/g, "バ").replace(/ヺ/g, "ボ");
    return s.replace(/[ーｰ〜~・･\s]/g, "").toLowerCase();
  }

  function withinEditDistance(left, right, limit) {
    limit = limit || 1;
    if (left === right) return true;
    if (Math.abs(left.length - right.length) > limit) return false;
    if (left.length > right.length) { var tmp = left; left = right; right = tmp; }
    var prev = [];
    var i, j;
    for (j = 0; j <= right.length; j++) prev[j] = j;
    for (i = 1; i <= left.length; i++) {
      var curr = [i];
      var rowMin = i;
      for (j = 1; j <= right.length; j++) {
        var val = Math.min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + (left.charAt(i - 1) === right.charAt(j - 1) ? 0 : 1));
        curr[j] = val;
        if (val < rowMin) rowMin = val;
      }
      if (rowMin > limit) return false;
      prev = curr;
    }
    return prev[right.length] <= limit;
  }

  function fuzzyPoints(token, alias) {
    if (!token || !alias || token === alias) return 0;
    var a = foldForMatch(token);
    var b = foldForMatch(alias);
    if (!a || !b) return 0;
    if (a === b) return 300;
    if (Math.min(a.length, b.length) < 4) return 0;
    if (/[\u3040-\u30ff\u4e00-\u9fff]/.test(a + b)) return 0;
    return withinEditDistance(a, b, 1) ? 170 : 0;
  }

  function scoreEntry(entry, haystack, tokens, fuzzyTokens) {
    var tokenSet = {};
    var tokenCf = {};
    (tokens || []).forEach(function (token) {
      tokenSet[token] = 1;
      tokenCf[String(token).toLowerCase()] = 1;
    });
    var hay = haystack || "";
    var fuzzy = fuzzyTokens || tokens || [];
    var best = 0;
    var lemma = entry.lemma || "";
    if (lemma) {
      if (tokenSet[lemma] || tokenCf[lemma.toLowerCase()]) best = Math.max(best, 500);
      else if (lemma.length >= 2 && hay.toLowerCase().indexOf(lemma.toLowerCase()) >= 0) best = Math.max(best, 280);
    }
    var jaAliases = splitJaAliases(entry.gloss_ja || "");
    var primary = (jaAliases[0] || "").trim();
    jaAliases.forEach(function (alias) {
      alias = String(alias || "").trim();
      if (!alias) return;
      var n = alias.length;
      if (n < 2 && alias !== primary) return;
      if (tokenSet[alias]) best = Math.max(best, 450 + n * 10);
      else if (n >= 2 && hay.indexOf(alias) >= 0) best = Math.max(best, 200 + n * 10);
      else {
        (tokens || []).forEach(function (token) {
          if (String(token).length < 2) return;
          if (n >= 2 && (String(token).indexOf(alias) === 0 || alias.indexOf(token) === 0)) {
            best = Math.max(best, 90 + Math.min(n, String(token).length) * 6);
          }
        });
        fuzzy.forEach(function (token) { best = Math.max(best, fuzzyPoints(token, alias)); });
      }
    });
    if (lemma) {
      fuzzy.forEach(function (token) { best = Math.max(best, fuzzyPoints(token, lemma)); });
    }
    String(entry.gloss_en || "").replace(/\//g, ",").split(",").forEach(function (alias) {
      alias = alias.trim();
      var low = alias.toLowerCase();
      if (!low || EN_STOP[low]) return;
      if (tokenSet[alias] || tokenCf[low]) best = Math.max(best, 400 + alias.length * 4);
      else if (low.length >= 3 && hay.toLowerCase().indexOf(low) >= 0) best = Math.max(best, 180 + alias.length * 4);
      else fuzzy.forEach(function (token) { best = Math.max(best, fuzzyPoints(token, alias)); });
    });
    return best;
  }

  Lexicon.prototype.rank = function (haystack, tokens, limit, fuzzyTokens) {
    limit = limit || 40;
    var expanded = [];
    var seenTok = {};
    (tokens || []).forEach(function (token) {
      jaQueryVariants(token).concat(enQueryVariants(token), [token]).forEach(function (variant) {
        if (variant && !seenTok[variant]) { seenTok[variant] = 1; expanded.push(variant); }
      });
    });
    var fuzzyExpanded = expanded;
    if (fuzzyTokens) {
      fuzzyExpanded = [];
      var seenF = {};
      fuzzyTokens.forEach(function (token) {
        jaQueryVariants(token).concat(enQueryVariants(token), [token]).forEach(function (variant) {
          if (variant && !seenF[variant]) { seenF[variant] = 1; fuzzyExpanded.push(variant); }
        });
      });
    }
    var scored = [];
    this.entries.forEach(function (entry) {
      var points = scoreEntry(entry, haystack, expanded, fuzzyExpanded);
      if (points >= 150) scored.push({ points: points, lemma: entry.lemma, entry: entry });
    });
    scored.sort(function (a, b) {
      if (b.points !== a.points) return b.points - a.points;
      return String(a.lemma).localeCompare(String(b.lemma));
    });
    var picked = [];
    var seenLemma = {};
    scored.forEach(function (row) {
      var key = norm(row.lemma);
      if (seenLemma[key] || picked.length >= limit) return;
      seenLemma[key] = 1;
      picked.push(row.entry);
    });
    return picked;
  };

  Lexicon.prototype.search = function (query, lang, limit) {
    var exact = this.lookup(query, lang || "auto");
    if (exact.length) return exact.slice(0, limit || 8);
    return this.rank(query, uniqStrings(jaQueryVariants(query).concat(enQueryVariants(query))), limit || 8);
  };

  function FormIndex(lexicon) {
    this.map = {};
    var self = this;
    lexicon.entries.forEach(function (entry) {
      if (entry.pos === "noun" || entry.pos === "pronoun") {
        var forms = decline(entry);
        CASES.forEach(function (c) { self.add(forms[c], { entry: entry, kind: entry.pos, case: c }); });
      } else if (entry.pos === "verb") {
        self.add(entry.lemma, { entry: entry, kind: "verb", mood: "indicative", aspect: "indefinite", voices: [] });
        allVerbForms(entry).forEach(function (row) {
          self.add(row.form, { entry: entry, kind: "verb", mood: row.mood, aspect: row.aspect, voices: row.voices });
        });
      } else {
        self.add(entry.lemma, { entry: entry, kind: entry.pos });
      }
    });
  }

  FormIndex.prototype.add = function (form, info) {
    var k = norm(form);
    this.map[k] = this.map[k] || [];
    this.map[k].push(info);
  };

  FormIndex.prototype.lookup = function (form) {
    return this.map[norm(form)] || [];
  };

  function tokenizeBaronh(text) {
    return String(text || "").normalize("NFC").replace(/’/g, "'")
      .match(/[A-Za-zÉéÏïÜüŸÿŒœ']+|[^\s]/g) || [];
  }

  function tokenizeEn(text) {
    return String(text || "").match(/[A-Za-z']+|[0-9]+|[^\s\w]/g) || [];
  }

  function jaBoundary(src, index) {
    if (index >= src.length) return null;
    var a, p, after, rest;
    for (a = 0; a < JA_ATOMIC.length; a++) {
      if (src.slice(index, index + JA_ATOMIC[a].length) === JA_ATOMIC[a]) return JA_ATOMIC[a];
    }
    var keys = Object.keys(JA_PARTICLES).sort(function (x, y) { return y.length - x.length; });
    for (a = 0; a < keys.length; a++) {
      p = keys[a];
      if (src.slice(index, index + p.length) !== p) continue;
      after = index + p.length;
      if (JA_FINAL_ONLY[p]) {
        rest = src.slice(after);
        if (rest === "" || "、。！？!?., \t".indexOf(rest.charAt(0)) >= 0) return p;
        continue;
      }
      return p;
    }
    return null;
  }

  function jaMatchPhrases(lexicon) {
    if (!lexicon) return [];
    var skip = {};
    Object.keys(JA_PARTICLES).forEach(function (p) { skip[p] = 1; });
    JA_ATOMIC.forEach(function (p) { skip[p] = 1; });
    var phrases = {};
    lexicon.entries.forEach(function (entry) {
      splitJaAliases(entry.gloss_ja || "").forEach(function (alias) {
        var text = String(alias || "").trim();
        if (text.length < 2 || skip[text]) return;
        phrases[text] = 1;
      });
    });
    return Object.keys(phrases).sort(function (a, b) { return b.length - a.length; });
  }

  function longestJaPhrase(src, index, phrases) {
    var i;
    for (i = 0; i < phrases.length; i++) {
      if (src.slice(index, index + phrases[i].length) === phrases[i]) return phrases[i];
    }
    return null;
  }

  function tokenizeJa(text, lexicon) {
    var tokens = [];
    var src = String(text || "").trim();
    var phrases = jaMatchPhrases(lexicon);
    var i = 0;
    while (i < src.length) {
      if (/\s/.test(src[i])) { i++; continue; }
      if ("、。！？!?.,".indexOf(src[i]) >= 0) { tokens.push(src[i]); i++; continue; }
      var particle = jaBoundary(src, i);
      var phrase = longestJaPhrase(src, i, phrases);
      if (particle && (!phrase || phrase.length <= particle.length)) {
        tokens.push(particle);
        i += particle.length;
        continue;
      }
      var j = i + 1;
      while (j < src.length && !/\s/.test(src[j]) && "、。！？!?.,".indexOf(src[j]) < 0) {
        if (jaBoundary(src, j)) break;
        j++;
      }
      var leftover = src.slice(i, j);
      if (phrase && phrase.length > leftover.length) {
        tokens.push(phrase);
        i += phrase.length;
        continue;
      }
      if (leftover) { tokens.push(leftover); i = j; continue; }
      if (phrase) { tokens.push(phrase); i += phrase.length; continue; }
      tokens.push(src[i]);
      i++;
    }
    return tokens;
  }

  function verbFeaturesJa(word) {
    var voices = [];
    var mood = "indicative";
    var aspect = "indefinite";
    var core = word;
    if (core.endsWith("か")) core = core.slice(0, -1);
    var pairs = [
      ["させられない", ["causative", "passive", "negative"]],
      ["させない", ["causative", "negative"]],
      ["されない", ["passive", "negative"]],
      ["させる", ["causative"]],
      ["される", ["passive"]],
      ["しない", ["negative"]],
      ["ない", ["negative"]],
      ["ません", ["negative"]]
    ];
    for (var i = 0; i < pairs.length; i++) {
      if (core.endsWith(pairs[i][0])) {
        voices = voices.concat(pairs[i][1]);
        core = core.slice(0, -pairs[i][0].length);
        break;
      }
    }
    if (/している$|しています$/.test(core)) { aspect = "progressive"; core = core.replace(/している$|しています$/, ""); }
    else if (/した$|しました$|た$/.test(core) && core.length > 1) { aspect = "perfect"; core = core.replace(/しました$|した$|た$/, ""); }
    else if (/しろ$|せよ$|ください$/.test(core)) { mood = "imperative"; core = core.replace(/してください$|ください$|しろ$|せよ$/, ""); }
    else if (/すれば$|なら$|ならば$/.test(core)) { mood = "subjunctive"; core = core.replace(/すれば$|ならば$|なら$/, ""); }
    core = core.replace(/します$|する$|です$|だ$/, "");
    return { stem: core || word, mood: mood, voices: voices, aspect: aspect };
  }

  function lookupJa(lexicon, word) {
    if (word.endsWith("します") || word.endsWith("する")) {
      var asSuru = word.endsWith("します") ? word.slice(0, -3) + "する" : word;
      var suruHits = lexicon.lookup(asSuru, "ja").filter(function (e) { return e.pos === "verb"; });
      if (suruHits.length) return suruHits;
    }
    var direct = lexicon.lookup(word, "ja");
    if (direct.length) return direct;
    var feat = verbFeaturesJa(word);
    if (feat.stem !== word) {
      var found = lexicon.lookup(feat.stem, "ja");
      if (found.length) return found;
    }
    var cands = [word];
    if (word.endsWith("ます") && word.length > 2) {
      var iStem = word.slice(0, -2);
      var map = { "き": "く", "ぎ": "ぐ", "し": "す", "ち": "つ", "に": "ぬ", "び": "ぶ", "み": "む", "り": "る" };
      var godan = iStem ? iStem.slice(0, -1) + (map[iStem.slice(-1)] || iStem.slice(-1)) : iStem;
      cands.push(iStem + "る", godan, iStem);
    }
    ["します", "しました", "する", "した", "です", "だ", "たち"].forEach(function (suf) {
      if (word.endsWith(suf) && word.length > suf.length) cands.push(word.slice(0, -suf.length));
    });
    for (var i = 0; i < cands.length; i++) {
      found = lexicon.lookup(cands[i], "ja");
      if (found.length) return found;
    }
    return [];
  }

  function applyCase(entry, caseName) {
    if ((entry.pos === "noun" || entry.pos === "pronoun") && CASE_PARTICLE[caseName]) {
      return decline(entry)[caseName];
    }
    return entry.lemma;
  }

  function detectLang(text, lexicon) {
    var stripped = String(text || "").trim();
    if (!stripped) return "ja";
    if (/[\u3040-\u30ff\u4e00-\u9fff]/.test(stripped)) return "ja";
    if (lexicon) {
      var index = new FormIndex(lexicon);
      var tokens = tokenizeBaronh(stripped);
      var hits = tokens.filter(function (t) { return index.lookup(t.replace(/[.,!?;:]/g, "")).length; }).length;
      if (tokens.length && hits / tokens.length >= 0.4) return "baronh";
    }
    if (/[éïüÿœÉÏÜŸŒ]|'/.test(stripped)) return "baronh";
    if (/\b(the|is|are|you|i|we|they|this|that)\b/i.test(stripped)) return "en";
    return "baronh";
  }

  function result(src, tgt, sourceText, text, analysis, notes, unknown, substitutions) {
    return {
      source_lang: src,
      target_lang: tgt,
      source_text: sourceText,
      text: text,
      engine: "local",
      ath_keys: toAthKeys(tgt === "baronh" ? text : sourceText),
      reading_ja: readingJa(tgt === "baronh" ? text : (src === "baronh" ? sourceText : text)),
      analysis: analysis || [],
      notes: notes || [],
      unknown: unknown || [],
      substitutions: substitutions || []
    };
  }

  function vectorLookup(query, lexicon) {
    var vdb = global.BaronhVectorDB;
    if (!vdb) return null;
    try {
      var hits = vdb.getIndex(lexicon).search(query, 1, 0.12);
      return hits.length ? hits[0] : null;
    } catch (err) {
      return null;
    }
  }

  function tryVectorHit(tok, lexicon, nxt) {
    if (looksLikeProperNoun(tok, nxt, !!JA_COPULA[nxt])) return null;
    return vectorLookup(tok, lexicon);
  }

  function jaToBaronh(text, lexicon, vectorSearch) {
    var tokens = tokenizeJa(text, lexicon);
    var question = /[か？?]$/.test(text.trim()) || tokens.indexOf("か") >= 0;
    var vocative = tokens.indexOf("よ") >= 0;
    var pieces = [];
    var analysis = [];
    var unknown = [];
    var substitutions = [];
    var phoneticPairs = [];
    var pending = null;
    var pendingSrc = "";

    function flush(caseName) {
      if (!pending) return;
      var form, surface;
      var mark = isPhonetic(pending) ? " / " + PHONETIC_NOTE : "";
      if (caseName === "topic") {
        form = (pending.pos === "noun" || pending.pos === "pronoun") ? decline(pending).nom : pending.lemma;
        surface = pending.pos === "pronoun" ? topicContract(form) : form + " a";
        pieces.push(surface);
        analysis.push({ source: pendingSrc + "は", target: surface, note: "主題" + mark });
      } else if (caseName === "vocative") {
        form = (pending.pos === "noun" || pending.pos === "pronoun") ? decline(pending).nom : pending.lemma;
        surface = form + " éü";
        pieces.push(surface);
        analysis.push({ source: pendingSrc + "よ", target: surface, note: "呼びかけ" + mark });
      } else {
        form = applyCase(pending, CASE_PARTICLE[caseName] ? caseName : "nom");
        pieces.push(form);
        analysis.push({ source: pendingSrc, target: form, note: (CASE_PARTICLE[caseName] || "") + mark });
      }
      pending = null;
      pendingSrc = "";
    }

    for (var i = 0; i < tokens.length; i++) {
      var tok = tokens[i];
      if ("、。！？!?.,".indexOf(tok) >= 0) continue;
      if (["です", "だ", "である", "であります", "でした", "だった"].indexOf(tok) >= 0) {
        if (pending) flush("ins");
        continue;
      }
      if (JA_PARTICLES[tok]) {
        if (pending) flush(JA_PARTICLES[tok]);
        else if (JA_PARTICLES[tok] === "question") question = true;
        continue;
      }
      var entries = lookupJa(lexicon, tok);
      if (!entries.length) {
        var hon = splitHonorific(tok);
        if (hon.hon) entries = lookupJa(lexicon, hon.core);
      }
      if (!entries.length && vectorSearch) {
        var vecHit = tryVectorHit(tok, lexicon, tokens[i + 1] || "");
        if (vecHit) {
          entries = [vecHit.entry];
          substitutions.push({
            from: tok,
            to: vecHit.entry.gloss_ja,
            lemma: vecHit.entry.lemma,
            pos: vecHit.entry.pos,
            gloss: vecHit.entry.gloss_ja,
            score: String(vecHit.score),
            via: "vector"
          });
        }
      }
      if (!entries.length) {
        var nxt0 = tokens[i + 1] || "";
        var phonetic = tryPhoneticNoun(tok, nxt0);
        if (phonetic) {
          phoneticPairs.push(tok + "→" + phonetic.lemma);
          pending = phonetic;
          pendingSrc = tok;
          continue;
        }
        unknown.push(tok);
        pieces.push(tok);
        analysis.push({ source: tok, target: tok, note: "未登録" });
        continue;
      }
      var nxt = tokens[i + 1] || "";
      var nounish = entries.find(function (e) { return e.pos === "noun" || e.pos === "pronoun" || e.pos === "adjective"; });
      var verbish = entries.find(function (e) { return e.pos === "verb"; });
      var other = entries.find(function (e) { return e.pos === "interjection" || e.pos === "adverb" || e.pos === "postposition"; });
      if (nounish && JA_PARTICLES[nxt]) { pending = nounish; pendingSrc = tok; continue; }
      if (verbish && (JA_PARTICLES[nxt] || !nxt || "。！？!?".indexOf(nxt) >= 0 || i === tokens.length - 1)) {
        flush("nom");
        var feat = verbFeaturesJa(tok);
        var form = conjugate(verbish, feat.mood, feat.aspect, feat.voices);
        pieces.push(form);
        analysis.push({ source: tok, target: form, note: verbish.gloss_ja });
        continue;
      }
      if (other && !JA_PARTICLES[nxt]) {
        pieces.push(other.lemma);
        analysis.push({ source: tok, target: other.lemma, note: other.pos });
        continue;
      }
      if (nounish) { pending = nounish; pendingSrc = tok; continue; }
      if (verbish) {
        feat = verbFeaturesJa(tok);
        form = conjugate(verbish, feat.mood, feat.aspect, feat.voices);
        pieces.push(form);
        analysis.push({ source: tok, target: form, note: verbish.gloss_ja });
        continue;
      }
      if (other) {
        pieces.push(other.lemma);
        analysis.push({ source: tok, target: other.lemma, note: other.pos });
      }
    }
    if (pending) {
      if (/です|だ|である/.test(text)) flush("ins");
      else if (vocative) flush("vocative");
      else flush("nom");
    }
    if (question && pieces.every(function (p) { return p !== "sa" && !p.endsWith(" sa"); })) {
      pieces.push("sa");
      analysis.push({ source: "か", target: "sa", note: "疑問" });
    }
    var surface = pieces.filter(Boolean).join(" ");
    if (surface && !/[.!?]$/.test(surface)) surface += question ? "?" : ".";
    var notes = [];
    if (phoneticPairs.length) notes.push(PHONETIC_SUMMARY + " " + phoneticPairs.join("、") + "。");
    if (substitutions.length) {
      notes.push("ベクトル検索: " + substitutions.map(function (item) {
        return (item.from || item.source) + "→" + item.lemma + "「" + (item.gloss || item.gloss_ja || "") + "」";
      }).join("、") + "。");
    }
    if (unknown.length) notes.push("未登録の語は原文のまま残しています。");
    return result("ja", "baronh", text, surface, analysis, notes, unknown, substitutions);
  }

  function enToBaronh(text, lexicon, vectorSearch) {
    var tokens = tokenizeEn(text);
    var question = /\?$/.test(text.trim()) || (tokens[0] && /^(is|are|do|does|can)$/i.test(tokens[0]));
    var pieces = [];
    var analysis = [];
    var unknown = [];
    var substitutions = [];
    var phoneticPairs = [];
    var pending = null;
    var pendingSrc = "";
    function flush(caseName) {
      if (!pending) return;
      var form = applyCase(pending, CASE_PARTICLE[caseName] ? caseName : "nom");
      if (caseName === "topic" && pending.pos === "pronoun") form = topicContract(decline(pending).nom);
      var mark = isPhonetic(pending) ? " / " + PHONETIC_NOTE : "";
      pieces.push(form);
      analysis.push({ source: pendingSrc, target: form, note: caseName + mark });
      pending = null;
    }
    for (var i = 0; i < tokens.length; i++) {
      var tok = tokens[i];
      var low = tok.toLowerCase();
      if (",.!?theaan".indexOf(low) >= 0 || low === "the" || low === "a" || low === "an") continue;
      if (EN_PREP[low]) { flush(EN_PREP[low]); continue; }
      var entries = lexicon.lookup(low, "en");
      if (!entries.length && low.endsWith("s")) entries = lexicon.lookup(low.slice(0, -1), "en");
      if (!entries.length && vectorSearch && !isLatinName(tok, true)) {
        var vecHit = vectorLookup(tok, lexicon) || vectorLookup(low, lexicon);
        if (vecHit) {
          entries = [vecHit.entry];
          substitutions.push({
            from: tok,
            to: vecHit.entry.gloss_ja,
            lemma: vecHit.entry.lemma,
            pos: vecHit.entry.pos,
            gloss: vecHit.entry.gloss_ja,
            score: String(vecHit.score),
            via: "vector"
          });
        }
      }
      if (!entries.length) {
        if (isLatinName(tok, true)) {
          var transcribed = transcribeProperNoun(tok);
          phoneticPairs.push(tok + "→" + transcribed.lemma);
          pending = phoneticNounEntry(tok, transcribed.lemma, transcribed.declension);
          pendingSrc = tok;
          continue;
        }
        unknown.push(tok);
        pieces.push(tok);
        continue;
      }
      var nxt = (tokens[i + 1] || "").toLowerCase();
      var nounish = entries.find(function (e) { return e.pos === "noun" || e.pos === "pronoun"; });
      var verbish = entries.find(function (e) { return e.pos === "verb"; });
      if (nounish && (EN_PREP[nxt] || /^(is|am|are)$/.test(nxt))) { pending = nounish; pendingSrc = tok; continue; }
      if (/^(is|am|are|was|were|be)$/.test(low)) { if (pending) flush("topic"); continue; }
      if (verbish) {
        flush("nom");
        var aspect = /ed$/.test(low) ? "perfect" : /ing$/.test(low) ? "progressive" : "indefinite";
        var form = conjugate(verbish, "indicative", aspect, []);
        pieces.push(form);
        analysis.push({ source: tok, target: form, note: verbish.gloss_en });
        continue;
      }
      if (nounish) { pending = nounish; pendingSrc = tok; continue; }
      pieces.push(entries[0].lemma);
    }
    if (pending) flush(tokens.some(function (t) { return /^(is|am|are)$/i.test(t); }) ? "ins" : "nom");
    if (question) pieces.push("sa");
    var surface = pieces.filter(Boolean).join(" ");
    if (surface && !/[.!?]$/.test(surface)) surface += question ? "?" : ".";
    var notes = [];
    if (phoneticPairs.length) notes.push(PHONETIC_SUMMARY + " " + phoneticPairs.join("、") + "。");
    if (substitutions.length) {
      notes.push("ベクトル検索: " + substitutions.map(function (item) {
        return (item.from || item.source) + "→" + item.lemma + "「" + (item.gloss || item.gloss_ja || "") + "」";
      }).join("、") + "。");
    }
    return result("en", "baronh", text, surface, analysis, notes, unknown, substitutions);
  }

  function baronhOut(text, lexicon, target) {
    var index = new FormIndex(lexicon);
    var tokens = tokenizeBaronh(text);
    var pieces = [];
    var analysis = [];
    var unknown = [];
    var phoneticPairs = [];
    var question = false;
    tokens.forEach(function (tok) {
      if (".!?,".indexOf(tok) >= 0) { if (tok === "?" ) question = true; return; }
      if (tok.toLowerCase() === "sa") { question = true; analysis.push({ source: tok, target: target === "ja" ? "か" : "?", note: "question" }); return; }
      if (tok.toLowerCase() === "éü") { pieces.push(target === "ja" ? "よ" : "O"); return; }
      var extras = [];
      var surface = tok;
      if (tok.indexOf("'") >= 0 && /'a$/i.test(tok)) {
        extras.push("topic");
        surface = { f: "fe", d: "de", s: "se" }[tok[0].toLowerCase()] || surface;
      }
      var hits = index.lookup(surface);
      if (!hits.length) {
        if (/^[A-Za-zÉéÏïÜüŸÿŒœ][A-Za-zÉéÏïÜüŸÿŒœ''\-]*$/.test(tok)) {
          if (target === "ja") {
            var kana = readingJa(tok);
            pieces.push(kana);
            analysis.push({ source: tok, target: kana, note: PHONETIC_NOTE });
            phoneticPairs.push(tok + "→" + kana);
          } else {
            pieces.push(tok);
            analysis.push({ source: tok, target: tok, note: PHONETIC_NOTE });
            phoneticPairs.push(tok);
          }
          return;
        }
        unknown.push(tok);
        pieces.push(tok);
        return;
      }
      var hit = hits[0];
      var word = target === "ja" ? (hit.entry.gloss_ja || "").split("/")[0] : (hit.entry.gloss_en || "").split("/")[0];
      if (extras[0] === "topic") word = target === "ja" ? word + "は" : word + " (topic)";
      else if (hit.case) word = target === "ja" ? word + (CASE_PARTICLE[hit.case] || "") : word + "[" + hit.case + "]";
      if (hit.mood === "imperative" && target === "ja") word += "（命令）";
      if (hit.aspect === "perfect" && target === "ja") word += "した";
      pieces.push(word);
      analysis.push({ source: tok, target: word, note: hit.entry.lemma + "「" + hit.entry.gloss_ja + "」" });
    });
    if (question) pieces.push(target === "ja" ? "か" : "?");
    var surface = target === "ja" ? pieces.join("") : pieces.join(" ");
    if (target === "ja") {
      surface = surface.replace("はが", "は");
      if (question && !/[か？]$/.test(surface)) surface += "か";
      if (surface && !/[。？！か]$/.test(surface)) surface += "。";
    }
    var notes = ["規則ベースの直訳です。"];
    if (phoneticPairs.length) notes.push(PHONETIC_SUMMARY + " " + phoneticPairs.join("、") + "。");
    return result("baronh", target, text, surface, analysis, notes, unknown);
  }

  function translate(text, lexicon, sourceLang, targetLang, options) {
    text = String(text || "").trim();
    var src = (!sourceLang || sourceLang === "auto") ? detectLang(text, lexicon) : sourceLang;
    var tgt = (!targetLang || targetLang === "auto") ? (src === "baronh" ? "ja" : "baronh") : targetLang;
    var vectorSearch = !!(options && options.vectorSearch);
    if (src === tgt) return result(src, tgt, text, text, [], [], []);
    if (src === "ja" && tgt === "baronh") return jaToBaronh(text, lexicon, vectorSearch);
    if (src === "en" && tgt === "baronh") return enToBaronh(text, lexicon, vectorSearch);
    if (src === "baronh" && (tgt === "ja" || tgt === "en")) return baronhOut(text, lexicon, tgt);
    if (src === "ja" && tgt === "en") {
      var mid = jaToBaronh(text, lexicon, vectorSearch);
      var back = baronhOut(mid.text, lexicon, "en");
      back.source_lang = "ja";
      back.source_text = text;
      back.substitutions = mid.substitutions || [];
      return back;
    }
    if (src === "en" && tgt === "ja") {
      mid = enToBaronh(text, lexicon, vectorSearch);
      back = baronhOut(mid.text, lexicon, "ja");
      back.source_lang = "en";
      back.source_text = text;
      back.substitutions = mid.substitutions || [];
      return back;
    }
    throw new Error("no local route for " + src + "->" + tgt);
  }

  var GRAMMAR_BRIEF = "あなたはアーヴ語 (Baronh) の翻訳者です。公式の完全辞書は公開されていないため、与えられた辞書・文法だけを根拠にします。下訳は規則ベースで抜けや誤りがあります。辞書と文法で直してください。原文の誤字・仮名漢字・ヴ/ブ・長音の表記ゆれは辞書の近い見出しに寄せてよい。普通名詞など辞書にない語は造語せず原文の語を残します。辞書にない固有名詞はアーヴ語の正書法で発音転記して構いません（ジ行は gh、カ行は c、主格は -c/-h/-n。j/k/w/v は使わない）。ただし辞書に近い見出しがあるなら転記より辞書を優先します。必要な語は lookup_lexicon、文法の確認は grammar_note で追加検索できます。訳文だけを出力してください。";
  var FEW_SHOT_TO_BARONH = "例（ja/en → baronh）:\n- 私は移民します → F'a usere.\n- 私はアーヴです → F'a bale.\n- 分かりますか → face sa?\n- ありがとう → zom.\n- ジントはアーヴです → ghintoc a bale.";
  var FEW_SHOT_FROM_BARONH = "例（baronh → ja/en）:\n- F'a usere. → 私は移民する / I immigrate.\n- F'a bale. → 私はアーヴだ / I am Abh.\n- face sa? → 分かりますか / Do you understand?\n- zom. → ありがとう / Thanks.";
  var CLOSED_BARONH = { a: 1, "éü": 1, sa: 1, te: 1, le: 1, lo: 1, "f'a": 1, "d'a": 1, "s'a": 1 };

  var GRAMMAR_TOPICS = {
    cases: "7格: 主格 nom（が）対格 acc（を）生格 gen（の）与格 dat（に）向格 all（へ）奪格 abl（から）具格 ins（で）。第1型 abh/abe/bar/bari/baré/abhar/bale。第2型 -h: lamh/lame/lamr/lami/lamé/lamhar/lamhle。第3型 -c。第4型 -iac。主題は代名詞で F'a。普通名詞は lemma a。",
    verbs: "動詞は語幹+態+語尾。直説法: 不定 -e, 完了 -le, 進行 -lér, 未然 -to。仮定法: -éme -lar -lérm -dar。命令 -é。態は -as- -ar- -ad-。",
    pronouns: "fe 私, de あなた, se 彼/彼女, farh 私たち, darh あなたたち, cnac 彼ら, so これ, re それ, ai あれ。fe の格: fe/fal/far/feri/feré/fasar/fale。主題 F'a。",
    syntax: "語順は SOV または SVO。修飾語は被修飾語の後ろ。後置詞: a は, éü よ, sa か, te と。AはBだ は主題+具格。疑問は sa。",
    phonology: "c は /k/。Ath キー: ai→A, au→I, eu→E。辞書にない固有名詞はアーヴ語正書法で発音転記する（ジ行は gh、カ行は ca/ci/cu/ce/co、主格は -c/-h/-n。j/k/w/v は使わない）。読み上げはローマ字を仮名に落として日本語 TTS に渡す。"
  };

  var MOOD_JA = { indicative: "直説法", subjunctive: "仮定法", imperative: "命令法", participle: "分詞" };
  var ASPECT_JA = { indefinite: "不定相", perfect: "完了相", progressive: "進行相", prospective: "未然相" };

  function grammarContext() {
    var verbLines = Object.keys(VERB_ENDINGS).map(function (key) {
      var parts = key.split("|");
      return "- " + MOOD_JA[parts[0]] + " / " + ASPECT_JA[parts[1]] + ": -" + VERB_ENDINGS[key];
    });
    return [
      "# アーヴ語文法",
      "名詞は7格: 主格 nom（が）対格 acc（を）生格 gen（の）与格 dat（に）向格 all（へ）奪格 abl（から）具格 ins（で）。",
      "第1型 abh/abe/bar/bari/baré/abhar/bale。第2型 -h: lamh/lame/lamr/lami/lamé/lamhar/lamhle。",
      "第3型 -c: duc/dul/dur/duri/dugh/dusar/dule。第4型 -iac: saidiac/saidél/saidér/saidéri/saidégh/saidiasar/saidéle。",
      "主題は代名詞で F'a / D'a / S'a（Fe+a の縮約）。普通名詞の主題は lemma a。",
      "",
      "## 動詞",
      "動詞は語幹+態+語尾。態接辞は語幹と語尾の間に使役 -as- 受動 -ar- 否定 -ad- の順。",
      "命令は母音語幹なら -éno。例: sac → sace / sacle / sacasé。"
    ].concat(verbLines, [
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
      "名詞の主格は -c / -h / -n で終わる。"
    ]).join("\n");
  }

  var AGENT_BRIEF = "あなたはアーヴ語 (Baronh) の翻訳エージェントです。公式の完全辞書は公開されていないため、\n与えられた文法コンテキストと、ベクトル検索した辞書だけを根拠に、自分で訳文を組み立てます。\n規則ベースの下訳は渡しません。なぞらないでください。\n\n目標言語がアーヴ語のとき、最優先は「辞書にある語で意味が通ること」です。\n辞書にない普通名詞は造語せず、search_lexicon（ベクトル検索）や find_synonyms で\n語釈の類義語・言い換えを探し、その見出しの格変化・活用で訳してください。\n意味がややずれても、未登録語を残すより辞書の類義語を使います。\n固有名詞は transcribe_name でアーヴ語正書法へ発音転記します\n（ジ行 gh、カ行 c、主格 -c/-h/-n。j/k/w/v は使わない）。\n文法は下のコンテキストに全文があります。grammar_note は確認用です。\n訳文だけを出力し、解説や引用符は付けないでください。";

  var FEW_SHOT_SYNONYM = "例（類義語で辞書に寄せる。文はモデルが組む）:\n- 星たちの光を見ます → 光は辞書に無いので 輝くもの (sairiac) に寄せ、gereulacr sairiac mire.\n- 私はアーヴです → F'a bale.\n- ジントはアーヴです → ghintoc a bale.（ジントは固有名詞の発音転記）";

  var AGENT_TOOLS = [
    { type: "function", function: { name: "search_lexicon", description: "アーヴ語辞書のベクトル検索。日本語・英語・アーヴ語の意味に近い見出しを返す。", parameters: { type: "object", properties: { query: { type: "string" }, limit: { type: "integer" } }, required: ["query"] } } },
    { type: "function", function: { name: "lookup_lexicon", description: "辞書の厳密検索。lemma / gloss / alias の近い一致。", parameters: { type: "object", properties: { query: { type: "string" }, lang: { type: "string", enum: ["auto", "baronh", "ja", "en"] } }, required: ["query"] } } },
    { type: "function", function: { name: "find_synonyms", description: "未登録の普通名詞を辞書語釈の類義語へ寄せる。固有名詞には使わない。", parameters: { type: "object", properties: { query: { type: "string" }, extra_keys: { type: "array", items: { type: "string" } } }, required: ["query"] } } },
    { type: "function", function: { name: "transcribe_name", description: "固有名詞をアーヴ語音写する。ジ行は gh、カ行は c、ヴは bh。", parameters: { type: "object", properties: { name: { type: "string" } }, required: ["name"] } } },
    { type: "function", function: { name: "grammar_note", description: "文法トピックを取り出す。", parameters: { type: "object", properties: { topic: { type: "string", enum: ["cases", "verbs", "pronouns", "syntax", "phonology"] } }, required: ["topic"] } } },
    { type: "function", function: { name: "validate_baronh", description: "生成したアーヴ語のうち辞書語形でも発音転記でもない語を列挙する。", parameters: { type: "object", properties: { text: { type: "string" } }, required: ["text"] } } }
  ];
  var CHAT_TOOLS = AGENT_TOOLS;

  function formatEntry(entry) {
    var line = "- " + entry.lemma + " [" + entry.pos + "] ja:" + entry.gloss_ja + " en:" + (entry.gloss_en || "");
    if (entry.pos === "noun" || entry.pos === "pronoun") {
      var forms = decline(entry);
      line += " " + CASES.map(function (c) { return forms[c]; }).join("/");
    } else if (entry.pos === "verb") {
      line += " 活用:" + [
        conjugate(entry, "indicative", "indefinite", []),
        conjugate(entry, "indicative", "perfect", []),
        conjugate(entry, "indicative", "progressive", []),
        conjugate(entry, "imperative", "indefinite", [])
      ].join("/");
    }
    return line;
  }

  function formatEntryLine(entry, score) {
    var line = formatEntry(entry);
    if (score != null && isFinite(score)) line += " score=" + Number(score).toFixed(3);
    return line;
  }

  var JA_MORPH = ["するもの", "すること", "もの", "こと", "する", "した", "して", "します", "される", "られる", "れる", "い", "な", "る", "り", "み", "き", "く", "ん"];
  var COMPOUND_MARKERS = ["の", "・", "／", "/", "（", "(", "〔", "[", "、"];

  function kanjiOf(text) {
    return (String(text || "").match(/[\u4e00-\u9fff]/g) || []).join("");
  }

  function isSimpleAlias(alias) {
    var text = String(alias || "").trim();
    if (!text || text.length > 8) return false;
    var i;
    for (i = 0; i < COMPOUND_MARKERS.length; i++) {
      if (text.indexOf(COMPOUND_MARKERS[i]) >= 0) return false;
    }
    return kanjiOf(text).length <= 3;
  }

  function tooSpecific(query, alias) {
    var q = String(query || "").trim();
    var a = String(alias || "").trim();
    if (!q || !a) return true;
    if (q === a) return false;
    if (a.indexOf(q) >= 0 && a.length >= q.length + 3) return true;
    var qk = kanjiOf(q);
    var ak = kanjiOf(a);
    if (qk && ak && ak.indexOf(qk) >= 0 && ak.length >= qk.length + 2) return true;
    return false;
  }

  function morphKeys(query) {
    var text = String(query || "").trim();
    if (!text) return [];
    var out = [];
    var seen = {};
    function take(item) {
      if (item && !seen[item]) { seen[item] = 1; out.push(item); }
    }
    jaQueryVariants(text).concat(enQueryVariants(text), [text]).forEach(function (variant) {
      take(variant);
      if (!variant) return;
      JA_MORPH.forEach(function (suf) {
        if (variant.length > suf.length && variant.slice(-suf.length) === suf) take(variant.slice(0, -suf.length));
        take(variant + suf);
      });
    });
    return out;
  }

  function aliasCandidates(entry) {
    var aliases = [];
    var seen = {};
    [entry.gloss_ja, entry.gloss_en, entry.lemma].forEach(function (raw) {
      splitJaAliases(raw || "").forEach(function (alias) {
        var text = String(alias || "").trim();
        var key = norm(text);
        if (!text || seen[key]) return;
        seen[key] = 1;
        aliases.push(text);
      });
      String(raw || "").split(/[,/;]/).forEach(function (part) {
        var text = part.trim();
        var key = norm(text);
        if (!text || seen[key]) return;
        seen[key] = 1;
        aliases.push(text);
      });
    });
    return aliases;
  }

  function findSynonyms(query, lexicon, extraKeys, limit) {
    var text = String(query || "").trim();
    limit = limit || 6;
    if (!text || JA_PARTICLES[text]) return [];
    var hits = [];
    var seen = {};
    function take(entry, via, relation, score) {
      var key = norm(entry.lemma) + "|" + entry.pos;
      if (seen[key]) return;
      seen[key] = 1;
      hits.push({ query: text, entry: entry, via: via, relation: relation, score: score });
    }
    lexicon.lookup(text, "auto").forEach(function (entry) { take(entry, text, "exact", 1000); });
    var keysMap = global.BaronhVectorDB && global.BaronhVectorDB.PARAPHRASE_KEYS || {};
    var paraphrase = [].concat(keysMap[text] || [], keysMap[String(text).toLowerCase()] || []);
    paraphrase.forEach(function (key, offset) {
      lexicon.lookup(key, "auto").forEach(function (entry) { take(entry, key, "paraphrase", 760 - offset); });
    });
    var keys = [];
    morphKeys(text).concat(extraKeys || []).forEach(function (item) {
      if (item && item !== text && keys.indexOf(item) < 0) keys.push(item);
    });
    keys.forEach(function (key) {
      lexicon.lookup(key, "auto").forEach(function (entry) { take(entry, key, "morph", 820); });
    });
    var folded = {};
    keys.concat([text], paraphrase).forEach(function (k) { folded[norm(k)] = 1; });
    lexicon.entries.forEach(function (entry) {
      if (seen[norm(entry.lemma) + "|" + entry.pos]) return;
      var aliases = aliasCandidates(entry);
      var i;
      for (i = 0; i < aliases.length; i++) {
        var alias = aliases[i];
        if (!isSimpleAlias(alias) || tooSpecific(text, alias)) continue;
        if (folded[norm(alias)]) {
          take(entry, alias, paraphrase.indexOf(alias) >= 0 ? "paraphrase" : "morph", 640);
          return;
        }
        var qk = kanjiOf(text);
        var ak = kanjiOf(alias);
        if (qk && ak === qk && alias.length <= text.length + 2) {
          take(entry, alias, "stem", 520);
          return;
        }
      }
    });
    hits.sort(function (a, b) {
      if (b.score !== a.score) return b.score - a.score;
      return String(a.entry.lemma).localeCompare(String(b.entry.lemma));
    });
    return hits.slice(0, limit);
  }

  function sourceTokens(text, lexicon, sourceLang) {
    if (sourceLang === "en") return tokenizeEn(text);
    if (sourceLang === "baronh") return tokenizeBaronh(text);
    return tokenizeJa(text, lexicon);
  }

  function dictionaryHints(text, lexicon, sourceLang) {
    var lines = [];
    var seen = {};
    sourceTokens(text, lexicon, sourceLang).forEach(function (tok) {
      var word = String(tok).replace(/[.,!?;:。？！]/g, "");
      if (!word || seen[word] || JA_PARTICLES[word] || "、。！？!?:.".indexOf(word) >= 0) return;
      seen[word] = 1;
      var exact = lexicon.lookup(word, "auto");
      if (exact.length) {
        lines.push("- " + word + ": 辞書 " + exact[0].lemma + " [" + exact[0].pos + "] 「" + exact[0].gloss_ja + "」");
        return;
      }
      var syn = findSynonyms(word, lexicon, [], 3);
      if (syn.length) {
        lines.push("- " + word + ": 未登録の普通名詞。類義語候補 " + syn.slice(0, 3).map(function (hit) {
          return hit.entry.lemma + "「" + hit.entry.gloss_ja + "」（" + hit.via + "）";
        }).join(" / "));
        return;
      }
      if (looksLikeProperNoun(word)) {
        lines.push("- " + word + ": 固有名詞の可能性。transcribe_name で発音転記");
        return;
      }
      lines.push("- " + word + ": 未登録。search_lexicon / find_synonyms で辞書内の言い換えを探す");
    });
    return lines.length ? lines.join("\n") : "(ヒントなし。search_lexicon で引いてください)";
  }

  function isSearchableNote(note) {
    var text = String(note || "").trim();
    if (!text || JA_PARTICLES[text] || text === "主題") return false;
    if (/未登録|発音転記/.test(text)) return false;
    return true;
  }

  function promptTokens(text, lexicon, local) {
    var tokens = tokenizeJa(text, lexicon).concat(tokenizeEn(text));
    if (/[A-Za-zÉéÏïÜüŸÿŒœ']/.test(text)) tokens = tokens.concat(tokenizeBaronh(text));
    if (local) {
      tokens = tokens.concat(tokenizeBaronh(local.text));
      if (/[\u3040-\u30ff\u4e00-\u9fff]/.test(local.text || "")) tokens = tokens.concat(tokenizeJa(local.text, lexicon));
      (local.analysis || []).forEach(function (row) {
        if (row.source) tokens.push(row.source);
        if (row.target) tokens.push(row.target);
        if (isSearchableNote(row.note)) {
          String(row.note || "").replace(/\//g, " ").split(/\s+/).forEach(function (part) {
            if (part) tokens.push(part);
          });
        }
      });
      (local.unknown || []).forEach(function (word) { tokens.push(word); });
    }
    return uniqStrings(tokens.map(function (word) {
      return String(word || "").replace(/[.,!?;:。？！]/g, "");
    }).filter(function (word) {
      if (!word) return false;
      if (word.length === 1 && !JA_PARTICLES[word] && word !== "a" && word !== "I" && !/[\u3040-\u30ff\u4e00-\u9fff]/.test(word)) return false;
      return true;
    }));
  }

  function retrieveLexiconEntries(text, lexicon, local, limit) {
    var tokens = promptTokens(text, lexicon, local);
    var parts = [text];
    if (local) {
      parts.push(local.text);
      (local.analysis || []).forEach(function (row) { if (isSearchableNote(row.note)) parts.push(row.note); });
    }
    return lexicon.rank(parts.join("\n"), tokens, limit || 36, promptTokens(text, lexicon, null));
  }

  function retrieveLexiconContext(text, lexicon, local, limit) {
    var picked = retrieveLexiconEntries(text, lexicon, local, limit).map(formatEntry);
    return picked.length ? picked.join("\n") : "(該当なし。lookup_lexicon で追加検索してください)";
  }

  function describeGaps(local, lexicon) {
    if (!local) return "";
    var lines = [];
    var seen = {};
    function closeHits(query) {
      return lexicon && query ? lexicon.search(query, "auto", 3) : [];
    }
    (local.analysis || []).forEach(function (item) {
      if (seen[item.source]) return;
      var note = item.note || "";
      var close = closeHits(item.source);
      if (close.length && (/発音転記/.test(note) || /未登録/.test(note))) {
        seen[item.source] = 1;
        lines.push("- " + item.source + " は表記ゆれの可能性。辞書の " + close[0].lemma + "「" + close[0].gloss_ja + "」を優先" +
          (/発音転記/.test(note) ? "（発音転記 " + item.target + " より）" : ""));
        return;
      }
      if (/発音転記/.test(note)) {
        seen[item.source] = 1;
        lines.push("- " + item.source + " → " + item.target + "（固有名詞の発音転記。この語形は使ってよい）");
      } else if (/未登録/.test(note)) {
        seen[item.source] = 1;
        lines.push("- " + item.source + "（辞書にない。造語せず原文の語を残す）");
      }
    });
    (local.unknown || []).forEach(function (word) {
      if (seen[word]) return;
      seen[word] = 1;
      var close = closeHits(word);
      if (close.length) {
        lines.push("- " + word + " は表記ゆれの可能性。辞書の " + close[0].lemma + "「" + close[0].gloss_ja + "」を優先");
      } else {
        lines.push("- " + word + "（辞書にない。造語せず原文の語を残す）");
      }
    });
    return lines.join("\n");
  }

  function agentSystemPrompt(targetLang) {
    var grammar = grammarContext();
    if (targetLang === "baronh") return AGENT_BRIEF + "\n\n" + grammar + "\n\n" + FEW_SHOT_SYNONYM;
    return systemPromptLegacy(targetLang) + "\n\n" + grammar;
  }

  function systemPromptLegacy(targetLang) {
    var shot = (targetLang === "ja" || targetLang === "en") ? FEW_SHOT_FROM_BARONH : FEW_SHOT_TO_BARONH;
    var topics = Object.keys(GRAMMAR_TOPICS).map(function (name) {
      return "- " + name + ": " + GRAMMAR_TOPICS[name];
    }).join("\n");
    return GRAMMAR_BRIEF + "\n\n文法の詳細:\n" + topics + "\n" + shot;
  }

  function systemPrompt(targetLang) {
    return agentSystemPrompt(targetLang);
  }

  function buildAgentUserPrompt(text, lexicon, sourceLang, targetLang) {
    var vdb = global.BaronhVectorDB;
    var queries = [text].concat(sourceTokens(text, lexicon, sourceLang));
    var retrieved = "(ヒットなし。search_lexicon で追加検索してください)";
    if (vdb) {
      var hits = vdb.getIndex(lexicon).searchMany(queries, 16);
      if (hits.length) {
        retrieved = hits.map(function (hit) { return formatEntryLine(hit.entry, hit.score); }).join("\n");
      }
    }
    var hints = dictionaryHints(text, lexicon, sourceLang);
    return "翻訳方向: " + sourceLang + " → " + targetLang +
      "\n原文:\n" + text +
      "\n\n辞書ヒント（文ではない。訳は自分で組む）:\n" + hints +
      "\n\nベクトル検索した関連辞書（全文ではない）:\n" + retrieved +
      "\n\n訳文だけを出力してください。規則ベースの下訳はありません。" +
      "足りない普通名詞は search_lexicon または find_synonyms、見出しは lookup_lexicon、" +
      "固有名詞は transcribe_name、格はシステムプロンプトの文法か grammar_note、" +
      "書き上がったら validate_baronh を使ってください。";
  }

  function buildUserPrompt(text, lexicon, local, targetLang) {
    var sourceLang = (local && local.source_lang) || detectLang(text, lexicon);
    return buildAgentUserPrompt(text, lexicon, sourceLang, targetLang);
  }

  function phoneticDeclinedForms(lemma) {
    lemma = String(lemma || "").replace(/[.,!?;:']/g, "");
    if (!lemma || !/[A-Za-zÉéÏïÜüŸÿŒœ]/.test(lemma)) return [];
    var last = lemma.charAt(lemma.length - 1).toLowerCase();
    var kind = last === "c" ? "3" : last === "h" ? "2" : last === "n" ? "1n" : "";
    var forms = [lemma.toLowerCase()];
    var declined = decline({ lemma: lemma, pos: "noun", gloss_ja: lemma, declension: kind, paradigm: {} });
    CASES.forEach(function (c) { forms.push(String(declined[c] || "").toLowerCase()); });
    return forms;
  }

  function inventedBaronhForms(text, lexicon, local) {
    var index = new FormIndex(lexicon);
    var allowed = {};
    (local && local.analysis ? local.analysis : []).forEach(function (item) {
      if (/発音転記/.test(item.note || "")) {
        tokenizeBaronh(item.target).forEach(function (tok) {
          phoneticDeclinedForms(tok).forEach(function (form) { allowed[form] = 1; });
        });
      }
    });
    ((local && local.notes) || []).forEach(function (note) {
      var re = /→([A-Za-zÉéÏïÜüŸÿŒœ']+)/g;
      var m;
      while ((m = re.exec(String(note))) ) {
        phoneticDeclinedForms(m[1]).forEach(function (form) { allowed[form] = 1; });
      }
    });
    var invented = [];
    tokenizeBaronh(text).forEach(function (token) {
      var surface = String(token).replace(/[.,!?;:]/g, "");
      if (!surface) return;
      var key = surface.toLowerCase();
      if (CLOSED_BARONH[key] || allowed[key]) return;
      if (/[\u3040-\u30ff\u4e00-\u9fff]/.test(surface)) return;
      if (!/[A-Za-zÉéÏïÜüŸÿŒœ]/.test(surface)) return;
      if (index.lookup(surface).length) return;
      invented.push(surface);
    });
    return invented;
  }

  function cleanModelText(text) {
    var out = String(text || "").trim();
    if (out.indexOf("```") === 0) {
      var lines = out.split(/\n/);
      if (lines[0].indexOf("```") === 0) lines = lines.slice(1);
      if (lines.length && lines[lines.length - 1].trim() === "```") lines = lines.slice(0, -1);
      out = lines.join("\n").trim();
    }
    return out.replace(/^["「]+|["」]+$/g, "");
  }

  function dispatchAgentTool(name, args, lexicon, trace, local) {
    args = args || {};
    trace = trace || { substitutions: [], names: [] };
    var vdb = global.BaronhVectorDB;
    if (name === "search_lexicon") {
      var limit = parseInt(args.limit, 10);
      if (!isFinite(limit) || limit < 1) limit = 8;
      if (limit > 16) limit = 16;
      var found = vdb ? vdb.getIndex(lexicon).search(args.query || "", limit) : [];
      return JSON.stringify({
        query: args.query || "",
        hits: found.map(function (hit) {
          var row = vdb.hitToDict(hit);
          row.line = formatEntryLine(hit.entry, hit.score);
          return row;
        })
      });
    }
    if (name === "find_synonyms") {
      var extra = args.extra_keys || [];
      if (!Array.isArray(extra)) extra = [String(extra)];
      extra = extra.map(function (item) { return String(item || "").trim(); }).filter(Boolean);
      var syn = findSynonyms(args.query || "", lexicon, extra);
      if (syn.length && !trace.substitutions.some(function (item) { return item.from === (args.query || ""); })) {
        trace.substitutions.push({
          from: args.query || "",
          to: syn[0].via,
          lemma: syn[0].entry.lemma,
          gloss: syn[0].entry.gloss_ja,
          relation: syn[0].relation,
          via: syn[0].via
        });
      }
      return JSON.stringify({
        query: args.query || "",
        hits: syn.map(function (hit) {
          return {
            query: hit.query,
            lemma: hit.entry.lemma,
            pos: hit.entry.pos,
            gloss_ja: hit.entry.gloss_ja,
            gloss_en: hit.entry.gloss_en,
            via: hit.via,
            relation: hit.relation,
            score: hit.score
          };
        })
      });
    }
    if (name === "transcribe_name") {
      var rawName = String(args.name || "").trim();
      var transcribed = transcribeProperNoun(rawName);
      if (!transcribed.lemma) return JSON.stringify({ error: "empty name" });
      var entry = { lemma: transcribed.lemma, pos: "noun", gloss_ja: rawName, declension: transcribed.declension || "" };
      trace.names.push([rawName, transcribed.lemma]);
      return JSON.stringify({
        name: rawName,
        lemma: transcribed.lemma,
        declension: transcribed.declension,
        forms: decline(entry),
        note: "固有名詞の発音転記。辞書の見出しではない。"
      });
    }
    if (name === "validate_baronh") {
      return JSON.stringify({ text: args.text || "", invented: inventedBaronhForms(args.text || "", lexicon, local) });
    }
    if (name === "lookup_lexicon") {
      var hits = lexicon.search(args.query || "", args.lang || "auto", 8);
      return JSON.stringify({ query: args.query || "", hits: hits.map(formatEntry) });
    }
    if (name === "grammar_note") {
      var note = GRAMMAR_TOPICS[args.topic];
      if (!note) return JSON.stringify({ error: "unknown topic", topics: Object.keys(GRAMMAR_TOPICS) });
      return JSON.stringify({ topic: args.topic, note: note });
    }
    return JSON.stringify({ error: "unknown tool: " + name });
  }

  function dispatchTool(name, args, lexicon) {
    return dispatchAgentTool(name, args, lexicon, { substitutions: [], names: [] }, null);
  }

  function inferSubstitutions(text, generated, lexicon, sourceLang, existing) {
    var out = (existing || []).slice();
    var seen = {};
    out.forEach(function (item) { if (item.from) seen[item.from] = 1; });
    var hay = String(generated || "").toLowerCase();
    sourceTokens(text, lexicon, sourceLang).forEach(function (tok) {
      var word = String(tok).replace(/[.,!?;:。？！]/g, "");
      if (!word || seen[word] || JA_PARTICLES[word]) return;
      if (lexicon.lookup(word, "auto").length) return;
      if (looksLikeProperNoun(word)) return;
      var syn = findSynonyms(word, lexicon, [], 4);
      var i;
      for (i = 0; i < syn.length; i++) {
        var lemma = syn[i].entry.lemma;
        if (lemma && hay.indexOf(lemma.toLowerCase()) >= 0) {
          out.push({
            from: word,
            to: syn[i].via,
            lemma: lemma,
            gloss: syn[i].entry.gloss_ja,
            relation: syn[i].relation,
            via: syn[i].via
          });
          seen[word] = 1;
          break;
        }
      }
    });
    return out;
  }

  function phoneticStub(trace, sourceLang, targetLang, sourceText) {
    return {
      source_lang: sourceLang,
      target_lang: targetLang,
      source_text: sourceText,
      text: "",
      analysis: (trace.names || []).map(function (pair) {
        return { source: pair[0], target: pair[1], note: PHONETIC_NOTE };
      })
    };
  }

  function runChatToolLoop(chatOnce, messages, lexicon, trace, useTools, maxRounds) {
    function step(round) {
      if (round > maxRounds) return Promise.resolve("");
      var payload = { temperature: 0.2, messages: messages };
      if (useTools) {
        payload.tools = AGENT_TOOLS;
        payload.tool_choice = "auto";
      }
      return Promise.resolve(chatOnce(payload)).then(function (data) {
        var message = (((data && data.choices) || [])[0] || {}).message || {};
        var calls = message.tool_calls || [];
        if (!calls.length) return String(message.content || "").trim();
        messages.push(message);
        var stub = phoneticStub(trace, "", "", "");
        calls.forEach(function (call) {
          var fn = call.function || {};
          var args = {};
          try { args = JSON.parse(fn.arguments || "{}"); } catch (err) { args = {}; }
          messages.push({
            role: "tool",
            tool_call_id: call.id || fn.name,
            content: dispatchAgentTool(fn.name, args, lexicon, trace, stub)
          });
        });
        return step(round + 1);
      });
    }
    return step(1);
  }

  function translateAgent(text, lexicon, opts) {
    opts = opts || {};
    if (!opts.chatOnce) {
      return Promise.reject(new Error("ブラウザの生成 AI には API キーまたは互換 URL が必要です。規則ベースはエンジン「ローカル辞書」を使ってください。"));
    }
    text = String(text || "").trim();
    var src = (!opts.sourceLang || opts.sourceLang === "auto") ? detectLang(text, lexicon) : opts.sourceLang;
    var tgt = (!opts.targetLang || opts.targetLang === "auto") ? (src === "baronh" ? "ja" : "baronh") : opts.targetLang;
    var trace = { substitutions: [], names: [] };
    var notes = ["ブラウザの生成 AI がベクトル辞書と文法コンテキストで訳します。規則ベースの下訳は使いません。"];
    var messages = [
      { role: "system", content: agentSystemPrompt(tgt) },
      { role: "user", content: buildAgentUserPrompt(text, lexicon, src, tgt) }
    ];
    var chatOnce = opts.chatOnce;
    return runChatToolLoop(chatOnce, messages.slice(), lexicon, trace, true, opts.maxRounds || 10).catch(function (err) {
      if (/tool/i.test(err.message || "") || /400/.test(err.message || "")) {
        notes.push("ツール非対応のため生成の単発に切り替えました。規則下訳には戻しません。");
        return runChatToolLoop(chatOnce, messages.slice(), lexicon, trace, false, 3);
      }
      throw err;
    }).then(function (out) {
      out = cleanModelText(out);
      if (!out) throw new Error("生成結果が空でした。規則ベースへはフォールバックしません。");
      var stub = phoneticStub(trace, src, tgt, text);
      function maybeRewrite(textOut) {
        if (tgt !== "baronh") return Promise.resolve({ text: textOut, invented: [] });
        var invented = inventedBaronhForms(textOut, lexicon, stub);
        if (!invented.length) return Promise.resolve({ text: textOut, invented: invented });
        var critique = "次の語は辞書の語形でも発音転記でもありません: " + invented.join(", ") +
          "。造語せず、search_lexicon / find_synonyms で辞書の類義語に寄せて書き直してください。" +
          "規則ベースの下訳は無いので、自分で訳してください。訳文だけを出力してください。";
        var retry = messages.concat([
          { role: "assistant", content: textOut },
          { role: "user", content: critique }
        ]);
        return runChatToolLoop(chatOnce, retry, lexicon, trace, true, 4).then(function (rewritten) {
          rewritten = cleanModelText(rewritten);
          notes.push("辞書にない語形 " + invented.join(", ") + " を検出し、再生成しました。");
          if (rewritten) {
            var again = inventedBaronhForms(rewritten, lexicon, stub);
            if (again.length <= invented.length) {
              return { text: rewritten, invented: again };
            }
          }
          return { text: textOut, invented: invented };
        }).catch(function () {
          notes.push("語形の再生成に失敗したため、最初の生成を使います。規則下訳には戻しません。");
          return { text: textOut, invented: invented };
        });
      }
      return maybeRewrite(out);
    }).then(function (done) {
      if (done.invented && done.invented.length) notes.push("辞書にない語形: " + done.invented.join(", ") + "。");
      var substitutions = inferSubstitutions(text, done.text, lexicon, src, trace.substitutions);
      var analysis = [];
      var seen = {};
      (trace.names || []).forEach(function (pair) {
        analysis.push({ source: pair[0], target: pair[1], note: PHONETIC_NOTE });
        seen[pair[0]] = 1;
      });
      substitutions.forEach(function (item) {
        if (!item.from || seen[item.from]) return;
        analysis.push({
          source: item.from,
          target: item.lemma || "",
          note: "類義語 " + (item.gloss || "") + (item.via ? "（" + item.via + "）" : "")
        });
        seen[item.from] = 1;
      });
      return {
        source_lang: src,
        target_lang: tgt,
        source_text: text,
        text: done.text,
        engine: "openai",
        ath_keys: tgt === "baronh" ? toAthKeys(done.text) : "",
        reading_ja: tgt === "baronh" ? readingJa(done.text) : "",
        analysis: analysis,
        notes: notes,
        unknown: [],
        substitutions: substitutions
      };
    });
  }

  function parseImported(text, filename) {
    var name = (filename || "").toLowerCase();
    if (name.endsWith(".json") || text.trim().charAt(0) === "{") {
      var doc = JSON.parse(text);
      if (Array.isArray(doc)) doc = { entries: doc };
      return doc;
    }
    var entries = [];
    text.split(/\r?\n/).forEach(function (line) {
      if (!line.trim() || line.charAt(0) === "#") return;
      var parts = line.indexOf("\t") >= 0 ? line.split("\t") : line.split(",");
      if (parts.length >= 2) {
        entries.push({ lemma: parts[0].trim(), gloss_ja: parts[1].trim(), gloss_en: (parts[2] || parts[1]).trim(), pos: (parts[3] || "noun").trim() });
      }
    });
    return { entries: entries };
  }

  global.BaronhEngine = {
    CASES: CASES,
    CASE_JA: CASE_JA,
    Lexicon: Lexicon,
    FormIndex: FormIndex,
    decline: decline,
    conjugate: conjugate,
    allVerbForms: allVerbForms,
    translate: translate,
    detectLang: detectLang,
    readingJa: readingJa,
    toAthKeys: toAthKeys,
    parseImported: parseImported,
    topicContract: topicContract,
    GRAMMAR_BRIEF: GRAMMAR_BRIEF,
    GRAMMAR_TOPICS: GRAMMAR_TOPICS,
    AGENT_TOOLS: AGENT_TOOLS,
    CHAT_TOOLS: CHAT_TOOLS,
    grammarContext: grammarContext,
    agentSystemPrompt: agentSystemPrompt,
    buildAgentUserPrompt: buildAgentUserPrompt,
    retrieveLexiconContext: retrieveLexiconContext,
    retrieveLexiconEntries: retrieveLexiconEntries,
    dispatchTool: dispatchTool,
    dispatchAgentTool: dispatchAgentTool,
    findSynonyms: findSynonyms,
    translateAgent: translateAgent,
    inventedBaronhForms: inventedBaronhForms,
    buildUserPrompt: buildUserPrompt,
    systemPrompt: systemPrompt,
    describeGaps: describeGaps,
    cleanModelText: cleanModelText
  };
})(typeof window !== "undefined" ? window : globalThis);
