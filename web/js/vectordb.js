/* ブラウザ内のアーヴ語辞書ベクトル DB。
 *
 * 調査した JS/WASM 製品:
 * - EdgeVec / VantaDB / TalaDB: ブラウザ向け WASM+HNSW。npm と .wasm 配布が要る。
 * - USearch WASM: 作者自身が「ブラウザの数千件には向かない。近似検索は大規模向け」と述べている。
 * - Voy / Orama: 同様にバンドルか CDN が要る。埋め込みモデルは別途。
 *
 * このサイトは GitHub Pages の静的 JS で、辞書は約 2400 語・512 次元。
 * ここでのベクトル DB はプロセス内の Flat 索引（完全な余弦類似度）にする。
 * 行列は GitHub Actions の `python -m baronh export-web` が blake2b で事前構築し、
 * `vectors.bin` / `vectors.json` として配る。ページ読み込み時には組まない。
 * クエリとユーザー追加辞書だけ実行時に embed する。
 */
(function (global) {
  "use strict";

  var VECTOR_DIM = 512;
  var INDEX_HASH = "blake2b-8";
  var _INDEX_CACHE = { lexicon: null, generation: -1, index: null };
  var _PREBUILT = null;
  var UTF8 = new TextEncoder();

  var PARAPHRASE_KEYS = {
    "光": ["輝くもの", "輝く者", "輝き", "光る", "shine", "light", "glow"],
    "明かり": ["輝くもの", "輝く者", "light"],
    "輝き": ["輝くもの", "輝く者"],
    "光線": ["輝くもの", "凝集光"],
    light: ["輝くもの", "輝く者", "shine", "glow"],
    lights: ["輝くもの", "輝く者"],
    shine: ["輝くもの", "輝く者"],
    glow: ["輝くもの", "輝く者"],
    bright: ["輝くもの", "輝く者"],
    brightness: ["輝くもの", "輝く者"],
    "火": ["点火", "火照る"],
    "炎": ["点火"],
    fire: ["点火"],
    flame: ["点火"],
    "死": ["死ぬ"],
    death: ["死ぬ"],
    die: ["死ぬ"],
    "生": ["生きる"],
    life: ["生きる"],
    live: ["生きる"],
    "赤": ["赤い", "真っ赤に"],
    red: ["赤い"],
    "白": ["真白"],
    white: ["真白"],
    "愛": ["愛する"],
    love: ["愛する"],
    "空": ["通常空間", "真空世界"],
    sky: ["通常空間"],
    space: ["通常空間", "真空世界"],
    "声": ["口"],
    voice: ["口", "言う"],
    "食べる": ["口"],
    eat: ["口"],
    "悪い": ["敵"],
    bad: ["敵"],
    "友": ["人"],
    friend: ["人"],
    "時間": ["〔物理〕時間"],
    time: ["〔物理〕時間"]
  };

  function u64(n) {
    return BigInt.asUintN(64, typeof n === "bigint" ? n : BigInt(n));
  }

  function rotr64(x, n) {
    x = u64(x);
    n = BigInt(n);
    return u64((x >> n) | (x << (64n - n)));
  }

  var BLAKE2B_IV = [
    0x6a09e667f3bcc908n, 0xbb67ae8584caa73bn, 0x3c6ef372fe94f82bn, 0xa54ff53a5f1d36f1n,
    0x510e527fade682d1n, 0x9b05688c2b3e6c1fn, 0x1f83d9abfb41bd6bn, 0x5be0cd19137e2179n
  ];

  var SIGMA = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
    [14, 10, 4, 8, 9, 15, 13, 6, 1, 12, 0, 2, 11, 7, 5, 3],
    [11, 8, 12, 0, 5, 2, 15, 13, 10, 14, 3, 6, 7, 1, 9, 4],
    [7, 9, 3, 1, 13, 12, 11, 14, 2, 6, 5, 10, 4, 0, 15, 8],
    [9, 0, 5, 7, 2, 4, 10, 15, 14, 1, 11, 12, 6, 8, 3, 13],
    [2, 12, 6, 10, 0, 11, 8, 3, 4, 13, 7, 5, 15, 14, 1, 9],
    [12, 5, 1, 15, 14, 13, 4, 10, 0, 7, 6, 3, 9, 2, 8, 11],
    [13, 11, 7, 14, 12, 1, 3, 9, 5, 0, 15, 4, 8, 6, 2, 10],
    [6, 15, 14, 9, 11, 3, 0, 8, 12, 2, 13, 7, 1, 4, 10, 5],
    [10, 2, 8, 4, 7, 6, 1, 5, 15, 11, 9, 14, 3, 12, 13, 0],
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
    [14, 10, 4, 8, 9, 15, 13, 6, 1, 12, 0, 2, 11, 7, 5, 3]
  ];

  function load64(bytes, off) {
    var n = 0n;
    var i;
    for (i = 7; i >= 0; i--) n = (n << 8n) | BigInt(bytes[off + i]);
    return u64(n);
  }

  function store64(out, off, val) {
    var i;
    val = u64(val);
    for (i = 0; i < 8; i++) {
      out[off + i] = Number(val & 0xffn);
      val >>= 8n;
    }
  }

  function blake2bCompress(h, chunk, t, last) {
    var v = new Array(16);
    var i;
    for (i = 0; i < 8; i++) v[i] = h[i];
    for (i = 0; i < 8; i++) v[8 + i] = BLAKE2B_IV[i];
    v[12] ^= u64(t);
    v[13] ^= u64(t >> 64n);
    if (last) v[14] = u64(~v[14]);
    var m = [];
    for (i = 0; i < 16; i++) m[i] = load64(chunk, i * 8);
    function G(a, b, c, d, x, y) {
      v[a] = u64(v[a] + v[b] + x);
      v[d] = rotr64(v[d] ^ v[a], 32);
      v[c] = u64(v[c] + v[d]);
      v[b] = rotr64(v[b] ^ v[c], 24);
      v[a] = u64(v[a] + v[b] + y);
      v[d] = rotr64(v[d] ^ v[a], 16);
      v[c] = u64(v[c] + v[d]);
      v[b] = rotr64(v[b] ^ v[c], 63);
    }
    for (i = 0; i < 12; i++) {
      var s = SIGMA[i];
      G(0, 4, 8, 12, m[s[0]], m[s[1]]);
      G(1, 5, 9, 13, m[s[2]], m[s[3]]);
      G(2, 6, 10, 14, m[s[4]], m[s[5]]);
      G(3, 7, 11, 15, m[s[6]], m[s[7]]);
      G(0, 5, 10, 15, m[s[8]], m[s[9]]);
      G(1, 6, 11, 12, m[s[10]], m[s[11]]);
      G(2, 7, 8, 13, m[s[12]], m[s[13]]);
      G(3, 4, 9, 14, m[s[14]], m[s[15]]);
    }
    for (i = 0; i < 8; i++) h[i] = u64(h[i] ^ v[i] ^ v[i + 8]);
  }

  function blake2b(data, outlen) {
    outlen = outlen || 8;
    var h = BLAKE2B_IV.slice();
    h[0] ^= u64(0x01010000 ^ outlen);
    var t = 0n;
    var offset = 0;
    var chunk = new Uint8Array(128);
    while (offset + 128 <= data.length) {
      t += 128n;
      chunk.set(data.subarray(offset, offset + 128));
      blake2bCompress(h, chunk, t, false);
      offset += 128;
    }
    chunk.fill(0);
    chunk.set(data.subarray(offset));
    t += BigInt(data.length - offset);
    blake2bCompress(h, chunk, t, true);
    var out = new Uint8Array(outlen);
    var buf = new Uint8Array(64);
    var i;
    for (i = 0; i < 8; i++) store64(buf, i * 8, h[i]);
    out.set(buf.subarray(0, outlen));
    return out;
  }

  function fold(text) {
    return String(text || "").toLowerCase().replace(/\s+/g, " ").trim();
  }

  function partsOf(text) {
    var src = fold(text);
    if (!src) return [];
    var seen = {};
    var out = [];
    src.split(/[\s/・,，、]+/).concat([src]).forEach(function (part) {
      if (!part || seen[part]) return;
      seen[part] = 1;
      out.push(part);
    });
    return out;
  }

  function ngrams(text) {
    var grams = [];
    partsOf(text).forEach(function (part) {
      grams.push(part);
      var compact = part.replace(/ /g, "");
      var minSize = compact.length <= 2 ? 1 : 2;
      var size, i;
      for (size = minSize; size < 4; size++) {
        if (compact.length < size) continue;
        for (i = 0; i <= compact.length - size; i++) grams.push(compact.slice(i, i + size));
      }
    });
    return grams;
  }

  function tokenBoost(query, document) {
    var q = fold(query);
    if (!q) return 0;
    var tokens = fold(document).split(/[\s/・,，、]+/);
    var i;
    for (i = 0; i < tokens.length; i++) {
      if (tokens[i] === q) return 1;
    }
    return 0;
  }

  function u32le(bytes, off) {
    return (
      bytes[off] |
      (bytes[off + 1] << 8) |
      (bytes[off + 2] << 16) |
      (bytes[off + 3] << 24)
    ) >>> 0;
  }

  function embedText(text, dim) {
    dim = dim || VECTOR_DIM;
    var vec = new Float32Array(dim);
    var i;
    ngrams(text).forEach(function (gram) {
      var digest = blake2b(UTF8.encode(gram), 8);
      var idx = u32le(digest, 0) % dim;
      var sign = digest[4] % 2 === 0 ? 1 : -1;
      var weight = 1 + digest[5] / 255;
      vec[idx] += sign * weight;
    });
    var norm = 0;
    for (i = 0; i < dim; i++) norm += vec[i] * vec[i];
    norm = Math.sqrt(norm);
    if (norm > 0) {
      for (i = 0; i < dim; i++) vec[i] /= norm;
    }
    return vec;
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

  function bridgeTerms(entry) {
    var aliases = {};
    splitJaAliases(entry.gloss_ja).concat(splitJaAliases(entry.gloss_en || ""), [entry.lemma, entry.gloss_ja], splitJaAliases(entry.notes || "")).forEach(function (alias) {
      if (alias) aliases[alias] = 1;
    });
    if (entry.notes) aliases[entry.notes] = 1;
    var terms = [];
    Object.keys(PARAPHRASE_KEYS).forEach(function (query) {
      var keys = PARAPHRASE_KEYS[query];
      var i;
      for (i = 0; i < keys.length; i++) {
        if (aliases[keys[i]]) {
          terms.push(query);
          return;
        }
      }
    });
    return terms;
  }

  function noteSnippet(text, limit) {
    var note = String(text || "").replace(/\s+/g, " ").trim();
    limit = limit || 80;
    if (note.length > limit) return note.slice(0, limit - 1) + "…";
    return note;
  }

  function entryDocument(entry) {
    return [
      entry.lemma,
      entry.pos,
      entry.gloss_ja,
      entry.gloss_en || "",
      splitJaAliases(entry.gloss_ja).join(" "),
      entry.notes || "",
      bridgeTerms(entry).join(" ")
    ].filter(Boolean).join(" ");
  }

  function LexiconIndex(lexicon, dim) {
    this.lexicon = lexicon;
    this.dim = dim || VECTOR_DIM;
    this.generation = lexicon.generation || 0;
    this.entries = lexicon.entries.slice();
    this.documents = this.entries.map(entryDocument);
    this.matrix = new Float32Array(this.entries.length * this.dim);
    var i, vec;
    for (i = 0; i < this.entries.length; i++) {
      vec = embedText(this.documents[i], this.dim);
      this.matrix.set(vec, i * this.dim);
    }
  }

  function fromPrebuilt(lexicon, payload) {
    var dim = payload.dim || VECTOR_DIM;
    var hash = payload.hash || INDEX_HASH;
    if (hash !== INDEX_HASH) {
      throw new Error("未対応のベクトル索引 hash: " + hash);
    }
    var matrixIn = payload.matrix;
    if (!matrixIn || matrixIn.length !== payload.count * dim) {
      throw new Error("vectors.bin の大きさが keys と合いません");
    }
    var byPre = {};
    var i;
    for (i = 0; i < payload.keys.length; i++) {
      byPre[payload.keys[i]] = {
        document: payload.documents[i],
        offset: i * dim
      };
    }
    var entries = lexicon.entries.slice();
    var documents = [];
    var matrix = new Float32Array(entries.length * dim);
    var gen = lexicon.generation || 0;
    for (i = 0; i < entries.length; i++) {
      var entry = entries[i];
      var key = entry.lemma + "|" + entry.pos;
      var doc = entryDocument(entry);
      var pre = byPre[key];
      var vec;
      if (pre && (gen === 0 || pre.document === doc)) {
        vec = matrixIn.subarray(pre.offset, pre.offset + dim);
        documents.push(pre.document);
      } else {
        vec = embedText(doc, dim);
        documents.push(doc);
      }
      matrix.set(vec, i * dim);
    }
    var index = Object.create(LexiconIndex.prototype);
    index.lexicon = lexicon;
    index.dim = dim;
    index.generation = lexicon.generation || 0;
    index.entries = entries;
    index.documents = documents;
    index.matrix = matrix;
    return index;
  }

  LexiconIndex.prototype.search = function (query, limit, minScore) {
    limit = limit || 8;
    minScore = minScore == null ? 0.08 : minScore;
    var text = String(query || "").trim();
    if (!text || !this.entries.length) return [];
    var q = embedText(text, this.dim);
    var scored = [];
    var i, d, sum, score;
    for (i = 0; i < this.entries.length; i++) {
      sum = 0;
      for (d = 0; d < this.dim; d++) sum += this.matrix[i * this.dim + d] * q[d];
      score = sum + tokenBoost(text, this.documents[i]);
      if (score >= minScore) scored.push({ i: i, score: score });
    }
    scored.sort(function (a, b) { return b.score - a.score; });
    var hits = [];
    var seen = {};
    for (i = 0; i < scored.length && hits.length < limit; i++) {
      var entry = this.entries[scored[i].i];
      var key = entry.lemma + "|" + entry.pos;
      if (seen[key]) continue;
      seen[key] = 1;
      hits.push({ entry: entry, score: scored[i].score, document: this.documents[scored[i].i] });
    }
    return hits;
  };

  LexiconIndex.prototype.searchMany = function (queries, limit, minScore) {
    limit = limit || 16;
    var best = {};
    var self = this;
    (queries || []).forEach(function (query) {
      if (!String(query || "").trim()) return;
      self.search(query, limit, minScore).forEach(function (hit) {
        var key = hit.entry.lemma + "|" + hit.entry.pos;
        if (!best[key] || hit.score > best[key].score) best[key] = hit;
      });
    });
    return Object.keys(best).map(function (key) { return best[key]; })
      .sort(function (a, b) { return b.score - a.score; })
      .slice(0, limit);
  };

  function setPrebuilt(payload) {
    _PREBUILT = payload;
    invalidateIndex();
  }

  function getIndex(lexicon) {
    var gen = lexicon.generation || 0;
    if (_INDEX_CACHE.lexicon === lexicon && _INDEX_CACHE.generation === gen &&
        _INDEX_CACHE.index && _INDEX_CACHE.index.entries.length === lexicon.entries.length) {
      return _INDEX_CACHE.index;
    }
    if (!_PREBUILT) {
      throw new Error("ベクトル索引がありません。python -m baronh export-web を実行してください。");
    }
    var index = fromPrebuilt(lexicon, _PREBUILT);
    _INDEX_CACHE = { lexicon: lexicon, generation: gen, index: index };
    return index;
  }

  function invalidateIndex() {
    _INDEX_CACHE = { lexicon: null, generation: -1, index: null };
  }

  function searchContext(queries, lexicon, limit) {
    var hits = getIndex(lexicon).searchMany(queries, limit || 16);
    if (!hits.length) return "(ヒットなし。search_lexicon で追加検索してください)";
    return hits.map(function (hit) {
      var line = "- " + hit.entry.lemma + " [" + hit.entry.pos + "] ja:" + hit.entry.gloss_ja +
        " en:" + (hit.entry.gloss_en || "");
      if (hit.entry.notes) line += " notes:" + noteSnippet(hit.entry.notes);
      line += " score=" + hit.score.toFixed(3);
      return line;
    }).join("\n");
  }

  function hitToDict(hit) {
    return {
      lemma: hit.entry.lemma,
      pos: hit.entry.pos,
      gloss_ja: hit.entry.gloss_ja,
      gloss_en: hit.entry.gloss_en,
      notes: hit.entry.notes || "",
      score: Math.round(hit.score * 1000) / 1000,
      document: hit.document
    };
  }

  global.BaronhVectorDB = {
    VECTOR_DIM: VECTOR_DIM,
    INDEX_HASH: INDEX_HASH,
    PARAPHRASE_KEYS: PARAPHRASE_KEYS,
    blake2b: blake2b,
    embedText: embedText,
    entryDocument: entryDocument,
    LexiconIndex: LexiconIndex,
    fromPrebuilt: fromPrebuilt,
    setPrebuilt: setPrebuilt,
    getIndex: getIndex,
    invalidateIndex: invalidateIndex,
    searchContext: searchContext,
    hitToDict: hitToDict
  };
})(typeof window !== "undefined" ? window : globalThis);
