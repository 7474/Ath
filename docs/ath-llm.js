/**
 * OpenAI-compatible Baronh translation with local grammar/lexicon retrieval.
 * Keep behavior in sync with ath_openai.py / ath_retrieve.py / ath_translate_llm.py.
 */
(function (global) {
  var DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1";
  var DEFAULT_CHAT_MODEL = "gpt-4o-mini";
  var knowledge = { grammar: [], lexicon: [], phonemes: { keys: [] } };

  var SYSTEM_PROMPT =
    "You translate Japanese or English into Baronh (アーヴ語). " +
    "Write Baronh using the Aarth webfont keys: lowercase phonemes, A=ai, I=au, E=eu. " +
    "Use only retrieved lexicon/grammar or tool results. Reply with JSON only: " +
    '{"baronh":"...","notesJa":["..."],"used":[]}';

  function normalizeOpenAIBaseUrl(url) {
    var u = String(url == null ? "" : url).replace(/^\s+|\s+$/g, "").replace(/\/+$/, "");
    if (!u) u = DEFAULT_OPENAI_BASE_URL;
    try {
      var parsed = new URL(u);
      if (!parsed.pathname || parsed.pathname === "/") u += "/v1";
    } catch (err) { /* keep */ }
    return u;
  }

  function chatCompletionsUrl(baseUrl) {
    return normalizeOpenAIBaseUrl(baseUrl) + "/chat/completions";
  }

  function audioSpeechUrl(baseUrl) {
    return normalizeOpenAIBaseUrl(baseUrl) + "/audio/speech";
  }

  function tokens(text) {
    return String(text || "").toLowerCase().match(/[a-zà-ÿœ0-9ぁ-んァ-ン一-龯ー]+/gi) || [];
  }

  function blob(item) {
    var parts = [item.id, item.title, item.text, item.baronh, item.ja, item.en, item.note, item.pos];
    (item.tags || []).forEach(function (t) { parts.push(t); });
    return parts.filter(Boolean).join(" ").toLowerCase();
  }

  function score(queryTokens, item) {
    var hay = blob(item);
    var n = 0;
    queryTokens.forEach(function (tok) {
      if (!tok) return;
      if (hay.indexOf(tok) !== -1) n += tok.length >= 2 ? 3 : 1;
      if (String(item.baronh || "").toLowerCase() === tok) n += 8;
      if (String(item.ja || "").toLowerCase() === tok) n += 8;
    });
    return n;
  }

  function searchList(list, query, limit) {
    var q = tokens(query);
    return list
      .map(function (item) { return { s: score(q, item), item: item }; })
      .filter(function (row) { return row.s > 0; })
      .sort(function (a, b) { return b.s - a.s; })
      .slice(0, limit || 6)
      .map(function (row) { return row.item; });
  }

  function retrieve(query) {
    var grammar = searchList(knowledge.grammar, query, 4);
    if (!grammar.length) grammar = searchList(knowledge.grammar, "概要 格 翻訳 音声", 3);
    return {
      grammar: grammar.slice(0, 3),
      lexicon: searchList(knowledge.lexicon, query, 8)
    };
  }

  function keysToIpa(athKeys) {
    var table = (knowledge.phonemes.keys || []).slice().sort(function (a, b) {
      return b.key.length - a.key.length;
    });
    var out = "";
    var i = 0;
    var text = String(athKeys || "");
    while (i < text.length) {
      if (/\s/.test(text.charAt(i))) {
        out += " ";
        i += 1;
        continue;
      }
      var hit = null;
      for (var k = 0; k < table.length; k++) {
        if (text.indexOf(table[k].key, i) === i) {
          hit = table[k];
          break;
        }
      }
      if (hit) {
        out += hit.ipa;
        i += hit.key.length;
      } else {
        out += text.charAt(i);
        i += 1;
      }
    }
    return out;
  }

  function runTool(name, args) {
    var query = (args && args.query) || "";
    if (name === "search_lexicon") return JSON.stringify(searchList(knowledge.lexicon, query, 8));
    if (name === "search_grammar") return JSON.stringify(searchList(knowledge.grammar, query, 4));
    if (name === "get_phonemes") return JSON.stringify(knowledge.phonemes);
    return JSON.stringify({ error: "unknown tool " + name });
  }

  var TOOLS = [
    {
      type: "function",
      function: {
        name: "search_lexicon",
        description: "Search the local Baronh seed lexicon.",
        parameters: { type: "object", properties: { query: { type: "string" } }, required: ["query"] }
      }
    },
    {
      type: "function",
      function: {
        name: "search_grammar",
        description: "Search grammar cards.",
        parameters: { type: "object", properties: { query: { type: "string" } }, required: ["query"] }
      }
    },
    {
      type: "function",
      function: {
        name: "get_phonemes",
        description: "Ath webfont key to IPA map.",
        parameters: { type: "object", properties: {} }
      }
    }
  ];

  function parseContent(content) {
    var raw = String(content || "").replace(/^\s+|\s+$/g, "");
    var fenced = raw.match(/```(?:json)?\s*([\s\S]*?)```/);
    if (fenced) raw = fenced[1].replace(/^\s+|\s+$/g, "");
    var data = JSON.parse(raw);
    var baronh = data.baronh || "";
    return {
      baronh: baronh,
      ipa: keysToIpa(baronh),
      notesJa: data.notesJa || [],
      used: data.used || []
    };
  }

  function loadKnowledge(baseHref) {
    var root = baseHref || "knowledge/";
    return Promise.all([
      fetch(root + "grammar.json").then(function (r) { return r.json(); }),
      fetch(root + "lexicon.json").then(function (r) { return r.json(); }),
      fetch(root + "phonemes.json").then(function (r) { return r.json(); })
    ]).then(function (pack) {
      knowledge.grammar = pack[0];
      knowledge.lexicon = pack[1];
      knowledge.phonemes = pack[2];
      return knowledge;
    });
  }

  function translate(text, options) {
    options = options || {};
    var retrieved = retrieve(text);
    var trace = [{
      step: "retrieve",
      grammar: retrieved.grammar.map(function (g) { return g.id; }),
      lexicon: retrieved.lexicon.map(function (e) { return e.baronh; })
    }];
    var messages = [
      { role: "system", content: SYSTEM_PROMPT },
      { role: "user", content: JSON.stringify({ text: text, retrieved: retrieved }) }
    ];
    var useTools = options.useTools !== false;
    var fetchFn = options.fetch || global.fetch;
    var headers = { "Content-Type": "application/json" };
    if (options.apiKey) headers.Authorization = "Bearer " + options.apiKey;

    function post(msgs, tools) {
      var body = {
        model: options.model || DEFAULT_CHAT_MODEL,
        temperature: 0,
        messages: msgs
      };
      if (tools) {
        body.tools = tools;
        body.tool_choice = "auto";
      }
      return fetchFn(chatCompletionsUrl(options.baseUrl), {
        method: "POST",
        headers: headers,
        body: JSON.stringify(body)
      }).then(function (res) {
        return res.text().then(function (raw) {
          var payload = null;
          try { payload = raw ? JSON.parse(raw) : null; } catch (err) { payload = null; }
          if (!res.ok) {
            var msg = payload && payload.error && payload.error.message
              ? payload.error.message
              : ("HTTP " + res.status);
            var error = new Error(msg);
            error.status = res.status;
            throw error;
          }
          return payload;
        });
      });
    }

    function loop(msgs, tools, round) {
      if (round > 6) return Promise.reject(new Error("model did not finish translation"));
      return post(msgs, tools).then(function (payload) {
        var message = payload.choices && payload.choices[0] && payload.choices[0].message;
        if (!message) throw new Error("empty chat response");
        var calls = message.tool_calls || [];
        if (calls.length) {
          msgs.push(message);
          calls.forEach(function (call) {
            var fn = call.function || {};
            var args = {};
            try { args = JSON.parse(fn.arguments || "{}"); } catch (err) { args = {}; }
            trace.push({ step: "tool", name: fn.name, arguments: args });
            msgs.push({
              role: "tool",
              tool_call_id: call.id || fn.name,
              content: runTool(fn.name, args)
            });
          });
          return loop(msgs, tools, round + 1);
        }
        var parsed = parseContent(message.content);
        parsed.trace = trace;
        parsed.baseUrl = normalizeOpenAIBaseUrl(options.baseUrl);
        parsed.speechUrl = audioSpeechUrl(options.baseUrl);
        return parsed;
      }, function (err) {
        if (tools && round === 0) {
          trace.push({ step: "tools-unsupported", error: String(err.message || err) });
          return loop(msgs, null, round + 1);
        }
        throw err;
      });
    }

    return loop(messages, useTools ? TOOLS : null, 0);
  }

  function speakViaApi(inputText, options) {
    options = options || {};
    var fetchFn = options.fetch || global.fetch;
    var headers = { "Content-Type": "application/json" };
    if (options.apiKey) headers.Authorization = "Bearer " + options.apiKey;
    return fetchFn(audioSpeechUrl(options.baseUrl), {
      method: "POST",
      headers: headers,
      body: JSON.stringify({
        model: options.speechModel || "tts-1",
        voice: options.voice || "alloy",
        input: inputText
      })
    }).then(function (res) {
      if (!res.ok) {
        return res.text().then(function (t) {
          throw new Error(t || ("HTTP " + res.status));
        });
      }
      return res.blob();
    });
  }

  global.AthLlm = {
    loadKnowledge: loadKnowledge,
    retrieve: retrieve,
    translate: translate,
    keysToIpa: keysToIpa,
    speakViaApi: speakViaApi,
    normalizeOpenAIBaseUrl: normalizeOpenAIBaseUrl,
    chatCompletionsUrl: chatCompletionsUrl,
    audioSpeechUrl: audioSpeechUrl,
    DEFAULT_OPENAI_BASE_URL: DEFAULT_OPENAI_BASE_URL,
    knowledge: knowledge
  };
})(typeof window !== "undefined" ? window : this);
