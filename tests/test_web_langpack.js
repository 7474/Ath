#!/usr/bin/env node
"use strict";

var fs = require("fs");
var path = require("path");
var vm = require("vm");
var assert = require("assert");

var ROOT = path.resolve(__dirname, "..");
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
  TextEncoder: typeof TextEncoder !== "undefined" ? TextEncoder : undefined,
  BigInt: typeof BigInt !== "undefined" ? BigInt : undefined,
  Promise: Promise,
  setTimeout: setTimeout,
  globalThis: null
};
context.globalThis = context;
context.window = context;

function load(rel) {
  vm.runInNewContext(fs.readFileSync(path.join(ROOT, rel), "utf8"), context, { filename: rel });
}

load("web/js/engine.js");
load("web/js/langpack.js");

var spec = JSON.parse(fs.readFileSync(path.join(ROOT, "langs/mina/language.json"), "utf8"));
var doc = JSON.parse(fs.readFileSync(path.join(ROOT, "langs/mina/lexicon.json"), "utf8"));
var lexicon = new context.BaronhEngine.Lexicon(doc.entries);
context.Langpack.register(spec, lexicon);

assert.ok(context.Langpack.isPackLang("mina"));
assert.ok(context.Langpack.usesPackRoute("ja", "mina"));
assert.ok(!context.Langpack.isPackLang("baronh"));

var r = context.Langpack.translate("私はミーナです", "ja", "mina");
assert.strictEqual(r.text, "na ya minde.");
assert.strictEqual(r.engine, "transfer");
assert.strictEqual(r.target_lang, "mina");
assert.ok(r.reading_ja.indexOf("ナ") >= 0);

var star = context.Langpack.translate("星を見る", "ja", "mina");
assert.strictEqual(star.text, "soro miru.");

var water = context.Langpack.translate("水に行く", "ja", "mina");
assert.strictEqual(water.text, "nami piru.");

var back = context.Langpack.translate("na ya minde.", "mina", "ja");
assert.ok(back.text.indexOf("私") >= 0);
assert.ok(back.text.indexOf("ミーナ") >= 0);

var mina = lexicon.lookup("mina", "mina")[0] || lexicon.lookup("ミーナ", "ja")[0];
assert.ok(mina);
var forms = context.Langpack.decline(mina, spec);
assert.strictEqual(forms.nom, "mina");
assert.strictEqual(forms.ins, "minde");

console.log("mina=" + r.text);
console.log("ok");
