(function (global) {
  "use strict";

  var engine = global.BaronhEngine;
  var packs = {};
  var VOWEL_INDEX = { a: 0, i: 1, u: 2, e: 3, o: 4 };

  function catalog() {
    return Object.keys(packs).map(function (id) { return packs[id].spec; });
  }

  function isPackLang(id) {
    return !!(id && packs[id] && !packs[id].builtin);
  }

  function register(spec, lexicon) {
    if (!spec || !spec.id) return;
    packs[spec.id] = {
      spec: spec,
      lexicon: lexicon,
      builtin: !!(spec.builtin || (spec.morphology && spec.morphology.engine === "baronh") || spec.id === "baronh")
    };
  }

  function get(id) {
    return packs[id] || null;
  }

  function morph(spec) {
    return spec.morphology || {};
  }

  function syntax(spec) {
    return spec.syntax || {};
  }

  function casesOf(spec) {
    return morph(spec).cases || engine.CASES;
  }

  function nounStem(entry, spec) {
    if (entry.stem) return entry.stem;
    var kind = entry.declension || morph(spec).default_noun || "a";
    var decl = (morph(spec).declensions || {})[kind] || {};
    var drop = (decl.stem && decl.stem.drop_suffix) || decl.drop_suffix || "";
    var lemma = entry.lemma || "";
    if (drop && lemma.slice(-drop.length) === drop) {
      var body = lemma.slice(0, -drop.length);
      return body || lemma;
    }
    return lemma;
  }

  function decline(entry, spec) {
    var caseNames = casesOf(spec);
    if (entry.paradigm) {
      var fromPara = {};
      caseNames.forEach(function (c) { fromPara[c] = entry.paradigm[c] || entry.lemma; });
      return fromPara;
    }
    var kind = entry.declension || morph(spec).default_noun || "a";
    var decl = (morph(spec).declensions || {})[kind];
    if (!decl) {
      var same = {};
      caseNames.forEach(function (c) { same[c] = entry.lemma; });
      return same;
    }
    var stem = nounStem(entry, spec);
    var suffixes = decl.suffixes || {};
    var forms = {};
    caseNames.forEach(function (c) { forms[c] = stem + (suffixes[c] || ""); });
    return forms;
  }

  function conjugate(entry, spec, mood, aspect, voices) {
    mood = mood || "indicative";
    aspect = aspect || "indefinite";
    voices = voices || [];
    var stem = entry.stem || entry.lemma;
    var voiceMap = morph(spec).voice_suffix || {};
    var order = morph(spec).voices || ["causative", "passive", "negative"];
    var affix = "";
    var wanted = {};
    voices.forEach(function (v) { wanted[v] = 1; });
    order.forEach(function (name) {
      if (wanted[name]) affix += voiceMap[name] || "";
    });
    var endings = morph(spec).verb_endings || {};
    var ending = endings[mood + "|" + aspect];
    if (ending == null) ending = endings["indicative|indefinite"] || "";
    return stem + affix + ending;
  }

  function allVerbForms(entry, spec) {
    var endings = morph(spec).verb_endings || {};
    var voicesList = morph(spec).voices || [];
    var sets = [[]];
    voicesList.forEach(function (v) { sets.push([v]); });
    if (voicesList.length >= 2) sets.push(voicesList.slice(0, 2));
    if (voicesList.length >= 3) sets.push(voicesList.slice());
    var rows = [];
    sets.forEach(function (vs) {
      Object.keys(endings).forEach(function (key) {
        var parts = key.split("|");
        rows.push({
          mood: parts[0],
          aspect: parts[1],
          voices: vs,
          form: conjugate(entry, spec, parts[0], parts[1], vs)
        });
      });
    });
    return rows;
  }

  function topicForm(entry, spec) {
    var syn = syntax(spec).topic || {};
    var forms = decline(entry, spec);
    var nom = forms[syn.form || "nom"] || entry.lemma;
    var contract = syn.pronoun_contract || {};
    if (entry.pos === "pronoun" && contract[String(nom).toLowerCase()]) {
      return contract[String(nom).toLowerCase()];
    }
    var particle = syn.particle || "";
    if (!particle) return nom;
    return syn.position === "before" ? (particle + " " + nom).trim() : (nom + " " + particle).trim();
  }

  function vocativeForm(entry, spec) {
    var syn = syntax(spec).vocative || {};
    var forms = decline(entry, spec);
    var nom = forms[syn.form || "nom"] || entry.lemma;
    var particle = syn.particle || "";
    if (!particle) return nom;
    return syn.position === "before" ? (particle + " " + nom).trim() : (nom + " " + particle).trim();
  }

  function applyCase(entry, spec, caseName) {
    if ((entry.pos === "noun" || entry.pos === "pronoun") && (morph(spec).case_particle_ja || {})[caseName]) {
      return decline(entry, spec)[caseName];
    }
    return entry.lemma;
  }

  function PackFormIndex(spec, lexicon) {
    this.map = {};
    var self = this;
    lexicon.entries.forEach(function (entry) {
      if (entry.pos === "noun" || entry.pos === "pronoun") {
        var forms = decline(entry, spec);
        Object.keys(forms).forEach(function (c) {
          self.add(forms[c], { entry: entry, kind: entry.pos, case: c, extras: [] });
        });
        self.add(topicForm(entry, spec), { entry: entry, kind: entry.pos, extras: ["topic"] });
      } else if (entry.pos === "verb") {
        self.add(entry.lemma, { entry: entry, kind: "verb", mood: "indicative", aspect: "indefinite", voices: [], extras: [] });
        allVerbForms(entry, spec).forEach(function (row) {
          self.add(row.form, { entry: entry, kind: "verb", mood: row.mood, aspect: row.aspect, voices: row.voices, extras: [] });
        });
      } else {
        self.add(entry.lemma, { entry: entry, kind: entry.pos, extras: [] });
      }
    });
    ((spec.closed_forms) || []).forEach(function (form) {
      self.add(form, { entry: { lemma: form, pos: "particle", gloss_ja: form, gloss_en: form }, kind: "particle", extras: [] });
    });
  }

  PackFormIndex.prototype.add = function (form, info) {
    var k = String(form || "").toLowerCase();
    if (!k) return;
    this.map[k] = this.map[k] || [];
    this.map[k].push(info);
  };

  PackFormIndex.prototype.lookup = function (form) {
    return this.map[String(form || "").toLowerCase()] || [];
  };

  function jaParticles(spec) {
    var map = Object.assign({}, engine.JA_PARTICLES);
    Object.assign(map, (syntax(spec).ja_particles) || {});
    return map;
  }

  function enPrep(spec) {
    var map = Object.assign({}, engine.EN_PREP);
    Object.assign(map, (syntax(spec).en_prep) || {});
    return map;
  }

  function analyzeJa(text, lexicon, spec) {
    var tokens = engine.tokenizeJa(text, lexicon);
    var particles = jaParticles(spec);
    var copula = engine.JA_COPULA;
    var question = /[か？?]$/.test(text.trim()) || tokens.indexOf("か") >= 0;
    var vocative = tokens.indexOf("よ") >= 0;
    var slots = [];
    var unknown = [];
    var pending = null;
    var pendingSrc = "";

    function flush(role) {
      if (!pending) return;
      slots.push({ source: pendingSrc, role: role, entry: pending });
      pending = null;
      pendingSrc = "";
    }

    var i, tok, nxt, entries, nounish, verbish, other, feat;
    for (i = 0; i < tokens.length; i++) {
      tok = tokens[i];
      if ("、。！？!?.,".indexOf(tok) >= 0) continue;
      if (copula[tok]) {
        if (pending) flush("ins");
        continue;
      }
      if (particles[tok]) {
        if (pending) flush(particles[tok]);
        else if (particles[tok] === "question") question = true;
        else if (particles[tok] === "vocative") vocative = true;
        continue;
      }
      entries = engine.lookupJa(lexicon, tok);
      if (!entries.length) {
        unknown.push(tok);
        slots.push({ source: tok, role: "unknown" });
        continue;
      }
      nxt = tokens[i + 1] || "";
      nounish = entries.filter(function (e) { return e.pos === "noun" || e.pos === "pronoun" || e.pos === "adjective"; })[0];
      verbish = entries.filter(function (e) { return e.pos === "verb"; })[0];
      other = entries.filter(function (e) { return e.pos === "interjection" || e.pos === "adverb" || e.pos === "postposition"; })[0];
      if (nounish && particles[nxt]) { pending = nounish; pendingSrc = tok; continue; }
      if (verbish) {
        flush("nom");
        feat = engine.verbFeaturesJa(tok);
        slots.push({ source: tok, role: "verb", entry: verbish, mood: feat.mood, aspect: feat.aspect, voices: feat.voices });
        continue;
      }
      if (other && !particles[nxt]) {
        slots.push({ source: tok, role: other.pos, entry: other });
        continue;
      }
      if (nounish) { pending = nounish; pendingSrc = tok; continue; }
      unknown.push(tok);
    }
    if (pending) {
      if (/(です|だ|である)\s*$/.test(text.trim())) flush("ins");
      else if (vocative) flush("vocative");
      else flush("nom");
    }
    if (question) slots.push({ source: "か", role: "question" });
    return { slots: slots, unknown: unknown };
  }

  function analyzeEn(text, lexicon, spec) {
    var tokens = engine.tokenizeEn(text);
    var prep = enPrep(spec);
    var question = /\?\s*$/.test(text) || (tokens[0] && /^(is|are|do|does|can)$/i.test(tokens[0]));
    var slots = [];
    var unknown = [];
    var pending = null;
    var pendingSrc = "";
    var seenVerb = false;

    function flush(role) {
      if (!pending) return;
      slots.push({ source: pendingSrc, role: role, entry: pending });
      pending = null;
      pendingSrc = "";
    }

    var i, tok, low, nxt, entries, nounish, verbish;
    for (i = 0; i < tokens.length; i++) {
      tok = tokens[i];
      low = tok.toLowerCase();
      if (",.!?".indexOf(low) >= 0 || low === "the" || low === "a" || low === "an") continue;
      if (prep[low]) { flush(prep[low]); continue; }
      entries = lexicon.lookup(low, "en");
      if (!entries.length && /s$/.test(low)) entries = lexicon.lookup(low.slice(0, -1), "en");
      if (!entries.length) {
        unknown.push(tok);
        slots.push({ source: tok, role: "unknown" });
        continue;
      }
      nxt = tokens[i + 1] ? tokens[i + 1].toLowerCase() : "";
      nounish = entries.filter(function (e) { return e.pos === "noun" || e.pos === "pronoun"; })[0];
      verbish = entries.filter(function (e) { return e.pos === "verb"; })[0];
      if (nounish && (prep[nxt] || /^(is|am|are)$/.test(nxt))) { pending = nounish; pendingSrc = tok; continue; }
      if (/^(is|am|are|was|were|be)$/.test(low)) {
        if (pending) flush("topic");
        continue;
      }
      if (verbish) {
        flush("nom");
        seenVerb = true;
        slots.push({
          source: tok,
          role: "verb",
          entry: verbish,
          mood: "indicative",
          aspect: /ed$/.test(low) ? "perfect" : (/ing$/.test(low) ? "progressive" : "indefinite"),
          voices: []
        });
        continue;
      }
      if (nounish) { pending = nounish; pendingSrc = tok; continue; }
      slots.push({ source: tok, role: entries[0].pos, entry: entries[0] });
    }
    if (pending) {
      if (tokens.some(function (t) { return /^(is|am|are)$/i.test(t); })) flush("ins");
      else if (seenVerb) flush("acc");
      else flush("nom");
    }
    if (question) slots.push({ source: "?", role: "question" });
    return { slots: slots, unknown: unknown };
  }

  function realize(slots, spec, sourceLang, sourceText, unknown) {
    var pieces = [];
    var analysis = [];
    var question = false;
    var caseParticles = morph(spec).case_particle_ja || {};
    slots.forEach(function (slot) {
      if (slot.role === "question") { question = true; return; }
      if (!slot.entry) {
        pieces.push(slot.source);
        analysis.push({ source: slot.source, target: slot.source, note: "未登録" });
        return;
      }
      var surface, note;
      if (slot.role === "topic") {
        surface = topicForm(slot.entry, spec);
        note = "主題";
      } else if (slot.role === "vocative") {
        surface = vocativeForm(slot.entry, spec);
        note = "呼びかけ";
      } else if (slot.role === "verb") {
        surface = conjugate(slot.entry, spec, slot.mood, slot.aspect, slot.voices || []);
        note = slot.entry.gloss_ja;
      } else if (caseParticles[slot.role]) {
        surface = applyCase(slot.entry, spec, slot.role);
        note = caseParticles[slot.role];
      } else {
        surface = slot.entry.lemma;
        note = slot.entry.pos;
      }
      pieces.push(surface);
      analysis.push({ source: slot.source, target: surface, note: note });
    });
    var qParticle = (syntax(spec).question || {}).particle;
    if (question && qParticle && pieces.indexOf(qParticle) < 0) {
      pieces.push(qParticle);
      analysis.push({ source: "か", target: qParticle, note: "疑問" });
    }
    var surface = pieces.filter(Boolean).join(" ");
    var mark = question ? (syntax(spec).question_mark || "?") : (syntax(spec).period || ".");
    if (surface && mark && !/[.!?]$/.test(surface)) surface += mark;
    var notes = [];
    if (unknown.length) notes.push("未登録の語は原文のまま残しています。言語パックの lexicon.json に足せます。");
    return {
      source_lang: sourceLang,
      target_lang: spec.id,
      source_text: sourceText,
      text: surface,
      engine: "transfer",
      ath_keys: "",
      reading_ja: readingJa(surface, spec),
      analysis: analysis,
      notes: notes,
      unknown: unknown,
      substitutions: []
    };
  }

  function tokenizePack(text) {
    return String(text || "").match(/[A-Za-zÉéÏïÜüŸÿŒœ']+|[^\s]/g) || [];
  }

  function translateOut(text, spec, lexicon, target) {
    var index = new PackFormIndex(spec, lexicon);
    var tokens = tokenizePack(text);
    var pieces = [];
    var analysis = [];
    var unknown = [];
    var question = false;
    var topicParticle = String((syntax(spec).topic || {}).particle || "").toLowerCase();
    var vocParticle = String((syntax(spec).vocative || {}).particle || "").toLowerCase();
    var qParticle = String((syntax(spec).question || {}).particle || "").toLowerCase();
    var caseParticles = morph(spec).case_particle_ja || {};
    var i, tok, low, nxt, hits, hit, extras, word;
    for (i = 0; i < tokens.length; i++) {
      tok = tokens[i];
      if (".!?,".indexOf(tok) >= 0) {
        if (tok === "?") question = true;
        continue;
      }
      low = tok.toLowerCase();
      if (qParticle && low === qParticle) { question = true; continue; }
      if (vocParticle && low === vocParticle) {
        pieces.push(target === "ja" ? "よ" : "O");
        continue;
      }
      nxt = tokens[i + 1] ? tokens[i + 1].toLowerCase() : "";
      hits = index.lookup(tok);
      if (!hits.length) {
        unknown.push(tok);
        pieces.push(tok);
        continue;
      }
      hit = hits[0];
      extras = (hit.extras || []).slice();
      if (topicParticle && nxt === topicParticle) {
        extras.push("topic");
        i += 1;
      }
      if (target === "ja") {
        word = String(hit.entry.gloss_ja || "").split("/")[0];
        if (extras.indexOf("topic") >= 0) word += "は";
        else if (hit.case) word += caseParticles[hit.case] || "";
        if (hit.mood === "imperative") word += "（命令）";
        else if (hit.aspect === "perfect") word += "した";
        else if (hit.aspect === "progressive") word += "している";
      } else {
        word = String(hit.entry.gloss_en || "").split("/")[0];
        if (extras.indexOf("topic") >= 0) word += " (topic)";
        else if (hit.case) word = word + "[" + hit.case + "]";
      }
      pieces.push(word);
      analysis.push({ source: tok, target: word, note: hit.entry.lemma });
    }
    var surface = target === "ja" ? pieces.join("") : pieces.join(" ");
    if (target === "ja") {
      surface = surface.replace("はが", "は").replace("がは", "は");
      if (question && !/[か？]$/.test(surface)) surface += "か";
      if (surface && !/[。？！か]$/.test(surface)) surface += "。";
    }
    return {
      source_lang: spec.id,
      target_lang: target,
      source_text: text,
      text: surface,
      engine: "transfer",
      ath_keys: "",
      reading_ja: readingJa(text, spec),
      analysis: analysis,
      notes: ["規則ベースの直訳です。語順は原文に近い語釈の連結です。"],
      unknown: unknown,
      substitutions: []
    };
  }

  function longestKeys(map) {
    return Object.keys(map || {}).sort(function (a, b) { return b.length - a.length; });
  }

  function readingJa(text, spec) {
    var ph = spec.phonology || {};
    var vowels = (ph.reading_ja && ph.reading_ja.vowels) || {};
    var cv = (ph.reading_ja && ph.reading_ja.cv) || {};
    var coda = (ph.reading_ja && ph.reading_ja.coda) || {};
    var digraphs = ph.digraphs || {};
    var silent = {};
    (ph.silent_final || []).forEach(function (s) { silent[s.toLowerCase()] = 1; });
    var src = String(text || "");
    var pieces = [];
    var i = 0;
    while (i < src.length) {
      var ch = src.charAt(i);
      if (/\s/.test(ch)) { pieces.push(" "); i += 1; continue; }
      if (".,!?;:".indexOf(ch) >= 0) { pieces.push("。"); i += 1; continue; }
      if ("'’\"-".indexOf(ch) >= 0) { i += 1; continue; }
      var matched = false;
      longestKeys(digraphs).forEach(function (key) {
        if (matched) return;
        if (src.slice(i, i + key.length).toLowerCase() === key.toLowerCase()) {
          pieces.push(vowels[digraphs[key]] || digraphs[key]);
          i += key.length;
          matched = true;
        }
      });
      if (matched) continue;
      var cons = ch.toLowerCase();
      var nxt = i + 1 < src.length ? src.charAt(i + 1).toLowerCase() : "";
      var row = cv[cons];
      if (row && VOWEL_INDEX[nxt] != null && vowels[nxt]) {
        var idx = VOWEL_INDEX[nxt];
        if (row.indexOf(",") >= 0) {
          var units = row.split(",");
          pieces.push(units[idx] || row);
        } else if (row.length === 5) {
          pieces.push(row.charAt(idx));
        } else {
          pieces.push(row);
        }
        i += 2;
        continue;
      }
      if (coda[cons] && (!nxt || /\s|[.,!?;:]/.test(nxt) || silent[nxt] || cv[nxt] || vowels[nxt])) {
        pieces.push(coda[cons]);
        i += 1;
        continue;
      }
      if (vowels[cons]) { pieces.push(vowels[cons]); i += 1; continue; }
      var atEnd = !nxt || /\s|[.,!?;:]/.test(nxt);
      if (atEnd && silent[cons]) { i += 1; continue; }
      if (row) { pieces.push(row.charAt(0)); i += 1; continue; }
      pieces.push(ch);
      i += 1;
    }
    return pieces.join("").replace(/ {2,}/g, " ").trim();
  }

  function ipa(text, spec) {
    var ph = spec.phonology || {};
    var mapping = Object.assign({}, ph.ipa || {}, ph.digraphs || {});
    var silent = {};
    (ph.silent_final || []).forEach(function (s) { silent[s.toLowerCase()] = 1; });
    var src = String(text || "");
    var pieces = [];
    var i = 0;
    while (i < src.length) {
      var ch = src.charAt(i);
      if (/\s/.test(ch)) { pieces.push(" "); i += 1; continue; }
      if (".,!?;:'’\"-".indexOf(ch) >= 0) { i += 1; continue; }
      var matched = false;
      longestKeys(mapping).forEach(function (key) {
        if (matched) return;
        if (src.slice(i, i + key.length).toLowerCase() === key.toLowerCase()) {
          var after = src.charAt(i + key.length);
          var atEnd = !after || /\s|[.,!?;:]/.test(after);
          if (silent[key.toLowerCase()] && atEnd) {
            i += key.length;
            matched = true;
            return;
          }
          pieces.push(mapping[key]);
          i += key.length;
          matched = true;
        }
      });
      if (matched) continue;
      var low = ch.toLowerCase();
      var nxt = src.charAt(i + 1);
      if ((!nxt || /\s|[.,!?;:]/.test(nxt)) && silent[low]) { i += 1; continue; }
      pieces.push(mapping[low] || low);
      i += 1;
    }
    return pieces.join("").replace(/ {2,}/g, " ").trim();
  }

  function usesPackRoute(sourceLang, targetLang) {
    return isPackLang(sourceLang) || isPackLang(targetLang);
  }

  function translate(text, sourceLang, targetLang) {
    text = String(text || "").trim();
    var src = sourceLang;
    var tgt = targetLang;
    var packId = isPackLang(src) ? src : (isPackLang(tgt) ? tgt : "");
    var rec = packId ? packs[packId] : null;
    if (!rec || rec.builtin) {
      throw new Error("no pack route for " + src + "->" + tgt);
    }
    var spec = rec.spec;
    var lexicon = rec.lexicon;
    if (!src || src === "auto") {
      if (/[\u3040-\u30ff\u4e00-\u9fff]/.test(text)) src = "ja";
      else if (/\b(the|is|are|you|i|we|they|this|that|see|go)\b/i.test(text)) src = "en";
      else src = packId;
    }
    if (!tgt || tgt === "auto") tgt = src === packId ? "ja" : packId;
    if (src === tgt) {
      return {
        source_lang: src, target_lang: tgt, source_text: text, text: text,
        engine: "transfer", ath_keys: "", reading_ja: src === packId ? readingJa(text, spec) : "",
        analysis: [], notes: [], unknown: [], substitutions: []
      };
    }
    if ((src === "ja" || src === "en") && tgt === packId) {
      var parsed = src === "ja" ? analyzeJa(text, lexicon, spec) : analyzeEn(text, lexicon, spec);
      return realize(parsed.slots, spec, src, text, parsed.unknown);
    }
    if (src === packId && (tgt === "ja" || tgt === "en")) {
      return translateOut(text, spec, lexicon, tgt);
    }
    if ((src === "ja" || src === "en") && (tgt === "ja" || tgt === "en")) {
      var midParsed = src === "ja" ? analyzeJa(text, lexicon, spec) : analyzeEn(text, lexicon, spec);
      var mid = realize(midParsed.slots, spec, src, text, midParsed.unknown);
      var back = translateOut(mid.text, spec, lexicon, tgt);
      back.source_lang = src;
      back.source_text = text;
      back.notes = (back.notes || []).concat([src + "→" + packId + "→" + tgt + " の二段翻訳です。"]);
      return back;
    }
    throw new Error("no transfer route for " + src + "->" + tgt);
  }

  global.Langpack = {
    register: register,
    get: get,
    catalog: catalog,
    isPackLang: isPackLang,
    usesPackRoute: usesPackRoute,
    translate: translate,
    decline: decline,
    conjugate: conjugate,
    allVerbForms: allVerbForms,
    readingJa: readingJa,
    ipa: ipa,
    PackFormIndex: PackFormIndex
  };
})(typeof window !== "undefined" ? window : globalThis);
