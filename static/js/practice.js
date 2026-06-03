(function () {
  let examLimitMs = 40 * 60 * 1000;
  const qid = window.QUESTION_ID;

  const essay = document.getElementById("essay");
  const wordEl = document.getElementById("word-count");
  const timerMain = document.getElementById("timer-main");
  const timerLabel = document.getElementById("timer-label");
  const timerDisplay = document.getElementById("timer-display");
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
  const promptToolbar = document.getElementById("prompt-toolbar");
  const promptHighlightBtn = document.getElementById("prompt-highlight-btn");
  const chartSizeControl = document.getElementById("chart-size-control");
  const chartSize = document.getElementById("chart-size");

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
  let sessionHighlights = [];
  let savedEssaySel = { start: 0, end: 0 };
  let savedPromptRange = null;

  function closeMenus() {
    essayMenu.classList.remove("is-open");
    promptMenu.classList.remove("is-open");
  }

  function openMenu(menu, x, y) {
    closeMenus();
    menu.style.left = x + "px";
    menu.style.top = y + "px";
    menu.classList.add("is-open");
  }

  function saveEssaySelection() {
    savedEssaySel = { start: essay.selectionStart, end: essay.selectionEnd };
  }

  function getEssaySel() {
    let start = essay.selectionStart;
    let end = essay.selectionEnd;
    if (start === end && savedEssaySel.start !== savedEssaySel.end) {
      start = savedEssaySel.start;
      end = savedEssaySel.end;
    }
    return { start, end };
  }

  function showEssayWordMenu(clientX, clientY) {
    const { start, end } = getEssaySel();
    if (start >= end) return false;
    const wc = countWords(essay.value.slice(start, end));
    essayMenu.querySelector(".wc-label").textContent = `${wc} word${wc === 1 ? "" : "s"} selected`;
    openMenu(essayMenu, clientX, clientY);
    return true;
  }

  function showPromptHighlightMenu(clientX, clientY) {
    const promptEl = document.getElementById("prompt-text");
    if (!promptEl) return false;

    const sel = window.getSelection();
    let range = savedPromptRange;
    if (sel && !sel.isCollapsed && promptEl.contains(sel.anchorNode)) {
      range = sel.getRangeAt(0).cloneRange();
      savedPromptRange = range.cloneRange();
    }
    if (!range || !promptEl.contains(range.commonAncestorContainer)) return false;

    promptMenu._range = range.cloneRange();
    openMenu(promptMenu, clientX, clientY);
    return true;
  }

  function updatePromptToolbar() {
    if (!promptToolbar) return;
    const promptEl = document.getElementById("prompt-text");
    if (!promptEl) {
      promptToolbar.hidden = true;
      return;
    }
    const sel = window.getSelection();
    if (sel && !sel.isCollapsed && promptEl.contains(sel.anchorNode)) {
      savedPromptRange = sel.getRangeAt(0).cloneRange();
      promptToolbar.hidden = false;
    } else {
      promptToolbar.hidden = true;
    }
  }

  function highlightStorageKey() {
    return writingId ? `practice-highlights-${qid}-${writingId}` : null;
  }

  function loadStoredHighlights() {
    const key = highlightStorageKey();
    if (!key) return [];
    try {
      const raw = sessionStorage.getItem(key);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }

  function saveStoredHighlights() {
    const key = highlightStorageKey();
    if (!key) return;
    sessionStorage.setItem(key, JSON.stringify(sessionHighlights));
  }

  function refreshPromptHighlights() {
    const promptEl = document.getElementById("prompt-text");
    if (promptEl && plainPrompt) {
      promptEl.innerHTML = renderPromptHtml(plainPrompt, sessionHighlights);
    }
  }

  function clearPracticeHighlights() {
    sessionHighlights = [];
    const key = highlightStorageKey();
    if (key) sessionStorage.removeItem(key);
    sessionStorage.removeItem(`practice-highlights-${qid}`);
    refreshPromptHighlights();
  }

  async function applyPromptHighlight() {
    const range = promptMenu._range || savedPromptRange;
    const promptEl = document.getElementById("prompt-text");
    if (!range || !plainPrompt || !promptEl) return;
    const offsets = rangeToPlainOffsets(promptEl, range);
    if (!offsets) return;
    sessionHighlights = mergeHighlights(sessionHighlights, offsets);
    saveStoredHighlights();
    refreshPromptHighlights();
    savedPromptRange = null;
    if (promptToolbar) promptToolbar.hidden = true;
    window.getSelection()?.removeAllRanges();
  }

  function rangeToPlainOffsets(container, range) {
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    let offset = 0;
    let start = null;
    let end = null;
    let node;
    while ((node = walker.nextNode())) {
      const len = node.textContent.length;
      if (node === range.startContainer) start = offset + range.startOffset;
      if (node === range.endContainer) end = offset + range.endOffset;
      offset += len;
    }
    if (start == null || end == null || start >= end) return null;
    return { start, end };
  }

  function renderPromptHtml(text, highlights) {
    if (!highlights || !highlights.length) {
      return `<strong class="prompt-strong">${escapeHtml(text)}</strong>`;
    }
    return applyHighlightsHtml(text, highlights);
  }

  function applyHighlightsHtml(text, highlights) {
    if (!highlights || !highlights.length) return escapeHtml(text);
    const sorted = highlights.slice().sort((a, b) => a.start - b.start);
    let out = "";
    let pos = 0;
    for (const h of sorted) {
      if (h.start < pos || h.end > text.length || h.start >= h.end) continue;
      out += escapeHtml(text.slice(pos, h.start));
      out += '<mark class="q-highlight">' + escapeHtml(text.slice(h.start, h.end)) + "</mark>";
      pos = h.end;
    }
    out += escapeHtml(text.slice(pos));
    return out;
  }

  function mergeHighlights(existing, added) {
    const merged = existing.slice();
    merged.push(added);
    merged.sort((a, b) => a.start - b.start);
    const out = [];
    for (const h of merged) {
      if (!out.length || h.start > out[out.length - 1].end) {
        out.push({ ...h });
      } else {
        out[out.length - 1].end = Math.max(out[out.length - 1].end, h.end);
      }
    }
    return out;
  }

  fontSize.addEventListener("input", applyEditorStyle);
  lineHeight.addEventListener("input", applyEditorStyle);
  if (chartSize) chartSize.addEventListener("input", applyChartSize);
  applyEditorStyle();

  function applyChartSize() {
    const img = document.querySelector("#question-pane .task1-chart");
    if (img && chartSize) {
      img.style.width = chartSize.value + "%";
      sessionStorage.setItem(`chart-size-${qid}`, chartSize.value);
    }
  }

  function updateChartControl() {
    if (!chartSizeControl || !question) return;
    const show = question.has_image && question.task_type === "task1";
    chartSizeControl.hidden = !show;
    if (show && chartSize) {
      const saved = sessionStorage.getItem(`chart-size-${qid}`);
      if (saved) chartSize.value = saved;
      applyChartSize();
    }
  }

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

  function renderPrompt() {
    const mins = question.task_type === "task1" ? 20 : 40;
    const imgHtml = question.has_image
      ? `<figure class="task1-figure"><img src="${escapeHtml(question.image_url)}" alt="Chart" class="task1-chart"></figure>`
      : "";
    plainPrompt = question.prompt || "";
    sessionHighlights = [];
    sessionStorage.removeItem(`practice-highlights-${qid}`);
    const promptInner = renderPromptHtml(plainPrompt, sessionHighlights);
    questionPane.innerHTML = `
      <span class="task-badge">${escapeHtml(question.task_type)} · ${mins} min exam time</span>
      <h2 class="question-title">${escapeHtml(question.title)}</h2>
      <div id="prompt-text" class="prompt-text">${promptInner}</div>
      ${imgHtml}
      <p class="selection-hint">Select question text → Highlight (this attempt only)</p>`;
    savedPromptRange = null;
    if (promptToolbar) promptToolbar.hidden = true;
    updateChartControl();
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
  }

  questionPane.addEventListener("mouseup", () => updatePromptToolbar());
  questionPane.addEventListener("keyup", () => updatePromptToolbar());

  questionPane.addEventListener(
    "mousedown",
    (e) => {
      if (e.button !== 2) return;
      const promptEl = e.target.closest("#prompt-text");
      if (!promptEl) return;
      const sel = window.getSelection();
      if (sel && !sel.isCollapsed && promptEl.contains(sel.anchorNode)) {
        savedPromptRange = sel.getRangeAt(0).cloneRange();
      }
    },
    true
  );

  questionPane.addEventListener(
    "contextmenu",
    (e) => {
      const promptEl = e.target.closest("#prompt-text");
      if (!promptEl) return;
      if (showPromptHighlightMenu(e.clientX, e.clientY)) {
        e.preventDefault();
        e.stopImmediatePropagation();
      }
    },
    true
  );

  document.addEventListener("selectionchange", () => {
    if (document.getElementById("prompt-text")) updatePromptToolbar();
  });

  if (promptHighlightBtn) {
    promptHighlightBtn.addEventListener("click", async () => {
      promptMenu._range = savedPromptRange;
      await applyPromptHighlight();
    });
  }

  promptMenu.addEventListener("click", (e) => e.stopPropagation());

  promptMenu.querySelector("[data-action=highlight]").addEventListener("click", async (e) => {
    e.stopPropagation();
    closeMenus();
    await applyPromptHighlight();
  });

  async function loadDraft() {
    const res = await api(`/api/writings/active/${qid}`);
    const w = await res.json();
    if (w && w.id) {
      writingId = w.id;
      if (w.content) essay.value = w.content;
      sessionHighlights = loadStoredHighlights();
      refreshPromptHighlights();
      updateWordCount();
      saveStatus.textContent = "Draft loaded - click Start to continue timing";
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
    if (!writingId && data.id) {
      writingId = data.id;
      saveStoredHighlights();
    }
    saveStatus.textContent = finish ? "Saved" : "Saved " + new Date().toLocaleTimeString();
    return data;
  }

  function startSession() {
    if (started) return;
    if (!writingId) clearPracticeHighlights();
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
    clearPracticeHighlights();
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

  essay.addEventListener("select", saveEssaySelection);
  essay.addEventListener("mouseup", saveEssaySelection);

  essay.addEventListener("keyup", () => {
    saveEssaySelection();
    if (started) activeParaIndex = paragraphIndexAtPosition(essay.value, essay.selectionStart);
  });

  essay.addEventListener(
    "mousedown",
    (e) => {
      if (e.button === 2) saveEssaySelection();
    },
    true
  );

  essay.addEventListener(
    "contextmenu",
    (e) => {
      saveEssaySelection();
      if (showEssayWordMenu(e.clientX, e.clientY)) {
        e.preventDefault();
        e.stopPropagation();
      }
    },
    true
  );

  essay.addEventListener("auxclick", (e) => {
    if (e.button !== 2) return;
    saveEssaySelection();
    if (showEssayWordMenu(e.clientX, e.clientY)) {
      e.preventDefault();
    }
  });

  essayMenu.addEventListener("click", (e) => e.stopPropagation());

  document.addEventListener("click", closeMenus);
  document.addEventListener(
    "scroll",
    () => {
      closeMenus();
    },
    true
  );

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
