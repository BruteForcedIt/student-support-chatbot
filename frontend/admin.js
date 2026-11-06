/* =====================================================================
   Staff area: page behaviour
   Sign in (Hub staff or lecturer), list / search / filter documents, upload (drag and drop),
   replace, delete, activity log, re-index, staff accounts, change password, theme.
   Lecturers ("reviewer" accounts) only see the Peer review tab; the server enforces this too.
   ===================================================================== */
(function () {
  "use strict";

  var API = location.port === "8000" ? "" : "http://localhost:8000";
  var MAX_MB = 10;
  var ALLOWED = [".pdf", ".docx", ".txt", ".md"];
  var CATEGORIES = {
    general: "General enquiries",
    academic: "Academic support",
    modules: "Modules and courses",
    finance: "Finance and tuition fees",
    documents: "Official documents",
    campus: "Campus and visa support"
  };
  var ACTIONS = { upload: "added", replace: "replaced", "delete": "deleted", reindex: "rebuilt the index", login: "signed in",
                  review: "reviewed an answer", ethics: "ran the ethics tests", ethics_check: "checked an ethics test",
                  add_user: "added a staff account", remove_user: "removed a staff account", password: "changed their password" };
  var ROLE_NAMES = { admin: "Hub staff", reviewer: "Lecturer" };

  var $ = function (s) { return document.querySelector(s); };
  var $$ = function (s) { return Array.prototype.slice.call(document.querySelectorAll(s)); };
  var state = { docs: [], filter: "all", query: "", replacing: null };

  function store(k, v) { try { sessionStorage.setItem(k, v); } catch (e) { /* blocked */ } }
  function recall(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } }
  function forget(k) { try { sessionStorage.removeItem(k); } catch (e) { /* blocked */ } }
  var token = recall("cb_admin_token");
  var username = recall("cb_admin_user");
  var role = "admin";            // confirmed by the server (/admin/me) before the page is shown

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  // ---------------------------------------------------------- server calls
  async function api(path, options) {
    options = options || {};
    var headers = Object.assign({}, options.headers || {});
    if (token) headers.Authorization = "Bearer " + token;
    var res;
    try {
      res = await fetch(API + path, Object.assign({}, options, { headers: headers }));
    } catch (e) {
      throw new Error("Can't reach the server. Check that it's running on port 8000.");
    }
    var data = null;
    try { data = await res.json(); } catch (e) { /* no body */ }
    if (res.status === 401 && token) {
      showLogin("Your session has expired. Please sign in again.");
      throw new Error("signed-out");
    }
    var detail = data && data.detail;
    if (Array.isArray(detail)) detail = detail.map(function (d) { return d.msg; }).join(" ");
    if (!res.ok) throw new Error(detail || "Something went wrong (" + res.status + ").");
    return data;
  }

  // ---------------------------------------------------------- feedback to the admin
  function toast(message, kind) {
    var t = el("div", "ad-toast" + (kind ? " is-" + kind : ""), message);
    t.setAttribute("role", kind === "error" ? "alert" : "status");
    $("#toasts").appendChild(t);
    setTimeout(function () { t.remove(); }, kind === "error" ? 7000 : 4500);
  }
  function reportError(err) { if (err.message !== "signed-out") toast(err.message, "error"); }
  window.CBAdmin = { api: function (p, o) { return api(p, o); }, toast: toast, reportError: reportError,
                     el: el, relTime: relTime, categories: CATEGORIES, roleNames: ROLE_NAMES,
                     loadAccounts: loadAccounts, role: role };

  function confirmAction(title, text, okLabel) {
    var d = $("#confirm-dialog");
    $("#confirm-title").textContent = title;
    $("#confirm-text").textContent = text;
    $("#confirm-ok").textContent = okLabel || "Confirm";
    return new Promise(function (resolve) {
      d.addEventListener("close", function onClose() {
        d.removeEventListener("close", onClose);
        resolve(d.returnValue === "ok");
      });
      d.returnValue = "";
      d.showModal();
    });
  }

  // ---------------------------------------------------------- time helpers
  function relTime(iso) {
    var then = new Date(iso), secs = Math.round((Date.now() - then) / 1000);
    if (isNaN(then)) return "";
    if (secs < 60) return "just now";
    var mins = Math.round(secs / 60); if (mins < 60) return mins + " min ago";
    var hrs = Math.round(mins / 60); if (hrs < 24) return hrs + (hrs === 1 ? " hour ago" : " hours ago");
    var days = Math.round(hrs / 24); if (days < 7) return days + (days === 1 ? " day ago" : " days ago");
    return then.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  }
  function shortTime(iso) {
    var d = new Date(iso);
    var sameDay = d.toDateString() === new Date().toDateString();
    return sameDay ? d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
                   : d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
  }

  // ---------------------------------------------------------- theme
  function setTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    $$("[data-theme-choice]").forEach(function (b) { b.setAttribute("aria-checked", String(b.dataset.themeChoice === theme)); });
    try { localStorage.setItem("cb-theme", theme); } catch (e) { /* blocked */ }
  }

  // ---------------------------------------------------------- sign in / out
  function showLogin(message) {
    token = null; forget("cb_admin_token"); forget("cb_admin_user");
    delete document.documentElement.dataset.role;
    $("#app").hidden = true;
    $("#login").hidden = false;
    $("#login-error").textContent = message || "";
    $("#login-user").focus();
  }

  function showApp() {
    $("#login").hidden = true;
    $("#app").hidden = false;
    document.documentElement.dataset.role = role;      // CSS hides [data-admin-only] from lecturers
    window.CBAdmin.role = role;
    $("#who").textContent = username;
    $("#user-initial").textContent = (username || "?").charAt(0);
    $("#who-role").textContent = ROLE_NAMES[role] || role;
    $("#brand-title").textContent = role === "admin" ? "Knowledge base admin" : "Lecturer peer review";
    if (role === "admin") refresh();
    document.dispatchEvent(new CustomEvent("cb-admin-ready", { detail: { role: role } }));
  }

  $("#login-form").addEventListener("submit", async function (e) {
    e.preventDefault();
    var btn = $("#login-btn");
    btn.disabled = true; btn.textContent = "Signing in…";
    $("#login-error").textContent = "";
    try {
      var data = await api("/admin/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: $("#login-user").value, password: $("#login-pass").value })
      });
      token = data.token; username = data.username; role = data.role || "admin";
      store("cb_admin_token", token); store("cb_admin_user", username);
      $("#login-pass").value = "";
      showApp();
    } catch (err) {
      $("#login-error").textContent = err.message;
    } finally {
      btn.disabled = false; btn.textContent = "Sign in";
    }
  });

  $("#signout").addEventListener("click", async function () {
    try { await api("/admin/logout", { method: "POST" }); } catch (e) { /* already signed out */ }
    showLogin("You have signed out.");
  });

  // ---------------------------------------------------------- loading data
  async function refresh() {
    try {
      var results = await Promise.all([api("/admin/documents"), api("/admin/stats")]);
      state.docs = results[0];
      renderStats(results[1]);
      renderFilters();
      renderDocs();
      loadActivity();
    } catch (err) { reportError(err); }
  }

  function renderStats(s) {
    $("#stat-docs").textContent = s.documents;
    $("#stat-chunks").textContent = s.chunks;
    var up = s.feedback_up || 0, down = s.feedback_down || 0, total = up + down;
    var fb = $("#stat-feedback");
    fb.replaceChildren();
    if (total) {
      fb.appendChild(document.createTextNode(Math.round(up / total * 100) + "% "));
      fb.appendChild(el("small", null, "helpful (" + up + " of " + total + ")"));
    } else {
      fb.appendChild(el("small", null, "No ratings yet"));
    }
    $("#stat-meter").style.width = total ? (up / total * 100) + "%" : "0";
    $("#stat-models").textContent = "Search model: " + s.embedding_model + ". Chat model: " + s.chat_model + ".";
    $("#reindex-warning").hidden = !s.needs_reindex;
  }

  // ---------------------------------------------------------- document list
  function renderFilters() {
    var box = $("#cat-filters");
    box.replaceChildren();
    var counts = { all: state.docs.length };
    state.docs.forEach(function (d) { counts[d.category] = (counts[d.category] || 0) + 1; });
    [["all", "All"]].concat(Object.keys(CATEGORIES).map(function (k) { return [k, CATEGORIES[k]]; }))
      .forEach(function (pair) {
        if (pair[0] !== "all" && !counts[pair[0]]) return;   // hide empty categories
        var chip = el("button", "ad-chip", pair[1] + " ");
        chip.type = "button";
        chip.appendChild(el("span", null, String(counts[pair[0]] || 0)));
        chip.setAttribute("aria-pressed", String(state.filter === pair[0]));
        chip.addEventListener("click", function () { state.filter = pair[0]; renderFilters(); renderDocs(); });
        box.appendChild(chip);
      });
  }

  function renderDocs() {
    var listBox = $("#doc-list");
    listBox.replaceChildren();
    var q = state.query.toLowerCase();
    var shown = state.docs.filter(function (d) {
      return (state.filter === "all" || d.category === state.filter) &&
             (!q || d.title.toLowerCase().indexOf(q) > -1 || d.filename.toLowerCase().indexOf(q) > -1);
    });

    $("#empty").hidden = shown.length > 0;
    if (!state.docs.length) {
      $("#empty-title").textContent = "No documents yet";
      $("#empty-text").textContent = "Add your first document. Students can ask about it straight away.";
    } else if (!shown.length) {
      $("#empty-title").textContent = "No matching documents";
      $("#empty-text").textContent = "Try a different search or category.";
    }

    shown.forEach(function (doc) {
      var row = el("article", "ad-doc");
      row.dataset.id = doc.id;

      var title = el("div", "ad-doc-title");
      if (doc.source_url) {
        var a = el("a", null, doc.title);
        a.href = doc.source_url; a.target = "_blank"; a.rel = "noopener noreferrer";
        a.title = "Open the official page";
        title.appendChild(a);
        var ext = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        ext.setAttribute("viewBox", "0 0 24 24"); ext.setAttribute("class", "ad-icon"); ext.setAttribute("aria-hidden", "true");
        ext.innerHTML = '<path d="M14 4.5h5.5V10M19.5 4.5 11 13M17 14v4.5a1 1 0 0 1-1 1H5.5a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1H10"/>';
        a.appendChild(ext);
      } else {
        title.textContent = doc.title;
      }

      var meta = el("div", "ad-doc-meta");
      meta.appendChild(el("span", "ad-cat", CATEGORIES[doc.category] || doc.category));
      meta.appendChild(el("span", null, "Version " + doc.version));
      meta.appendChild(el("span", null, doc.chunk_count + (doc.chunk_count === 1 ? " passage" : " passages")));
      var when = el("span", null, "Updated " + relTime(doc.updated_at) + " by " + doc.uploaded_by);
      when.title = new Date(doc.updated_at).toLocaleString();
      meta.appendChild(when);
      meta.appendChild(el("span", null, doc.filename));

      var actions = el("div", "ad-doc-actions");
      var rep = el("button", "ad-link-btn", "Replace");
      rep.type = "button";
      rep.setAttribute("aria-label", "Replace file for " + doc.title);
      rep.addEventListener("click", function () { state.replacing = doc; $("#replace-input").value = ""; $("#replace-input").click(); });
      var del = el("button", "ad-link-btn is-danger", "Delete");
      del.type = "button";
      del.setAttribute("aria-label", "Delete " + doc.title);
      del.addEventListener("click", function () { deleteDoc(doc, row); });
      actions.appendChild(rep); actions.appendChild(del);

      row.appendChild(title); row.appendChild(actions); row.appendChild(meta);
      listBox.appendChild(row);
    });
  }

  $("#doc-search").addEventListener("input", function (e) { state.query = e.target.value.trim(); renderDocs(); });

  // ---------------------------------------------------------- activity
  async function loadActivity() {
    try {
      var rows = await api("/admin/audit");
      var list = $("#activity-list");
      list.replaceChildren();
      if (!rows.length) { list.appendChild(el("li", null, "Nothing yet.")); return; }
      rows.slice(0, 30).forEach(function (r) {
        var li = el("li");
        var t = el("time", null, shortTime(r.ts));
        t.dateTime = r.ts; t.title = new Date(r.ts).toLocaleString();
        var text = el("div");
        text.appendChild(el("strong", null, r.username));
        text.appendChild(document.createTextNode(" " + (ACTIONS[r.action] || r.action)));
        if (r.detail) { text.appendChild(document.createElement("br")); text.appendChild(el("span", "ad-act-detail", r.detail)); }
        li.appendChild(t); li.appendChild(text);
        list.appendChild(li);
      });
    } catch (err) { reportError(err); }
  }

  // ---------------------------------------------------------- upload
  var fileInput = $("#f-file");
  var drop = $("#drop-zone");

  function checkFile(file) {
    if (!file) return "Choose a file first.";
    var ext = (file.name.match(/\.[^.]+$/) || [""])[0].toLowerCase();
    if (ALLOWED.indexOf(ext) < 0) return "That file type isn't supported. Use PDF, Word, text or Markdown.";
    if (file.size > MAX_MB * 1024 * 1024) return "That file is larger than " + MAX_MB + " MB.";
    if (!file.size) return "That file is empty.";
    return "";
  }

  function showChosen() {
    var file = fileInput.files[0];
    var problem = file ? checkFile(file) : "";
    drop.classList.toggle("has-file", !!file && !problem);
    $("#drop-label").textContent = file ? file.name : "";
    if (!file) $("#drop-label").innerHTML = "Drop a file here or <u>browse</u>";
    $("#drop-sub").textContent = problem || (file ? (file.size / 1024).toFixed(0) + " KB. Click to choose a different file" :
      "PDF, Word, text or Markdown, up to " + MAX_MB + " MB");
    $("#upload-btn").disabled = !file || !!problem;
  }
  // A Markdown file with a "---" header (title, source_url, category) fills in the form for you.
  function prefillFromMarkdown(file) {
    if (!file || !/\.md$/i.test(file.name)) return;
    file.text().then(function (text) {
      var m = text.match(/^---\s*\n([\s\S]*?)\n---/);
      if (!m) return;
      var meta = {};
      m[1].split("\n").forEach(function (line) {
        var i = line.indexOf(":");
        if (i > 0) meta[line.slice(0, i).trim().toLowerCase()] = line.slice(i + 1).trim().replace(/^["']|["']$/g, "");
      });
      if (meta.title && !$("#f-title").value) $("#f-title").value = meta.title;
      if (meta.source_url && !$("#f-url").value) $("#f-url").value = meta.source_url;
      if (CATEGORIES[meta.category]) $("#f-category").value = meta.category;
      if (meta.title || meta.category) toast("Filled in the details from the file's header. Check them before uploading.", "info");
    });
  }

  fileInput.addEventListener("change", function () { showChosen(); prefillFromMarkdown(fileInput.files[0]); });

  ["dragenter", "dragover"].forEach(function (ev) {
    drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add("is-over"); });
  });
  ["dragleave", "drop"].forEach(function (ev) {
    drop.addEventListener(ev, function () { drop.classList.remove("is-over"); });
  });
  drop.addEventListener("drop", function (e) {
    e.preventDefault();
    if (e.dataTransfer.files.length) {
      fileInput.files = e.dataTransfer.files;
      showChosen();
      prefillFromMarkdown(fileInput.files[0]);
    }
  });

  $("#upload-form").addEventListener("submit", async function (e) {
    e.preventDefault();
    var problem = checkFile(fileInput.files[0]);
    if (problem) { toast(problem, "error"); return; }
    var btn = $("#upload-btn");
    btn.disabled = true; btn.textContent = "Uploading and indexing…";
    try {
      var doc = await api("/admin/documents", { method: "POST", body: new FormData(e.target) });
      toast("Added \u201c" + doc.title + "\u201d (" + doc.chunk_count + (doc.chunk_count === 1 ? " passage" : " passages") +
        "). Students can ask about it now.");
      e.target.reset();
      showChosen();
      refresh();
    } catch (err) {
      reportError(err);
      btn.disabled = false;
    } finally {
      btn.textContent = "Upload document";
    }
  });

  // ---------------------------------------------------------- replace and delete
  function rowFor(doc) { return document.querySelector('.ad-doc[data-id="' + doc.id + '"]'); }

  $("#replace-input").addEventListener("change", async function () {
    var file = this.files[0], doc = state.replacing;
    if (!file || !doc) return;
    var problem = checkFile(file);
    if (problem) { toast(problem, "error"); return; }
    var row = rowFor(doc);
    if (row) row.classList.add("is-busy");
    toast("Replacing “" + doc.title + "”…", "info");
    var body = new FormData();
    body.append("file", file);
    try {
      var updated = await api("/admin/documents/" + doc.id, { method: "PUT", body: body });
      toast("“" + updated.title + "” is now version " + updated.version + ". The old version is no longer used.");
      refresh();
    } catch (err) {
      if (row) row.classList.remove("is-busy");
      reportError(err);
    }
  });

  async function deleteDoc(doc, row) {
    var ok = await confirmAction("Delete this document?",
      "“" + doc.title + "” will be removed and students will no longer get answers from it. The file is kept in the archive.",
      "Delete");
    if (!ok) return;
    row.classList.add("is-busy");
    try {
      await api("/admin/documents/" + doc.id, { method: "DELETE" });
      toast("Deleted “" + doc.title + "”.");
      refresh();
    } catch (err) {
      row.classList.remove("is-busy");
      reportError(err);
    }
  }

  // ---------------------------------------------------------- maintenance
  $("#reindex-btn").addEventListener("click", async function () {
    var ok = await confirmAction("Rebuild the search index?",
      "Every stored document is read and indexed again. This can take a few minutes; the chatbot may be slow meanwhile.",
      "Rebuild");
    if (!ok) return;
    var btn = this;
    btn.disabled = true; btn.textContent = "Rebuilding…";
    try {
      var r = await api("/admin/reindex", { method: "POST" });
      toast("Rebuilt " + r.reindexed + " documents" + (r.failed.length ? ", " + r.failed.length + " failed." : "."),
        r.failed.length ? "error" : null);
      refresh();
    } catch (err) {
      reportError(err);
    } finally {
      btn.disabled = false; btn.textContent = "Rebuild search index";
    }
  });

  // ---------------------------------------------------------- staff accounts (Hub staff only)
  async function loadAccounts() {
    try {
      var data = await api("/admin/users");
      renderAccounts(data.users);
    } catch (err) { reportError(err); }
  }

  function renderAccounts(users) {
    var table = el("table", "ad-table ad-accounts");
    var head = el("tr");
    ["Username", "Role", "Added", ""].forEach(function (h) { head.appendChild(el("th", null, h)); });
    table.appendChild(head);
    users.forEach(function (u) {
      var tr = el("tr");
      tr.appendChild(el("td", null, u.username));
      tr.appendChild(el("td", null, ROLE_NAMES[u.role] || u.role));
      var added = el("td", null, relTime(u.created_at));
      added.title = new Date(u.created_at).toLocaleString();
      tr.appendChild(added);
      var cell = el("td");
      if (u.username.toLowerCase() === String(username).toLowerCase()) {
        cell.appendChild(el("span", "ad-hint", "You"));
      } else {
        var remove = el("button", "ad-link-btn is-danger", "Remove");
        remove.type = "button";
        remove.setAttribute("aria-label", "Remove " + u.username);
        remove.addEventListener("click", function () { removeAccount(u); });
        cell.appendChild(remove);
      }
      tr.appendChild(cell);
      table.appendChild(tr);
    });
    $("#accounts-list").replaceChildren(table);
  }

  async function removeAccount(u) {
    var ok = await confirmAction("Remove this account?",
      "\u201c" + u.username + "\u201d (" + (ROLE_NAMES[u.role] || u.role) + ") will be signed out and can no longer sign in. " +
      "Their past reviews are kept.", "Remove");
    if (!ok) return;
    try {
      await api("/admin/users/" + encodeURIComponent(u.username), { method: "DELETE" });
      toast("Removed \u201c" + u.username + "\u201d.");
      loadAccounts();
    } catch (err) { reportError(err); }
  }

  $("#account-form").addEventListener("submit", async function (e) {
    e.preventDefault();
    var name = $("#acc-user").value.trim(), pass = $("#acc-pass").value;
    if (name.length < 3) { toast("The username needs at least 3 characters.", "error"); return; }
    if (pass.length < 10) { toast("The password needs at least 10 characters.", "error"); return; }
    var btn = $("#acc-add-btn");
    btn.disabled = true;
    try {
      var u = await api("/admin/users", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: name, password: pass, role: $("#acc-role").value })
      });
      toast("Added " + (ROLE_NAMES[u.role] || u.role) + " account \u201c" + u.username + "\u201d. Share the password with them privately.");
      e.target.reset();
      loadAccounts();
    } catch (err) { reportError(err); }
    finally { btn.disabled = false; }
  });

  // ---------------------------------------------------------- change your own password
  var pwDialog = $("#password-dialog");
  $("#change-password").addEventListener("click", function () {
    $("#password-form").reset();
    $("#pw-error").textContent = "";
    pwDialog.showModal();
  });
  $("#pw-cancel").addEventListener("click", function () { pwDialog.close(); });
  $("#password-form").addEventListener("submit", async function (e) {
    e.preventDefault();
    var next = $("#pw-new").value;
    if (next.length < 10) { $("#pw-error").textContent = "The new password needs at least 10 characters."; return; }
    if (next !== $("#pw-repeat").value) { $("#pw-error").textContent = "The two new passwords are different."; return; }
    var btn = $("#pw-save");
    btn.disabled = true;
    try {
      await api("/admin/me/password", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_password: $("#pw-current").value, new_password: next })
      });
      pwDialog.close();
      toast("Password changed. You have been signed out on your other devices.");
    } catch (err) {
      if (err.message !== "signed-out") $("#pw-error").textContent = err.message;
    } finally { btn.disabled = false; }
  });

  // ---------------------------------------------------------- start
  var catSelect = $("#f-category");
  Object.keys(CATEGORIES).forEach(function (k) {
    var o = el("option", null, CATEGORIES[k]); o.value = k; catSelect.appendChild(o);
  });
  setTheme(document.documentElement.getAttribute("data-theme") || "light");
  $$("[data-theme-choice]").forEach(function (b) { b.addEventListener("click", function () { setTheme(b.dataset.themeChoice); }); });
  // Signed in earlier in this tab: ask the server who this is (and whether the session is still valid).
  if (token) {
    api("/admin/me").then(function (me) { username = me.username; role = me.role; showApp(); })
      .catch(function (err) { if (err.message !== "signed-out") showLogin(err.message); });
  } else {
    showLogin("");
  }
})();
