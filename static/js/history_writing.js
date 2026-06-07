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

  function taskCriterionLabel(taskType) {
    return (taskType || "task2") === "task1" ? "Task Achievement" : "Task Response";
  }

  function criterionSections(taskType) {
    return [
      { key: "task", label: taskCriterionLabel(taskType), field: "task_comment" },
      { key: "coherence_cohesion", label: "Coherence and Cohesion", field: "coherence_comment" },
      { key: "lexical_resource", label: "Lexical Resource", field: "lexical_comment" },
      { key: "grammatical_range", label: "Grammatical Range and Accuracy", field: "grammar_comment" },
    ];
  }

  function sentenceStatusLabel(status) {
    if (status === "accurately_hit") return "Accurately Hit Key Points";
    if (status === "slightly_off") return "Slightly Off Key Points";
    return "Off Key Points";
  }

  function sentenceStatusClass(status) {
    if (status === "accurately_hit") return "hit";
    if (status === "slightly_off") return "slight";
    return "off";
  }

  function renderCorrections(corrections, title) {
    if (!corrections || !corrections.length) return "";
    const items = corrections
      .map((c) => {
        const orig = c.original || c.wrong_text || "";
        const fixed = c.corrected || c.corrected_text || "";
        const note = c.note ? ` <span class="eval-correction-note">(${esc(c.note)})</span>` : "";
        return `<li class="eval-correction-item"><span class="eval-correction-orig">${esc(orig)}</span> → <span class="eval-correction-fix">${esc(fixed)}</span>${note}</li>`;
      })
      .join("");
    const heading = title ? `<h5 class="eval-subsection-title">${esc(title)}</h5>` : "";
    return `${heading}<ul class="eval-correction-list">${items}</ul>`;
  }

  function renderSentenceComments(comments) {
    if (!comments || !comments.length) return "";
    return comments
      .map((sc) => {
        const cls = sentenceStatusClass(sc.status);
        return `
        <div class="eval-sentence-comment eval-sentence-${cls}">
          <div class="eval-sentence-head">
            <span class="eval-sentence-label eval-sentence-label-${cls}">${esc(sentenceStatusLabel(sc.status))}</span>
            <em class="eval-sentence-text">${esc(sc.sentence)}</em>
          </div>
          <p class="eval-sentence-detail">${esc(sc.comment)}</p>
        </div>`;
      })
      .join("");
  }

  function renderCriterionSection(label, score, comment) {
    if (!comment) return "";
    const summary = comment.summary || "";
    const corrections = renderCorrections(comment.corrections, comment.corrections_title);
    const sentences = renderSentenceComments(comment.sentence_comments);
    return `
      <section class="eval-criterion-block">
        <div class="eval-criterion-head">
          <h4 class="eval-criterion-title">${esc(label)}</h4>
          ${score != null ? `<span class="eval-criterion-band">${Number(score).toFixed(1)}</span>` : ""}
        </div>
        <p class="eval-criterion-summary">${esc(summary)}</p>
        ${sentences}
        ${corrections}
      </section>`;
  }

  function renderLegacyMistake(m) {
    const wrong = m.wrong_text || m.excerpt || "";
    const corrected = m.corrected_text || "";
    return `
      <li class="eval-mistake">
        <span class="eval-mistake-cat">${esc(m.category || "Issue")}</span>
        <p class="eval-correction-line">
          ${wrong ? `<span class="eval-wrong">❌ ${esc(wrong)}</span>` : ""}
          ${corrected ? `<span class="eval-correct">✅ ${esc(corrected)}</span>` : ""}
        </p>
        <p class="eval-issue"><strong>Issue:</strong> ${esc(m.issue || "")}</p>
      </li>`;
  }

  function renderEvaluationV2(evalData, taskType) {
    const scores = evalData.criterion_scores || {};
    const sections = criterionSections(taskType)
      .map((s) => renderCriterionSection(s.label, scores[s.key], evalData[s.field]))
      .join("");

    const topCorrections =
      (taskType || "task2") === "task2" && evalData.corrections && evalData.corrections.length
        ? `<section class="eval-section"><h4>Corrections</h4>${renderCorrections(evalData.corrections)}</section>`
        : "";

    const composition = evalData.optimized_composition || evalData.rewritten_essay || "";

    return `
      <div class="eval-band-box">
        <span class="eval-band-box-label">Band Score</span>
        <span class="eval-band-box-score">${Number(evalData.band_score).toFixed(1)}</span>
      </div>
      ${topCorrections}
      <div class="eval-criteria-stack">${sections}</div>
      <section class="eval-section eval-overall-review">
        <h4>Overall Review</h4>
        <p class="eval-review-text">${esc(evalData.overall_review || "")}</p>
      </section>
      <section class="eval-section">
        <h4>Optimized Composition</h4>
        <div class="essay-readonly eval-optimized">${esc(composition)}</div>
      </section>
      <p class="q-meta eval-meta">Generated ${esc(evalData.updated_at || evalData.created_at || "")}${evalData.model ? ` · ${esc(evalData.model)}` : ""}${evalData.question_subtype ? ` · ${esc(evalData.question_subtype)}` : ""}</p>`;
  }

  function renderEvaluationV1(evalData, taskType) {
    const scores = evalData.criterion_scores || {};
    const scoreRows = Object.entries(scores)
      .map(([k, v]) => {
        const labels = {
          task: taskCriterionLabel(taskType),
          coherence_cohesion: "Coherence & Cohesion",
          lexical_resource: "Lexical Resource",
          grammatical_range: "Grammatical Range",
        };
        return `<div class="stat-row"><span>${esc(labels[k] || k)}</span><strong>${Number(v).toFixed(1)}</strong></div>`;
      })
      .join("");
    const mistakes = (evalData.mistakes || []).map(renderLegacyMistake).join("");
    const feedback = evalData.overall_feedback || evalData.overall_review || "";
    const feedbackHtml = Array.isArray(feedback)
      ? `<ul class="eval-feedback-list">${feedback.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>`
      : `<p class="eval-text">${esc(feedback)}</p>`;

    return `
      <div class="eval-band-box">
        <span class="eval-band-box-label">Band Score</span>
        <span class="eval-band-box-score">${Number(evalData.band_score).toFixed(1)}</span>
      </div>
      <div class="stat-grid eval-criteria">${scoreRows}</div>
      <section class="eval-section"><h4>Overall feedback</h4>${feedbackHtml}</section>
      <section class="eval-section"><h4>Mistakes</h4><ul class="eval-mistake-list">${mistakes || '<li class="q-meta">None listed.</li>'}</ul></section>
      <section class="eval-section"><h4>Optimized Composition</h4><div class="essay-readonly eval-optimized">${esc(evalData.rewritten_essay || "")}</div></section>`;
  }

  function renderEvaluation(evalData, taskType) {
    if (!evalData) return '<p class="q-meta">No evaluation yet.</p>';
    if (evalData.format_version === 2 || evalData.task_comment) {
      return renderEvaluationV2(evalData, taskType);
    }
    return renderEvaluationV1(evalData, taskType);
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

  function showModalError(message, settingsUrl) {
    const settingsLink = settingsUrl ? ` <a href="${esc(settingsUrl)}">Configure API key</a>` : "";
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
      showModalProgress(0, "Loading saved evaluation…");
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
        evalModalBody.innerHTML = renderEvaluation(cachedEvaluation, cachedWriting?.question_task_type || "task2");
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
        try {
          const data = JSON.parse(line.slice(5).trim());
          if (data.type === "progress") showModalProgress(data.percent || 0, data.message || "Evaluating…");
          else if (data.type === "error") throw new Error(data.error || "Evaluation failed");
          else if (data.type === "complete") finalResult = data.result;
        } catch (e) {
          if (e.message && e.message !== "Evaluation failed") continue;
          throw e;
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
      evalModalBody.innerHTML = renderEvaluation(cachedEvaluation, cachedWriting?.question_task_type || "task2");
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
    btn.textContent = cachedEvaluation ? "View AI Evaluation" : "Evaluate with AI";
    btn.classList.toggle("secondary", !!cachedEvaluation);
  }

  function bindModalEvents() {
    evalModalClose.addEventListener("click", () => evalModal.classList.remove("show"));
    evalModal.addEventListener("click", (e) => {
      if (e.target === evalModal) evalModal.classList.remove("show");
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
    if (adminView && pageTitle) pageTitle.textContent = w.username ? `Attempt - ${w.username}` : "Attempt detail";
    if (adminView && backLink) {
      const uid = backUid || w.user_id;
      if (uid) backLink.href = `/admin/users/${uid}`;
    }

    const stats = w.paragraph_stats || [];
    const totalParaTime = stats.reduce((s, p) => s + (p.time_ms || 0), 0) || w.elapsed_ms || 1;
    let paraTable = stats.length
      ? `<table class="para-table"><thead><tr><th>#</th><th>Time</th><th>%</th><th>Words</th><th>Preview</th></tr></thead><tbody>${stats.map((p, i) => `<tr><td>${i + 1}</td><td>${fmtMs(p.time_ms)}</td><td>${pct(p.time_ms, totalParaTime)}%</td><td>${p.words ?? "-"}</td><td class="preview-cell">${esc((p.text || p.preview || "").slice(0, 80))}</td></tr>`).join("")}</tbody></table>`
      : '<p class="q-meta">No paragraph timing recorded.</p>';

    const userLine = adminView && w.username ? `<div class="stat-row"><span>Student</span><strong>${esc(w.username)}</strong></div>` : "";
    const examMins = w.question_task_type === "task1" ? 20 : 40;
    const evalSection = adminView
      ? `<section class="panel" id="eval-panel" hidden><h2>AI Evaluation</h2><p class="q-meta" id="eval-status">Loading…</p><button type="button" class="secondary" id="view-eval-btn" hidden>View AI Evaluation</button></section>`
      : `<section class="panel" id="eval-panel"><h2>AI Evaluation</h2><p class="q-meta" id="eval-status">Get IELTS-style band score, per-criterion feedback, and an optimized composition.</p><button type="button" id="evaluate-btn">Evaluate with AI</button></section>`;

    root.innerHTML = `
      <section class="panel"><h2>${esc(w.question_title || "Writing")}</h2><p class="q-meta">${esc((w.question_task_type || "task2").toUpperCase())} · ${examMins} min exam</p>${task1ChartHtml(w)}
        <div class="stat-grid">${userLine}<div class="stat-row"><span>Finished</span><strong>${esc(w.finished_at)}</strong></div><div class="stat-row"><span>Total time</span><strong>${fmtMs(w.elapsed_ms)}</strong></div><div class="stat-row"><span>Words</span><strong>${w.final_words || 0}</strong></div></div>
      </section>
      <section class="panel"><h2>Time per paragraph</h2>${paraTable}</section>
      ${evalSection}
      <section class="panel"><h2>Answer</h2><pre class="essay-readonly">${esc(w.content)}</pre></section>`;

    if (!adminView) {
      document.getElementById("evaluate-btn").addEventListener("click", () => {
        cachedEvaluation ? openEvaluationModal() : runEvaluation(false);
      });
    } else {
      document.getElementById("view-eval-btn").addEventListener("click", openEvaluationModal);
    }
    bindModalEvents();
    await loadEvaluation(false);
    if (adminView && cachedEvaluation) {
      document.getElementById("eval-panel").hidden = false;
      document.getElementById("eval-status").textContent = `Band ${Number(cachedEvaluation.band_score).toFixed(1)} · saved evaluation`;
      document.getElementById("view-eval-btn").hidden = false;
    }
  }

  load();
})();
