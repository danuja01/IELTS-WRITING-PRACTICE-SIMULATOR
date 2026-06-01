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

  let question = null;
  let writingId = null;
  let started = false;
  let startTime = null;
  let tickInterval = null;
  let saveInterval = null;
  let at40Recorded = false;
  let snapshot40 = { ms: null, words: 0, caret: 0 };

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
    questionPane.innerHTML = `
      <span class="task-badge">${escapeHtml(question.task_type)} · ${mins} min exam time</span>
      <h2 style="margin:0 0 0.75rem;font-size:1.05rem">${escapeHtml(question.title)}</h2>
      <pre>${escapeHtml(question.prompt)}</pre>`;
  }

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
    essay.disabled = false;
    essay.focus();
    startBtn.disabled = true;
    finishBtn.disabled = false;
    saveStatus.textContent = "Writing…";

    tickInterval = setInterval(updateTimer, 250);
    saveInterval = setInterval(() => saveDraft(false), 15000);
    updateTimer();
    updateWordCount();
  }

  function showResults(elapsed) {
    const words = countWords(essay.value);
    const pos = snapshot40.caret || 0;
    const preview = essay.value.slice(Math.max(0, pos - 40), pos + 40);
    const rows = [
      ["Total time", formatDuration(elapsed)],
      ["Final word count", String(words)],
    ];
    if (snapshot40.ms != null) {
      rows.push(
        [`Time at ${examLimitMs / 60000} min mark`, formatDuration(snapshot40.ms)],
        [`Words at ${examLimitMs / 60000} min`, String(snapshot40.words)],
        [`Cursor at ${examLimitMs / 60000} min`, `character ${pos}`]
      );
    } else {
      rows.push(["Exam time mark", `Not reached (finished under ${examLimitMs / 60000} min)`]);
    }
    resultStats.innerHTML = rows
      .map(
        ([k, v], i) =>
          `<div class="stat-row${i === 2 || k.includes("40 min") ? " highlight" : ""}">
            <span>${k}</span><strong>${escapeHtml(String(v))}</strong>
          </div>`
      )
      .join("");
    if (snapshot40.ms != null && preview.trim()) {
      resultStats.innerHTML += `<p style="font-size:0.8rem;color:var(--muted);margin:0">Near cursor at 40:00:<br><em>${escapeHtml(preview)}…</em></p>`;
    }
    resultModal.classList.add("show");
  }

  async function finishSession() {
    if (!started) return;
    clearInterval(tickInterval);
    clearInterval(saveInterval);
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

  essay.addEventListener("input", updateWordCount);
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
