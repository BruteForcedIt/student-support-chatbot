/* =====================================================================
   Admin: Analytics, Peer review and Ethics tests tabs.
   Uses the helpers admin.js puts on window.CBAdmin, and Chart.js.
   ===================================================================== */
(function () {
  "use strict";

  var A = window.CBAdmin;
  var $ = function (s) { return document.querySelector(s); };
  var $$ = function (s) { return Array.prototype.slice.call(document.querySelectorAll(s)); };
  var el = A.el;
  var charts = {};
  var state = { tab: "kb", days: 30, analytics: null, ethics: null, ethicsFilter: "all", poll: null, answer: null };

  var LANG_NAMES = { en: "English", ms: "Bahasa Melayu", zh: "Chinese" };
  var OUTCOME_NAMES = {
    answered: "Answered from documents", no_info: "No matching document", small_talk: "Greeting or thanks",
    crisis: "Sent to human support", blocked: "Blocked by safety rules", error: "Model unavailable"
  };
  var CATEGORY_NAMES = { safety: "Distress safety", injection: "Prompt injection", harmful: "Harmful requests",
    hallucination: "No made-up facts", privacy: "Privacy", fairness: "Fairness", multilingual: "Multilingual",
    bias: "Answer bias" };
  var TABS = ["kb", "analytics", "review", "ethics", "accounts"];
  var RUBRIC = [
    ["accuracy", "Accurate", "Matches the official documents, nothing invented"],
    ["completeness", "Complete", "Answers the whole question"],
    ["clarity", "Clear", "Easy for a student to follow"],
    ["tone", "Tone", "Kind, respectful and professional"]
  ];

  // ---------------------------------------------------------- colours (validated palette, see README)
  function dark() { return document.documentElement.getAttribute("data-theme") === "dark"; }
  function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  function colours() {
    var d = dark();
    return {
      s1: d ? "#3987e5" : "#2a78d6",       // series 1 (blue)
      s2: d ? "#d95926" : "#eb6834",       // series 2 (orange)
      good: "#0ca30c", warning: "#fab219", critical: "#d03b3b",
      ink: css("--ink"), muted: css("--muted"), line: css("--line"), surface: css("--surface")
    };
  }

  function baseOptions(extra) {
    var c = colours();
    var opts = {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 300 },
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false, labels: { color: c.ink, boxWidth: 12, boxHeight: 12, useBorderRadius: true, borderRadius: 3 } },
        tooltip: { backgroundColor: c.surface, titleColor: c.ink, bodyColor: c.ink, borderColor: c.line, borderWidth: 1,
                   padding: 10, boxPadding: 4, usePointStyle: true }
      },
      scales: {
        x: { grid: { display: false }, border: { color: c.line }, ticks: { color: c.muted, maxRotation: 0, autoSkipPadding: 12 } },
        y: { beginAtZero: true, grid: { color: c.line, drawTicks: false }, border: { display: false },
             ticks: { color: c.muted, precision: 0, padding: 6 } }
      }
    };
    return deepMerge(opts, extra || {});
  }
  function deepMerge(a, b) {
    Object.keys(b).forEach(function (k) {
      if (b[k] && typeof b[k] === "object" && !Array.isArray(b[k]) && a[k] && typeof a[k] === "object") deepMerge(a[k], b[k]);
      else a[k] = b[k];
    });
    return a;
  }
  function bar(colour, extra) {
    return Object.assign({ backgroundColor: colour, borderRadius: 4, borderSkipped: "start", maxBarThickness: 22,
                           borderColor: colours().surface, borderWidth: 1 }, extra || {});
  }

  function draw(id, config) {
    if (!window.Chart) return;
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart(document.getElementById(id), config);
  }

  function pct(x) { return x == null ? "–" : Math.round(x * 100) + "%"; }
  function secs(ms) { return ms == null ? "–" : (ms / 1000).toFixed(ms < 10000 ? 1 : 0) + " s"; }

  function kpi(container, items) {
    container.replaceChildren();
    items.forEach(function (it) {
      var box = el("div", "ad-stat");
      box.appendChild(el("dt", null, it[0]));
      var dd = el("dd", null, it[1]);
      if (it[2]) dd.appendChild(el("small", null, " " + it[2]));
      box.appendChild(dd);
      container.appendChild(box);
    });
  }

  // ---------------------------------------------------------- tabs
  function showTab(name) {
    if (A.role !== "admin") name = "review";          // lecturers only have the Peer review tab
    state.tab = name;
    TABS.forEach(function (t) {
      var btn = $("#tab-btn-" + t), panel = $("#tab-" + t);
      var on = t === name;
      btn.setAttribute("aria-selected", String(on));
      btn.tabIndex = on ? 0 : -1;
      panel.hidden = !on;
    });
    if (name === "analytics") loadAnalytics();
    if (name === "review") loadReviews();
    if (name === "ethics") loadEthics();
    if (name === "accounts") A.loadAccounts();
  }
  $$(".ad-tab").forEach(function (btn) {
    btn.addEventListener("click", function () { showTab(btn.id.replace("tab-btn-", "")); });
    btn.addEventListener("keydown", function (e) {
      var step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
      if (!step) return;
      var shown = $$(".ad-tab").filter(function (b) { return b.offsetParent !== null; });   // skip hidden tabs
      var next = shown[(shown.indexOf(btn) + step + shown.length) % shown.length];
      next.focus(); next.click();
    });
  });

  // ---------------------------------------------------------- analytics
  $$(".ad-range .ad-chip").forEach(function (b) {
    b.addEventListener("click", function () {
      state.days = Number(b.dataset.days);
      $$(".ad-range .ad-chip").forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
      loadAnalytics();
    });
  });

  async function loadAnalytics() {
    try {
      state.analytics = await A.api("/admin/analytics?days=" + state.days);
      renderAnalytics();
    } catch (err) { A.reportError(err); }
  }

  function renderAnalytics() {
    var a = state.analytics, c = colours(), t = a.totals;
    kpi($("#kpis"), [
      ["Questions", String(t.questions), "in " + a.days + " days"],
      ["Answered from documents", pct(t.answer_rate)],
      ["Students who found it helpful", pct(t.helpful_rate), t.ratings ? "of " + t.ratings + " ratings" : "no ratings yet"],
      ["Typical reply time", secs(t.median_ms), t.p90_ms != null ? "90% under " + secs(t.p90_ms) : ""],
      ["Sent to human support", String(t.crisis), "distress messages"]
    ]);

    var labels = a.per_day.map(function (d) {
      return new Date(d.date + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short" });
    });
    draw("ch-daily", {
      type: "line",
      data: { labels: labels, datasets: [
        { label: "All questions", data: a.per_day.map(function (d) { return d.total; }), borderColor: c.s1,
          backgroundColor: c.s1, borderWidth: 2, pointRadius: 0, pointHoverRadius: 5, tension: 0.25 },
        { label: "Answered from documents", data: a.per_day.map(function (d) { return d.answered; }), borderColor: c.s2,
          backgroundColor: c.s2, borderWidth: 2, pointRadius: 0, pointHoverRadius: 5, tension: 0.25 }
      ] },
      options: baseOptions({ plugins: { legend: { display: true, position: "top", align: "start" } } })
    });

    var outcomeKeys = Object.keys(a.outcomes).filter(function (k) { return a.outcomes[k] > 0 || k === "answered" || k === "no_info"; });
    draw("ch-outcomes", {
      type: "bar",
      data: { labels: outcomeKeys.map(function (k) { return OUTCOME_NAMES[k]; }),
              datasets: [bar(c.s1, { label: "Questions", data: outcomeKeys.map(function (k) { return a.outcomes[k]; }) })] },
      options: baseOptions({ indexAxis: "y", interaction: { mode: "nearest", axis: "y" },
        scales: { x: { beginAtZero: true, grid: { display: true, color: c.line }, ticks: { precision: 0 } }, y: { grid: { display: false } } } })
    });

    draw("ch-categories", {
      type: "bar",
      data: { labels: a.categories.map(function (r) { return A.categories[r.category] || r.category; }),
              datasets: [
                bar(c.s1, { label: "Answered", data: a.categories.map(function (r) { return r.answered; }) }),
                bar(c.s2, { label: "No matching document", data: a.categories.map(function (r) { return r.no_info; }) })
              ] },
      options: baseOptions({ indexAxis: "y", interaction: { mode: "index", axis: "y" },
        plugins: { legend: { display: true, position: "top", align: "start" } },
        scales: { x: { beginAtZero: true, grid: { display: true, color: c.line }, ticks: { precision: 0 } }, y: { grid: { display: false } } } })
    });

    draw("ch-hours", {
      type: "bar",
      data: { labels: a.busy_hours.map(function (_, h) { return (h < 10 ? "0" : "") + h + ":00"; }),
              datasets: [bar(c.s1, { label: "Questions", data: a.busy_hours, maxBarThickness: 14 })] },
      options: baseOptions({ scales: { x: { ticks: { autoSkip: true, maxTicksLimit: 8 } } } })
    });

    var langKeys = Object.keys(a.languages);
    draw("ch-languages", {
      type: "bar",
      data: { labels: langKeys.map(function (k) { return LANG_NAMES[k] || k; }),
              datasets: [bar(c.s1, { label: "Questions", data: langKeys.map(function (k) { return a.languages[k]; }) })] },
      options: baseOptions({ indexAxis: "y", interaction: { mode: "nearest", axis: "y" },
        scales: { x: { beginAtZero: true, grid: { display: true, color: c.line }, ticks: { precision: 0 } }, y: { grid: { display: false } } } })
    });
    var ch = a.channels || {}, chTotal = (ch.page || 0) + (ch.widget || 0);
    $("#channel-split").textContent = chTotal
      ? "Asked from the side panel on other pages: " + pct((ch.widget || 0) / chTotal) + ", from the full chat page: " + pct((ch.page || 0) / chTotal) + "."
      : "";

    // knowledge gaps
    var list = $("#gaps-list");
    list.replaceChildren();
    if (!a.unanswered_enabled) {
      $("#gaps-note").textContent = "Switched off. To see which questions have no matching document, start the server with " +
        "LOG_UNANSWERED=true (agree this with the Hub first: it is the only place question text is kept). " +
        "Meanwhile, the topic chart above shows where answers are missing.";
    } else if (!a.unanswered.length) {
      $("#gaps-note").textContent = "None in this period.";
    } else {
      $("#gaps-note").textContent = "Each of these is a document to add or improve. Crisis and blocked messages are never listed.";
      a.unanswered.forEach(function (u) {
        var li = el("li");
        li.appendChild(el("span", "ad-gap-q", u.question));
        li.appendChild(el("span", "ad-gap-meta", (A.categories[u.category] || u.category) + " · " + (LANG_NAMES[u.language] || u.language) + " · " + A.relTime(u.ts)));
        list.appendChild(li);
      });
    }

    // table view (accessibility, and for copying into the report)
    var rows = [["Topic", "Questions", "Answered", "No document", "Helpful", "Not helpful"]].concat(
      a.categories.map(function (r) { return [A.categories[r.category] || r.category, r.total, r.answered, r.no_info, r.up, r.down]; }));
    $("#analytics-table").replaceChildren(table(rows));
  }

  function table(rows) {
    var t = el("table", "ad-table");
    rows.forEach(function (r, i) {
      var tr = el("tr");
      r.forEach(function (cell) { tr.appendChild(el(i ? "td" : "th", null, String(cell))); });
      t.appendChild(tr);
    });
    return t;
  }

  // ---------------------------------------------------------- peer review
  function buildRubric() {
    var fs = $("#rubric");
    fs.appendChild(el("legend", "sr-only", "Rubric"));
    RUBRIC.forEach(function (r) {
      var row = el("div", "ad-rubric-row");
      var label = el("div", "ad-rubric-label");
      label.appendChild(el("strong", null, r[1]));
      label.appendChild(el("span", null, r[2]));
      row.appendChild(label);
      var scale = el("div", "ad-scale");
      scale.setAttribute("role", "radiogroup");
      scale.setAttribute("aria-label", r[1] + ", 1 to 5");
      for (var n = 1; n <= 5; n++) {
        var lab = el("label", "ad-scale-opt");
        var inp = el("input");
        inp.type = "radio"; inp.name = "rb-" + r[0]; inp.value = n; inp.required = true;
        lab.appendChild(inp);
        lab.appendChild(el("span", null, String(n)));
        scale.appendChild(lab);
      }
      row.appendChild(scale);
      fs.appendChild(row);
    });
    var safe = el("div", "ad-rubric-row");
    var sl = el("div", "ad-rubric-label");
    sl.appendChild(el("strong", null, "Safe to show a student"));
    sl.appendChild(el("span", null, "No harmful, private or misleading content"));
    safe.appendChild(sl);
    var opts = el("div", "ad-scale");
    opts.setAttribute("role", "radiogroup");
    opts.setAttribute("aria-label", "Safe to show a student");
    [["1", "Yes"], ["0", "No"]].forEach(function (p) {
      var lab = el("label", "ad-scale-opt ad-scale-wide");
      var inp = el("input");
      inp.type = "radio"; inp.name = "rb-safe"; inp.value = p[0]; inp.required = true;
      lab.appendChild(inp);
      lab.appendChild(el("span", null, p[1]));
      opts.appendChild(lab);
    });
    safe.appendChild(opts);
    fs.appendChild(safe);
  }
  buildRubric();

  function renderAnswerBox(data) {
    var box = $("#r-answer");
    box.hidden = false;
    box.replaceChildren();
    var label = data.flag ? OUTCOME_NAMES[data.flag] : data.answered ? "Answered from documents" : "No matching document";
    box.appendChild(el("span", "ad-cat", label));
    box.appendChild(el("p", "ad-answer-text", (data.reply || "").replace(/\*\*([^*]+)\*\*/g, "$1")));
    if (data.sources && data.sources.length) {
      box.appendChild(el("p", "ad-hint", "Sources: " + data.sources.map(function (s) { return s.title; }).join("; ")));
    }
  }

  function setRubricEnabled(on) {
    $("#rubric").disabled = !on;
    $("#r-comment").disabled = !on;
    $("#r-save-btn").disabled = !on;
  }

  $("#review-ask").addEventListener("submit", async function (e) {
    e.preventDefault();
    var q = $("#r-question").value.trim();
    if (!q) return;
    var btn = $("#r-ask-btn");
    btn.disabled = true; btn.textContent = "Waiting for the model…";
    try {
      var data = await A.api("/admin/reviews/ask", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, language: $("#r-lang").value })
      });
      state.answer = { question: q, answer: data.reply || "", language: $("#r-lang").value };
      renderAnswerBox(data);
      $("#review-rate").reset();
      setRubricEnabled(true);
    } catch (err) { A.reportError(err); }
    finally { btn.disabled = false; btn.textContent = "Get answer"; }
  });

  $("#review-rate").addEventListener("submit", async function (e) {
    e.preventDefault();
    if (!state.answer) return;
    var form = e.target, body = Object.assign({}, state.answer);
    var missing = [];
    RUBRIC.forEach(function (r) {
      var v = form.querySelector('input[name="rb-' + r[0] + '"]:checked');
      if (!v) missing.push(r[1]); else body[r[0]] = Number(v.value);
    });
    var safe = form.querySelector('input[name="rb-safe"]:checked');
    if (!safe) missing.push("Safe"); else body.safe = safe.value === "1";
    if (missing.length) { A.toast("Please rate: " + missing.join(", "), "error"); return; }
    body.comment = $("#r-comment").value.trim();
    try {
      await A.api("/admin/reviews", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      A.toast("Review saved. Thank you.");
      form.reset(); setRubricEnabled(false); state.answer = null;
      $("#r-answer").hidden = true; $("#r-question").value = "";
      loadReviews();
    } catch (err) { A.reportError(err); }
  });

  async function loadReviews() {
    try {
      var res = await Promise.all([A.api("/admin/reviews"), A.api("/admin/reviews/summary?days=90")]);
      $("#reviews-title").textContent = A.role === "admin" ? "Recent staff reviews" : "Your recent reviews";
      renderReviews(res[0]);
      renderCompare(res[1]);
    } catch (err) { A.reportError(err); }
  }

  // Three independent views of answer quality: students (thumbs), lecturers and Hub staff (rubric).
  function renderCompare(s) {
    var box = $("#compare");
    box.replaceChildren();
    var st = s.students;
    var students = el("div", "ad-compare-card");
    students.appendChild(el("p", "ad-compare-kicker", "Students (last " + s.days + " days)"));
    students.appendChild(el("p", "ad-compare-big", pct(st.helpful_rate)));
    students.appendChild(el("p", "ad-hint", st.ratings ? "found answers helpful, from " + st.ratings + " ratings" : "No student ratings yet"));
    var reasons = st.reasons, reasonTotal = Object.keys(reasons).reduce(function (n, k) { return n + reasons[k]; }, 0);
    if (reasonTotal) {
      var ul = el("ul", "ad-reason-list");
      Object.keys(reasons).sort(function (x, y) { return reasons[y] - reasons[x]; }).forEach(function (k) {
        if (!reasons[k]) return;
        var li = el("li");
        li.appendChild(el("span", null, st.reason_labels[k]));
        var meter = el("span", "ad-mini-meter"); var fill = el("span");
        fill.style.width = (reasons[k] / reasonTotal * 100) + "%";
        meter.appendChild(fill);
        li.appendChild(meter);
        li.appendChild(el("span", "ad-num", String(reasons[k])));
        ul.appendChild(li);
      });
      students.appendChild(el("p", "ad-compare-sub", "Why answers weren't helpful"));
      students.appendChild(ul);
    }
    box.appendChild(students);
    [["reviewer", "Lecturers"], ["admin", "Hub staff"]].forEach(function (p) {
      box.appendChild(staffCard(p[1] + " (last " + s.days + " days)", s.staff_by_role[p[0]]));
    });
  }

  function staffCard(title, r) {
    var card = el("div", "ad-compare-card");
    card.appendChild(el("p", "ad-compare-kicker", title));
    if (!r) {
      card.appendChild(el("p", "ad-compare-big", "–"));
      card.appendChild(el("p", "ad-hint", "No reviews yet. Ask a question below and rate the answer."));
      return card;
    }
    var avg = (r.accuracy + r.completeness + r.clarity + r.tone) / 4;
    card.appendChild(el("p", "ad-compare-big", avg.toFixed(1) + " / 5"));
    card.appendChild(el("p", "ad-hint", "average across " + r.count + " review" + (r.count === 1 ? "" : "s") + ", rated safe " + pct(r.safe_rate)));
    var ul = el("ul", "ad-reason-list");
    RUBRIC.forEach(function (x) {
      var li = el("li");
      li.appendChild(el("span", null, x[1]));
      var meter = el("span", "ad-mini-meter"); var fill = el("span");
      fill.style.width = (r[x[0]] / 5 * 100) + "%";
      meter.appendChild(fill);
      li.appendChild(meter);
      li.appendChild(el("span", "ad-num", r[x[0]].toFixed(1)));
      ul.appendChild(li);
    });
    card.appendChild(ul);
    return card;
  }

  function renderReviews(rows) {
    var box = $("#reviews-list");
    box.replaceChildren();
    if (!rows.length) { box.appendChild(el("p", "ad-text", "No reviews yet.")); return; }
    rows.forEach(function (r) {
      var item = el("article", "ad-review");
      var head = el("div", "ad-review-head");
      head.appendChild(el("strong", null, r.question));
      head.appendChild(el("span", "ad-gap-meta", r.reviewer + " (" + (A.roleNames[r.reviewer_role] || "Hub staff") + ") · " + A.relTime(r.ts)));
      item.appendChild(head);
      var scores = el("p", "ad-review-scores");
      RUBRIC.forEach(function (x) { scores.appendChild(el("span", "ad-cat", x[1] + " " + r[x[0]] + "/5")); });
      scores.appendChild(el("span", "ad-cat " + (r.safe ? "is-good" : "is-bad"), r.safe ? "✓ Safe" : "✕ Not safe"));
      item.appendChild(scores);
      if (r.comment) item.appendChild(el("p", "ad-text", "“" + r.comment + "”"));
      box.appendChild(item);
    });
  }

  // ---------------------------------------------------------- ethics tests
  async function loadEthics() {
    try {
      state.ethics = await A.api("/admin/ethics");
      renderEthics();
    } catch (err) { A.reportError(err); }
  }

  $("#e-run").addEventListener("click", async function () {
    try {
      await A.api("/admin/ethics/run", { method: "POST", headers: { "Content-Type": "application/json" },
                                         body: JSON.stringify({ judge: $("#e-judge").checked }) });
      A.toast("Ethics tests started. You can keep using the page.", "info");
      loadEthics();
    } catch (err) { A.reportError(err); }
  });

  function renderEthics() {
    var e = state.ethics, st = e.status;
    $("#e-run").disabled = st.running;
    $("#e-progress").hidden = !st.running;
    if (st.running) {
      $("#e-progress-bar").style.width = (st.total ? st.done / st.total * 100 : 0) + "%";
      $("#e-progress-text").textContent = "Running test " + st.done + " of " + st.total + "…";
      clearTimeout(state.poll);
      state.poll = setTimeout(function () { if (state.tab === "ethics") loadEthics(); }, 2000);
    }
    if (st.error && st.error !== state.lastError) A.toast("The ethics run stopped: " + st.error, "error");
    state.lastError = st.error;

    var r = e.latest;
    $("#e-empty").hidden = !!r;
    $("#e-results").hidden = !r;
    if (!r) return;
    renderReadiness(e.readiness);

    var review = r.cases.filter(function (x) { return x.status === "review"; }).length;
    var failed = r.cases.filter(function (x) { return x.status === "fail" || x.status === "error"; }).length;
    kpi($("#e-kpis"), [
      ["Pass rate", pct(r.pass_rate), r.passed + " of " + r.total],
      ["Failed", String(failed)],
      ["Needs a person to check", String(review)],
      ["Last run", A.relTime(r.run_at), r.duration_s + " s"],
      ["Model tested", r.chat_model, r.judge ? "with AI judge" : "rules only"]
    ]);

    var c = colours(), cats = Object.keys(r.summary);
    function series(key) { return cats.map(function (k) { return r.summary[k][key]; }); }
    draw("ch-ethics", {
      type: "bar",
      data: { labels: cats.map(function (k) { return CATEGORY_NAMES[k] || k; }), datasets: [
        bar(c.good, { label: "✓ Passed", data: series("pass"), borderRadius: 0, borderWidth: 2 }),
        bar(c.warning, { label: "! Needs review", data: series("review"), borderRadius: 0, borderWidth: 2 }),
        bar(c.critical, { label: "✕ Failed", data: cats.map(function (k) { return r.summary[k].fail + r.summary[k].error; }), borderRadius: 0, borderWidth: 2 })
      ] },
      options: baseOptions({ indexAxis: "y", interaction: { mode: "index", axis: "y" },
        plugins: { legend: { display: true, position: "top", align: "start" },
          tooltip: { callbacks: { afterTitle: function (items) { var k = cats[items[0].dataIndex]; return r.summary[k].description; } } } },
        scales: { x: { stacked: true, beginAtZero: true, grid: { display: true, color: c.line }, ticks: { precision: 0 } },
                  y: { stacked: true, grid: { display: false } } } })
    });

    var hist = e.history || [];
    $("#e-trend-panel").hidden = hist.length < 2;
    if (hist.length >= 2) {
      draw("ch-ethics-trend", {
        type: "line",
        data: { labels: hist.map(function (h) { return new Date(h.run_at).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }); }),
                datasets: [{ label: "Pass rate", data: hist.map(function (h) { return Math.round(h.pass_rate * 100); }),
                             borderColor: c.s1, backgroundColor: c.s1, borderWidth: 2, pointRadius: 4, tension: 0.2 }] },
        options: baseOptions({ scales: { y: { min: 0, max: 100, ticks: { callback: function (v) { return v + "%"; } } } },
          plugins: { tooltip: { callbacks: { label: function (i) {
            var h = hist[i.dataIndex];
            return " Pass rate: " + i.parsed.y + "% (" + h.chat_model + ")" +
              (h.ready == null ? "" : h.ready ? ", ready for release" : ", not ready");
          } } } } })
      });
    }
    renderCases();
  }

  var FILTERS = [["all", "All"], ["fail", "Failed"], ["review", "Needs review"], ["pass", "Passed"]];
  function renderCases() {
    var r = state.ethics.latest, f = $("#e-filters");
    f.replaceChildren();
    FILTERS.forEach(function (p) {
      var n = p[0] === "all" ? r.cases.length : r.cases.filter(function (x) { return x.status === p[0] || (p[0] === "fail" && x.status === "error"); }).length;
      var chip = el("button", "ad-chip");
      chip.type = "button";
      chip.setAttribute("aria-pressed", String(state.ethicsFilter === p[0]));
      chip.appendChild(document.createTextNode(p[1] + " "));
      chip.appendChild(el("span", null, String(n)));
      chip.addEventListener("click", function () { state.ethicsFilter = p[0]; renderCases(); });
      f.appendChild(chip);
    });
    var box = $("#e-cases");
    var open = {};                                         // keep open rows open after marking a test
    $$("#e-cases details[open]").forEach(function (d) { open[d.dataset.id] = true; });
    box.replaceChildren();
    var ICON = { pass: "✓", review: "!", fail: "✕", error: "✕" };
    var LABEL = { pass: "Passed", review: "Needs review", fail: "Failed", error: "Error" };
    r.cases.filter(function (x) {
      return state.ethicsFilter === "all" || x.status === state.ethicsFilter || (state.ethicsFilter === "fail" && x.status === "error");
    }).forEach(function (x) {
      var row = el("details", "ad-case is-" + x.status);
      row.dataset.id = x.id;
      row.open = !!open[x.id];
      var sum = el("summary");
      var badge = el("span", "ad-status is-" + x.status);
      badge.appendChild(el("span", null, ICON[x.status] || "?"));
      badge.appendChild(document.createTextNode(" " + (LABEL[x.status] || x.status)));
      sum.appendChild(badge);
      sum.appendChild(el("span", "ad-case-id", x.id));
      sum.appendChild(el("span", "ad-case-prompt", x.prompt));
      sum.appendChild(el("span", "ad-cat", (CATEGORY_NAMES[x.category] || x.category) +
        (x.expect === "same_answer" && x.group ? " · " + x.group : "") + " · " + x.language.toUpperCase()));
      row.appendChild(sum);
      var body = el("div", "ad-case-body");
      body.appendChild(el("p", null, x.detail));
      if (x.reply) body.appendChild(el("blockquote", null, x.reply));
      if (x.top_document) body.appendChild(el("p", "ad-hint", "Document found: " + x.top_document + " (score " + x.score + ")"));
      if (x.status === "review" || x.checked_by) body.appendChild(verdictButtons(x));
      row.appendChild(body);
      box.appendChild(row);
    });
  }

  // The release check: is the chatbot ready for students, based on the latest run?
  function renderReadiness(ready) {
    var box = $("#e-ready");
    box.replaceChildren();
    box.hidden = !ready;
    if (!ready) return;
    box.className = "ad-ready " + (ready.ready ? "is-ready" : "is-not-ready");
    var head = el("div", "ad-ready-head");
    var mark = el("span", "ad-ready-icon", ready.ready ? "✓" : "!");
    mark.setAttribute("aria-hidden", "true");
    head.appendChild(mark);
    var text = el("div");
    text.appendChild(el("h2", "ad-ready-title", ready.ready ? "Ready for release" : "Not ready for release yet"));
    text.appendChild(el("p", "ad-hint", "Release check for the latest run. Pass mark " + pct(ready.pass_mark) +
      " (the ETHICS_PASS_MARK setting: agree it with the Hub)."));
    head.appendChild(text);
    box.appendChild(head);
    var list = el("ul", "ad-checklist");
    ready.checks.forEach(function (c) {
      var li = el("li", c.ok ? "is-ok" : "is-bad");
      var tick = el("span", "ad-check-mark", c.ok ? "✓" : "✕");
      tick.setAttribute("aria-hidden", "true");
      li.appendChild(tick);
      li.appendChild(el("span", "sr-only", c.ok ? "Met: " : "Not met: "));
      li.appendChild(el("span", null, c.label));
      li.appendChild(el("span", "ad-num", c.detail));
      list.appendChild(li);
    });
    box.appendChild(list);
  }

  // A person reads a reply the rules or the judge could not decide, and marks it.
  function verdictButtons(x) {
    var box = el("div", "ad-verdict");
    box.appendChild(el("span", "ad-hint", x.checked_by ? "Marked by " + x.checked_by + ". Change it:" :
      x.expect === "same_answer" ? "Compare the replies in this group, then mark the whole group:" : "Read the reply, then mark this test:"));
    [["pass", "Mark as passed"], ["fail", "Mark as failed"]].forEach(function (p) {
      var b = el("button", "ad-btn ad-btn-secondary", p[1]);
      b.type = "button";
      b.addEventListener("click", function () { markCase(x, p[0], b); });
      box.appendChild(b);
    });
    return box;
  }

  async function markCase(x, status, btn) {
    btn.disabled = true;
    try {
      var res = await A.api("/admin/ethics/cases/" + encodeURIComponent(x.id) + "/verdict", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: status })
      });
      A.toast((x.expect === "same_answer" ? "Group " + x.group : x.id) + " marked as " + (status === "pass" ? "passed." : "failed."));
      state.ethics.latest = res.latest;
      state.ethics.readiness = res.readiness;
      loadEthics();
    } catch (err) {
      btn.disabled = false;
      A.reportError(err);
    }
  }

  // ---------------------------------------------------------- redraw charts when the theme changes
  new MutationObserver(function () {
    if (state.tab === "analytics" && state.analytics) renderAnalytics();
    if (state.tab === "ethics" && state.ethics && state.ethics.latest) renderEthics();
  }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  document.addEventListener("cb-admin-ready", function () { showTab(state.tab); });   // showTab checks the role
})();
