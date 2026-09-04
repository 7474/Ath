(function () {
  "use strict";

  var KEY = "ath-translate.openai-key";
  var MODEL_KEY = "ath-translate.openai-model";
  var BASE_KEY = "ath-translate.openai-base";
  var TTS_MODEL_KEY = "ath-translate.openai-tts-model";
  var AGENT_URL_KEY = "ath-translate.agent-url";
  var OVERLAY_KEY = "ath-translate.overlay";
  var VECTOR_SEARCH_KEY = "ath-translate.local-vector";
  var EXAMPLES = [
    ["ja", "baronh", "私は移民します"],
    ["ja", "baronh", "私はアーヴです"],
    ["ja", "baronh", "あなたの家族は？"],
    ["ja", "baronh", "星たちよ"],
    ["ja", "baronh", "分かりますか"],
    ["ja", "baronh", "ありがとう"],
    ["ja", "baronh", "私はジントです"],
    ["ja", "baronh", "星たちの光を見ます"],
    ["baronh", "ja", "F'a usere."],
    ["baronh", "ja", "F'a bale."],
    ["baronh", "en", "Facle sa?"],
    ["en", "baronh", "I immigrate"]
  ];
  var exampleAt = 0;
  var lexicon = null;

  var $ = function (id) { return document.getElementById(id); };

  function setStatus(text) { $("status").textContent = text || ""; }

  function dataUrls(name) {
    name = name || "lexicon.json";
    return [
      "data/" + name,
      "/data/" + name,
      "../data/" + name
    ];
  }

  function loadJson(url) {
    return fetch(url).then(function (res) {
      if (!res.ok) throw new Error(res.status + " " + url);
      return res.json();
    });
  }

  function loadBuffer(url) {
    return fetch(url).then(function (res) {
      if (!res.ok) throw new Error(res.status + " " + url);
      return res.arrayBuffer();
    });
  }

  function firstOf(urls, loader) {
    var chain = Promise.reject(new Error("no url"));
    urls.forEach(function (url) {
      chain = chain.catch(function () { return loader(url); });
    });
    return chain;
  }

  function firstJson(urls) {
    return firstOf(urls, loadJson);
  }

  function firstBuffer(urls) {
    return firstOf(urls, loadBuffer);
  }

  function delay(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  var FETCH_RETRIES = 3;
  var RETRYABLE_STATUS = { 408: 1, 429: 1, 500: 1, 502: 1, 503: 1, 504: 1 };

  function fetchWithRetry(url, init, attempt) {
    attempt = attempt || 0;
    return fetch(url, init).then(function (res) {
      if (res.ok || !RETRYABLE_STATUS[res.status] || attempt >= FETCH_RETRIES - 1) return res;
      return delay(400 * Math.pow(2, attempt)).then(function () {
        return fetchWithRetry(url, init, attempt + 1);
      });
    }, function (err) {
      if (attempt >= FETCH_RETRIES - 1) throw err;
      return delay(400 * Math.pow(2, attempt)).then(function () {
        return fetchWithRetry(url, init, attempt + 1);
      });
    });
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
    if (result.substitutions && result.substitutions.length) {
      var extra = result.substitutions.map(function (item) {
        return "<div class='meta'>" + escapeHtml(item.from) + " → " + escapeHtml(item.lemma) +
          " <span class='meta'>（類義語 " + escapeHtml(item.gloss || item.via || "") + "）</span></div>";
      }).join("");
      $("analysis").innerHTML += extra;
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

  function agentEndpoint() {
    var raw = (localStorage.getItem(AGENT_URL_KEY) || ($("agent-url") && $("agent-url").value) || "/api/translate").trim();
    if (!raw) raw = "/api/translate";
    raw = raw.replace(/\/+$/, "");
    if (!/\/api\/translate$/i.test(raw)) raw += "/api/translate";
    return raw;
  }

  function agentHealthUrl() {
    return agentEndpoint().replace(/\/api\/translate$/i, "/api/health");
  }

  function setAgentOptionVisible(visible) {
    var sel = $("engine");
    if (!sel) return;
    var opt = sel.querySelector('option[value="agent"]');
    if (!opt) return;
    opt.hidden = !visible;
    opt.disabled = !visible;
    if (!visible && sel.value === "agent") {
      sel.value = "local";
      syncLocalVectorOption();
    }
  }

  function probeAgentConfigured() {
    return fetch(agentHealthUrl()).then(function (res) {
      if (!res.ok) return false;
      return res.json().then(function (body) {
        return !!(body && body.ok && body.model);
      }, function () { return false; });
    }).catch(function () { return false; }).then(function (ok) {
      setAgentOptionVisible(ok);
      return ok;
    });
  }

  function agentTranslate() {
    return fetchWithRetry(agentEndpoint(), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: $("source-text").value,
        source_lang: $("source-lang").value,
        target_lang: $("target-lang").value,
        engine: "agent"
      })
    }).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) {
          var msg = (data && data.error) || res.statusText;
          if (res.status === 404) {
            msg = "エージェント API がありません。python -m baronh serve を使うか、設定に Cloud Run の URL を入れてください。";
          }
          throw new Error(msg);
        }
        return data;
      }, function () {
        throw new Error("エージェント API の応答を読めませんでした。python -m baronh serve か Cloud Run の URL が必要です。");
      });
    });
  }

  function localTranslate() {
    var src = $("source-lang").value;
    var tgt = $("target-lang").value;
    return BaronhEngine.translate($("source-text").value, lexicon, src, tgt, {
      vectorSearch: !!($("local-vector-search") && $("local-vector-search").checked)
    });
  }

  function syncLocalVectorOption() {
    var wrap = $("local-vector-wrap");
    if (!wrap) return;
    wrap.hidden = $("engine").value !== "local";
  }

  function openaiTranslate() {
    var base = apiBase();
    var key = localStorage.getItem(KEY) || $("api-key").value.trim();
    if (!key && /api\.openai\.com/.test(base)) {
      throw new Error("API キーが未設定です。設定から保存してください。");
    }
    var model = localStorage.getItem(MODEL_KEY) || $("chat-model").value || "gpt-4o-mini";
    return BaronhEngine.translateAgent($("source-text").value, lexicon, {
      sourceLang: $("source-lang").value,
      targetLang: $("target-lang").value,
      chatOnce: function (payload) {
        payload.model = payload.model || model;
        return fetchWithRetry(apiUrl("chat/completions"), {
          method: "POST",
          headers: {
            "Authorization": "Bearer " + (key || "no-key"),
            "Content-Type": "application/json"
          },
          body: JSON.stringify(payload)
        }).then(function (res) {
          return res.json().then(function (data) {
            if (!res.ok) throw new Error((data.error && data.error.message) || res.statusText);
            return data;
          });
        });
      }
    }).then(function (result) {
      result.notes = (result.notes || []).concat(["OpenAI 互換 API（" + base + "）。"]);
      return result;
    });
  }

  function runTranslate() {
    if (!lexicon) return;
    $("translate-btn").disabled = true;
    setStatus("翻訳中…");
    var engine = $("engine").value;
    var work = engine === "agent"
      ? agentTranslate()
      : engine === "openai"
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
    var blocks = [];
    if (!hits.length) {
      blocks.push("完全一致なし");
    } else {
      blocks.push(hits.map(function (e) {
        var lines = [e.lemma + "  [" + e.pos + "]  " + e.gloss_ja + " / " + e.gloss_en];
        if (e.pos === "noun" || e.pos === "pronoun") {
          var forms = BaronhEngine.decline(e);
          lines.push(BaronhEngine.CASES.map(function (c) {
            return BaronhEngine.CASE_JA[c] + " " + forms[c];
          }).join("  "));
        }
        return lines.join("\n");
      }).join("\n\n"));
    }
    if (window.BaronhVectorDB) {
      var vec = BaronhVectorDB.getIndex(lexicon).search(q, 5);
      if (vec.length) {
        blocks.push("ベクトル検索:\n" + vec.map(function (hit) {
          return hit.entry.lemma + "  [" + hit.entry.pos + "]  " + hit.entry.gloss_ja +
            "  (" + hit.score.toFixed(3) + ")";
        }).join("\n"));
      }
    }
    $("lookup-out").textContent = blocks.join("\n\n");
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
  $("engine").addEventListener("change", syncLocalVectorOption);
  if ($("local-vector-search")) {
    $("local-vector-search").addEventListener("change", function () {
      localStorage.setItem(VECTOR_SEARCH_KEY, $("local-vector-search").checked ? "1" : "0");
    });
  }
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
    if ($("agent-url")) localStorage.setItem(AGENT_URL_KEY, $("agent-url").value.trim());
    setStatus("設定をこのブラウザに保存しました（エージェント: " + agentEndpoint() + "）");
    probeAgentConfigured();
  });
  $("clear-key").addEventListener("click", function () {
    localStorage.removeItem(KEY);
    localStorage.removeItem(BASE_KEY);
    localStorage.removeItem(MODEL_KEY);
    localStorage.removeItem(TTS_MODEL_KEY);
    localStorage.removeItem(AGENT_URL_KEY);
    $("api-key").value = "";
    $("api-base").value = "https://api.openai.com/v1";
    $("chat-model").value = "gpt-4o-mini";
    $("tts-model").value = "gpt-4o-mini-tts";
    if ($("agent-url")) $("agent-url").value = "/api/translate";
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
  if ($("agent-url")) $("agent-url").value = localStorage.getItem(AGENT_URL_KEY) || "/api/translate";
  if ($("local-vector-search")) {
    $("local-vector-search").checked = localStorage.getItem(VECTOR_SEARCH_KEY) === "1";
  }
  syncLocalVectorOption();
  setAgentOptionVisible(false);

  firstJson(dataUrls("lexicon.json")).then(function (doc) {
    lexicon = new BaronhEngine.Lexicon(doc.entries || []);
    return firstJson(["/data/user_lexicon.json", "../data/user_lexicon.json"]).then(function (overlay) {
      lexicon.mergeDocument(overlay);
    }).catch(function () { /* ユーザー辞書は任意 */ });
  }).then(function () {
    applyOverlay();
    refreshCount();
    if (!window.BaronhVectorDB || !lexicon) return;
    return Promise.all([
      firstJson(dataUrls("vectors.json")),
      firstBuffer(dataUrls("vectors.bin"))
    ]).then(function (pair) {
      var meta = pair[0];
      var matrix = new Float32Array(pair[1]);
      BaronhVectorDB.setPrebuilt({
        dim: meta.dim,
        count: meta.count,
        hash: meta.hash,
        keys: meta.keys,
        documents: meta.documents,
        matrix: matrix
      });
      BaronhVectorDB.getIndex(lexicon);
    });
  }).then(function () {
    return probeAgentConfigured();
  }).then(function () {
    syncAthScript();
    runTranslate();
  }).catch(function (err) {
    setStatus("辞書またはベクトル索引を読めませんでした: " + err.message +
      "。python -m baronh export-web のあと python -m baronh serve で起動してください。");
  });
})();
