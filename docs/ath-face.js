/* アースのウェブフォントフェイス。faces.json が一覧の正。 */
(function () {
  var DEFAULT_ID = "aarth";
  var storageKey = "ath-face";
  var facesUrl = "faces.json";
  var faces = [];
  var defaultId = DEFAULT_ID;

  var thisScript = document.currentScript;
  if (thisScript) {
    var specified = thisScript.getAttribute("data-faces");
    if (specified) facesUrl = specified;
  }

  function stored() {
    try {
      return localStorage.getItem(storageKey) || "";
    } catch (err) {
      return "";
    }
  }

  function knownId(id) {
    if (!id) return false;
    for (var i = 0; i < faces.length; i++) {
      if (faces[i].id === id) return true;
    }
    return false;
  }

  function apply(id) {
    if (!id) {
      document.documentElement.removeAttribute("data-ath-face");
      return;
    }
    document.documentElement.setAttribute("data-ath-face", id);
  }

  function persist(id) {
    try {
      if (!id || id === defaultId) localStorage.removeItem(storageKey);
      else localStorage.setItem(storageKey, id);
    } catch (err) { /* private mode など */ }
  }

  function currentId() {
    var saved = stored();
    if (knownId(saved)) return saved;
    return defaultId;
  }

  function fillSelect(select) {
    if (!select) return;
    select.innerHTML = "";
    faces.forEach(function (face) {
      var option = document.createElement("option");
      option.value = face.id;
      option.textContent = face.label || face.family || face.id;
      select.appendChild(option);
    });
    select.value = currentId();
    select.addEventListener("change", function () {
      var id = select.value;
      persist(id);
      apply(id);
    });
  }

  function boot(catalog) {
    if (catalog && typeof catalog === "object") {
      if (catalog.storageKey) storageKey = catalog.storageKey;
      if (catalog.default) defaultId = catalog.default;
      if (Array.isArray(catalog.faces)) faces = catalog.faces;
    }
    apply(currentId());
    fillSelect(document.getElementById("ath-face-select"));
  }

  apply(stored() || DEFAULT_ID);

  fetch(facesUrl, { credentials: "same-origin" })
    .then(function (res) {
      if (!res.ok) throw new Error("faces.json " + res.status);
      return res.json();
    })
    .then(boot)
    .catch(function () {
      boot({ default: DEFAULT_ID, faces: [] });
    });
})();
