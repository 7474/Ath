(function () {
  "use strict";

  var KEY = "ath-translate.openai-key";
  var MODEL_KEY = "ath-translate.openai-model";
  var OVERLAY_KEY = "ath-translate.overlay";
  var EXAMPLES = [
    ["ja", "baronh", "私は移民します"],
    ["ja", "baronh", "私はアーヴです"],
    ["ja", "baronh", "あなたの家族は？"],
    ["ja", "baronh", "星たちよ"],
    ["ja", "baronh", "分かりますか"],
    ["ja", "baronh", "ありがとう"],
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

  function renderResult(result) {
    $("target-text").value = result.text;
    $("ath-view").textContent = result.ath_keys || result.text;
    var bits = [];
    if (result.reading_ja) bits.push("読み: " + result.reading_ja);
    bits.push(result.source_lang + " → " + result.target_lang + " / " + result.engine);
    $("reading").textContent = bits.join(" · ");
    $("analysis").innerHTML = (result.analysis || []).map(function (row) {
      return "<div>" + escapeHtml(row.source) + " → " + escapeHtml(row.target) +
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

  function localTranslate() {
    var src = $("source-lang").value;
    var tgt = $("target-lang").value;
    return BaronhEngine.translate($("source-text").value, lexicon, src, tgt);
  }

  function openaiTranslate() {
    var key = localStorage.getItem(KEY) || $("api-key").value.trim();
    if (!key) throw new Error("OpenAI API キーが未設定です。設定から保存してください。");
    var model = localStorage.getItem(MODEL_KEY) || $("chat-model").value || "gpt-4o-mini";
    var local = localTranslate();
    var body = {
      model: model,
      temperature: 0.2,
      messages: [
        { role: "system", content: "あなたはアーヴ語 (Baronh) の翻訳者です。与えた下訳と辞書を優先し、知らない語は造語せず残してください。訳文だけを返します。" },
        { role: "user", content: "方向: " + local.source_lang + " → " + ($("target-lang").value) + "\n原文:\n" + $("source-text").value + "\n下訳:\n" + local.text }
      ]
    };
    return fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json"
      },
      body: JSON.stringify(body)
    }).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) throw new Error((data.error && data.error.message) || res.statusText);
        var text = data.choices[0].message.content.trim();
        local.text = text;
        local.engine = "openai";
        if (local.target_lang === "baronh") {
          local.ath_keys = BaronhEngine.toAthKeys(text);
          local.reading_ja = BaronhEngine.readingJa(text);
        }
        return local;
      });
    });
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
    var key = localStorage.getItem(KEY);
    if ($("engine").value === "openai" && key) {
      setStatus("OpenAI TTS を呼び出しています…");
      return fetch("https://api.openai.com/v1/audio/speech", {
        method: "POST",
        headers: {
          "Authorization": "Bearer " + key,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ model: "gpt-4o-mini-tts", voice: "alloy", input: spoken, format: "mp3" })
      }).then(function (res) {
        if (!res.ok) throw new Error("TTS に失敗しました");
        return res.blob();
      }).then(function (blob) {
        var audio = new Audio(URL.createObjectURL(blob));
        audio.play();
        setStatus("読み: " + spoken);
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
  });
  $("lookup-btn").addEventListener("click", doLookup);
  $("lookup-q").addEventListener("keydown", function (ev) { if (ev.key === "Enter") doLookup(); });
  $("conj-btn").addEventListener("click", doConj);
  $("open-settings").addEventListener("click", function () {
    $("settings-panel").hidden = !$("settings-panel").hidden;
  });
  $("save-key").addEventListener("click", function () {
    localStorage.setItem(KEY, $("api-key").value.trim());
    localStorage.setItem(MODEL_KEY, $("chat-model").value.trim() || "gpt-4o-mini");
    setStatus("API キーをこのブラウザに保存しました");
  });
  $("clear-key").addEventListener("click", function () {
    localStorage.removeItem(KEY);
    $("api-key").value = "";
    setStatus("API キーを消去しました");
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

  firstJson(dataUrls()).then(function (doc) {
    lexicon = new BaronhEngine.Lexicon(doc.entries || []);
    return firstJson(["/data/user_lexicon.json", "../data/user_lexicon.json"]).then(function (overlay) {
      lexicon.mergeDocument(overlay);
    }).catch(function () { /* ユーザー辞書は任意 */ });
  }).then(function () {
    applyOverlay();
    refreshCount();
    runTranslate();
  }).catch(function (err) {
    setStatus("辞書を読めませんでした: " + err.message + "。python -m baronh serve で起動してください。");
  });
})();
