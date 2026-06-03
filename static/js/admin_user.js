(function () {
  const uid = window.ADMIN_USER_ID;
  const panel = document.getElementById("user-panel");
  const cardsEl = document.getElementById("question-cards");

  if (!cardsEl || uid == null) {
    if (panel) panel.innerHTML = '<p class="msg error">Page failed to load.</p>';
    return;
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

  function safeImageUrl(url) {
    if (!url || typeof url !== "string") return "";
    return /^\/api\/questions\/\d+\/image$/.test(url) ? url : "";
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

  function renderQuestionCards(questions) {
    const list = questions || [];
    if (!list.length) {
      cardsEl.innerHTML = '<p class="q-meta">No questions yet.</p>';
      return;
    }

    cardsEl.innerHTML = list
      .map((q) => {
        const attempts = q.attempts || [];
        const imgUrl = safeImageUrl(q.image_url);
        const img =
          q.has_image && imgUrl
            ? `<div class="history-chart-box admin-chart-box"><img src="${imgUrl}" alt="Chart" class="history-chart-img"></div>`
            : "";
        const prompt = q.prompt || "";
        const preview = esc(prompt.slice(0, 220)) + (prompt.length > 220 ? "…" : "");
        const forkCount = q.fork_count || 0;
        const forksHtml =
          forkCount > 0
            ? `<div class="admin-forks" data-forks-qid="${q.id}">
                <button type="button" class="link-btn admin-forks-toggle">${forkCount} fork${forkCount === 1 ? "" : "s"}</button>
                <ul class="admin-fork-list" hidden></ul>
              </div>`
            : q.is_fork
              ? '<p class="q-meta">Fork of a shared question</p>'
              : "";
        const attemptsHtml = attempts.length
          ? `<ul class="admin-attempt-list">
              ${attempts
                .map(
                  (a, i) => `
                <li>
                  <span>Attempt ${attempts.length - i} · ${fmtDate(a.finished_at)} · ${a.final_words || 0} words · ${fmtMs(a.elapsed_ms)}</span>
                  <a class="btn secondary" href="/admin/writing/${a.id}?user_id=${uid}">View</a>
                </li>`
                )
                .join("")}
            </ul>`
          : '<p class="admin-attempts-empty">No finished attempts yet.</p>';

        return `
        <article class="admin-q-card">
          <header class="admin-q-head">
            <div>
              <span class="task-badge">${esc(q.task_type || "task2")}</span>
              <strong>${esc(q.title || "Untitled")}</strong>
              <span class="q-meta"> · ${q.attempt_count != null ? q.attempt_count : attempts.length} attempt(s)</span>
            </div>
            <a class="btn" href="/admin/questions/${q.id}/edit">Edit</a>
          </header>
          ${img}
          <p class="admin-q-preview">${preview}</p>
          ${forksHtml}
          <section class="admin-attempts-section">
            <h4 class="admin-q-sub">Attempts</h4>
            <div class="admin-attempts-body">
              ${attemptsHtml}
            </div>
          </section>
        </article>`;
      })
      .join("");

    cardsEl.querySelectorAll(".admin-forks-toggle").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const wrap = btn.closest(".admin-forks");
        const list = wrap.querySelector(".admin-fork-list");
        const qid = wrap.dataset.forksQid;
        if (!list.hidden && list.innerHTML) {
          list.hidden = true;
          return;
        }
        const res = await fetch(`/api/admin/questions/${qid}/forks`);
        const data = await res.json();
        if (!res.ok) {
          list.innerHTML = `<li class="q-meta">${esc(data.error)}</li>`;
        } else if (!data.forks.length) {
          list.innerHTML = '<li class="q-meta">No forks</li>';
        } else {
          list.innerHTML = data.forks
            .map(
              (f) =>
                `<li>${esc(f.username)} · ${fmtDate(f.created_at)} · question #${f.id}</li>`
            )
            .join("");
        }
        list.hidden = false;
      });
    });
  }

  async function load() {
    try {
      const res = await fetch(`/api/admin/users/${uid}`);
      let data;
      try {
        data = await res.json();
      } catch {
        cardsEl.innerHTML = '<p class="msg error">Invalid server response.</p>';
        panel.innerHTML = '<p class="msg error">Invalid server response.</p>';
        return;
      }

      if (!res.ok) {
        const err = esc(data.error || "Failed to load user");
        panel.innerHTML = `<p class="msg error">${err}</p>`;
        cardsEl.innerHTML = `<p class="msg error">${err}</p>`;
        return;
      }

      const u = data.user;
      panel.innerHTML = `
      <h2>${esc(u.username)}</h2>
      <form id="user-edit" class="inline-form">
        <label>Email <input type="email" id="u-email" value="${esc(u.email || "")}"></label>
        <label>Username <input type="text" id="u-name" value="${esc(u.username)}"></label>
        <button type="submit">Save user</button>
      </form>
      <div class="actions" style="margin-top:0.75rem">
        <button type="button" id="reset-pw" class="secondary">Set temp password</button>
        <span id="temp-pw" class="q-meta"></span>
      </div>
      <p class="msg" id="user-msg"></p>`;

      document.getElementById("user-edit").addEventListener("submit", async (e) => {
        e.preventDefault();
        const r = await fetch(`/api/admin/users/${uid}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: document.getElementById("u-email").value.trim(),
            username: document.getElementById("u-name").value.trim(),
          }),
        });
        const d = await r.json();
        document.getElementById("user-msg").textContent = r.ok ? "Saved." : d.error || "Failed";
      });

      document.getElementById("reset-pw").addEventListener("click", async () => {
        const custom = prompt("Temp password (leave empty for random):", "");
        const body = custom ? { password: custom } : {};
        const r = await fetch(`/api/admin/users/${uid}/reset-password`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const d = await r.json();
        if (r.ok) {
          document.getElementById("temp-pw").textContent = `Temp password: ${d.temp_password}`;
        } else {
          alert(d.error || "Failed");
        }
      });

      renderQuestionCards(data.questions);
    } catch (err) {
      console.error(err);
      cardsEl.innerHTML = `<p class="msg error">Failed to load questions: ${esc(err.message)}</p>`;
    }
  }

  load();
})();
