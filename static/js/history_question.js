(function () {
  const qid = window.HISTORY_QUESTION_ID;
  const viewUid = window.VIEW_USER_ID;
  const listEl = document.getElementById("attempt-list");
  const headerEl = document.getElementById("question-header");
  const titleEl = document.getElementById("page-title");

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s ?? "";
    return d.innerHTML;
  }

  function fmtDate(iso) {
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso || "";
    }
  }

  function fmtMs(ms) {
    if (ms == null) return "-";
    const sec = Math.floor(ms / 1000);
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}m ${s}s`;
  }

  async function load() {
    const url = viewUid
      ? `/api/admin/users/${viewUid}/writings/by-question/${qid}`
      : `/api/writings/by-question/${qid}`;
    const res = await fetch(url);
    const data = await res.json();
    if (!res.ok) {
      listEl.innerHTML = `<li class="msg error">${esc(data.error)}</li>`;
      return;
    }
    titleEl.textContent = data.question.title || "Attempts";
    const q = data.question;
    if (headerEl) {
      const chartBlock =
        q && q.has_image && q.image_url
          ? `<div class="history-chart-box"><img src="${esc(q.image_url)}" alt="Task 1 chart" class="history-chart-img"></div>`
          : "";
      headerEl.innerHTML = `
        <h2>${esc(q.title || "Question")}</h2>
        <p class="q-meta">${esc((q.task_type || "task2").toUpperCase())}</p>
        ${chartBlock}`;
    }
    if (!data.attempts.length) {
      listEl.innerHTML = '<li class="q-meta">No finished attempts for this question.</li>';
      return;
    }
    const base = viewUid ? "/admin/writing" : "/history/writing";
    listEl.innerHTML = data.attempts
      .map(
        (w, i) => `
      <li>
        <div>
          <strong>Attempt ${data.attempts.length - i}</strong>
          <div class="q-meta">${fmtDate(w.finished_at)} · ${w.final_words || 0} words · ${fmtMs(w.elapsed_ms)} total</div>
        </div>
        <a class="btn" href="${base}/${w.id}">Details</a>
      </li>`
      )
      .join("");
  }

  load();
})();
