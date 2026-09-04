#!/usr/bin/env node
"use strict";

var fs = require("fs");
var path = require("path");
var vm = require("vm");
var assert = require("assert");

var ROOT = path.resolve(__dirname, "..");
var dest = process.env.VECTORS_DIR;
if (!dest) {
  console.error("VECTORS_DIR is required (python -m baronh export-web output)");
  process.exit(1);
}

var context = {
  console: console,
  JSON: JSON,
  Math: Math,
  parseInt: parseInt,
  isFinite: isFinite,
  Array: Array,
  Object: Object,
  String: String,
  Number: Number,
  Boolean: Boolean,
  Error: Error,
  ArrayBuffer: ArrayBuffer,
  Uint8Array: Uint8Array,
  Float32Array: Float32Array,
  TextEncoder: TextEncoder,
  BigInt: BigInt,
  Promise: Promise,
  setTimeout: setTimeout,
  globalThis: null
};
context.globalThis = context;
context.window = context;

function load(rel) {
  vm.runInNewContext(fs.readFileSync(path.join(ROOT, rel), "utf8"), context, { filename: rel });
}

load("web/js/vectordb.js");
load("web/js/engine.js");

var doc = JSON.parse(fs.readFileSync(path.join(dest, "lexicon.json"), "utf8"));
var lexicon = new context.BaronhEngine.Lexicon(doc.entries);
var vdb = context.BaronhVectorDB;
var engine = context.BaronhEngine;

var digest = vdb.blake2b(new TextEncoder().encode("光"), 8);
assert.strictEqual(Buffer.from(digest).toString("hex"), "e6da787a6f859e86");

assert.throws(function () { vdb.getIndex(lexicon); }, /ベクトル索引がありません/);

var meta = JSON.parse(fs.readFileSync(path.join(dest, "vectors.json"), "utf8"));
var raw = fs.readFileSync(path.join(dest, "vectors.bin"));
var copy = new Uint8Array(raw.length);
copy.set(raw);
var matrix = new Float32Array(copy.buffer);
assert.strictEqual(matrix.length, meta.count * meta.dim);
assert.strictEqual(meta.hash, vdb.INDEX_HASH);

vdb.setPrebuilt({
  dim: meta.dim,
  count: meta.count,
  hash: meta.hash,
  keys: meta.keys,
  documents: meta.documents,
  matrix: matrix
});

var q = vdb.embedText("光");
if (process.env.EMBED_LIGHT_0) {
  var expected = Number(process.env.EMBED_LIGHT_0);
  assert.ok(Math.abs(q[0] - expected) < 1e-5, "embed mismatch " + q[0] + " vs " + expected);
}

var t0 = Date.now();
var index = vdb.getIndex(lexicon);
var built = Date.now() - t0;
assert.ok(built < 2000, "prebuilt load too slow (should not rebuild): " + built);

var light = index.search("光", 8);
assert.ok(light.length, "光 should hit");
assert.strictEqual(light[0].entry.lemma, "sairiac");
var glosses = light.map(function (h) { return h.entry.gloss_ja; }).join(" ");
assert.ok(glosses.indexOf("凝集光銃") < 0, "should not swallow 凝集光銃");

var see = index.search("見る", 8);
var seeLemmas = see.map(function (h) { return h.entry.lemma; });
assert.ok(["mire", "bie", "bicoth"].some(function (lemma) { return seeLemmas.indexOf(lemma) >= 0; }));

var syn = engine.findSynonyms("光", lexicon);
assert.ok(syn.some(function (h) { return h.entry.lemma === "sairiac"; }));

var localOff = engine.translate("星たちの光を見ます", lexicon, "ja", "baronh");
assert.ok(localOff.text.indexOf("光") >= 0);
assert.strictEqual((localOff.substitutions || []).length, 0);
var localOn = engine.translate("星たちの光を見ます", lexicon, "ja", "baronh", { vectorSearch: true });
assert.ok(localOn.text.indexOf("sairiac") >= 0);
assert.ok(localOn.substitutions.some(function (item) { return item.lemma === "sairiac"; }));
var proper = engine.translate("私はジントです", lexicon, "ja", "baronh", { vectorSearch: true });
assert.ok(proper.text.indexOf("ghinto") >= 0);
assert.strictEqual((proper.substitutions || []).length, 0);

var grammar = engine.grammarContext();
assert.ok(grammar.indexOf("主格") >= 0);
assert.ok(grammar.indexOf("直説法") >= 0);
var sys = engine.agentSystemPrompt("baronh");
assert.ok(sys.indexOf(grammar) >= 0);
assert.ok(sys.indexOf("ベクトル検索") >= 0);

var user = engine.buildAgentUserPrompt("星たちの光を見ます", lexicon, "ja", "baronh");
assert.ok(user.indexOf("sairiac") >= 0);
assert.ok(user.indexOf("規則ベースの下訳（誤り") < 0);
assert.ok(user.indexOf("search_lexicon") >= 0);

var calls = 0;
engine.translateAgent("星たちの光を見ます", lexicon, {
  sourceLang: "ja",
  targetLang: "baronh",
  chatOnce: function (payload) {
    calls += 1;
    if (calls === 1) {
      var system = payload.messages[0].content;
      var u = payload.messages[1].content;
      assert.ok(system.indexOf("主格") >= 0);
      assert.ok(u.indexOf("sairiac") >= 0);
      assert.ok(payload.tools.some(function (t) { return t.function.name === "search_lexicon"; }));
      return {
        choices: [{
          message: {
            tool_calls: [{
              id: "1",
              function: { name: "search_lexicon", arguments: JSON.stringify({ query: "光" }) }
            }]
          }
        }]
      };
    }
    return { choices: [{ message: { content: "gereulacr sairiac mire." } }] };
  }
}).then(function (out) {
  assert.strictEqual(out.engine, "openai");
  assert.strictEqual(out.source_text, "星たちの光を見ます");
  assert.ok(out.text.indexOf("sairiac") >= 0);
  assert.ok(out.text.indexOf("mire") >= 0);
  assert.ok(calls >= 2);
  console.log("OK prebuilt=" + built + "ms light=" + light[0].entry.lemma + " translate=" + out.text);
}).catch(function (err) {
  console.error(err);
  process.exit(1);
});
