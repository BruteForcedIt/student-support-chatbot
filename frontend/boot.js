/* Runs in <head> before the student chat page paints (kept in its own file because the page's
   security policy does not allow scripts written inside the HTML). Sets the light/dark theme
   and, inside the side panel (widget.js opens the page with ?embed=1), the compact layout. */
(function () {
  "use strict";
  try {
    var t = localStorage.getItem("cb-theme") ||
      (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.setAttribute("data-theme", t);
  } catch (e) { /* storage blocked: stay on light */ }
  if (/[?&]embed=1/.test(location.search)) document.documentElement.classList.add("cb-embed");
})();
