(function () {
  const myListRoot = document.getElementById("my-question-list");
  const allListRoot = document.getElementById("all-question-list");
  const myCountEl = document.getElementById("my-question-count");
  const allCountEl = document.getElementById("all-question-count");
  const historyEl = document.getElementById("history-list");
  const form = document.getElementById("add-question-form");
  const formMsg = document.getElementById("form-msg");
  const taskSelect = document.getElementById("q-task");
  const imageBlock = document.getElementById("task1-image-block");
  const imageInput = document.getElementById("q-image");
  const imagePreview = document.getElementById("q-image-preview");
  const catSelect = document.getElementById("q-category");
  const catList = document.getElementById("category-list");
  const catForm = document.getElementById("add-category-form");

  let categories = [];
  let questions = [];
  const assets = window.HOME_ASSETS || {};
  const iconDots = assets.dots || "/static/assets/three-dots-line.svg";
  const iconBin = assets.bin || "/static/assets/bin.svg";

  function closeAllRowMenus() {
    document.querySelectorAll(".row-menu-dropdown.is-open").forEach((el) => {
      el.classList.remove("is-open", "drop-up");
      el.hidden = true;
      el.style.position = "";
      el.style.left = "";
      el.style.top = "";
      el.style.zIndex = "";
    });
    document.querySelectorAll(".row-menu-btn[aria-expanded='true']").forEach((btn) => {
      btn.setAttribute("aria-expanded", "false");
    });
    document.querySelectorAll(".q-row.menu-open").forEach((row) => row.classList.remove("menu-open"));
  }

  function positionRowMenu(btn, panel) {
    panel.classList.remove("drop-up");
    panel.hidden = false;
    panel.classList.add("is-open");
    panel.style.position = "fixed";
    panel.style.zIndex = "200";
    panel.style.right = "auto";
    panel.style.bottom = "auto";

    const btnRect = btn.getBoundingClientRect();
    const panelRect = panel.getBoundingClientRect();
    const w = panelRect.width;
    const h = panelRect.height;
    const margin = 8;

    let left = btnRect.right - w;
    if (left < margin) left = margin;
    if (left + w > window.innerWidth - margin) left = window.innerWidth - w - margin;

    let top = btnRect.bottom + 4;
    if (top + h > window.innerHeight - margin) {
      top = btnRect.top - h - 4;
      panel.classList.add("drop-up");
    }
    if (top < margin) top = margin;

    panel.style.left = `${left}px`;
    panel.style.top = `${top}px`;
  }

  function openRowMenu(btn, panel) {
    const row = btn.closest(".q-row");
    if (row) row.classList.add("menu-open");
    positionRowMenu(btn, panel);
    btn.setAttribute("aria-expanded", "true");
  }

  function initExclusiveAccordions() {
    const accordions = document.querySelectorAll(".question-accordions .accordion");
    accordions.forEach((panel) => {
      panel.addEventListener("toggle", () => {
        if (!panel.open) return;
        accordions.forEach((other) => {
          if (other !== panel) other.removeAttribute("open");
        });
      });
    });
  }

  document.getElementById("logout-btn").addEventListener("click", async () => {
    await fetch("/api/logout", { method: "POST" });
    window.location.href = "/login";
  });

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
    return `${m}:${String(s).padStart(2, "0")}`;
  }

  function toggleTask1Image() {
    const isTask1 = taskSelect.value === "task1";
    imageBlock.hidden = !isTask1;
    if (!isTask1) {
      imageInput.value = "";
      imagePreview.hidden = true;
    }
  }

  taskSelect.addEventListener("change", toggleTask1Image);
  imageInput.addEventListener("change", () => {
    const file = imageInput.files[0];
    if (!file) {
      imagePreview.hidden = true;
      return;
    }
    imagePreview.src = URL.createObjectURL(file);
    imagePreview.hidden = false;
  });

  async function loadCategories() {
    const res = await fetch("/api/categories");
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    categories = await res.json();
    catSelect.innerHTML =
      '<option value="">Uncategorized</option>' +
      categories.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("");
    catList.innerHTML = categories.length
      ? categories
          .map(
            (c) => `
        <li class="tag-item">
          <span>${esc(c.name)}</span>
          <button type="button" data-del-cat="${c.id}" class="link-btn">×</button>
        </li>`
          )
          .join("")
      : '<li class="q-meta">No categories yet.</li>';
    catList.querySelectorAll("[data-del-cat]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!confirm("Delete category? Questions become uncategorized.")) return;
        await fetch(`/api/categories/${btn.dataset.delCat}`, { method: "DELETE" });
        await loadCategories();
        loadQuestions();
      });
    });
    if (questions.length) renderQuestions();
  }

  function moveCategoryOptions(q) {
    const current = q.category_id == null ? null : Number(q.category_id);
    const opts = categories
      .filter((c) => Number(c.id) !== current)
      .map((c) => `<option value="${c.id}">${esc(c.name)}</option>`)
      .join("");
    const uncat = current != null ? '<option value="0">Uncategorized</option>' : "";
    return opts + uncat;
  }

  function userHasForkOf(sourceId) {
    const root = Number(sourceId);
    return questions.some((q) => q.is_mine && Number(q.copied_from_id) === root);
  }

  function renderQuestionRows(items, showOwner) {
    return items
      .map((q) => {
        const ownerLine = showOwner && !q.is_mine ? ` · by ${esc(q.owner_username || "unknown")}` : "";
        const forkLine = q.is_fork
          ? " · Fork"
          : showOwner && q.fork_count > 0
            ? ` · ${q.fork_count} fork${q.fork_count === 1 ? "" : "s"}`
            : "";
        const copyBtn =
          showOwner && !q.is_mine && !userHasForkOf(q.id)
            ? `<button type="button" class="secondary copy-to-my" data-copy="${q.id}">Copy to My</button>`
            : "";
        const manageActions = q.is_mine
          ? `
                <div class="row-menu-wrap">
                  <button type="button" class="icon-btn row-menu-btn" data-menu="${q.id}" aria-label="More options" aria-expanded="false" aria-haspopup="true">
                    <img src="${iconDots}" alt="" width="18" height="18">
                  </button>
                  <div class="row-menu-dropdown" data-menu-panel="${q.id}" hidden>
                    <label class="row-menu-move">
                      <span>Move to</span>
                      <select data-move="${q.id}" class="move-cat">
                        <option value="">Choose category…</option>
                        ${moveCategoryOptions(q)}
                      </select>
                    </label>
                    <button type="button" class="row-menu-item row-menu-danger" data-del="${q.id}">
                      <img src="${iconBin}" alt="" width="16" height="16">
                      Delete
                    </button>
                  </div>
                </div>`
          : "";
        return `
            <li class="q-row">
              <div class="q-row-main">
                <div class="q-row-title">
                  <span class="task-pill">${esc((q.task_type || "task2").toUpperCase())}</span>
                  <strong>${esc(q.title)}</strong>
                </div>
                <div class="q-meta">${q.has_image ? "Chart · " : ""}${fmtDate(q.created_at)}${ownerLine}${forkLine}</div>
              </div>
              <div class="actions q-row-actions">
                ${copyBtn}
                <a class="btn" href="/practice/${q.id}">Start</a>
                ${manageActions}
              </div>
            </li>`;
      })
      .join("");
  }

  function renderGroupedList(root, items, showOwner) {
    if (!items.length) {
      root.innerHTML = '<p class="q-meta">No questions here yet.</p>';
      return;
    }
    const byCat = {};
    items.forEach((q) => {
      const key = q.category_id || 0;
      if (!byCat[key]) byCat[key] = { name: q.category_name || "Uncategorized", items: [] };
      byCat[key].items.push(q);
    });
    const keys = Object.keys(byCat).sort((a, b) => {
      if (a === "0") return 1;
      if (b === "0") return -1;
      return byCat[a].name.localeCompare(byCat[b].name);
    });
    root.innerHTML = keys
      .map((k) => {
        const group = byCat[k];
        const count = group.items.length;
        return `
      <div class="cat-block">
        <div class="cat-header">
          <div class="cat-header-left">
            <span class="cat-label">Category</span>
            <h3 class="cat-heading">${esc(group.name)}</h3>
          </div>
          <span class="cat-count">${count} question${count === 1 ? "" : "s"}</span>
        </div>
        <ul class="cat-questions">
          ${renderQuestionRows(group.items, showOwner)}
        </ul>
      </div>`;
      })
      .join("");
  }

  function bindQuestionActions(root) {
    root.querySelectorAll(".row-menu-wrap").forEach((wrap) => {
      wrap.addEventListener("click", (e) => e.stopPropagation());
    });
    root.querySelectorAll(".row-menu-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const id = btn.dataset.menu;
        const panel = root.querySelector(`[data-menu-panel="${id}"]`);
        if (!panel) return;
        const open = panel.classList.contains("is-open");
        closeAllRowMenus();
        if (!open) openRowMenu(btn, panel);
      });
    });
    root.querySelectorAll("[data-del]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        closeAllRowMenus();
        if (!confirm("Delete question?")) return;
        await fetch(`/api/questions/${btn.dataset.del}`, { method: "DELETE" });
        loadQuestions();
      });
    });
    root.querySelectorAll(".move-cat").forEach((sel) => {
      sel.addEventListener("change", async () => {
        const qid = sel.dataset.move;
        const val = sel.value;
        if (!val) return;
        closeAllRowMenus();
        const categoryId = val === "0" ? null : parseInt(val, 10);
        await fetch(`/api/questions/${qid}/move`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ category_id: categoryId }),
        });
        loadQuestions();
      });
    });
    root.querySelectorAll("[data-copy]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        btn.disabled = true;
        const res = await fetch(`/api/questions/${btn.dataset.copy}/copy`, { method: "POST" });
        const data = await res.json().catch(() => ({}));
        btn.disabled = false;
        if (!res.ok) {
          alert(data.error || "Could not copy question");
          return;
        }
        await loadQuestions();
        const myAccordion = document.querySelector('.question-accordions .accordion:first-of-type');
        const allAccordion = document.querySelector('.question-accordions .accordion:last-of-type');
        if (myAccordion) myAccordion.setAttribute("open", "");
        if (allAccordion) allAccordion.removeAttribute("open");
      });
    });
  }

  function renderQuestions() {
    const mine = questions.filter((q) => q.is_mine);
    const allCatalog = questions.filter((q) => !q.copied_from_id);
    if (myCountEl) myCountEl.textContent = mine.length ? `${mine.length}` : "0";
    if (allCountEl) allCountEl.textContent = allCatalog.length ? `${allCatalog.length}` : "0";
    renderGroupedList(myListRoot, mine, false);
    renderGroupedList(allListRoot, allCatalog, true);
    bindQuestionActions(myListRoot);
    bindQuestionActions(allListRoot);
  }

  async function loadQuestions(retry = 0) {
    const res = await fetch("/api/questions");
    if (res.status === 503 && retry < 3) {
      await new Promise((r) => setTimeout(r, 500 * (retry + 1)));
      return loadQuestions(retry + 1);
    }
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    if (!res.ok) {
      myListRoot.innerHTML = '<p class="q-meta">Could not load questions. Refresh the page.</p>';
      allListRoot.innerHTML = myListRoot.innerHTML;
      return;
    }
    questions = await res.json();
    renderQuestions();
  }

  async function loadHistory() {
    const res = await fetch("/api/writings");
    const items = await res.json();
    if (!items.length) {
      historyEl.innerHTML = '<li class="q-meta">No finished sessions yet.</li>';
      return;
    }
    historyEl.innerHTML = items
      .map(
        (w) => `
      <li>
        <div>
          <strong>${esc(w.question_title || "Question")}</strong>
          <div class="q-meta">${fmtDate(w.finished_at)} · ${w.final_words || 0} words · ${fmtMs(w.elapsed_ms)}</div>
        </div>
        <a class="btn secondary" href="/history/writing/${w.id}">View</a>
      </li>`
      )
      .join("");
  }

  catForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = document.getElementById("cat-name").value.trim();
    const res = await fetch("/api/categories", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (res.ok) {
      document.getElementById("cat-name").value = "";
      await loadCategories();
    }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    formMsg.textContent = "";
    const title = document.getElementById("q-title").value.trim();
    const task_type = taskSelect.value;
    const prompt = document.getElementById("q-prompt").value.trim();
    const category_id = catSelect.value || null;
    const imageFile = imageInput.files[0];

    let res;
    if (task_type === "task1" && imageFile) {
      const fd = new FormData();
      fd.append("title", title);
      fd.append("task_type", task_type);
      fd.append("prompt", prompt);
      if (category_id) fd.append("category_id", category_id);
      fd.append("image", imageFile);
      res = await fetch("/api/questions", { method: "POST", body: fd });
    } else {
      res = await fetch("/api/questions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, task_type, prompt, category_id: category_id ? parseInt(category_id, 10) : null }),
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
    loadQuestions();
  });

  toggleTask1Image();
  initExclusiveAccordions();
  document.addEventListener("click", () => closeAllRowMenus());
  window.addEventListener("scroll", () => closeAllRowMenus(), true);
  window.addEventListener("resize", () => closeAllRowMenus());
  (async () => {
    await loadCategories();
    await loadQuestions();
    loadHistory();
  })();
})();
