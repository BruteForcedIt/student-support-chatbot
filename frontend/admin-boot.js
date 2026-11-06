/* Runs in <head> before the staff page paints (kept in its own file because the page's security
   policy does not allow scripts written inside the HTML). Sets the light/dark theme. */
(function () {
  "use strict";
  try {
    var t = localStorage.getItem("cb-theme") ||
      (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.setAttribute("data-theme", t);
  } catch (e) { /* storage blocked: stay on light */ }
})();
