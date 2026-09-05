/* 表示テーマ。未保存ならシステム設定に従う。 */
(function () {
  var KEY = "ath-theme";
  var LABELS = { system: "自動", light: "明", dark: "暗" };
  var NEXT = { system: "light", light: "dark", dark: "system" };
  var NEXT_JA = { system: "ライト", light: "ダーク", dark: "システム" };
  var DESCRIBE = {
    system: "システム設定に従う",
    light: "ライト",
    dark: "ダーク"
  };

  function stored() {
    try {
      var value = localStorage.getItem(KEY);
      return value === "light" || value === "dark" ? value : "system";
    } catch (err) {
      return "system";
    }
  }

  function apply(pref) {
    if (pref === "light" || pref === "dark") {
      document.documentElement.setAttribute("data-theme", pref);
    } else {
      document.documentElement.removeAttribute("data-theme");
      pref = "system";
    }
    syncToggle(pref);
    syncThemeColor();
  }

  function resolved() {
    var forced = document.documentElement.getAttribute("data-theme");
    if (forced === "light" || forced === "dark") return forced;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function syncThemeColor() {
    var meta = document.querySelector('meta[name="theme-color"]');
    if (!meta) {
      meta = document.createElement("meta");
      meta.setAttribute("name", "theme-color");
      document.head.appendChild(meta);
    }
    meta.setAttribute("content", resolved() === "dark" ? "#161614" : "#fafaf8");
  }

  function syncToggle(pref) {
    var button = document.getElementById("theme-toggle");
    if (!button) return;
    button.dataset.themePref = pref;
    button.textContent = LABELS[pref];
    button.setAttribute(
      "aria-label",
      "表示テーマ: " + DESCRIBE[pref] + "。クリックで" + NEXT_JA[pref] + "に切り替え"
    );
    button.title = button.getAttribute("aria-label");
  }

  apply(stored());

  function bind() {
    var button = document.getElementById("theme-toggle");
    if (!button) return;
    syncToggle(stored());
    button.addEventListener("click", function () {
      var next = NEXT[stored()];
      try {
        if (next === "system") localStorage.removeItem(KEY);
        else localStorage.setItem(KEY, next);
      } catch (err) { /* private mode など */ }
      apply(next);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }

  var media = window.matchMedia("(prefers-color-scheme: dark)");
  var onChange = function () {
    if (stored() === "system") apply("system");
  };
  if (typeof media.addEventListener === "function") media.addEventListener("change", onChange);
  else if (typeof media.addListener === "function") media.addListener(onChange);
})();
