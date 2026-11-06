/* =====================================================================
   AI Student Support Buddy: side-panel widget

   Add the Buddy to ANY web page (NottinghamHub, Moodle, a faculty site) with one line:

     <script src="http://localhost:8000/app/widget.js" defer></script>

   Optional settings on the same tag:
     data-category="finance"   open focused on a topic (general, academic, modules, finance, documents, campus)
     data-lang="ms"            start in a language (en, ms, zh)
     data-dock="false"         on wide screens, overlay the page instead of pushing it aside
     data-label="Need help?"   text on the launcher button

   From the page's own code:
     SupportBuddy.open()   SupportBuddy.close()   SupportBuddy.toggle()
     SupportBuddy.ask("How do I pay my fees?")    // opens the panel and asks the question

   Any element with data-buddy-ask="question" becomes an "ask the Buddy" link.

   The chat itself runs in an iframe (index.html?embed=1), so the host page's styles can't break it
   and it can't read the host page.
   ===================================================================== */
(function () {
  "use strict";
  if (window.SupportBuddy) return;               // included twice

  var script = document.currentScript;
  var BASE = script ? script.src.replace(/widget\.js(\?.*)?$/, "") : "/app/";
  var ORIGIN = new URL(BASE, location.href).origin;
  var opts = (script && script.dataset) || {};
  var WIDTH = 420;                                // px, panel width on large screens
  var DOCK_MIN = 1100;                            // px, from this screen width the page moves aside
  var KEY = "cb-widget-open";

  var CREST = BASE + "style/favicon.png";
  var LABELS = {
    en: { open: "Ask Support Buddy", title: "AI Student Support Buddy", close: "Close" },
    ms: { open: "Tanya Rakan Sokongan", title: "Rakan Sokongan Pelajar AI", close: "Tutup" },
    zh: { open: "询问支持助手", title: "AI 学生支持助手", close: "关闭" }
  };
  var lang = LABELS[opts.lang] ? opts.lang : "en";
  var L = LABELS[lang];

  // ------------------------------------------------------------ styles (scoped by the cbw- prefix)
  var css = [
    ".cbw-launcher{position:fixed;right:20px;bottom:20px;z-index:2147483000;display:flex;align-items:center;gap:10px;",
    "padding:8px 18px 8px 8px;border:0;border-radius:999px;background:#10263b;color:#fff;cursor:pointer;",
    "font:600 15px/1.2 'Atkinson Hyperlegible Next','Segoe UI',system-ui,sans-serif;",
    "box-shadow:0 6px 20px rgba(16,38,59,.28),0 2px 6px rgba(16,38,59,.18);transition:transform .2s ease,opacity .2s ease}",
    ".cbw-launcher:hover{transform:translateY(-2px)}",
    ".cbw-launcher:focus-visible{outline:3px solid #2f7fd0;outline-offset:3px}",
    ".cbw-launcher img{width:36px;height:36px;border-radius:50%;background:#fff}",
    ".cbw-launcher.cbw-hidden{opacity:0;pointer-events:none;transform:translateY(12px)}",
    ".cbw-dot{position:absolute;top:6px;left:36px;width:10px;height:10px;border-radius:50%;background:#3fbf7f;border:2px solid #10263b}",
    ".cbw-panel{position:fixed;top:0;right:0;bottom:0;z-index:2147483001;width:" + WIDTH + "px;max-width:100vw;",
    "background:#eef1f4;box-shadow:-8px 0 30px rgba(16,38,59,.22);transform:translateX(105%);visibility:hidden;",
    "transition:transform .28s cubic-bezier(.2,.8,.2,1),visibility 0s linear .28s;display:flex}",
    ".cbw-panel.cbw-open{transform:none;visibility:visible;transition:transform .28s cubic-bezier(.2,.8,.2,1)}",
    ".cbw-panel iframe{flex:1;width:100%;height:100%;border:0;display:block}",
    ".cbw-resize{position:absolute;left:-4px;top:0;bottom:0;width:8px;cursor:ew-resize}",
    ".cbw-loading{position:absolute;inset:0;display:grid;place-items:center;color:#556474;",
    "font:15px 'Atkinson Hyperlegible Next','Segoe UI',system-ui,sans-serif}",
    "html.cbw-docked body{margin-right:var(--cbw-width," + WIDTH + "px)!important;transition:margin-right .28s cubic-bezier(.2,.8,.2,1)}",
    "html.cbw-dock-ready body{transition:margin-right .28s cubic-bezier(.2,.8,.2,1)}",
    "@media (max-width:600px){.cbw-panel{width:100vw!important}.cbw-launcher{right:14px;bottom:14px}",
    ".cbw-launcher span{display:none}.cbw-launcher{padding:8px}.cbw-resize{display:none}}",
    "@media (prefers-reduced-motion:reduce){.cbw-panel,.cbw-panel.cbw-open,.cbw-launcher,html.cbw-docked body{transition:none}}"
  ].join("");
  var style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  // ------------------------------------------------------------ launcher button
  var launcher = document.createElement("button");
  launcher.type = "button";
  launcher.className = "cbw-launcher";
  launcher.setAttribute("aria-expanded", "false");
  launcher.setAttribute("aria-controls", "cbw-panel");
  launcher.innerHTML = '<img alt="" src="' + CREST + '"><i class="cbw-dot" aria-hidden="true"></i><span></span>';
  launcher.querySelector("span").textContent = opts.label || L.open;
  launcher.setAttribute("aria-label", opts.label || L.open);

  // ------------------------------------------------------------ panel
  var panel = document.createElement("aside");
  panel.className = "cbw-panel";
  panel.id = "cbw-panel";
  panel.setAttribute("role", "complementary");
  panel.setAttribute("aria-label", L.title);
  var resizer = document.createElement("div");
  resizer.className = "cbw-resize";
  resizer.setAttribute("aria-hidden", "true");
  var loading = document.createElement("div");
  loading.className = "cbw-loading";
  loading.textContent = "…";
  panel.appendChild(resizer);
  panel.appendChild(loading);

  var frame = null;          // created on first open, so the host page loads no faster or slower
  var ready = false;
  var queue = [];
  var isOpen = false;

  function src() {
    var q = ["embed=1"];
    if (opts.lang) q.push("lang=" + encodeURIComponent(opts.lang));
    if (opts.category) q.push("category=" + encodeURIComponent(opts.category));
    return BASE + "index.html?" + q.join("&");
  }

  function post(msg) {
    msg.source = "cb-widget";
    if (ready && frame) frame.contentWindow.postMessage(msg, ORIGIN);
    else queue.push(msg);
  }

  function ensureFrame() {
    if (frame) return;
    frame = document.createElement("iframe");
    frame.title = L.title;
    frame.src = src();
    frame.allow = "microphone; clipboard-write";      // voice input and the Copy button
    panel.appendChild(frame);
  }

  function dockable() {
    return opts.dock !== "false" && window.innerWidth >= DOCK_MIN;
  }

  function setDock() {
    document.documentElement.classList.toggle("cbw-docked", isOpen && dockable());
  }

  function open(focus) {
    ensureFrame();
    isOpen = true;
    panel.classList.add("cbw-open");
    launcher.classList.add("cbw-hidden");
    launcher.setAttribute("aria-expanded", "true");
    setDock();
    try { sessionStorage.setItem(KEY, "1"); } catch (e) { /* blocked */ }
    if (focus !== false) {
      setTimeout(function () { frame.focus(); post({ type: "focus" }); }, 300);
    }
  }

  function close() {
    isOpen = false;
    panel.classList.remove("cbw-open");
    launcher.classList.remove("cbw-hidden");
    launcher.setAttribute("aria-expanded", "false");
    setDock();
    try { sessionStorage.removeItem(KEY); } catch (e) { /* blocked */ }
    launcher.focus();
  }

  function toggle() { if (isOpen) close(); else open(); }

  function ask(text) {
    open();
    post({ type: "ask", text: String(text || "") });
  }

  // Messages from the chat inside the panel. Only trust our own iframe.
  window.addEventListener("message", function (e) {
    if (!frame || e.source !== frame.contentWindow || e.origin !== ORIGIN) return;
    var msg = e.data || {};
    if (msg.source !== "cb-buddy") return;
    if (msg.type === "ready") {
      ready = true;
      loading.remove();
      queue.splice(0).forEach(post);
    }
    if (msg.type === "close") close();
  });

  launcher.addEventListener("click", function () { open(); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && isOpen) close(); });
  window.addEventListener("resize", setDock);

  // Drag the left edge to make the panel wider or narrower (large screens).
  resizer.addEventListener("pointerdown", function (e) {
    e.preventDefault();
    resizer.setPointerCapture(e.pointerId);
    if (frame) frame.style.pointerEvents = "none";    // keep receiving moves over the iframe
    document.documentElement.classList.remove("cbw-dock-ready");
    function move(ev) {
      var w = Math.max(340, Math.min(window.innerWidth - ev.clientX, Math.min(760, window.innerWidth * 0.6)));
      panel.style.width = w + "px";
      document.documentElement.style.setProperty("--cbw-width", w + "px");
    }
    function up() {
      resizer.removeEventListener("pointermove", move);
      resizer.removeEventListener("pointerup", up);
      if (frame) frame.style.pointerEvents = "";
    }
    resizer.addEventListener("pointermove", move);
    resizer.addEventListener("pointerup", up);
  });

  // "Ask the Buddy" links: <a href="#" data-buddy-ask="How do I appeal a mark?">Ask about appeals</a>
  document.addEventListener("click", function (e) {
    var link = e.target.closest && e.target.closest("[data-buddy-ask]");
    if (!link) return;
    e.preventDefault();
    ask(link.getAttribute("data-buddy-ask"));
  });

  function mount() {
    document.body.appendChild(panel);
    document.body.appendChild(launcher);
    document.documentElement.classList.add("cbw-dock-ready");
    // Re-open after moving to another page, if it was open (the chat itself is restored by the page).
    var wasOpen = false;
    try { wasOpen = sessionStorage.getItem(KEY) === "1"; } catch (e) { /* blocked */ }
    if (wasOpen) open(false);
  }

  if (document.body) mount(); else document.addEventListener("DOMContentLoaded", mount);

  window.SupportBuddy = { open: open, close: close, toggle: toggle, ask: ask };
})();
