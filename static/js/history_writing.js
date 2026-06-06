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

    const mistakes = (evalData.mistakes || [])
      .map(
        (m) => `
        <li class="eval-mistake">
          <span class="eval-mistake-cat">${esc(m.category)}</span>
          <blockquote class="eval-excerpt">"${esc(m.excerpt)}"</blockquote>
          <p><strong>Issue:</strong> ${esc(m.issue)}</p>
          <p><strong>Suggestion:</strong> ${esc(m.suggestion)}</p>
        </li>`
      )
      .join("");

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
        <h4>Mistakes & areas to improve</h4>
        <ul class="eval-mistake-list">${mistakes}</ul>
      </section>
      <section class="eval-section">
        <h4>Focus areas</h4>
        <ul class="eval-improve-list">${improvements}</ul>
      </section>
      <section class="eval-section">
        <h4>Band 7.5+ rewrite</h4>
        <pre class="essay-readonly eval-rewrite">${esc(evalData.rewritten_essay)}</pre>
      </section>
      <p class="q-meta eval-meta">Generated ${esc(evalData.updated_at || evalData.created_at || "")}${evalData.model ? ` · ${esc(evalData.model)}` : ""}</p>`;
  }

  function showModalLoading(message) {
    evalModalBody.innerHTML = `<p class="q-meta eval-loading">${esc(message)}</p>`;
    evalRegenerate.hidden = true;
    evalModal.classList.add("show");
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

  async function runEvaluation(isRegenerate) {
    if (evaluating || adminView) return;
    evaluating = true;
    showModalLoading(isRegenerate ? "Regenerating evaluation…" : "Evaluating with AI…");
    try {
      const res = await fetch(`/api/writings/${wid}/evaluate`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) {
        showModalError(data.error || "Evaluation failed", data.settings_url);
        return;
      }
      cachedEvaluation = data;
      updateEvaluateButton();
      evalModalBody.innerHTML = renderEvaluation(
        cachedEvaluation,
        cachedWriting?.question_task_type || "task2"
      );
      evalRegenerate.hidden = false;
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
