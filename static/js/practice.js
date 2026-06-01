(function () {
  let examLimitMs = 40 * 60 * 1000;
  const qid = window.QUESTION_ID;

  const essay = document.getElementById("essay");
  const wordEl = document.getElementById("word-count");
  const timerMain = document.getElementById("timer-main");
  const timerLabel = document.getElementById("timer-label");
  const timerDisplay = document.getElementById("timer-display");
  const elapsedMain = document.getElementById("elapsed-main");
  const startBtn = document.getElementById("start-btn");
  const finishBtn = document.getElementById("finish-btn");
  const saveStatus = document.getElementById("save-status");
  const fontSize = document.getElementById("font-size");
  const lineHeight = document.getElementById("line-height");
  const questionPane = document.getElementById("question-pane");
  const resultModal = document.getElementById("result-modal");
  const resultStats = document.getElementById("result-stats");
  const essayMenu = document.getElementById("essay-context-menu");
  const promptMenu = document.getElementById("prompt-context-menu");

  let question = null;
  let writingId = null;
  let started = false;
  let startTime = null;
  let tickInterval = null;
  let saveInterval = null;
  let paraInterval = null;
  let at40Recorded = false;
  let snapshot40 = { ms: null, words: 0, caret: 0 };
  let paragraphTimes = [];
  let lastParaTick = null;
  let activeParaIndex = 0;
  let plainPrompt = "";

  fontSize.addEventListener("input", applyEditorStyle);
  lineHeight.addEventListener("input", applyEditorStyle);
  applyEditorStyle();

  function applyEditorStyle() {
    essay.style.fontSize = fontSize.value + "px";
    essay.style.lineHeight = lineHeight.value / 100;
  }

  function countWords(text) {
    const t = (text || "").trim();
    if (!t) return 0;
    return t.split(/\s+/).filter(Boolean).length;
  }

  function splitParagraphs(text) {
    const parts = (text || "").split(/\n\s*\n/);
    return parts.filter((p) => p.trim().length > 0);
  }

  function paragraphIndexAtPosition(text, pos) {
    const paras = splitParagraphs(text);
    if (!paras.length) return 0;
    let offset = 0;
    const chunks = (text || "").split(/(\n\s*\n)/);
    let pIndex = 0;
    let inPara = false;
    for (let i = 0; i < chunks.length; i++) {
      const chunk = chunks[i];
      if (/^\n\s*\n$/.test(chunk)) {
        if (inPara) pIndex++;
        inPara = false;
        offset += chunk.length;
        continue;
      }
      if (!chunk.trim()) {
        offset += chunk.length;
        continue;
      }
      const start = offset;
      const end = offset + chunk.length;
      if (pos >= start && pos <= end) return Math.min(pIndex, paras.length - 1);
      offset = end;
      inPara = true;
    }
    return Math.max(0, paras.length - 1);
  }

  function buildParagraphStats() {
    const paras = splitParagraphs(essay.value);
    return paras.map((text, index) => ({
      index,
      time_ms: paragraphTimes[index] || 0,
      words: countWords(text),
      text: text.trim().slice(0, 120),
      preview: text.trim().slice(0, 80),
    }));
  }

  function tickParagraphTime() {
    if (!started || lastParaTick == null) return;
    const now = Date.now();
    const delta = now - lastParaTick;
    lastParaTick = now;
    activeParaIndex = paragraphIndexAtPosition(essay.value, essay.selectionStart);
    while (paragraphTimes.length <= activeParaIndex) paragraphTimes.push(0);
    paragraphTimes[activeParaIndex] += delta;
  }

  function formatClock(ms) {
    const sec = Math.max(0, Math.floor(ms / 1000));
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }

  function formatDuration(ms) {
    const sec = Math.floor(ms / 1000);
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    if (m >= 60) {
      const h = Math.floor(m / 60);
      const rm = m % 60;
      return `${h}h ${rm}m ${s}s`;
    }
    return `${m}m ${s}s`;
  }

  function updateWordCount() {
    wordEl.textContent = countWords(essay.value);
  }

  function updateTimer() {
    if (!started || !startTime) return;
    const elapsed = Date.now() - startTime;
    elapsedMain.textContent = formatClock(elapsed);
    const remaining = examLimitMs - elapsed;
    if (remaining > 0) {
      timerMain.textContent = formatClock(remaining);
      timerLabel.textContent = " remaining";
      timerDisplay.classList.remove("overtime");
    } else {
      const over = elapsed - examLimitMs;
      timerMain.textContent = "+" + formatClock(over);
      timerLabel.textContent = " over time";
      timerDisplay.classList.add("overtime");
      if (!at40Recorded) {
        at40Recorded = true;
        snapshot40 = {
          ms: elapsed,
          words: countWords(essay.value),
          caret: essay.selectionStart,
        };
        saveDraft(false);
      }
    }
  }

  async function api(path, opts) {
    const res = await fetch(path, opts);
    if (res.status === 401) {
      window.location.href = "/login";
      throw new Error("auth");
    }
    return res;
  }

  async function saveHighlights(highlights) {
    await api(`/api/questions/${qid}/highlights`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ highlights }),
    });
  }

  function renderPrompt() {
    const mins = question.task_type === "task1" ? 20 : 40;
    const imgHtml = question.has_image
      ? `<figure class="task1-figure"><img src="${escapeHtml(question.image_url)}" alt="Chart" class="task1-chart"></figure>`
      : "";
    questionPane.innerHTML = `
      <span class="task-badge">${escapeHtml(question.task_type)} · ${mins} min exam time</span>
      <h2 class="question-title">${escapeHtml(question.title)}</h2>
      ${imgHtml}
      <div id="prompt-text" class="prompt-text">${question.prompt_html || escapeHtml(question.prompt)}</div>`;
    plainPrompt = question.prompt || "";
  }

  async function loadQuestion() {
    const res = await api(`/api/questions/${qid}`);
    if (!res.ok) {
      questionPane.innerHTML = "<p>Question not found.</p>";
      return;
    }
    question = await res.json();
    const mins = question.task_type === "task1" ? 20 : 40;
    examLimitMs = mins * 60 * 1000;
    timerMain.textContent = formatClock(examLimitMs);
    renderPrompt();
    setupPromptHighlightMenu();
  }

  function setupPromptHighlightMenu() {
    const promptEl = document.getElementById("prompt-text");
    if (!promptEl) return;
    promptEl.addEventListener("contextmenu", (e) => {
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed || !promptEl.contains(sel.anchorNode)) return;
      e.preventDefault();
      promptMenu.style.left = e.pageX + "px";
      promptMenu.style.top = e.pageY + "px";
      promptMenu.hidden = false;
      promptMenu._range = sel.getRangeAt(0).cloneRange();
    });
  }

  promptMenu.querySelector("[data-action=highlight]").addEventListener("click", async () => {
    promptMenu.hidden = true;
    const range = promptMenu._range;
    if (!range || !plainPrompt) return;
    const pre = range.startContainer;
    const promptEl = document.getElementById("prompt-text");
    const temp = document.createElement("div");
    temp.appendChild(range.cloneContents());
    const selectedText = temp.textContent;
    if (!selectedText) return;
    const start = plainPrompt.indexOf(selectedText);
    if (start < 0) return;
    const end = start + selectedText.length;
    const highlights = (question.highlights || []).slice();
    highlights.push({ start, end });
    question.highlights = highlights;
    question.prompt_html = null;
    const sorted = highlights.slice().sort((a, b) => b.start - a.start);
    let html = plainPrompt;
    sorted.forEach((h) => {
      html =
        html.slice(0, h.start) +
        "<mark class=\"q-highlight\">" +
        html.slice(h.start, h.end) +
        "</mark>" +
        html.slice(h.end);
    });
    promptEl.innerHTML = html;
    await saveHighlights(highlights);
  });

  async function loadDraft() {
    const res = await api(`/api/writings/active/${qid}`);
    const w = await res.json();
    if (w && w.id) {
      writingId = w.id;
      if (w.content) essay.value = w.content;
      updateWordCount();
      saveStatus.textContent = "Draft loaded — click Start to continue timing";
    }
  }

  async function saveDraft(finish) {
    if (!writingId && !started && !finish) return;
    tickParagraphTime();
    const elapsed = started && startTime ? Date.now() - startTime : null;
    const body = {
      id: writingId,
      question_id: qid,
      content: essay.value,
      started_at: startTime ? new Date(startTime).toISOString() : undefined,
      elapsed_ms: elapsed,
      at_40min_ms: snapshot40.ms,
      words_at_40min: snapshot40.ms != null ? snapshot40.words : null,
      finish: !!finish,
      final_words: finish ? countWords(essay.value) : null,
      paragraph_stats: finish || started ? buildParagraphStats() : null,
    };
    const res = await api("/api/writings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!writingId && data.id) writingId = data.id;
    saveStatus.textContent = finish ? "Saved" : "Saved " + new Date().toLocaleTimeString();
    return data;
  }

  function startSession() {
    if (started) return;
    started = true;
    startTime = Date.now();
    lastParaTick = Date.now();
    paragraphTimes = [];
    activeParaIndex = 0;
    essay.disabled = false;
    essay.focus();
    startBtn.disabled = true;
    finishBtn.disabled = false;
    saveStatus.textContent = "Writing…";
    tickInterval = setInterval(updateTimer, 250);
    saveInterval = setInterval(() => saveDraft(false), 15000);
    paraInterval = setInterval(tickParagraphTime, 2000);
    updateTimer();
    updateWordCount();
  }

  function showResults(elapsed) {
    const words = countWords(essay.value);
    const pos = snapshot40.caret || 0;
    const rows = [
      ["Total time", formatDuration(elapsed)],
      ["Final word count", String(words)],
    ];
    if (snapshot40.ms != null) {
      rows.push(
        [`Time at ${examLimitMs / 60000} min mark`, formatDuration(snapshot40.ms)],
        [`Words at ${examLimitMs / 60000} min`, String(snapshot40.words)]
      );
    }
    const stats = buildParagraphStats();
    if (stats.length) {
      rows.push(["Paragraphs tracked", String(stats.length)]);
    }
    resultStats.innerHTML = rows
      .map(([k, v]) => `<div class="stat-row"><span>${k}</span><strong>${escapeHtml(String(v))}</strong></div>`)
      .join("");
    resultStats.innerHTML += `<p class="q-meta" style="margin-top:0.75rem"><a href="/history/writing/${writingId}">View full analytics →</a></p>`;
    resultModal.classList.add("show");
  }

  async function finishSession() {
    if (!started) return;
    clearInterval(tickInterval);
    clearInterval(saveInterval);
    clearInterval(paraInterval);
    tickParagraphTime();
    const elapsed = Date.now() - startTime;
    essay.disabled = true;
    finishBtn.disabled = true;
    await saveDraft(true);
    showResults(elapsed);
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  essay.addEventListener("input", () => {
    updateWordCount();
    if (started) activeParaIndex = paragraphIndexAtPosition(essay.value, essay.selectionStart);
  });

  essay.addEventListener("click", () => {
    if (started) tickParagraphTime();
  });

  essay.addEventListener("keyup", () => {
    if (started) activeParaIndex = paragraphIndexAtPosition(essay.value, essay.selectionStart);
  });

  essay.addEventListener("contextmenu", (e) => {
    const start = essay.selectionStart;
    const end = essay.selectionEnd;
    if (start === end) return;
    e.preventDefault();
    const selected = essay.value.slice(start, end);
    const wc = countWords(selected);
    essayMenu.querySelector(".wc-label").textContent = `${wc} word${wc === 1 ? "" : "s"} selected`;
    essayMenu.style.left = e.pageX + "px";
    essayMenu.style.top = e.pageY + "px";
    essayMenu.hidden = false;
  });

  document.addEventListener("click", () => {
    essayMenu.hidden = true;
    promptMenu.hidden = true;
  });

  startBtn.addEventListener("click", startSession);
  finishBtn.addEventListener("click", finishSession);
  document.getElementById("modal-home").addEventListener("click", () => {
    window.location.href = "/home";
  });

  window.addEventListener("beforeunload", (e) => {
    if (started && !finishBtn.disabled) {
      saveDraft(false);
      e.preventDefault();
      e.returnValue = "";
    }
  });

  loadQuestion();
  loadDraft();
})();
