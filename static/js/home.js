(function () {
  const listEl = document.getElementById("question-list");
  const historyEl = document.getElementById("history-list");
  const form = document.getElementById("add-question-form");
  const formMsg = document.getElementById("form-msg");
  const taskSelect = document.getElementById("q-task");
  const imageBlock = document.getElementById("task1-image-block");
  const imageInput = document.getElementById("q-image");
  const imagePreview = document.getElementById("q-image-preview");

  function toggleTask1Image() {
    const isTask1 = taskSelect.value === "task1";
    imageBlock.hidden = !isTask1;
    if (!isTask1) {
      imageInput.value = "";
      imagePreview.hidden = true;
      imagePreview.removeAttribute("src");
    }
  }

  taskSelect.addEventListener("change", toggleTask1Image);
  imageInput.addEventListener("change", () => {
    const file = imageInput.files[0];
    if (!file) {
      imagePreview.hidden = true;
      imagePreview.removeAttribute("src");
      return;
    }
    imagePreview.src = URL.createObjectURL(file);
    imagePreview.hidden = false;
  });
  toggleTask1Image();

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
          <div class="q-meta">${q.task_type.toUpperCase()}${q.has_image ? " · 📊 image" : ""} · ${formatDate(q.created_at)}</div>
        </div>
        <div class="actions">
          <a class="btn" href="/practice/${q.id}">Start</a>
          <button type="button" class="danger" data-id="${q.id}">Delete</button>
        </div>
      </li>`
      )
      .join("");

    listEl.querySelectorAll("button.danger").forEach((btn) => {
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
    const title = document.getElementById("q-title").value.trim();
    const task_type = taskSelect.value;
    const prompt = document.getElementById("q-prompt").value.trim();
    const imageFile = imageInput.files[0];

    let res;
    if (task_type === "task1" && imageFile) {
      const fd = new FormData();
      fd.append("title", title);
      fd.append("task_type", task_type);
      fd.append("prompt", prompt);
      fd.append("image", imageFile);
      res = await fetch("/api/questions", { method: "POST", body: fd });
    } else {
      res = await fetch("/api/questions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, task_type, prompt }),
      });
    }
    const data = await res.json();
    if (!res.ok) {
      formMsg.textContent = data.error || "Failed";
      formMsg.className = "msg error";
      return;
    }
    form.reset();
    toggleTask1Image();
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
