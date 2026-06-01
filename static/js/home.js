(function () {
  const listEl = document.getElementById("question-list");
  const historyEl = document.getElementById("history-list");
  const form = document.getElementById("add-question-form");
  const formMsg = document.getElementById("form-msg");

  document.getElementById("logout-btn").addEventListener("click", async () => {
    await fetch("/api/logout", { method: "POST" });
    window.location.href = "/login";
  });

  async function loadQuestions() {
    const res = await fetch("/api/questions");
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    const items = await res.json();
    if (!items.length) {
      listEl.innerHTML = '<li class="q-meta">No questions yet — add one above.</li>';
      return;
    }
    listEl.innerHTML = items
      .map(
        (q) => `
      <li>
        <div>
          <strong>${escapeHtml(q.title)}</strong>
          <div class="q-meta">${q.task_type.toUpperCase()} · ${formatDate(q.created_at)}</div>
        </div>
        <div class="actions">
          <a class="btn" href="/practice/${q.id}">Start</a>
          <button type="button" class="danger" data-id="${q.id}">Delete</button>
        </div>
      </li>`
      )
      .join("");

    listEl.querySelectorAll(".danger-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!confirm("Delete this question?")) return;
        await fetch(`/api/questions/${btn.dataset.id}`, { method: "DELETE" });
        loadQuestions();
      });
    });
  }

  async function loadHistory() {
    const res = await fetch("/api/writings");
    const items = await res.json();
    if (!items.length) {
      historyEl.innerHTML = '<li class="q-meta">No finished sessions yet.</li>';
      return;
    }
    historyEl.innerHTML = items
      .map((w) => {
        const total = formatMs(w.elapsed_ms);
        const at40 = w.at_40min_ms != null ? formatMs(w.at_40min_ms) : "—";
        const w40 = w.words_at_40min != null ? w.words_at_40min : "—";
        const title = w.question_title || "Question";
        return `<li>
          <div>
            <strong>${escapeHtml(title)}</strong>
            <div class="q-meta">${formatDate(w.finished_at)} · ${w.final_words || 0} words · ${total} total · at 40m: ${w40} words (${at40})</div>
          </div>
        </li>`;
      })
      .join("");
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    formMsg.textContent = "";
    const body = {
      title: document.getElementById("q-title").value.trim(),
      task_type: document.getElementById("q-task").value,
      prompt: document.getElementById("q-prompt").value.trim(),
    };
    const res = await fetch("/api/questions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      formMsg.textContent = data.error || "Failed";
      formMsg.className = "msg error";
      return;
    }
    form.reset();
    formMsg.textContent = "Saved.";
    formMsg.className = "msg";
    loadQuestions();
  });

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function formatDate(iso) {
    if (!iso) return "";
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  }

  function formatMs(ms) {
    if (ms == null) return "—";
    const sec = Math.floor(ms / 1000);
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}:${String(s).padStart(2, "0")}`;
  }

  loadQuestions();
  loadHistory();
})();
