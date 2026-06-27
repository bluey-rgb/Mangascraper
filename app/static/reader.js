// Reader enhancements: keyboard navigation, display settings (saved in the
// browser via localStorage), and optional auto-advance to the next chapter.

(function () {
  "use strict";

  var reader = document.getElementById("reader");
  var nextUrl = reader ? reader.getAttribute("data-next-url") : "";
  // Grab the actual prev/next links (anchors only, not disabled spans).
  var links = Array.prototype.slice.call(
    document.querySelectorAll(".reader-nav.top a.nav-btn")
  );
  var prevLink = links.find(function (a) { return a.textContent.indexOf("Prev") !== -1; });
  var nextLink = links.find(function (a) { return a.textContent.indexOf("Next") !== -1; });

  // ----- Display settings -----------------------------------------------
  var KEY = "mangaReaderSettings";
  var defaults = { width: "fit", dim: 100, gap: false, autoadvance: true };
  var settings = Object.assign({}, defaults, load());

  function load() {
    try { return JSON.parse(localStorage.getItem(KEY)) || {}; }
    catch (e) { return {}; }
  }
  function save() { localStorage.setItem(KEY, JSON.stringify(settings)); }

  var WIDTHS = { fit: "800px", narrow: "600px", wide: "1100px", full: "100%" };

  function apply() {
    if (reader) {
      reader.style.setProperty("--page-width", WIDTHS[settings.width] || "800px");
      reader.style.filter = "brightness(" + settings.dim / 100 + ")";
      reader.classList.toggle("with-gap", !!settings.gap);
    }
  }

  // Wire up the controls and reflect current values.
  var widthSel = document.getElementById("set-width");
  var dimRange = document.getElementById("set-dim");
  var gapChk = document.getElementById("set-gap");
  var autoChk = document.getElementById("set-autoadvance");

  if (widthSel) {
    widthSel.value = settings.width;
    widthSel.addEventListener("change", function () {
      settings.width = widthSel.value; save(); apply();
    });
  }
  if (dimRange) {
    dimRange.value = settings.dim;
    dimRange.addEventListener("input", function () {
      settings.dim = parseInt(dimRange.value, 10); save(); apply();
    });
  }
  if (gapChk) {
    gapChk.checked = settings.gap;
    gapChk.addEventListener("change", function () {
      settings.gap = gapChk.checked; save(); apply();
    });
  }
  if (autoChk) {
    autoChk.checked = settings.autoadvance;
    autoChk.addEventListener("change", function () {
      settings.autoadvance = autoChk.checked; save();
    });
  }

  apply();

  // ----- Keyboard navigation --------------------------------------------
  document.addEventListener("keydown", function (e) {
    // Ignore when typing in a field.
    var t = e.target.tagName;
    if (t === "INPUT" || t === "SELECT" || t === "TEXTAREA") return;
    if (e.key === "ArrowLeft" && prevLink) { window.location.href = prevLink.href; }
    if (e.key === "ArrowRight" && nextLink) { window.location.href = nextLink.href; }
  });

  // ----- Auto-advance ----------------------------------------------------
  // We deliberately use a scroll listener (not just an observer that fires on
  // load) and require a genuine user scroll to the bottom — otherwise a chapter
  // whose images are still loading has near-zero height and would advance
  // instantly.
  if (nextUrl) {
    var fired = false;
    var userScrolled = false;

    window.addEventListener("scroll", function () {
      if (window.scrollY > 100) userScrolled = true;
      if (fired || !settings.autoadvance || !userScrolled) return;

      var doc = document.documentElement;
      var scrollBottom = window.innerHeight + window.scrollY;
      var pageIsScrollable = doc.scrollHeight > window.innerHeight * 1.3;

      if (pageIsScrollable && scrollBottom >= doc.scrollHeight - 150) {
        fired = true;
        window.location.href = nextUrl;
      }
    }, { passive: true });
  }
})();
