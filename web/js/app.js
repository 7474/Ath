(function () {
  "use strict";

  var KEY = "ath-translate.openai-key";
  var MODEL_KEY = "ath-translate.openai-model";
  var BASE_KEY = "ath-translate.openai-base";
  var TTS_MODEL_KEY = "ath-translate.openai-tts-model";
  var OVERLAY_KEY = "ath-translate.overlay";
  var EXAMPLES = [
    ["ja", "baronh", "私は移民します"],
    ["ja", "baronh", "私はアーヴです"],
    ["ja", "baronh", "あなたの家族は？"],
    ["ja", "baronh", "星たちよ"],
    ["ja", "baronh", "分かりますか"],
    ["ja", "baronh", "ありがとう"],
    ["ja", "baronh", "私はジントです"],
    ["baronh", "ja", "F'a usere."],
    ["baronh", "ja", "F'a bale."],
    ["baronh", "en", "Facle sa?"],
    ["en", "baronh", "I immigrate"]
  ];
  var exampleAt = 0;
  var lexicon = null;

  var $ = function (id) { return document.getElementById(id); };

  function setStatus(text) { $("status").textContent = text || ""; }

  function dataUrls() {
    return [
      "data/lexicon.json",
      "/data/lexicon.json",
      "../data/lexicon.json"
    ];
  }

  function loadJson(url) {
    return fetch(url).then(function (res) {
      if (!res.ok) throw new Error(res.status + " " + url);
      return res.json();
    });
  }

  function firstJson(urls) {
    var chain = Promise.reject(new Error("no url"));
    urls.forEach(function (url) {
      chain = chain.catch(function () { return loadJson(url); });
    });
    return chain;
  }

  function refreshCount() {
    $("dict-count").textContent = "辞書 " + (lexicon ? lexicon.entries.length : 0) + " 語";
  }

  function applyOverlay() {
    var raw = localStorage.getItem(OVERLAY_KEY);
    if (!raw || !lexicon) return;
    try {
      lexicon.mergeDocument(JSON.parse(raw));
    } catch (err) {
      console.warn(err);
    }
  }

  function resolvedSourceLang() {
    var src = $("source-lang").value;
    if (src && src !== "auto") return src;
    if (!window.BaronhEngine) return "ja";
    return BaronhEngine.detectLang($("source-text").value, lexicon);
  }

  function resolvedTargetLang() {
    var tgt = $("target-lang").value;
    if (tgt && tgt !== "auto") return tgt;
    return resolvedSourceLang() === "baronh" ? "ja" : "baronh";
  }

  function syncAthScript() {
    $("source-text").classList.toggle("ath-script", resolvedSourceLang() === "baronh");
    $("target-text").classList.toggle("ath-script", resolvedTargetLang() === "baronh");
  }

  function renderResult(result) {
    $("target-text").value = result.text;
    syncAthScript();
    var bits = [];
    if (result.reading_ja) bits.push("読み: " + result.reading_ja);
    bits.push(result.source_lang + " → " + result.target_lang + " / " + result.engine);
    $("reading").textContent = bits.join(" · ");
    $("analysis").innerHTML = (result.analysis || []).map(function (row) {
      var phonetic = /発音転記/.test(row.note || "");
      return "<div" + (phonetic ? " class='phonetic'" : "") + ">" + escapeHtml(row.source) + " → " + escapeHtml(row.target) +
        (row.note ? " <span class='meta'>(" + escapeHtml(row.note) + ")</span>" : "") + "</div>";
    }).join("");
    if (result.notes && result.notes.length) {
      setStatus(result.notes.join(" "));
    } else {
      setStatus("");
    }
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (ch) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch];
    });
  }

  function apiBase() {
    var raw = (localStorage.getItem(BASE_KEY) || ($("api-base") && $("api-base").value) || "https://api.openai.com/v1").trim().replace(/\/+$/, "");
    if (!raw) raw = "https://api.openai.com/v1";
    if (/^https?:\/\/[^/]+$/i.test(raw)) raw += "/v1";
    return raw;
  }

  function apiUrl(path) {
    return apiBase() + "/" + String(path || "").replace(/^\//, "");
  }

  function localTranslate() {
    var src = $("source-lang").value;
    var tgt = $("target-lang").value;
    return BaronhEngine.translate($("source-text").value, lexicon, src, tgt);
  }

  function openaiTranslate() {
    var base = apiBase();
    var key = localStorage.getItem(KEY) || $("api-key").value.trim();
    if (!key && /api\.openai\.com/.test(base)) {
      throw new Error("API キーが未設定です。設定から保存してください。");
    }
    var model = localStorage.getItem(MODEL_KEY) || $("chat-model").value || "gpt-4o-mini";
    var local = localTranslate();
    var targetLang = $("target-lang").value;
    var messages = [
      { role: "system", content: BaronhEngine.systemPrompt(targetLang) },
      { role: "user", content: BaronhEngine.buildUserPrompt($("source-text").value, lexicon, local, targetLang) }
    ];
    function chat(useTools) {
      var body = { model: model, temperature: 0.2, messages: messages };
      if (useTools) {
        body.tools = BaronhEngine.CHAT_TOOLS;
        body.tool_choice = "auto";
      }
      return fetch(apiUrl("chat/completions"), {
        method: "POST",
        headers: {
          "Authorization": "Bearer " + (key || "no-key"),
          "Content-Type": "application/json"
        },
        body: JSON.stringify(body)
      }).then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok) throw new Error((data.error && data.error.message) || res.statusText);
          return data;
        });
      });
    }
    function loop(useTools, round) {
      if (round > 6) return Promise.resolve(local.text);
      return chat(useTools).then(function (data) {
        var message = (((data.choices || [])[0]) || {}).message || {};
        var calls = message.tool_calls || [];
        if (!calls.length) return BaronhEngine.cleanModelText(String(message.content || "").trim()) || local.text;
        messages.push(message);
        calls.forEach(function (call) {
          var fn = call.function || {};
          var args = {};
          try { args = JSON.parse(fn.arguments || "{}"); } catch (err) { args = {}; }
          messages.push({
            role: "tool",
            tool_call_id: call.id || fn.name,
            content: BaronhEngine.dispatchTool(fn.name, args, lexicon)
          });
        });
        return loop(useTools, round + 1);
      });
    }
    return loop(true, 1).catch(function (err) {
      if (/tool/i.test(err.message || "") || /400/.test(err.message || "")) {
        messages = messages.slice(0, 2);
        return loop(false, 1);
      }
      throw err;
    }).then(function (text) {
      text = BaronhEngine.cleanModelText(text) || local.text;
      var notes = ["OpenAI 互換 API（" + base + "）。辞書は全文スキャンして関連語だけ渡し、生成後に語形を検証します。"];
      if (targetLang === "baronh") {
        var invented = BaronhEngine.inventedBaronhForms(text, lexicon, local);
        if (invented.length && text !== local.text) {
          notes.push("辞書にない語形 " + invented.join(", ") + " を検出したので再生成します。");
          messages = messages.concat([
            { role: "assistant", content: text },
            { role: "user", content: "次の語は辞書の語形でも発音転記でもありません: " + invented.join(", ") + "。造語せず書き直してください。普通名詞が見つからなければ原文の語を残してください。訳文だけを出力してください。" }
          ]);
          return loop(true, 1).catch(function () { return text; }).then(function (rewritten) {
            rewritten = BaronhEngine.cleanModelText(rewritten) || text;
            var again = BaronhEngine.inventedBaronhForms(rewritten, lexicon, local);
            if (again.length <= invented.length) {
              text = rewritten;
              invented = again;
            }
            return finishOpenAi(text, local, notes, invented, targetLang, base);
          });
        }
        return finishOpenAi(text, local, notes, invented, targetLang, base);
      }
      return finishOpenAi(text, local, notes, [], targetLang, base);
    });
  }

  function finishOpenAi(text, local, notes, invented, targetLang, base) {
    if (invented && invented.length) {
      notes.push("辞書にない語形: " + invented.join(", ") + "。");
      var draftClean = BaronhEngine.inventedBaronhForms(local.text, lexicon, local);
      if (draftClean.length === 0 && invented.length >= 2) {
        notes.push("生成文の未登録語が多いため下訳を使いました。");
        text = local.text;
      }
    }
    local.text = text;
    local.engine = "openai";
    local.notes = (local.notes || []).concat(notes);
    if (targetLang === "baronh") {
      local.ath_keys = BaronhEngine.toAthKeys(text);
      local.reading_ja = BaronhEngine.readingJa(text);
    }
    return local;
  }

  function runTranslate() {
    if (!lexicon) return;
    $("translate-btn").disabled = true;
    setStatus("翻訳中…");
    var work = $("engine").value === "openai"
      ? openaiTranslate()
      : Promise.resolve(localTranslate());
    work.then(renderResult).catch(function (err) {
      setStatus(err.message || String(err));
    }).then(function () {
      $("translate-btn").disabled = false;
    });
  }

  function speak() {
    var resultText = $("target-text").value || $("source-text").value;
    var target = $("target-lang").value;
    var lang = target === "auto" ? (BaronhEngine.detectLang(resultText, lexicon)) : target;
    var spoken = lang === "baronh" ? BaronhEngine.readingJa(resultText) : resultText;
    var key = localStorage.getItem(KEY) || ($("api-key") && $("api-key").value.trim());
    var ttsModel = localStorage.getItem(TTS_MODEL_KEY) || ($("tts-model") && $("tts-model").value) || "gpt-4o-mini-tts";
    if ($("engine").value === "openai" && ttsModel) {
      setStatus("互換 TTS（/audio/speech）を呼び出しています…");
      return fetch(apiUrl("audio/speech"), {
        method: "POST",
        headers: {
          "Authorization": "Bearer " + (key || "no-key"),
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ model: ttsModel, voice: "alloy", input: spoken, format: "mp3" })
      }).then(function (res) {
        if (!res.ok) throw new Error("TTS に失敗しました（この互換 API は /audio/speech 未対応のことがあります）");
        return res.blob();
      }).then(function (blob) {
        var audio = new Audio(URL.createObjectURL(blob));
        audio.play();
        setStatus("読み: " + spoken + "（クラウド TTS）");
      }).catch(function (err) {
        setStatus(err.message);
        speakBrowser(spoken, lang);
      });
    }
    speakBrowser(spoken, lang);
  }

  function speakBrowser(spoken, lang) {
    if (!window.speechSynthesis) {
      setStatus("このブラウザは音声合成に未対応です。読み: " + spoken);
      return;
    }
    var utter = new SpeechSynthesisUtterance(spoken);
    utter.lang = lang === "en" ? "en-US" : "ja-JP";
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utter);
    setStatus("読み: " + spoken);
  }

  function doLookup() {
    var q = $("lookup-q").value.trim();
    if (!q) return;
    var hits = lexicon.lookup(q, "auto");
    if (!hits.length) {
      $("lookup-out").textContent = "見つかりません";
      return;
    }
    $("lookup-out").textContent = hits.map(function (e) {
      var lines = [e.lemma + "  [" + e.pos + "]  " + e.gloss_ja + " / " + e.gloss_en];
      if (e.pos === "noun" || e.pos === "pronoun") {
        var forms = BaronhEngine.decline(e);
        lines.push(BaronhEngine.CASES.map(function (c) {
          return BaronhEngine.CASE_JA[c] + " " + forms[c];
        }).join("  "));
      }
      return lines.join("\n");
    }).join("\n\n");
  }

  function doConj() {
    var q = $("conj-q").value.trim();
    var hits = lexicon.lookup(q, "auto").filter(function (e) { return e.pos === "verb"; });
    if (!hits.length) {
      $("conj-out").textContent = "動詞が見つかりません";
      return;
    }
    var e = hits[0];
    var rows = BaronhEngine.allVerbForms(e).filter(function (r) { return r.voices.length === 0; });
    $("conj-out").textContent = e.lemma + "「" + e.gloss_ja + "」\n" + rows.map(function (r) {
      return r.mood + " / " + r.aspect + "  " + r.form;
    }).join("\n");
  }

  $("translate-btn").addEventListener("click", runTranslate);
  $("speak-btn").addEventListener("click", speak);
  $("copy-btn").addEventListener("click", function () {
    var text = $("target-text").value;
    if (navigator.clipboard) navigator.clipboard.writeText(text);
    else window.prompt("Copy:", text);
  });
  $("examples-btn").addEventListener("click", function () {
    var ex = EXAMPLES[exampleAt % EXAMPLES.length];
    exampleAt += 1;
    $("source-lang").value = ex[0];
    $("target-lang").value = ex[1];
    $("source-text").value = ex[2];
    syncAthScript();
    runTranslate();
  });
  $("swap-langs").addEventListener("click", function () {
    var a = $("source-lang").value;
    var b = $("target-lang").value;
    if (a === "auto") a = "ja";
    if (b === "auto") b = "baronh";
    $("source-lang").value = b;
    $("target-lang").value = a;
    var src = $("source-text").value;
    $("source-text").value = $("target-text").value;
    $("target-text").value = src;
    syncAthScript();
  });
  $("source-lang").addEventListener("change", syncAthScript);
  $("target-lang").addEventListener("change", syncAthScript);
  $("source-text").addEventListener("input", syncAthScript);
  $("lookup-btn").addEventListener("click", doLookup);
  $("lookup-q").addEventListener("keydown", function (ev) { if (ev.key === "Enter") doLookup(); });
  $("conj-btn").addEventListener("click", doConj);
  $("open-settings").addEventListener("click", function () {
    $("settings-panel").hidden = !$("settings-panel").hidden;
  });
  $("save-key").addEventListener("click", function () {
    localStorage.setItem(KEY, $("api-key").value.trim());
    localStorage.setItem(MODEL_KEY, $("chat-model").value.trim() || "gpt-4o-mini");
    localStorage.setItem(BASE_KEY, $("api-base").value.trim() || "https://api.openai.com/v1");
    localStorage.setItem(TTS_MODEL_KEY, $("tts-model").value.trim() || "gpt-4o-mini-tts");
    setStatus("API 設定をこのブラウザに保存しました（送信先: " + apiBase() + "）");
  });
  $("clear-key").addEventListener("click", function () {
    localStorage.removeItem(KEY);
    localStorage.removeItem(BASE_KEY);
    localStorage.removeItem(MODEL_KEY);
    localStorage.removeItem(TTS_MODEL_KEY);
    $("api-key").value = "";
    $("api-base").value = "https://api.openai.com/v1";
    $("chat-model").value = "gpt-4o-mini";
    $("tts-model").value = "gpt-4o-mini-tts";
    setStatus("API 設定を消去しました");
  });
  $("import-file").addEventListener("change", function (ev) {
    var file = ev.target.files && ev.target.files[0];
    if (!file) return;
    file.text().then(function (text) {
      var doc = BaronhEngine.parseImported(text, file.name);
      lexicon.mergeDocument(doc);
      localStorage.setItem(OVERLAY_KEY, JSON.stringify(doc));
      refreshCount();
      setStatus((doc.entries || []).length + " 件をブラウザ辞書に追加しました");
    }).catch(function (err) {
      setStatus(err.message);
    });
  });
  $("clear-overlay").addEventListener("click", function () {
    localStorage.removeItem(OVERLAY_KEY);
    location.reload();
  });
  $("source-text").addEventListener("keydown", function (ev) {
    if ((ev.metaKey || ev.ctrlKey) && ev.key === "Enter") runTranslate();
  });

  $("api-key").value = localStorage.getItem(KEY) || "";
  $("chat-model").value = localStorage.getItem(MODEL_KEY) || "gpt-4o-mini";
  $("api-base").value = localStorage.getItem(BASE_KEY) || "https://api.openai.com/v1";
  $("tts-model").value = localStorage.getItem(TTS_MODEL_KEY) || "gpt-4o-mini-tts";

  firstJson(dataUrls()).then(function (doc) {
    lexicon = new BaronhEngine.Lexicon(doc.entries || []);
    return firstJson(["/data/user_lexicon.json", "../data/user_lexicon.json"]).then(function (overlay) {
      lexicon.mergeDocument(overlay);
    }).catch(function () { /* ユーザー辞書は任意 */ });
  }).then(function () {
    applyOverlay();
    refreshCount();
    syncAthScript();
    runTranslate();
  }).catch(function (err) {
    setStatus("辞書を読めませんでした: " + err.message + "。python -m baronh serve で起動してください。");
  });
})();
