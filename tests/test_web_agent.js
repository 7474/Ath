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
  assert.ok(user.indexOf("関連辞書") >= 0);

var progress = [];
var toolProgress = engine.describeToolProgress([{
  function: { name: "search_lexicon", arguments: JSON.stringify({ queries: ["光", "星"] }) }
}]);
assert.strictEqual(toolProgress.phase, "tools");
assert.ok(toolProgress.message.indexOf("光") >= 0);
assert.ok(toolProgress.queries.indexOf("光") >= 0);

var calls = 0;
engine.translateAgent("星たちの光を見ます", lexicon, {
  sourceLang: "ja",
  targetLang: "baronh",
  onProgress: function (ev) { progress.push(ev); },
  chatOnce: function (payload) {
    calls += 1;
    if (calls === 1) {
      var system = payload.messages[0].content;
      var u = payload.messages[1].content;
      assert.ok(system.indexOf("主格") >= 0);
      assert.ok(u.indexOf("sairiac") >= 0);
      assert.ok(payload.tools.some(function (t) { return t.function.name === "search_lexicon"; }));
      var search = payload.tools.filter(function (t) { return t.function.name === "search_lexicon"; })[0];
      assert.strictEqual(JSON.stringify(search.function.parameters.required), JSON.stringify(["queries"]));
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
    assert.strictEqual(payload.tool_choice, "none");
    var last = payload.messages[payload.messages.length - 1].content;
    assert.ok(last.indexOf("星たちの光を見ます") >= 0);
    assert.ok(last.indexOf("省略せず") >= 0);
    return { choices: [{ message: { content: "gereulacr sairiac mire." } }] };
  }
}).then(function (out) {
  assert.strictEqual(out.engine, "openai");
  assert.strictEqual(out.source_text, "星たちの光を見ます");
  assert.ok(out.text.indexOf("sairiac") >= 0);
  assert.ok(out.text.indexOf("mire") >= 0);
  assert.ok(calls >= 2);
  assert.ok(progress.some(function (ev) { return ev.phase === "chat"; }), "chat progress");
  assert.ok(progress.some(function (ev) {
    return ev.phase === "tools" && (ev.queries || []).indexOf("光") >= 0;
  }), "tool progress");
  assert.ok(progress.some(function (ev) {
    return ev.phase === "draft" && String(ev.draft || "").indexOf("sairiac") >= 0;
  }), "draft progress");
  console.log("OK prebuilt=" + built + "ms light=" + light[0].entry.lemma + " translate=" + out.text);

  var sample = "アーヴ語翻訳機\n\nリン・ジントって奴はあれでなかなか頭の出来がいい。なんたって故郷、俺らの、ついでにアーヴ語を読み書き出来るんだからな。よく分からん言葉を喋ってると別人に見えて困る。だからと言ってアーヴ語なんて覚える気はない、覚えられない訳じゃないぜ？　とは言えアーヴ語で何を喋ってるのか気にならんこともない。てな訳で機械に翻訳機を作って貰った。これでアーヴ語の読み書きは完璧だぜ。\n\nって、何喋ってるかは分からないじゃねーか！";
  var units = engine.splitSourceUnits(sample);
  assert.ok(units.length >= 8, "units " + units.length);
  assert.strictEqual(units[0], "アーヴ語翻訳機");
  var numbered = engine.formatNumberedSource(sample);
  assert.ok(numbered.indexOf("[1]") >= 0);
  assert.ok(engine.coverageIncomplete(sample, "ringhintoc a almee éni. murrautec farh."));
  assert.ok(!engine.coverageIncomplete("私はアーヴです", "F'a bale."));
  var prompt = engine.buildAgentUserPrompt(sample, lexicon, "ja", "baronh");
  assert.ok(prompt.indexOf("[1]") >= 0);
  assert.ok(prompt.indexOf("要約禁止") >= 0);

  var longCalls = 0;
  var longSrc = "私はアーヴです。分かりますか。";
  return engine.translateAgent(longSrc, lexicon, {
    sourceLang: "ja",
    targetLang: "baronh",
    chatOnce: function (payload) {
      longCalls += 1;
      var last = payload.messages[payload.messages.length - 1];
      if (longCalls === 1) {
        return {
          choices: [{
            message: {
              tool_calls: [{
                id: "1",
                function: { name: "search_lexicon", arguments: JSON.stringify({ queries: ["アーヴ"] }) }
              }]
            }
          }]
        };
      }
      if (/未訳|欠けて/.test(last.content || "")) {
        assert.ok(payload.messages.some(function (m) { return m.role === "tool"; }));
        return { choices: [{ message: { content: "[1] F'a bale.\n[2] face sa?" } }] };
      }
      if (payload.tool_choice === "none") {
        assert.ok((last.content || "").indexOf("[1]") >= 0);
        assert.ok((last.content || "").indexOf("私はアーヴです") >= 0);
        return { choices: [{ message: { content: "F'a bale." } }] };
      }
      return { choices: [{ message: { content: "[1] F'a bale.\n[2] face sa?" } }] };
    }
  }).then(function (longOut) {
    assert.ok(longOut.text.indexOf("bale") >= 0);
    assert.ok(longOut.text.indexOf("face") >= 0);
    assert.ok(longOut.text.indexOf("[1]") < 0);
    assert.ok(longOut.text.indexOf("[2]") < 0);
    assert.strictEqual(engine.finalizeTranslation("私はアーヴです。分かりますか。", "[1] F'a bale.\n[2] face sa?"), "F'a bale.\nface sa?");
    assert.ok(longCalls >= 3, "longCalls " + longCalls);
    console.log("OK coverage=" + longOut.text.replace(/\n/g, " / "));

    var talk = engine.findSynonyms("喋る", lexicon);
    assert.ok(talk.some(function (h) {
      return ["cadase", "canse", "banas", "clare", "ie"].indexOf(h.entry.lemma) >= 0;
    }));
    assert.ok(engine.findSynonyms("俺ら", lexicon).some(function (h) { return h.entry.lemma === "farh"; }));
    assert.ok(engine.findSynonyms("完璧", lexicon).some(function (h) {
      return h.entry.lemma === "batta" || h.entry.lemma === "bata";
    }));
    assert.ok(engine.findSynonyms("翻訳機", lexicon).some(function (h) { return h.entry.lemma === "catorac"; }));
    assert.strictEqual(engine.hintQueryPieces("リン・ジントって奴").join("|"), "リン・ジント");
    assert.strictEqual(engine.nameForTranscription("リン・ジントって奴"), "リン・ジント");
    var name = JSON.parse(engine.dispatchAgentTool("transcribe_name", { name: "リン・ジントって奴" }, lexicon));
    assert.ok(name.lemma.indexOf("rin") >= 0);
    assert.ok(name.lemma.indexOf("ghint") >= 0);
    var smart = engine.resolveLexiconHits("頭の出来がいい", lexicon);
    var smartLemmas = smart.map(function (h) { return h.lemma; });
    assert.ok(smartLemmas.indexOf("almec") >= 0 || smartLemmas.indexOf("éni") >= 0);
    assert.ok(smart.every(function (h) { return (h.gloss_ja || "").indexOf("領民") < 0; }));
    var searchLight = JSON.parse(engine.dispatchAgentTool("search_lexicon", { query: "光" }, lexicon));
    assert.ok(searchLight.hits.some(function (h) { return h.lemma === "sairiac"; }));
    var searchSmart = JSON.parse(engine.dispatchAgentTool("search_lexicon", { query: "頭の出来がいい" }, lexicon));
    assert.ok(searchSmart.hits.every(function (h) { return (h.gloss_ja || "").indexOf("領民") < 0; }));
    var invented = engine.inventedBaronhForms("cadase lér. iri sacre. fac ad e. catoracas. ciloclér. riread.", lexicon);
    assert.ok(invented.indexOf("lér") < 0, "lér " + invented);
    assert.ok(invented.indexOf("iri") < 0, "iri " + invented);
    assert.ok(invented.indexOf("ad") < 0, "ad " + invented);
    assert.ok(invented.indexOf("catoracas") < 0, "catoracas " + invented);
    assert.ok(invented.indexOf("ciloclér") < 0, "ciloclér " + invented);
    assert.ok(invented.indexOf("riread") < 0, "riread " + invented);
    var sampleHints = engine.buildAgentUserPrompt(sample, lexicon, "ja", "baronh");
    assert.ok(sampleHints.indexOf("- 来る:") < 0);
    assert.ok(sampleHints.indexOf("-ar-") < 0);
    assert.ok(sampleHints.indexOf("リン・ジント") >= 0);
    assert.ok(sampleHints.indexOf("- リン・ジントって奴") < 0);
    assert.ok(sampleHints.indexOf("catorac") >= 0 || sampleHints.indexOf("機械通訳") >= 0);
    console.log("OK lexicon-plausible");
  });
}).catch(function (err) {
  console.error(err);
  process.exit(1);
});
