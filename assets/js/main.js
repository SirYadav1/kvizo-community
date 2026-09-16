/* Kvizo site behaviour: theme, language, animations. */
(function () {
  "use strict";

  var I18N = window.KVIZO_I18N || { en: {} };
  var STORE_LANG = "kvizo-site-lang";
  var STORE_THEME = "kvizo-site-theme";
  var html = document.documentElement;
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------------------------------------------------------------- theme */
  function savedTheme() {
    try {
      var t = localStorage.getItem(STORE_THEME);
      if (t === "light" || t === "dark") return t;
    } catch (e) {}
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function applyTheme(theme) {
    html.setAttribute("data-theme", theme);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", theme === "dark" ? "#0E0A18" : "#7C3AED");
    var toggle = document.getElementById("themeToggle");
    if (toggle) toggle.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
  }

  applyTheme(savedTheme());

  /* ------------------------------------------------------------ language */
  function savedLang() {
    var supported = Object.keys(I18N);
    try {
      var l = localStorage.getItem(STORE_LANG);
      if (l && supported.indexOf(l) !== -1) return l;
    } catch (e) {}
    var nav = (navigator.language || "en").slice(0, 2).toLowerCase();
    if (nav === "zh") nav = "zh";
    return supported.indexOf(nav) !== -1 ? nav : "en";
  }

  function t(lang, key) {
    var dict = I18N[lang] || {};
    var value = dict[key];
    if (value === undefined) value = (I18N.en || {})[key];
    return value === undefined ? key : value;
  }

  var currentLang = savedLang();

  function applyLanguage(lang, animate) {
    currentLang = lang;
    html.setAttribute("lang", lang === "zh" ? "zh-CN" : lang);
    try { localStorage.setItem(STORE_LANG, lang); } catch (e) {}

    var nodes = document.querySelectorAll("[data-i18n]");
    for (var i = 0; i < nodes.length; i++) {
      nodes[i].textContent = t(lang, nodes[i].getAttribute("data-i18n"));
    }

    var label = document.querySelector(".lang-current");
    if (label) {
      var names = { en: "English", hi: "हिन्दी", zh: "中文", es: "Español", fr: "Français" };
      label.textContent = names[lang] || "English";
    }

    var options = document.querySelectorAll(".lang-menu [data-lang]");
    for (var j = 0; j < options.length; j++) {
      options[j].setAttribute("aria-selected", options[j].getAttribute("data-lang") === lang ? "true" : "false");
    }

    buildMarquee(lang);
    applyLevelLabels(lang);
    renderLevel(currentXp, false);
    setDocTitle(lang);

    if (animate && !reduceMotion) {
      document.body.animate(
        [{ opacity: 0.55 }, { opacity: 1 }],
        { duration: 260, easing: "ease-out" }
      );
    }
  }

  function setDocTitle(lang) {
    var titles = {
      en: "Kvizo — Forge knowledge. Earn XP. Play anywhere.",
      hi: "Kvizo — ज्ञान गढ़ें। XP कमाएँ। कहीं भी खेलें।",
      zh: "Kvizo — 锻造知识。赚取 XP。随时随地开玩。",
      es: "Kvizo — Forja conocimiento. Gana XP. Juega donde quieras.",
      fr: "Kvizo — Forgez votre savoir. Gagnez de l'XP. Jouez partout."
    };
    document.title = titles[lang] || titles.en;
  }

  /* -------------------------------------------------------------- marquee */
  var BADGE_KEYS = [
    "badge.1", "badge.2", "badge.3", "badge.4", "badge.5", "badge.6", "badge.7", "badge.8",
    "badge.9", "badge.10", "badge.11", "badge.12", "badge.13", "badge.14", "badge.15", "badge.16"
  ];

  function buildMarquee(lang) {
    var track = document.getElementById("marqueeTrack");
    if (!track) return;
    var html2 = "";
    for (var pass = 0; pass < 2; pass++) {
      for (var i = 0; i < BADGE_KEYS.length; i++) {
        html2 += "<span></span>";
      }
    }
    track.innerHTML = html2;
    var spans = track.children;
    var index = 0;
    for (var p = 0; p < 2; p++) {
      for (var k = 0; k < BADGE_KEYS.length; k++) {
        spans[index++].textContent = t(lang, BADGE_KEYS[k]);
      }
    }
  }

  /* --------------------------------------------------------------- levels
     Thresholds and titles mirror XpEngine.kt in the app exactly:
     level 1..6 start at 0 / 200 / 500 / 1000 / 2000 / 5000 XP.
     The bar, the label and the slider are all driven by one XP number, so the
     readout can never disagree with itself. */
  var LEVELS = [
    { xp: 0, key: "level.1" },
    { xp: 200, key: "level.2" },
    { xp: 500, key: "level.3" },
    { xp: 1000, key: "level.4" },
    { xp: 2000, key: "level.5" },
    { xp: 5000, key: "level.6" }
  ];
  var MAX_XP = 6000;
  var currentXp = 120;

  /* Every XP value is snapped to the slider's own `step` before it is shown.
     Without this a click on a level could render 335 XP while the range input
     sat on 340, so the readout and the thumb disagreed. */
  function xpStep() {
    var slider = document.getElementById("xpSlider");
    var step = slider ? parseFloat(slider.getAttribute("step")) : 1;
    return step > 0 ? step : 1;
  }

  function snapXp(xp) {
    var step = xpStep();
    return Math.max(0, Math.min(MAX_XP, Math.round(xp / step) * step));
  }

  /* levelFromXp — the same walk the app performs. */
  function levelIndexForXp(xp) {
    var index = 0;
    while (index < LEVELS.length - 1 && xp >= LEVELS[index + 1].xp) index++;
    return index;
  }

  /* totalProgress — 0..1 across the whole 0..MAX_XP range.
     The bar is scaled to the full range rather than to the current level, so it
     only ever moves forward as XP grows. A per-level bar reset to zero at every
     threshold, which read as the slider jumping backwards mid-drag. */
  function totalProgressForXp(xp) {
    return Math.max(0, Math.min(1, xp / MAX_XP));
  }

  /* One tick per level threshold. Without them nothing on the bar says where a
     level starts now that the bar spans the entire XP range. */
  function buildLevelTicks() {
    var bar = document.getElementById("levelBar");
    if (!bar || bar.querySelector(".levels-tick")) return;
    for (var i = 1; i < LEVELS.length; i++) {
      var tick = document.createElement("span");
      tick.className = "levels-tick";
      tick.setAttribute("aria-hidden", "true");
      tick.style.left = ((LEVELS[i].xp / MAX_XP) * 100).toFixed(3) + "%";
      bar.appendChild(tick);
    }
  }

  function formatXp(value) {
    return String(value).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }

  /* The list labels read "from {n} XP" so they describe a threshold rather than
     a total, which keeps them from ever looking wrong next to the bar. */
  function applyLevelLabels(lang) {
    var labels = document.querySelectorAll("#levelList em");
    for (var i = 0; i < labels.length; i++) {
      var button = labels[i].parentNode;
      var threshold = parseInt(button.getAttribute("data-xp"), 10) || 0;
      labels[i].textContent = t(lang, "levels.from").replace("{n}", formatXp(threshold));
    }
  }

  function renderLevel(xp, animate) {
    var value = snapXp(xp);
    currentXp = value;

    var index = levelIndexForXp(value);
    var level = LEVELS[index];
    var next = index + 1 < LEVELS.length ? LEVELS[index + 1] : null;
    var pct = Math.round(totalProgressForXp(value) * 100);

    var fill = document.getElementById("levelFill");
    var name = document.getElementById("levelName");
    var xpEl = document.getElementById("levelXp");
    var bar = document.getElementById("levelBar");
    var nextEl = document.getElementById("levelNext");
    var slider = document.getElementById("xpSlider");
    var out = document.getElementById("levelOut");
    var panel = document.getElementById("levelsPanel");

    /* the panel's hue follows the level, so the bar, name and thumb recolour */
    if (panel) panel.setAttribute("data-level", String(index + 1));

    if (name) name.textContent = t(currentLang, level.key);
    if (xpEl) xpEl.textContent = formatXp(value) + " XP";
    if (nextEl) {
      nextEl.textContent = next
        ? t(currentLang, "levels.next")
            .replace("{n}", formatXp(next.xp - value))
            .replace("{name}", t(currentLang, next.key))
        : t(currentLang, "levels.max");
    }
    if (bar) {
      bar.setAttribute("aria-valuenow", String(pct));
      bar.setAttribute("aria-valuetext", xpEl ? xpEl.textContent : formatXp(value) + " XP");
    }
    if (fill) fill.style.width = pct + "%";
    if (out) out.textContent = formatXp(value);
    if (slider && slider.value !== String(value)) slider.value = String(value);

    var buttons = document.querySelectorAll("#levelList button");
    for (var i = 0; i < buttons.length; i++) {
      var isActive = i === index;
      buttons[i].setAttribute("aria-pressed", isActive ? "true" : "false");
      buttons[i].setAttribute("data-active", isActive ? "true" : "false");
    }

    if (animate && name) {
      name.classList.remove("is-bumped");
      void name.offsetWidth; /* restart the animation on a repeat click */
      name.classList.add("is-bumped");
    }
  }

  /* --------------------------------------------------------------- reveal */
  function initReveal() {
    var items = document.querySelectorAll(".reveal");
    if (reduceMotion || !("IntersectionObserver" in window)) {
      for (var i = 0; i < items.length; i++) items[i].classList.add("in");
      return;
    }

    var observer = new IntersectionObserver(function (entries) {
      var shown = 0;
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var el = entry.target;
        el.style.setProperty("--d", (shown * 0.07).toFixed(2) + "s");
        el.classList.add("in");
        observer.unobserve(el);
        shown++;
      });
    }, { threshold: 0.12 });

    /* Anything already on screen (or above it, after a deep link or a restored
       scroll position) is revealed straight away; the rest waits for the scroll. */
    var fold = window.innerHeight * 0.94;
    var immediate = [];
    for (var j = 0; j < items.length; j++) {
      if (items[j].getBoundingClientRect().top < fold) immediate.push(items[j]);
      else observer.observe(items[j]);
    }

    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        for (var k = 0; k < immediate.length; k++) {
          immediate[k].style.setProperty("--d", Math.min(k * 0.06, 0.42).toFixed(2) + "s");
          immediate[k].classList.add("in");
        }
      });
    });
  }

  /* ---------------------------------------------------------------- count */
  function initCounters() {
    var counters = document.querySelectorAll(".count");
    if (!counters.length) return;

    function run(el) {
      var target = parseInt(el.getAttribute("data-count"), 10) || 0;
      if (reduceMotion || target === 0) {
        el.textContent = String(target);
        return;
      }
      var start = performance.now();
      var duration = 1300;
      function frame(now) {
        var p = Math.min(1, (now - start) / duration);
        var eased = 1 - Math.pow(1 - p, 3);
        el.textContent = String(Math.round(target * eased));
        if (p < 1) requestAnimationFrame(frame);
      }
      requestAnimationFrame(frame);
    }

    if (!("IntersectionObserver" in window)) {
      for (var i = 0; i < counters.length; i++) run(counters[i]);
      return;
    }

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        /* also fire for counters the user has already scrolled past */
        if (!entry.isIntersecting && entry.boundingClientRect.bottom > 0) return;
        run(entry.target);
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.5 });

    for (var j = 0; j < counters.length; j++) observer.observe(counters[j]);
  }

  /* ------------------------------------------------- scroll feedback layer */
  function initScrollFeedback() {
    var bar = document.getElementById("scrollBar");
    var nav = document.querySelector(".nav");
    var toTop = document.getElementById("toTop");
    var scheduled = false;

    function update() {
      scheduled = false;
      var doc = document.documentElement;
      var max = doc.scrollHeight - window.innerHeight;
      var y = window.scrollY || doc.scrollTop || 0;
      if (bar) bar.style.width = (max > 0 ? Math.min(100, (y / max) * 100) : 0) + "%";
      if (nav) nav.classList.toggle("is-scrolled", y > 24);
      if (toTop) toTop.classList.toggle("is-visible", y > 900);
    }

    function onScroll() {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(update);
    }

    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    window.addEventListener("pageshow", onScroll);
    update();

    if (toTop) {
      toTop.addEventListener("click", function () {
        window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" });
      });
    }
  }

  /* ---------------------------------------------------------- hero parallax */
  function initParallax() {
    if (reduceMotion) return;
    var stage = document.querySelector(".hero-visual");
    var hero = document.querySelector(".hero");
    if (!stage || !hero || window.matchMedia("(hover: none)").matches) return;

    hero.addEventListener("pointermove", function (event) {
      var rect = hero.getBoundingClientRect();
      var relX = (event.clientX - rect.left) / rect.width - 0.5;
      var relY = (event.clientY - rect.top) / rect.height - 0.5;
      stage.style.setProperty("--px", (relX * 16).toFixed(1) + "px");
      stage.style.setProperty("--py", (relY * 14).toFixed(1) + "px");
    });

    hero.addEventListener("pointerleave", function () {
      stage.style.setProperty("--px", "0px");
      stage.style.setProperty("--py", "0px");
    });
  }

  /* ------------------------------------------------------------------ nav */
  function initNav() {
    var toggle = document.getElementById("themeToggle");
    if (toggle) {
      toggle.addEventListener("click", function () {
        var next = html.getAttribute("data-theme") === "dark" ? "light" : "dark";
        applyTheme(next);
        try { localStorage.setItem(STORE_THEME, next); } catch (e) {}
      });
    }

    var langBox = document.querySelector(".lang");
    var langBtn = document.querySelector(".lang-btn");
    if (langBox && langBtn) {
      langBtn.addEventListener("click", function () {
        var open = langBox.getAttribute("data-open") === "true";
        langBox.setAttribute("data-open", open ? "false" : "true");
        langBtn.setAttribute("aria-expanded", open ? "false" : "true");
      });

      document.addEventListener("click", function (event) {
        if (!langBox.contains(event.target)) {
          langBox.setAttribute("data-open", "false");
          langBtn.setAttribute("aria-expanded", "false");
        }
      });

      document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
          langBox.setAttribute("data-open", "false");
          langBtn.setAttribute("aria-expanded", "false");
        }
      });

      var buttons = langBox.querySelectorAll("[data-lang]");
      for (var i = 0; i < buttons.length; i++) {
        (function (button) {
          button.addEventListener("click", function () {
            applyLanguage(button.getAttribute("data-lang"), true);
            langBox.setAttribute("data-open", "false");
            langBtn.setAttribute("aria-expanded", "false");
          });
        })(buttons[i]);
      }
    }

    var list = document.getElementById("levelList");
    if (list) {
      var items = list.querySelectorAll("button");
      for (var j = 0; j < items.length; j++) {
        (function (button) {
          button.addEventListener("click", function () {
            /* Preview the level that was pressed: land exactly on its threshold,
               which is also the XP printed on the button ("from N XP"), so the
               bar stops on that level's tick and nothing can contradict itself. */
            renderLevel(parseInt(button.getAttribute("data-xp"), 10) || 0, true);
          });
        })(items[j]);
      }
    }

    var slider = document.getElementById("xpSlider");
    if (slider) {
      slider.addEventListener("input", function () {
        renderLevel(parseFloat(slider.value), false);
      });
    }
  }

  /* ----------------------------------------------------------------- init */
  function init() {
    initNav();
    buildLevelTicks();
    applyLanguage(currentLang, false);
    renderLevel(currentXp, false);
    initReveal();
    initCounters();
    initScrollFeedback();
    initParallax();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
