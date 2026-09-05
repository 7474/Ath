(function () {
  "use strict";

  var KEY = "ath-translate.openai-key";
  var MODEL_KEY = "ath-translate.openai-model";
  var BASE_KEY = "ath-translate.openai-base";
  var TTS_MODEL_KEY = "ath-translate.openai-tts-model";
  var AGENT_URL_KEY = "ath-translate.agent-url";
  var OVERLAY_KEY = "ath-translate.overlay";
  var VECTOR_SEARCH_KEY = "ath-translate.local-vector";
  var lexicon = null;

  var $ = function (id) { return document.getElementById(id); };

  function setStatus(text) { $("status").textContent = text || ""; }

  var busyTimer = null;
  var busyStarted = 0;

  function formatElapsed(ms) {
    var sec = Math.max(0, Math.floor(ms / 1000));
    if (sec < 60) return sec + "秒経過";
    return Math.floor(sec / 60) + "分" + (sec % 60) + "秒経過";
  }

  function translatorPanel() {
    return $("translator") || document.querySelector(".translator");
  }

  function startBusy(message, opts) {
    opts = opts || {};
    var panel = translatorPanel();
    if (panel) {
      panel.classList.add("is-busy");
      panel.setAttribute("aria-busy", "true");
    }
    if (opts.clearResult) {
      $("analysis").innerHTML = "";
      $("reading").textContent = "";
    }
    var btn = $("translate-btn");
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
    var row = $("busy-row");
    if (row) row.hidden = false;
    busyStarted = Date.now();
    function tick() {
      var el = $("busy-elapsed");
      if (el) el.textContent = formatElapsed(Date.now() - busyStarted);
    }
    tick();
    if (busyTimer) clearInterval(busyTimer);
    busyTimer = setInterval(tick, 400);
    setStatus(message || "翻訳中…");
  }

  function updateBusy(event) {
    if (!event) return;
    if (event.message) setStatus(event.message);
    if (event.draft) {
      $("target-text").value = event.draft;
      $("reading").textContent = "下書き（生成中）";
    }
  }

  function stopBusy() {
    if (busyTimer) {
      clearInterval(busyTimer);
      busyTimer = null;
    }
    var panel = translatorPanel();
    if (panel) {
      panel.classList.remove("is-busy");
      panel.removeAttribute("aria-busy");
    }
    var btn = $("translate-btn");
    btn.disabled = false;
    btn.removeAttribute("aria-busy");
    var row = $("busy-row");
    if (row) row.hidden = true;
    var el = $("busy-elapsed");
    if (el) el.textContent = "";
  }

  function applyNdjsonLine(line, onProgress) {
    line = String(line || "").trim();
    if (!line) return null;
    var ev = JSON.parse(line);
    if (ev.type === "error") throw new Error(ev.error || "エージェント API でエラーが起きました。");
    if (ev.type === "result") return ev.result || ev;
    if (onProgress) onProgress(ev);
    return null;
  }

  function readNdjsonStream(res, onProgress) {
    var reader = res.body && res.body.getReader ? res.body.getReader() : null;
    if (!reader) {
      return res.text().then(function (text) {
        var result = null;
        String(text || "").split(/\r?\n/).forEach(function (line) {
          var got = applyNdjsonLine(line, onProgress);
          if (got) result = got;
        });
        if (!result) throw new Error("エージェント API の応答を読めませんでした。python -m baronh serve か Cloud Run の URL が必要です。");
        return result;
      });
    }
    var decoder = new TextDecoder();
    var buf = "";
    var result = null;
    function pump() {
      return reader.read().then(function (chunk) {
        if (chunk.value) buf += decoder.decode(chunk.value, { stream: !chunk.done });
        if (chunk.done) buf += decoder.decode();
        var lines = buf.split(/\r?\n/);
        buf = chunk.done ? "" : lines.pop();
        lines.forEach(function (line) {
          var got = applyNdjsonLine(line, onProgress);
          if (got) result = got;
        });
        if (!chunk.done) return pump();
        if (buf.trim()) {
          var last = applyNdjsonLine(buf, onProgress);
          if (last) result = last;
        }
        if (!result) throw new Error("エージェント API の応答を読めませんでした。python -m baronh serve か Cloud Run の URL が必要です。");
        return result;
      });
    }
    return pump();
  }

  function setSettingsStatus(text) {
    var el = $("settings-status");
    if (el) el.textContent = text || "";
  }

  function settingsDialog() { return $("settings-panel"); }

  function openSettings() {
    var dlg = settingsDialog();
    if (!dlg) return;
    setSettingsStatus("");
    if (typeof dlg.showModal === "function") {
      if (!dlg.open) dlg.showModal();
    } else {
      dlg.setAttribute("open", "");
    }
  }

  function closeSettings() {
    var dlg = settingsDialog();
    if (!dlg) return;
    if (typeof dlg.close === "function" && dlg.open) dlg.close();
    else dlg.removeAttribute("open");
  }

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

  function agentTranslate(onProgress) {
    return fetchWithRetry(agentEndpoint(), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/x-ndjson, application/json"
      },
      body: JSON.stringify({
        text: $("source-text").value,
        source_lang: $("source-lang").value,
        target_lang: $("target-lang").value,
        engine: "agent",
        stream: true
      })
    }).then(function (res) {
      var ctype = (res.headers.get("Content-Type") || "").toLowerCase();
      if (res.body && /ndjson/.test(ctype)) {
        return readNdjsonStream(res, onProgress);
      }
      return res.json().then(function (data) {
        if (!res.ok) {
          var msg = (data && data.error) || res.statusText;
          if (res.status === 404) {
            msg = "エージェント API がありません。python -m baronh serve を使うか、生成AI設定に Cloud Run の URL を入れてください。";
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

  function openaiTranslate(onProgress) {
    var base = apiBase();
    var key = localStorage.getItem(KEY) || $("api-key").value.trim();
    if (!key && /api\.openai\.com/.test(base)) {
      return Promise.reject(new Error("API キーが未設定です。生成AI設定から保存してください。"));
    }
    var model = localStorage.getItem(MODEL_KEY) || $("chat-model").value || "gpt-4o-mini";
    return BaronhEngine.translateAgent($("source-text").value, lexicon, {
      sourceLang: $("source-lang").value,
      targetLang: $("target-lang").value,
      onProgress: onProgress,
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

  function openaiNeedsSetup() {
    var base = apiBase();
    var key = localStorage.getItem(KEY) || ($("api-key") && $("api-key").value.trim());
    return $("engine").value === "openai" && !key && /api\.openai\.com/.test(base);
  }

  function runTranslate() {
    if (!lexicon) return;
    if (openaiNeedsSetup()) {
      openSettings();
      var msg = "API キーが未設定です。生成AI設定から保存してください。";
      setSettingsStatus(msg);
      setStatus(msg);
      return;
    }
    var engine = $("engine").value;
    startBusy(engine === "local" ? "翻訳中…" : "生成AIに問い合わせています…", {
      clearResult: engine !== "local"
    });
    var work = engine === "agent"
      ? agentTranslate(updateBusy)
      : engine === "openai"
        ? openaiTranslate(updateBusy)
        : Promise.resolve(localTranslate());
    work.then(renderResult).catch(function (err) {
      setStatus(err.message || String(err));
    }).then(function () {
      stopBusy();
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
    var readingEl = $("reading");
    if (readingEl) readingEl.textContent = "読み: " + spoken;
    if (!window.speechSynthesis) {
      setStatus("このブラウザは音声合成に未対応です。読みを表示しています。");
      return;
    }
    var utter = new SpeechSynthesisUtterance(spoken);
    utter.lang = lang === "en" ? "en-US" : "ja-JP";
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utter);
    setStatus("読み: " + spoken);
  }

  function renderEntryCard(entry, extraHtml) {
    var html = "<article class='entry-card'>";
    html += "<h3>" + escapeHtml(entry.lemma) + " <span class='pos'>" + escapeHtml(entry.pos || "") + "</span></h3>";
    html += "<p class='gloss'>" + escapeHtml(entry.gloss_ja || "");
    if (entry.gloss_en) html += " / " + escapeHtml(entry.gloss_en);
    html += "</p>";
    if (extraHtml) html += extraHtml;
    if (entry.pos === "noun" || entry.pos === "pronoun") {
      var forms = BaronhEngine.decline(entry);
      html += "<ul class='cases'>" + BaronhEngine.CASES.map(function (c) {
        return "<li><span class='case'>" + escapeHtml(BaronhEngine.CASE_JA[c]) + "</span> " +
          escapeHtml(forms[c]) + "</li>";
      }).join("") + "</ul>";
    }
    html += "</article>";
    return html;
  }

  function doLookup() {
    var q = $("lookup-q").value.trim();
    if (!q) return;
    var hits = lexicon.lookup(q, "auto");
    var html = "";
    if (!hits.length) {
      html += "<p class='hint'>完全一致なし</p>";
    } else {
      html += hits.map(function (e) { return renderEntryCard(e); }).join("");
    }
    if (window.BaronhVectorDB) {
      try {
        var vec = BaronhVectorDB.getIndex(lexicon).search(q, 5);
        if (vec.length) {
          html += "<p class='forms-heading'>ベクトル検索</p>";
          html += vec.map(function (hit) {
            var extra = hit.entry.notes
              ? "<p class='hint'>" + escapeHtml(String(hit.entry.notes).replace(/\s+/g, " ").trim()) +
                "（" + hit.score.toFixed(3) + "）</p>"
              : "<p class='hint'>" + hit.score.toFixed(3) + "</p>";
            return renderEntryCard(hit.entry, extra);
          }).join("");
        }
      } catch (err) {
        /* 索引が無くても語釈と格変化は出す */
      }
    }
    $("lookup-out").innerHTML = html;
  }

  function doConj() {
    var q = $("conj-q").value.trim();
    var hits = lexicon.lookup(q, "auto").filter(function (e) { return e.pos === "verb"; });
    if (!hits.length) {
      $("conj-out").innerHTML = "<p class='hint'>動詞が見つかりません</p>";
      return;
    }
    var e = hits[0];
    var rows = BaronhEngine.allVerbForms(e).filter(function (r) { return r.voices.length === 0; });
    var list = "<ul class='forms-list'>" + rows.map(function (r) {
      return "<li><span class='mood'>" + escapeHtml(r.mood) + " / " + escapeHtml(r.aspect) +
        "</span> " + escapeHtml(r.form) + "</li>";
    }).join("") + "</ul>";
    $("conj-out").innerHTML = renderEntryCard(e, list);
  }

  $("translate-btn").addEventListener("click", runTranslate);
  $("speak-btn").addEventListener("click", speak);
  $("copy-btn").addEventListener("click", function () {
    var text = $("target-text").value;
    if (navigator.clipboard) navigator.clipboard.writeText(text);
    else window.prompt("Copy:", text);
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
  $("engine").addEventListener("change", function () {
    syncLocalVectorOption();
    if (openaiNeedsSetup()) {
      openSettings();
      setSettingsStatus("ブラウザ生成AIを使うには接続先を保存してください。");
    }
  });
  if ($("local-vector-search")) {
    $("local-vector-search").addEventListener("change", function () {
      localStorage.setItem(VECTOR_SEARCH_KEY, $("local-vector-search").checked ? "1" : "0");
    });
  }
  $("source-text").addEventListener("input", syncAthScript);
  $("lookup-btn").addEventListener("click", doLookup);
  $("lookup-q").addEventListener("keydown", function (ev) { if (ev.key === "Enter") doLookup(); });
  $("conj-btn").addEventListener("click", doConj);
  $("open-settings").addEventListener("click", openSettings);
  if ($("close-settings")) $("close-settings").addEventListener("click", closeSettings);
  (function bindSettingsDismiss() {
    var dlg = settingsDialog();
    if (!dlg) return;
    dlg.addEventListener("click", function (ev) {
      var rect = dlg.getBoundingClientRect();
      var inside = ev.clientX >= rect.left && ev.clientX <= rect.right &&
        ev.clientY >= rect.top && ev.clientY <= rect.bottom;
      if (!inside) closeSettings();
    });
  })();
  $("save-key").addEventListener("click", function () {
    localStorage.setItem(KEY, $("api-key").value.trim());
    localStorage.setItem(MODEL_KEY, $("chat-model").value.trim() || "gpt-4o-mini");
    localStorage.setItem(BASE_KEY, $("api-base").value.trim() || "https://api.openai.com/v1");
    localStorage.setItem(TTS_MODEL_KEY, $("tts-model").value.trim() || "gpt-4o-mini-tts");
    if ($("agent-url")) localStorage.setItem(AGENT_URL_KEY, $("agent-url").value.trim());
    var msg = "設定をこのブラウザに保存しました（エージェント: " + agentEndpoint() + "）";
    setSettingsStatus(msg);
    setStatus(msg);
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
    setSettingsStatus("API 設定を消去しました");
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
    }).catch(function (err) {
      console.warn(err);
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
