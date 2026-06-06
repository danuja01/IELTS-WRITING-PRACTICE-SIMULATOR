(function () {
  const wid = window.HISTORY_WRITING_ID;
  const adminView = window.ADMIN_VIEW === true;
  const backUid = window.ADMIN_USER_ID;
  const root = document.getElementById("detail-root");
  const backLink = document.getElementById("back-link");
  const pageTitle = document.getElementById("page-title");
  const evalModal = document.getElementById("eval-modal");
  const evalModalBody = document.getElementById("eval-modal-body");
  const evalModalClose = document.getElementById("eval-modal-close");
  const evalRegenerate = document.getElementById("eval-regenerate");

  let cachedWriting = null;
  let cachedEvaluation = null;
  let evaluating = false;

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s ?? "";
    return d.innerHTML;
  }

  function fmtMs(ms) {
    if (ms == null) return "-";
    const sec = Math.floor(ms / 1000);
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}m ${s}s`;
  }

  function pct(part, total) {
    if (!total) return "0";
    return ((part / total) * 100).toFixed(1);
  }

  function task1ChartHtml(w) {
    if (!w.question_has_image || !w.question_image_url) return "";
    return `
      <div class="history-chart-box">
        <img src="${esc(w.question_image_url)}" alt="Task 1 chart" class="history-chart-img">
      </div>`;
  }

  function criterionLabel(taskType, key) {
    if (key === "task") {
      return (taskType || "task2") === "task1" ? "Task Achievement" : "Task Response";
    }
    const labels = {
      coherence_cohesion: "Coherence & Cohesion",
      lexical_resource: "Lexical Resource",
      grammatical_range: "Grammatical Range",
    };
    return labels[key] || key;
  }

  function renderRewrite(text) {
    if (!text) return "";
    const cleaned = String(text)
      .replace(/<br\s*\/?>/gi, "\n\n")
      .replace(/<\/?p>/gi, "\n\n");
    const parts = cleaned.split(/(<<[^>]+>>)/g);
    return parts
      .map((part) => {
        if (part.startsWith("<<") && part.endsWith(">>")) {
          return `<strong class="eval-highlight">${esc(part.slice(2, -2))}</strong>`;
        }
        return esc(part);
      })
      .join("");
  }

  function renderMistake(m) {
    const wrong = m.wrong_text || m.excerpt || "";
    const corrected = m.corrected_text || m.suggestion || "";
    const correctionLine =
      wrong || corrected
        ? `<p class="eval-correction-line">
            ${wrong ? `<span class="eval-wrong">❌ ${esc(wrong)}</span>` : ""}
            ${corrected ? `<span class="eval-correct">✅ ${esc(corrected)}</span>` : ""}
          </p>`
        : "";

    return `
      <li class="eval-mistake">
        <span class="eval-mistake-cat">${esc(m.category || "Issue")}</span>
        ${correctionLine}
        <p class="eval-issue"><strong>Issue:</strong> <span class="eval-issue-text">${esc(m.issue || "")}</span></p>
        ${m.suggestion && m.corrected_text ? `<p class="eval-suggestion"><strong>Tip:</strong> ${esc(m.suggestion)}</p>` : ""}
      </li>`;
  }

  function renderEvaluation(evalData, taskType) {
    if (!evalData) {
      return '<p class="q-meta">No evaluation yet.</p>';
    }
    const scores = evalData.criterion_scores || {};
    const scoreRows = Object.entries(scores)
      .map(
        ([k, v]) => `
        <div class="stat-row">
          <span>${esc(criterionLabel(taskType, k))}</span>
          <strong>${Number(v).toFixed(1)}</strong>
        </div>`
      )
      .join("");

    const mistakes = (evalData.mistakes || []).map(renderMistake).join("");
    const mistakeCount = (evalData.mistakes || []).length;

    const improvements = (evalData.areas_for_improvement || [])
      .map((a) => `<li>${esc(a)}</li>`)
      .join("");

    return `
      <div class="eval-band">
        <span class="eval-band-label">Predicted band</span>
        <span class="eval-band-score">${Number(evalData.band_score).toFixed(1)}</span>
      </div>
      <div class="stat-grid eval-criteria">${scoreRows}</div>
      <section class="eval-section">
        <h4>Overall feedback</h4>
        <p class="eval-text">${esc(evalData.overall_feedback)}</p>
      </section>
      <section class="eval-section">
        <h4>All mistakes found <span class="eval-count">(${mistakeCount})</span></h4>
        <ul class="eval-mistake-list">${mistakes || '<li class="q-meta">No mistakes listed.</li>'}</ul>
      </section>
      <section class="eval-section">
        <h4>Focus areas</h4>
        <ul class="eval-improve-list">${improvements}</ul>
      </section>
      <section class="eval-section">
        <h4>Band 7.5+ ${(taskType || "task2") === "task1" ? "model report" : "rewrite"}</h4>
        <p class="q-meta eval-rewrite-legend"><span class="eval-highlight-inline">Green bold</span> = improved words &amp; phrases${(taskType || "task2") === "task1" ? " · Task 1: intro, overview, 2 body paragraphs (no conclusion)" : ""}</p>
        <div class="essay-readonly eval-rewrite">${renderRewrite(evalData.rewritten_essay)}</div>
      </section>
      <p class="q-meta eval-meta">Generated ${esc(evalData.updated_at || evalData.created_at || "")}${evalData.model ? ` · ${esc(evalData.model)}` : ""}</p>`;
  }

  function showModalProgress(percent, message) {
    evalModalBody.innerHTML = `
      <div class="eval-progress-wrap">
        <p class="eval-progress-label">${esc(message)}</p>
        <div class="eval-progress-track" role="progressbar" aria-valuenow="${percent}" aria-valuemin="0" aria-valuemax="100">
          <div class="eval-progress-bar" style="width:${Math.min(100, Math.max(0, percent))}%"></div>
        </div>
        <p class="eval-progress-pct">${Math.round(percent)}%</p>
      </div>`;
    evalRegenerate.hidden = true;
    evalModal.classList.add("show");
  }

  function showModalLoading(message) {
    showModalProgress(0, message);
  }

  function showModalError(message, settingsUrl) {
    const settingsLink = settingsUrl
      ? ` <a href="${esc(settingsUrl)}">Configure API key</a>`
      : "";
    evalModalBody.innerHTML = `<p class="msg error">${esc(message)}${settingsLink}</p>`;
    evalRegenerate.hidden = true;
  }

  function openEvaluationModal() {
    if (!cachedWriting) return;
    const taskType = cachedWriting.question_task_type || "task2";
    if (cachedEvaluation) {
      evalModalBody.innerHTML = renderEvaluation(cachedEvaluation, taskType);
      evalRegenerate.hidden = adminView;
    } else {
      showModalLoading("Loading saved evaluation…");
      loadEvaluation(true);
      return;
    }
    evalModal.classList.add("show");
    evalRegenerate.hidden = adminView;
  }

  async function loadEvaluation(openModal) {
    const res = await fetch(`/api/writings/${wid}/evaluation`);
    const data = await res.json();
    if (!res.ok) {
      if (openModal) showModalError(data.error || "Could not load evaluation");
      return;
    }
    cachedEvaluation = data && data.band_score != null ? data : null;
    updateEvaluateButton();
    if (openModal) {
      if (cachedEvaluation) {
        evalModalBody.innerHTML = renderEvaluation(
          cachedEvaluation,
          cachedWriting?.question_task_type || "task2"
        );
        evalRegenerate.hidden = adminView;
      } else {
        await runEvaluation(false);
      }
    }
  }

  async function consumeEvaluateStream(res) {
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let finalResult = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split("\n\n");
      buffer = chunks.pop() || "";

      for (const chunk of chunks) {
        const line = chunk.trim();
        if (!line.startsWith("data:")) continue;
        const raw = line.slice(5).trim();
        if (!raw) continue;
        let data;
        try {
          data = JSON.parse(raw);
        } catch {
          continue;
        }

        if (data.type === "progress") {
          showModalProgress(data.percent || 0, data.message || "Evaluating…");
        } else if (data.type === "error") {
          throw new Error(data.error || "Evaluation failed");
        } else if (data.type === "complete") {
          showModalProgress(100, data.message || "Complete");
          finalResult = data.result;
        }
      }
    }

    return finalResult;
  }

  async function runEvaluation(isRegenerate) {
    if (evaluating || adminView) return;
    evaluating = true;
    showModalProgress(0, isRegenerate ? "Regenerating evaluation…" : "Starting evaluation…");
    try {
      const res = await fetch(`/api/writings/${wid}/evaluate?stream=1`, { method: "POST" });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        showModalError(data.error || "Evaluation failed", data.settings_url);
        return;
      }

      const data = await consumeEvaluateStream(res);
      if (!data) {
        showModalError("Evaluation failed: no result returned");
        return;
      }

      cachedEvaluation = data;
      updateEvaluateButton();
      evalModalBody.innerHTML = renderEvaluation(
        cachedEvaluation,
        cachedWriting?.question_task_type || "task2"
      );
      evalRegenerate.hidden = false;
    } catch (err) {
      showModalError(err.message || "Evaluation failed");
    } finally {
      evaluating = false;
    }
  }

  function updateEvaluateButton() {
    const btn = document.getElementById("evaluate-btn");
    if (!btn) return;
    if (cachedEvaluation) {
      btn.textContent = "View AI Evaluation";
      btn.classList.add("secondary");
    } else {
      btn.textContent = "Evaluate with AI";
      btn.classList.remove("secondary");
    }
  }

  function bindModalEvents() {
    evalModalClose.addEventListener("click", () => {
      evalModal.classList.remove("show");
    });
    evalModal.addEventListener("click", (e) => {
      if (e.target === evalModal) {
        evalModal.classList.remove("show");
      }
    });
    evalRegenerate.addEventListener("click", () => runEvaluation(true));
  }

  async function load() {
    const res = await fetch(`/api/writings/${wid}`);
    const w = await res.json();
    if (!res.ok) {
      root.innerHTML = `<p class="msg error">${esc(w.error)}</p>`;
      return;
    }
    cachedWriting = w;

    if (adminView && pageTitle) {
      pageTitle.textContent = w.username ? `Attempt - ${w.username}` : "Attempt detail";
    }
    if (adminView && backLink) {
      const uid = backUid || w.user_id;
      if (uid) backLink.href = `/admin/users/${uid}`;
    }

    const stats = w.paragraph_stats || [];
    const totalParaTime = stats.reduce((s, p) => s + (p.time_ms || 0), 0) || w.elapsed_ms || 1;

    let paraTable = "";
    if (stats.length) {
      paraTable = `
        <table class="para-table">
          <thead><tr><th>#</th><th>Time</th><th>%</th><th>Words</th><th>Preview</th></tr></thead>
          <tbody>
            ${stats
              .map(
                (p, i) => `
              <tr>
                <td>${i + 1}</td>
                <td>${fmtMs(p.time_ms)}</td>
                <td>${pct(p.time_ms, totalParaTime)}%</td>
                <td>${p.words ?? "-"}</td>
                <td class="preview-cell">${esc((p.text || p.preview || "").slice(0, 80))}</td>
              </tr>`
              )
              .join("")}
          </tbody>
        </table>`;
    } else {
      paraTable = '<p class="q-meta">No paragraph timing recorded for this attempt.</p>';
    }

    const userLine = adminView && w.username
      ? `<div class="stat-row"><span>Student</span><strong>${esc(w.username)}</strong></div>`
      : "";

    const examMins = w.question_task_type === "task1" ? 20 : 40;

    const evalSection = adminView
      ? `<section class="panel" id="eval-panel" hidden>
          <h2>AI Evaluation</h2>
          <p class="q-meta" id="eval-status">Loading…</p>
          <button type="button" class="secondary" id="view-eval-btn" hidden>View AI Evaluation</button>
        </section>`
      : `<section class="panel" id="eval-panel">
          <h2>AI Evaluation</h2>
          <p class="q-meta" id="eval-status">Get IELTS-style feedback, band score, and a Band 7.5+ rewrite.</p>
          <button type="button" id="evaluate-btn">Evaluate with AI</button>
        </section>`;

    root.innerHTML = `
      <section class="panel">
        <h2>${esc(w.question_title || "Writing")}</h2>
        <p class="q-meta">${esc((w.question_task_type || "task2").toUpperCase())} · ${examMins} min exam</p>
        ${task1ChartHtml(w)}
        <div class="stat-grid">
          ${userLine}
          <div class="stat-row"><span>Finished</span><strong>${esc(w.finished_at)}</strong></div>
          <div class="stat-row"><span>Total time</span><strong>${fmtMs(w.elapsed_ms)}</strong></div>
          <div class="stat-row"><span>Words</span><strong>${w.final_words || 0}</strong></div>
          <div class="stat-row"><span>At exam limit</span><strong>${w.words_at_40min != null ? w.words_at_40min + " words" : "-"}</strong></div>
        </div>
      </section>
      <section class="panel">
        <h2>Time per paragraph</h2>
        ${paraTable}
      </section>
      ${evalSection}
      <section class="panel">
        <h2>Answer</h2>
        <pre class="essay-readonly">${esc(w.content)}</pre>
      </section>`;

    if (!adminView) {
      document.getElementById("evaluate-btn").addEventListener("click", () => {
        if (cachedEvaluation) {
          openEvaluationModal();
        } else {
          runEvaluation(false);
        }
      });
    } else {
      const viewBtn = document.getElementById("view-eval-btn");
      const evalPanel = document.getElementById("eval-panel");
      evalPanel.hidden = false;
      viewBtn.addEventListener("click", openEvaluationModal);
    }

    bindModalEvents();
    await loadEvaluation(false);

    if (adminView && cachedEvaluation) {
      const evalPanel = document.getElementById("eval-panel");
      const statusEl = document.getElementById("eval-status");
      const viewBtn = document.getElementById("view-eval-btn");
      evalPanel.hidden = false;
      statusEl.textContent = `Band ${Number(cachedEvaluation.band_score).toFixed(1)} · saved evaluation available`;
      viewBtn.hidden = false;
    }
  }

  load();
})();
