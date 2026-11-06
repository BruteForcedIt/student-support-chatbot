/* =====================================================================
   AI Student Support Buddy: page behaviour
   Replaces the old inline <script> and backend-api.js.
   Sections: settings, translations, helpers, theme, language,
   categories, chat, feedback, help dialog, start-up.
   ===================================================================== */
(function () {
  "use strict";

  // ---------------------------------------------------------- settings
  // When the page is served by the chatbot server itself (port 8000) use relative URLs,
  // otherwise (Live Server, file://) talk to the server on localhost:8000.
  var API_BASE = location.port === "8000" ? "" : "http://localhost:8000";
  var MAX_CHARS = 1000;
  var HISTORY_TURNS = 6;
  var HISTORY_CHARS = 2000;     // the server refuses longer turns, so long answers are shortened in the history
  var PARAMS = new URLSearchParams(location.search);
  var EMBED = PARAMS.get("embed") === "1";          // opened inside the side panel (widget.js)
  var CHANNEL = EMBED ? "widget" : "page";
  var TRANSCRIPT_KEY = "cb-transcript-" + CHANNEL;  // sessionStorage: cleared when the tab is closed

  // ---------------------------------------------------------- translations
  // Malay and Chinese text should be checked by a native speaker before launch.
  var T = {
    en: {
      "page.title": "AI Student Support Buddy | NottinghamHub",
      "a11y.skip": "Skip to the message box",
      "header.title": "AI Student Support Buddy",
      "header.help": "Help",
      "theme.group": "Colour theme",
      "theme.light": "Light",
      "theme.dark": "Dark",
      "subheader.backToHub": "Student Home",
      "subheader.badge": "AI Student Support Buddy",
      "subheader.newChat": "New conversation",
      "sidebar.categoriesTitle": "Support categories",
      "sidebar.hint": "Pick a topic to focus the answers. You can ask about anything either way.",
      "category.general": "General enquiries",
      "category.academic": "Academic support",
      "category.modules": "Modules and courses",
      "category.finance": "Finance and tuition fees",
      "category.documents": "Official documents",
      "category.campus": "Campus and visa support",
      "sidebar.languageLabel": "Language",
      "sidebar.languageNote": "Menus and answers switch to this language.",
      "urgent.title": "Need to talk to someone now?",
      "urgent.hotline": "24/7 wellbeing hotline",
      "urgent.security": "Campus security (24/7)",
      "urgent.danger": "Immediate danger",
      "chat.bannerTitle": "How can we help you today?",
      "chat.bannerDesc": "Ask about exams, fees, visas, accommodation, wellbeing and more. Answers come from official University of Nottingham Malaysia pages, with links so you can check them.",
      "chat.chooseLanguage": "Choose your language",
      "chat.suggestedLabel": "Try asking",
      "chat.inputLabel": "Type your question",
      "chat.inputPlaceholder": "Type your question here",
      "chat.sendBtn": "Send",
      "chat.disclaimer": "Automated guidance. Check important details with the office concerned, and never type passwords or bank details here.",
      "chat.typing": "The Support Buddy is writing a reply",
      "chat.sources": "Sources",
      "chat.page": "p.",
      "chat.copy": "Copy",
      "chat.copied": "Copied",
      "chat.helpful": "Helpful",
      "chat.notHelpful": "Not helpful",
      "chat.thanks": "Thanks for the feedback",
      "chat.retry": "Try again",
      "chat.error": "I can't reach the assistant right now. Check your connection and try again.",
      "chat.unavailable": "The Support Buddy is not available right now. Please try again in a few minutes, or contact the Student Services Centre.",
      "chat.tooFast": "You're sending messages very quickly. Please wait a minute and try again.",
      "chat.charsLeft": "{n} characters left",
      "chat.you": "You",
      "chat.bot": "Support Buddy",
      "embed.expand": "Open in full page",
      "embed.close": "Close panel",
      "chat.mic": "Speak your question",
      "chat.listening": "Listening… speak now",
      "chat.searching": "Searching official documents",
      "chat.writing": "Writing an answer from {n} source(s)",
      "chat.whyNot": "What went wrong?",
      "reason.wrong": "Wrong or misleading",
      "reason.incomplete": "Didn't answer my question",
      "reason.unclear": "Hard to understand",
      "reason.outdated": "Out of date",
      "chat.reasonThanks": "Thanks, this helps staff improve the answers",
      "help.title": "How the Support Buddy works",
      "help.close": "Close",
      "help.whatTitle": "What it can help with",
      "help.what": "Questions about university services: exams and extenuating circumstances, fees and payments, visas, accommodation, official documents, wellbeing and how to make a complaint.",
      "help.howTitle": "Where answers come from",
      "help.how": "Answers are written by an AI using only documents uploaded by university staff. Each answer lists its sources. If the documents do not cover your question, the Buddy says so instead of guessing.",
      "help.tipsTitle": "Getting a better answer",
      "help.tip1": "Ask one thing at a time, in your own words.",
      "help.tip2": "Choose a category on the left to focus the search.",
      "help.tip3": "Use the thumbs up or down under an answer to tell us if it helped.",
      "help.privacyTitle": "Your privacy",
      "help.privacy": "Conversations are not saved on our servers (this browser tab keeps your chat until you close it). Do not type passwords, card numbers or other private details. The Buddy cannot see your student record.",
      "help.urgentTitle": "In an emergency"
    },
    ms: {
      "page.title": "Rakan Sokongan Pelajar AI | NottinghamHub",
      "a11y.skip": "Langkau ke kotak mesej",
      "header.title": "Rakan Sokongan Pelajar AI",
      "header.help": "Bantuan",
      "theme.group": "Tema warna",
      "theme.light": "Cerah",
      "theme.dark": "Gelap",
      "subheader.backToHub": "Laman Utama Pelajar",
      "subheader.badge": "Rakan Sokongan Pelajar AI",
      "subheader.newChat": "Perbualan baharu",
      "sidebar.categoriesTitle": "Kategori sokongan",
      "sidebar.hint": "Pilih topik untuk memfokuskan jawapan. Anda masih boleh bertanya tentang apa sahaja.",
      "category.general": "Pertanyaan am",
      "category.academic": "Sokongan akademik",
      "category.modules": "Modul dan kursus",
      "category.finance": "Kewangan dan yuran pengajian",
      "category.documents": "Dokumen rasmi",
      "category.campus": "Sokongan kampus dan visa",
      "sidebar.languageLabel": "Bahasa",
      "sidebar.languageNote": "Menu dan jawapan akan bertukar kepada bahasa ini.",
      "urgent.title": "Perlu bercakap dengan seseorang sekarang?",
      "urgent.hotline": "Talian wellbeing 24 jam",
      "urgent.security": "Keselamatan kampus (24 jam)",
      "urgent.danger": "Bahaya segera",
      "chat.bannerTitle": "Bagaimana kami boleh membantu anda hari ini?",
      "chat.bannerDesc": "Tanya tentang peperiksaan, yuran, visa, penginapan, kesejahteraan dan banyak lagi. Jawapan diambil daripada laman rasmi University of Nottingham Malaysia, bersama pautan untuk anda semak.",
      "chat.chooseLanguage": "Pilih bahasa anda",
      "chat.suggestedLabel": "Cuba tanya",
      "chat.inputLabel": "Taip soalan anda",
      "chat.inputPlaceholder": "Taip soalan anda di sini",
      "chat.sendBtn": "Hantar",
      "chat.disclaimer": "Panduan automatik. Sahkan butiran penting dengan pejabat berkenaan, dan jangan taip kata laluan atau butiran bank di sini.",
      "chat.typing": "Rakan Sokongan sedang menulis jawapan",
      "chat.sources": "Sumber",
      "chat.page": "hlm.",
      "chat.copy": "Salin",
      "chat.copied": "Disalin",
      "chat.helpful": "Membantu",
      "chat.notHelpful": "Tidak membantu",
      "chat.thanks": "Terima kasih atas maklum balas anda",
      "chat.retry": "Cuba lagi",
      "chat.error": "Saya tidak dapat menghubungi pembantu sekarang. Semak sambungan anda dan cuba lagi.",
      "chat.unavailable": "Rakan Sokongan tidak tersedia buat masa ini. Sila cuba lagi dalam beberapa minit, atau hubungi Pusat Perkhidmatan Pelajar.",
      "chat.tooFast": "Anda menghantar mesej terlalu cepat. Sila tunggu seminit dan cuba lagi.",
      "chat.charsLeft": "{n} aksara lagi",
      "chat.you": "Anda",
      "chat.bot": "Rakan Sokongan",
      "embed.expand": "Buka dalam halaman penuh",
      "embed.close": "Tutup panel",
      "chat.mic": "Sebut soalan anda",
      "chat.listening": "Sedang mendengar… sila bercakap",
      "chat.searching": "Mencari dalam dokumen rasmi",
      "chat.writing": "Menulis jawapan daripada {n} sumber",
      "chat.whyNot": "Apa yang tidak kena?",
      "reason.wrong": "Salah atau mengelirukan",
      "reason.incomplete": "Tidak menjawab soalan saya",
      "reason.unclear": "Sukar difahami",
      "reason.outdated": "Sudah lapuk",
      "chat.reasonThanks": "Terima kasih, ini membantu kakitangan menambah baik jawapan",
      "help.title": "Cara Rakan Sokongan berfungsi",
      "help.close": "Tutup",
      "help.whatTitle": "Perkara yang boleh dibantu",
      "help.what": "Soalan tentang perkhidmatan universiti: peperiksaan dan keadaan luar jangka, yuran dan bayaran, visa, penginapan, dokumen rasmi, kesejahteraan dan cara membuat aduan.",
      "help.howTitle": "Dari mana jawapan datang",
      "help.how": "Jawapan ditulis oleh AI menggunakan dokumen yang dimuat naik oleh kakitangan universiti sahaja. Setiap jawapan menyenaraikan sumbernya. Jika dokumen tidak meliputi soalan anda, Rakan Sokongan akan memberitahu anda dan tidak meneka.",
      "help.tipsTitle": "Mendapatkan jawapan yang lebih baik",
      "help.tip1": "Tanya satu perkara pada satu masa, dalam perkataan anda sendiri.",
      "help.tip2": "Pilih kategori di sebelah kiri untuk memfokuskan carian.",
      "help.tip3": "Tekan ibu jari ke atas atau ke bawah di bawah jawapan untuk memberitahu kami sama ada ia membantu.",
      "help.privacyTitle": "Privasi anda",
      "help.privacy": "Perbualan tidak disimpan di pelayan kami (tab pelayar ini menyimpan perbualan sehingga anda menutupnya). Jangan taip kata laluan, nombor kad atau butiran peribadi lain. Rakan Sokongan tidak dapat melihat rekod pelajar anda.",
      "help.urgentTitle": "Dalam kecemasan"
    },
    zh: {
      "page.title": "AI 学生支持助手 | NottinghamHub",
      "a11y.skip": "跳到消息输入框",
      "header.title": "AI 学生支持助手",
      "header.help": "帮助",
      "theme.group": "颜色主题",
      "theme.light": "浅色",
      "theme.dark": "深色",
      "subheader.backToHub": "学生主页",
      "subheader.badge": "AI 学生支持助手",
      "subheader.newChat": "新对话",
      "sidebar.categoriesTitle": "支持类别",
      "sidebar.hint": "选择一个主题可以让回答更有针对性。不选也可以随时提问。",
      "category.general": "一般咨询",
      "category.academic": "学术支持",
      "category.modules": "模块与课程",
      "category.finance": "财务与学费",
      "category.documents": "官方文件",
      "category.campus": "校园与签证支持",
      "sidebar.languageLabel": "语言",
      "sidebar.languageNote": "菜单和回答都会切换为此语言。",
      "urgent.title": "现在就需要找人倾诉？",
      "urgent.hotline": "24 小时心理支持热线",
      "urgent.security": "校园保安（24 小时）",
      "urgent.danger": "紧急危险",
      "chat.bannerTitle": "今天我们可以如何帮助你？",
      "chat.bannerDesc": "你可以询问考试、学费、签证、住宿、身心健康等问题。回答来自诺丁汉大学马来西亚分校的官方网页，并附有链接方便你核对。",
      "chat.chooseLanguage": "选择你的语言",
      "chat.suggestedLabel": "试试问",
      "chat.inputLabel": "输入你的问题",
      "chat.inputPlaceholder": "在这里输入你的问题",
      "chat.sendBtn": "发送",
      "chat.disclaimer": "此为自动化指导。重要事项请向相关部门确认，切勿在此输入密码或银行资料。",
      "chat.typing": "支持助手正在撰写回复",
      "chat.sources": "来源",
      "chat.page": "第",
      "chat.copy": "复制",
      "chat.copied": "已复制",
      "chat.helpful": "有帮助",
      "chat.notHelpful": "没有帮助",
      "chat.thanks": "感谢你的反馈",
      "chat.retry": "重试",
      "chat.error": "目前无法连接到助手。请检查网络后重试。",
      "chat.unavailable": "支持助手暂时无法使用。请几分钟后再试，或联系学生服务中心。",
      "chat.tooFast": "你发送消息太快了。请等一分钟后再试。",
      "chat.charsLeft": "还可输入 {n} 个字符",
      "chat.you": "你",
      "chat.bot": "支持助手",
      "embed.expand": "在完整页面中打开",
      "embed.close": "关闭面板",
      "chat.mic": "语音提问",
      "chat.listening": "正在聆听…请说话",
      "chat.searching": "正在搜索官方文件",
      "chat.writing": "正在根据 {n} 个来源撰写回答",
      "chat.whyNot": "哪里有问题？",
      "reason.wrong": "错误或有误导性",
      "reason.incomplete": "没有回答我的问题",
      "reason.unclear": "难以理解",
      "reason.outdated": "信息过时",
      "chat.reasonThanks": "谢谢，这能帮助工作人员改进回答",
      "help.title": "支持助手如何运作",
      "help.close": "关闭",
      "help.whatTitle": "可以帮助的内容",
      "help.what": "关于大学服务的问题：考试与特殊情况申请、学费与付款、签证、住宿、官方文件、身心健康，以及如何提出投诉。",
      "help.howTitle": "回答从哪里来",
      "help.how": "回答由 AI 撰写，只使用大学工作人员上传的文件。每个回答都会列出来源。如果文件中没有相关内容，助手会直接告诉你，而不会猜测。",
      "help.tipsTitle": "如何获得更好的回答",
      "help.tip1": "一次只问一件事，用你自己的话来问。",
      "help.tip2": "在左侧选择类别，让搜索更集中。",
      "help.tip3": "在回答下方点击赞或踩，告诉我们是否有帮助。",
      "help.privacyTitle": "你的隐私",
      "help.privacy": "对话不会保存在我们的服务器上（此浏览器标签页会保留聊天记录，直到你关闭它）。请勿输入密码、卡号或其他私人信息。助手无法查看你的学生记录。",
      "help.urgentTitle": "紧急情况"
    }
  };

  // Suggested questions per category and language
  var PROMPTS = {
    en: {
      general: ["What is the Student Support Hub?", "How do I contact the Student Services Centre?", "How do I make a complaint?"],
      academic: ["How do I submit an extenuating circumstances claim?", "What happens if I miss an exam?", "How do I appeal a mark?"],
      modules: ["How do I change my modules?", "Where can I see my timetable?", "Why do I have a timetable clash?"],
      finance: ["When is the next tuition fee due date?", "How can I pay my tuition fees?", "Can I pay my fees in instalments?"],
      documents: ["How do I request a confirmation letter?", "Where do I get my transcript?", "How do I download my offer letter?"],
      campus: ["How do I renew my student pass?", "What should I do if I lose my passport?", "How do I apply for on-campus accommodation?"]
    },
    ms: {
      general: ["Apakah Student Support Hub?", "Bagaimana saya menghubungi Pusat Perkhidmatan Pelajar?", "Bagaimana saya membuat aduan?"],
      academic: ["Bagaimana saya menghantar tuntutan keadaan luar jangka?", "Apa berlaku jika saya terlepas peperiksaan?", "Bagaimana saya merayu markah?"],
      modules: ["Bagaimana saya menukar modul?", "Di mana saya boleh melihat jadual waktu?", "Kenapa jadual waktu saya bertindih?"],
      finance: ["Bilakah tarikh akhir yuran pengajian seterusnya?", "Bagaimana saya membayar yuran pengajian?", "Bolehkah saya membayar yuran secara ansuran?"],
      documents: ["Bagaimana saya memohon surat pengesahan?", "Di mana saya boleh mendapatkan transkrip?", "Bagaimana saya memuat turun surat tawaran?"],
      campus: ["Bagaimana saya memperbaharui pas pelajar?", "Apa perlu saya buat jika pasport hilang?", "Bagaimana saya memohon penginapan dalam kampus?"]
    },
    zh: {
      general: ["什么是学生支持中心（Student Support Hub）？", "如何联系学生服务中心？", "如何提出投诉？"],
      academic: ["如何提交特殊情况（EC）申请？", "如果我错过了考试怎么办？", "如何对成绩提出申诉？"],
      modules: ["如何更换我的模块？", "在哪里查看我的课程表？", "为什么我的课程表有冲突？"],
      finance: ["下一次学费截止日期是什么时候？", "如何缴纳学费？", "学费可以分期付款吗？"],
      documents: ["如何申请在读证明信？", "在哪里获取成绩单？", "如何下载我的录取通知书？"],
      campus: ["如何续签学生准证？", "护照丢失了该怎么办？", "如何申请校内住宿？"]
    }
  };

  // ---------------------------------------------------------- state and helpers
  var state = {
    lang: "en",
    category: "general",
    history: [],
    transcript: [],      // what is on screen, so the chat survives moving between pages
    sending: false
  };

  var $ = function (sel) { return document.querySelector(sel); };
  var $$ = function (sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); };
  var list = $("#cb-message-list");
  var input = $("#cb-user-input");
  var sendBtn = $("#cb-send-btn");
  var form = $("#cb-chat-form");
  var charCount = $("#cb-char-count");

  function t(key, vars) {
    var text = (T[state.lang] && T[state.lang][key]) || T.en[key] || key;
    if (vars) Object.keys(vars).forEach(function (k) { text = text.replace("{" + k + "}", vars[k]); });
    return text;
  }

  function store(key, value) {
    try { localStorage.setItem(key, value); } catch (e) { /* private mode */ }
  }
  function recall(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function icon(paths) {
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("class", "cb-icon");
    svg.setAttribute("aria-hidden", "true");
    svg.innerHTML = paths;
    return svg;
  }
  var ICONS = {
    up: '<path d="M7.5 10.5V20H4.5v-9.5zM7.5 10.5l4-7c1.4 0 2.3 1.1 2 2.5l-.8 3.5h5.4c1.3 0 2.2 1.2 1.9 2.4l-1.6 6.5c-.2.9-1 1.6-2 1.6H7.5"/>',
    down: '<path d="M16.5 13.5V4h3v9.5zM16.5 13.5l-4 7c-1.4 0-2.3-1.1-2-2.5l.8-3.5H5.9c-1.3 0-2.2-1.2-1.9-2.4l1.6-6.5c.2-.9 1-1.6 2-1.6h8.9"/>',
    close: '<path d="M6 6l12 12M18 6L6 18"/>',
    copy: '<rect x="8.5" y="8.5" width="11" height="11" rx="2"/><path d="M15.5 8.5V6a1.5 1.5 0 0 0-1.5-1.5H6A1.5 1.5 0 0 0 4.5 6v8A1.5 1.5 0 0 0 6 15.5h2.5"/>',
    phone: '<path d="M5 4h3.5l1.5 4-2.2 1.4a11 11 0 0 0 4.8 4.8L14 12l4 1.5V17a2 2 0 0 1-2 2A14 14 0 0 1 3 6a2 2 0 0 1 2-2z"/>'
  };

  function timeNow() {
    return new Date().toLocaleTimeString(state.lang === "zh" ? "zh-CN" : state.lang === "ms" ? "ms-MY" : "en-GB",
      { hour: "numeric", minute: "2-digit" });
  }

  // Very small, safe Markdown: text is escaped first, then a few patterns are formatted.
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function inlineMd(line) {
    return line
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\[(\d{1,2})\]/g, '<span class="cb-cite">[$1]</span>')
      .replace(/(https?:\/\/[^\s<)]+[^\s<).,;:!?])/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
  }
  function renderMarkdown(text) {
    var lines = escapeHtml(text.trim()).split(/\n/);
    var html = [], para = [], listType = null;
    function flushPara() { if (para.length) { html.push("<p>" + inlineMd(para.join("<br>")) + "</p>"); para = []; } }
    function closeList() { if (listType) { html.push("</" + listType + ">"); listType = null; } }
    lines.forEach(function (raw) {
      var line = raw.trim();
      var bullet = line.match(/^[-*•]\s+(.*)$/);
      var numbered = line.match(/^\d+[.)]\s+(.*)$/);
      if (bullet || numbered) {
        flushPara();
        var type = bullet ? "ul" : "ol";
        if (listType !== type) { closeList(); html.push("<" + type + ">"); listType = type; }
        html.push("<li>" + inlineMd((bullet || numbered)[1]) + "</li>");
      } else if (!line) {
        flushPara(); closeList();
      } else {
        closeList();
        para.push(line.replace(/^#{1,6}\s+/, ""));
      }
    });
    flushPara(); closeList();
    return html.join("");
  }

  // ---------------------------------------------------------- theme
  function setTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    $$("[data-theme-choice]").forEach(function (b) {
      b.setAttribute("aria-checked", String(b.dataset.themeChoice === theme));
    });
    store("cb-theme", theme);
  }

  // ---------------------------------------------------------- language
  function applyLanguage(lang) {
    if (!T[lang]) lang = "en";
    state.lang = lang;
    document.documentElement.lang = lang === "zh" ? "zh-CN" : lang;
    document.title = t("page.title");
    $$("[data-i18n]").forEach(function (node) { node.textContent = t(node.dataset.i18n); });
    $$("[data-i18n-placeholder]").forEach(function (node) { node.placeholder = t(node.dataset.i18nPlaceholder); });
    $$("[data-i18n-aria]").forEach(function (node) { node.setAttribute("aria-label", t(node.dataset.i18nAria)); });
    $$("[data-lang-select]").forEach(function (sel) { sel.value = lang; });
    $$(".cb-lang-pill").forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.lang === lang)); });
    renderPrompts();
    updateCharCount();
    store("cb-lang", lang);
  }

  // ---------------------------------------------------------- categories and prompts
  function setCategory(category) {
    state.category = category;
    $$(".cb-category-tile").forEach(function (b) {
      var on = b.dataset.category === category;
      b.setAttribute("aria-pressed", String(on));
      // in the narrow layouts the topics are a sideways-scrolling row: bring the chosen one into view
      var row = $(".cb-sidebar");
      if (on && row && row.scrollWidth > row.clientWidth) row.scrollLeft = Math.max(0, b.offsetLeft - 12);
    });
    renderPrompts();
  }

  function renderPrompts() {
    var box = $("#cb-prompt-list");
    box.replaceChildren();
    (PROMPTS[state.lang][state.category] || []).forEach(function (q) {
      var chip = el("button", "cb-prompt-chip", q);
      chip.type = "button";
      chip.addEventListener("click", function () { send(q); });
      box.appendChild(chip);
    });
  }

  // ---------------------------------------------------------- chat rendering
  function hideWelcome() {
    var w = $("#cb-welcome");
    if (w) w.hidden = true;
  }

  function scrollToEnd() {
    list.scrollTop = list.scrollHeight;
  }

  function addUserMessage(text) {
    var row = el("article", "cb-message cb-message-user");
    row.setAttribute("aria-label", t("chat.you"));
    var body = el("div", "cb-message-body");
    body.appendChild(el("div", "cb-bubble", text));
    body.appendChild(el("div", "cb-meta", timeNow()));
    row.appendChild(body);
    list.appendChild(row);
    scrollToEnd();
  }

  function addBotShell() {
    var row = el("article", "cb-message cb-message-bot");
    row.setAttribute("aria-label", t("chat.bot"));
    var avatar = el("div", "cb-avatar");
    var crest = el("img");
    crest.src = "style/favicon.png"; crest.alt = ""; crest.width = 34; crest.height = 34;
    avatar.appendChild(crest);
    row.appendChild(avatar);
    var body = el("div", "cb-message-body");
    var bubble = el("div", "cb-bubble");
    var typing = el("div", "cb-typing");
    typing.setAttribute("role", "status");
    typing.appendChild(el("span")); typing.appendChild(el("span")); typing.appendChild(el("span"));
    typing.appendChild(el("span", "sr-only", t("chat.typing")));
    bubble.appendChild(typing);
    body.appendChild(bubble);
    row.appendChild(body);
    list.appendChild(row);
    scrollToEnd();
    return { row: row, body: body, bubble: bubble };
  }

  function renderSources(bubble, sources) {
    if (!sources || !sources.length) return;
    var box = el("div", "cb-sources");
    box.appendChild(el("span", "cb-sources-label", t("chat.sources")));
    var ol = el("ol");
    sources.forEach(function (s) {
      var li = el("li");
      var label = s.title + (s.pages && s.pages.length ? " (" + t("chat.page") + " " + s.pages.join(", ") + ")" : "");
      if (s.url && /^https?:\/\//.test(s.url)) {
        var a = el("a", null, label);
        a.href = s.url; a.target = "_blank"; a.rel = "noopener noreferrer";
        li.appendChild(a);
      } else {
        li.textContent = label;
      }
      ol.appendChild(li);
    });
    box.appendChild(ol);
    bubble.appendChild(box);
  }

  // 24/7 contacts. These are the same numbers as in the page; on start-up they are replaced by the
  // server's list (config.py), so the call buttons always match the distress message.
  var contacts = [
    { key: "hotline", number: "019-266 0691", tel: "tel:+60192660691" },
    { key: "security", number: "03-8924 8777", tel: "tel:+60389248777" },
    { key: "emergency", number: "999", tel: "tel:999" }
  ];
  function validContacts(list) {
    return (Array.isArray(list) ? list : []).filter(function (c) {
      return c && /^[a-z]+$/.test(c.key) && typeof c.number === "string" && /^tel:\+?\d+$/.test(c.tel || "");
    });
  }

  function renderUrgentActions(bubble, list) {
    var actions = el("div", "cb-urgent-actions");
    var shown = validContacts(list);
    (shown.length ? shown : contacts).forEach(function (c) {
      if (c.key !== "hotline" && c.key !== "security") return;
      var a = el("a", "cb-call-btn");
      a.href = c.tel;
      a.appendChild(icon(ICONS.phone));
      a.appendChild(document.createTextNode(t("urgent." + c.key) + ": " + c.number));
      actions.appendChild(a);
    });
    bubble.appendChild(actions);
  }

  function loadContacts() {
    fetch(API_BASE + "/contacts").then(function (r) { return r.ok ? r.json() : null; }).then(function (data) {
      var list = validContacts(data && data.contacts);
      if (!list.length) return;
      contacts = list;
      list.forEach(function (c) {
        $$('[data-contact="' + c.key + '"]').forEach(function (a) { a.href = c.tel; a.textContent = c.number; });
      });
    }).catch(function () { /* server not reachable: keep the numbers written in the page */ });
  }

  // item: this answer's entry in the transcript. It remembers the rating, so an answer restored on
  // another page can't be rated twice, and the topic and language the question was asked in.
  function renderMeta(shell, data, item) {
    var meta = el("div", "cb-meta");
    meta.appendChild(el("span", null, timeNow()));

    var copyBtn = el("button", "cb-tool-btn");
    copyBtn.type = "button";
    copyBtn.appendChild(icon(ICONS.copy));
    var copyLabel = el("span", null, t("chat.copy"));
    copyBtn.appendChild(copyLabel);
    copyBtn.addEventListener("click", function () {
      copyText(data.reply || "").then(function () {
        copyLabel.textContent = t("chat.copied");
        setTimeout(function () { copyLabel.textContent = t("chat.copy"); }, 1600);
      });
    });
    meta.appendChild(copyBtn);

    if (!data.flag) {   // no ratings on safety messages
      var ratingContext = { language: item.lang || state.lang, category: item.category || state.category,
                            answered: !!data.answered };
      var up = feedbackButton("up", ICONS.up, t("chat.helpful"), ratingContext, item);
      var down = feedbackButton("down", ICONS.down, t("chat.notHelpful"), ratingContext, item);
      up.partner = down; down.partner = up;
      if (item.rated) {
        (item.rated === "up" ? up : down).setAttribute("aria-pressed", "true");
        up.disabled = down.disabled = true;
      }
      meta.appendChild(up);
      meta.appendChild(down);
    }
    shell.body.appendChild(meta);
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
    return new Promise(function (resolve) {
      var area = el("textarea"); area.value = text;
      area.style.position = "fixed"; area.style.opacity = "0";
      document.body.appendChild(area); area.select();
      try { document.execCommand("copy"); } catch (e) { /* ignore */ }
      area.remove(); resolve();
    });
  }

  // ---------------------------------------------------------- feedback
  function postJSON(path, body) {
    return fetch(API_BASE + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (r) { return r.ok ? r.json() : null; });
  }

  function feedbackButton(rating, svgPaths, label, context, item) {
    var btn = el("button", "cb-tool-btn");
    btn.type = "button";
    btn.setAttribute("aria-pressed", "false");
    btn.setAttribute("aria-label", label);
    btn.title = label;
    btn.appendChild(icon(svgPaths));
    btn.addEventListener("click", function () {
      btn.setAttribute("aria-pressed", "true");
      btn.disabled = true;
      btn.partner.disabled = true;
      item.rated = rating;
      saveTranscript();
      var meta = btn.parentNode;
      var saved = postJSON("/feedback", {
        rating: rating, language: context.language, category: context.category,
        answered: context.answered, channel: CHANNEL
      }).catch(function () { return null; });   // feedback is best-effort
      if (rating === "down") {
        askReason(meta, saved);
      } else {
        meta.appendChild(el("span", "cb-feedback-thanks", t("chat.thanks")));
      }
    });
    return btn;
  }

  // After a thumbs-down: one tap to say what was wrong. Fixed choices only, so nothing personal is stored.
  function askReason(meta, saved) {
    var box = el("div", "cb-reasons");
    box.setAttribute("role", "group");
    var label = el("span", "cb-reasons-label", t("chat.whyNot"));
    label.id = "cb-reasons-" + Math.random().toString(36).slice(2, 8);
    box.setAttribute("aria-labelledby", label.id);
    box.appendChild(label);
    ["wrong", "incomplete", "unclear", "outdated"].forEach(function (code) {
      var chip = el("button", "cb-reason-chip", t("reason." + code));
      chip.type = "button";
      chip.addEventListener("click", function () {
        saved.then(function (res) {
          if (res && res.id) postJSON("/feedback/" + res.id + "/reason", { reason: code }).catch(function () {});
        });
        box.replaceChildren(el("span", "cb-feedback-thanks", t("chat.reasonThanks")));
      });
      box.appendChild(chip);
    });
    var skip = el("button", "cb-reason-skip");
    skip.type = "button";
    skip.setAttribute("aria-label", t("help.close"));
    skip.appendChild(icon(ICONS.close));
    skip.addEventListener("click", function () { box.replaceChildren(el("span", "cb-feedback-thanks", t("chat.thanks"))); });
    box.appendChild(skip);
    meta.parentNode.appendChild(box);
    scrollToEnd();
  }

  // ---------------------------------------------------------- sending
  function setSending(on) {
    state.sending = on;
    sendBtn.disabled = on || !input.value.trim();
    form.setAttribute("aria-busy", String(on));
  }

  function nearBottom() {
    return list.scrollHeight - list.scrollTop - list.clientHeight < 120;
  }

  function setStatus(shell, text) {
    var status = shell.bubble.querySelector(".cb-status");
    if (!status) {
      status = el("div", "cb-status");
      shell.bubble.appendChild(status);
    }
    status.textContent = text;
  }

  // Draw a finished answer (also used to restore the conversation after moving to another page).
  function renderAnswer(shell, data, item) {
    shell.bubble.replaceChildren();
    shell.bubble.classList.remove("is-streaming");
    var content = el("div", "cb-message-text");
    content.innerHTML = renderMarkdown(data.reply || "");
    shell.bubble.appendChild(content);
    if (data.flag === "crisis") {
      shell.row.classList.add("is-urgent");
      renderUrgentActions(shell.bubble, data.contacts);
    }
    renderSources(shell.bubble, data.sources);
    renderMeta(shell, data, item || {});
  }

  // What the student sees when a request fails, in their language. The server's own messages are
  // for staff (they mention LM Studio) and the browser's are in English, so neither is shown.
  function errorFor(status) {
    if (status === 429) return t("chat.tooFast");
    if (status >= 500) return t("chat.unavailable");
    return t("chat.error");
  }
  function studentError(message) {
    var err = new Error(message);
    err.forStudent = true;
    return err;
  }

  // Returns a function that shows a half-written reply in the bubble with a blinking cursor.
  function partialWriter(shell) {
    var content = null;
    return function (text) {
      if (!content) {
        shell.bubble.replaceChildren();
        shell.bubble.classList.add("is-streaming");
        content = el("div", "cb-message-text");
        shell.bubble.appendChild(content);
      }
      var follow = nearBottom();
      content.innerHTML = renderMarkdown(text);
      var last = content.lastElementChild;                  // put the cursor at the end of the last line,
      while (last && /^(UL|OL)$/.test(last.tagName) && last.lastElementChild) last = last.lastElementChild;  // even inside a list
      var caret = el("span", "cb-caret"); caret.setAttribute("aria-hidden", "true");
      (last || content).appendChild(caret);
      if (follow) scrollToEnd();
    };
  }

  function wait(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  // Ready-made replies (greetings, "I don't have that information", blocked messages) arrive all
  // at once. Type them out word by word so they look like every other answer. Skipped for crisis
  // replies (the numbers must show at once) and for people who switched off animations.
  async function typeOut(shell, text) {
    var reduceMotion = false;
    try { reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (e) { /* old browser */ }
    if (reduceMotion || !text) return;
    await wait(350);                                         // let the typing dots show briefly
    var draw = partialWriter(shell);
    var pieces = /[㐀-鿿]/.test(text)
      ? Array.from(text)                                     // Chinese has no spaces: one character at a time
      : text.match(/\S+\s*|\s+/g) || [text];                 // otherwise words with the spaces after them
    var step = Math.max(1, Math.ceil(pieces.length / 60));   // long replies: a few words at a time
    var shown = "";
    for (var i = 0; i < pieces.length; i += step) {
      shown += pieces.slice(i, i + step).join("");
      draw(shown);
      await wait(30);
    }
  }

  // Read the reply as it is written: one JSON event per line (status, delta..., done).
  async function streamReply(body, shell) {
    var res = await fetch(API_BASE + "/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    if (res.status === 404 || res.status === 405) return null;        // older server: use /chat instead
    if (!res.ok || !res.body) throw studentError(errorFor(res.status));
    var reader = res.body.getReader();
    var decoder = new TextDecoder();
    var buffer = "", text = "", done = null, pending = false;
    var draw = partialWriter(shell);

    function handle(event) {
      if (event.type === "status") {
        setStatus(shell, event.stage === "writing" ? t("chat.writing", { n: event.sources_found || 1 }) : t("chat.searching"));
      } else if (event.type === "delta") {
        text += event.text;
        if (!pending) {
          pending = true;
          requestAnimationFrame(function () { pending = false; draw(text); });
        }
      } else if (event.type === "done") {
        done = event;
      } else if (event.type === "error") {
        throw studentError(t("chat.unavailable"));
      }
    }

    while (true) {
      var chunk = await reader.read();
      if (chunk.done) break;
      buffer += decoder.decode(chunk.value, { stream: true });
      var lines = buffer.split("\n");
      buffer = lines.pop();
      lines.forEach(function (line) { if (line.trim()) handle(JSON.parse(line)); });
    }
    if (buffer.trim()) handle(JSON.parse(buffer));
    if (!done) throw studentError(t("chat.error"));
    done.streamed = text.length > 0;
    return done;
  }

  async function plainReply(body) {
    var res = await fetch(API_BASE + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    var data = null;
    try { data = await res.json(); } catch (e) { /* not JSON */ }
    if (!res.ok || !data) throw studentError(errorFor(res.status));
    return data;
  }

  async function send(text) {
    text = (text || "").trim();
    if (!text || state.sending) return;
    if (text.length > MAX_CHARS) text = text.slice(0, MAX_CHARS);

    stopListening();
    hideWelcome();
    addUserMessage(text);
    input.value = "";
    autoGrow();
    updateCharCount();
    setSending(true);

    var shell = addBotShell();
    var body = {
      message: text,
      language: state.lang,
      category: state.category,
      history: state.history.slice(-HISTORY_TURNS),
      channel: CHANNEL
    };
    try {
      var data = await streamReply(body, shell);
      if (!data) data = await plainReply(body);
      if (!data.streamed && data.flag !== "crisis") await typeOut(shell, data.reply);
      var item = { q: text, category: body.category, lang: body.language, rated: null,
                   a: { reply: data.reply, sources: data.sources, flag: data.flag, answered: data.answered,
                        contacts: data.contacts } };
      renderAnswer(shell, data, item);

      state.history.push({ role: "user", content: text },
                         { role: "assistant", content: (data.reply || "").slice(0, HISTORY_CHARS) });
      state.history = state.history.slice(-HISTORY_TURNS * 2);
      state.transcript.push(item);
      saveTranscript();
    } catch (err) {
      showError(shell, err && err.forStudent ? err.message : t("chat.error"), text);
    } finally {
      setSending(false);
      scrollToEnd();
      if (!EMBED || document.hasFocus()) input.focus();
    }
  }

  // ---------------------------------------------------------- keep the chat when moving between pages
  function saveTranscript() {
    try {
      sessionStorage.setItem(TRANSCRIPT_KEY, JSON.stringify({
        transcript: state.transcript.slice(-20), history: state.history
      }));
    } catch (e) { /* storage blocked or full: the chat just won't be restored */ }
  }

  function restoreTranscript() {
    var saved = null;
    try { saved = JSON.parse(sessionStorage.getItem(TRANSCRIPT_KEY) || "null"); } catch (e) { saved = null; }
    if (!saved || !saved.transcript || !saved.transcript.length) return;
    state.transcript = saved.transcript;
    state.history = (saved.history || []).map(function (h) {
      return { role: h.role, content: String(h.content || "").slice(0, HISTORY_CHARS) };
    });
    hideWelcome();
    state.transcript.forEach(function (item) {
      addUserMessage(item.q);
      renderAnswer(addBotShell(), item.a || {}, item);
    });
    list.style.scrollBehavior = "auto";
    scrollToEnd();
    list.style.scrollBehavior = "";
  }

  function showError(shell, message, question) {
    shell.row.classList.add("is-error");
    shell.bubble.replaceChildren(el("p", null, message));
    var retry = el("button", "cb-retry-btn", t("chat.retry"));
    retry.type = "button";
    retry.addEventListener("click", function () {
      shell.row.remove();
      var last = list.querySelectorAll(".cb-message-user");
      if (last.length) last[last.length - 1].remove();
      send(question);
    });
    shell.bubble.appendChild(retry);
  }

  function resetConversation() {
    state.history = [];
    state.transcript = [];
    saveTranscript();
    $$(".cb-message").forEach(function (m) { m.remove(); });
    var w = $("#cb-welcome");
    if (w) w.hidden = false;
    input.value = "";
    autoGrow();
    updateCharCount();
    setSending(false);
    input.focus();
  }

  // ---------------------------------------------------------- composer
  function autoGrow() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 160) + "px";
  }

  function updateCharCount() {
    var left = MAX_CHARS - input.value.length;
    charCount.textContent = left <= 150 ? t("chat.charsLeft", { n: left }) : "";
    charCount.classList.toggle("is-near", left <= 50);
  }

  // ---------------------------------------------------------- voice input
  // Uses the browser's own speech recognition (Chrome, Edge, Safari). The button is hidden elsewhere.
  var Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  var recognizer = null;
  var SPEECH_LANG = { en: "en-MY", ms: "ms-MY", zh: "zh-CN" };

  function stopListening() {
    if (recognizer) { try { recognizer.stop(); } catch (e) { /* already stopped */ } }
  }

  function toggleListening() {
    var mic = $("#cb-mic-btn");
    if (recognizer) { stopListening(); return; }
    recognizer = new Recognition();
    recognizer.lang = SPEECH_LANG[state.lang] || "en-MY";
    recognizer.interimResults = true;
    var before = input.value ? input.value.replace(/\s*$/, " ") : "";
    recognizer.onresult = function (e) {
      var said = "";
      for (var i = 0; i < e.results.length; i++) said += e.results[i][0].transcript;
      input.value = (before + said).slice(0, MAX_CHARS);
      autoGrow(); updateCharCount();
      sendBtn.disabled = state.sending || !input.value.trim();
    };
    recognizer.onend = function () {
      recognizer = null;
      mic.setAttribute("aria-pressed", "false");
      mic.classList.remove("is-listening");
      input.placeholder = t("chat.inputPlaceholder");
      input.focus();
    };
    recognizer.onerror = recognizer.onend;
    mic.setAttribute("aria-pressed", "true");
    mic.classList.add("is-listening");
    input.placeholder = t("chat.listening");
    recognizer.start();
  }

  // ---------------------------------------------------------- side panel (widget.js) messages
  function tellParent(type) {
    if (EMBED && window.parent !== window) window.parent.postMessage({ source: "cb-buddy", type: type }, "*");
  }

  function listenToParent() {
    window.addEventListener("message", function (e) {
      if (e.source !== window.parent || !e.data || e.data.source !== "cb-widget") return;
      var msg = e.data;
      if (msg.type === "focus") input.focus();
      if (msg.type === "category" && PROMPTS.en[msg.value]) setCategory(msg.value);
      if (msg.type === "ask" && typeof msg.text === "string") send(msg.text.slice(0, MAX_CHARS));
    });
  }

  // ---------------------------------------------------------- help dialog
  function openHelp() {
    var d = $("#cb-help-dialog");
    if (typeof d.showModal === "function") d.showModal(); else d.setAttribute("open", "");
  }
  function closeHelp() {
    var d = $("#cb-help-dialog");
    if (typeof d.close === "function") d.close(); else d.removeAttribute("open");
    (EMBED ? $("#cb-embed-help") : $("#cb-help-btn")).focus();
  }

  // ---------------------------------------------------------- start-up
  function init() {
    // theme
    setTheme(document.documentElement.getAttribute("data-theme") || "light");
    $$("[data-theme-choice]").forEach(function (b) {
      b.addEventListener("click", function () { setTheme(b.dataset.themeChoice); });
    });

    // language: ?lang= in the URL, then the saved choice, then English
    var urlLang = new URLSearchParams(location.search).get("lang");
    applyLanguage(urlLang || recall("cb-lang") || "en");
    $$("[data-lang-select]").forEach(function (sel) {
      sel.addEventListener("change", function () { applyLanguage(sel.value); });
    });
    $$(".cb-lang-pill").forEach(function (b) {
      b.addEventListener("click", function () { applyLanguage(b.dataset.lang); });
    });

    // categories
    $$(".cb-category-tile").forEach(function (b) {
      b.addEventListener("click", function () { setCategory(b.dataset.category); });
    });

    // composer
    form.addEventListener("submit", function (e) { e.preventDefault(); send(input.value); });
    input.addEventListener("input", function () {
      autoGrow();
      updateCharCount();
      sendBtn.disabled = state.sending || !input.value.trim();
    });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {   // isComposing: don't send mid-way through Chinese input
        e.preventDefault();
        send(input.value);
      }
    });

    // category from the URL (the side panel can open focused on a topic, e.g. on a fees page)
    var urlCategory = PARAMS.get("category");
    if (urlCategory && PROMPTS.en[urlCategory]) setCategory(urlCategory);

    // voice input, where the browser supports it
    if (Recognition) {
      $("#cb-mic-btn").hidden = false;
      $("#cb-mic-btn").addEventListener("click", toggleListening);
    }

    // side panel
    if (EMBED) {
      $("#cb-embed-new").addEventListener("click", resetConversation);
      $("#cb-embed-help").addEventListener("click", openHelp);
      $("#cb-embed-close").addEventListener("click", function () { tellParent("close"); });
      $("#cb-embed-expand").addEventListener("click", function () {
        window.open("index.html?lang=" + state.lang, "_blank", "noopener");
      });
      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && !$("#cb-help-dialog").open) tellParent("close");
      });
      listenToParent();
      tellParent("ready");
    }

    loadContacts();
    $("#cb-reset-btn").addEventListener("click", resetConversation);
    $("#cb-help-btn").addEventListener("click", openHelp);
    $("#cb-help-close").addEventListener("click", closeHelp);
    $("#cb-help-dialog").addEventListener("click", function (e) {
      if (e.target === e.currentTarget) closeHelp();   // click on the backdrop
    });
  }

  init();
  restoreTranscript();
})();
