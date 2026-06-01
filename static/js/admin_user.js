(function () {
  const uid = window.ADMIN_USER_ID;
  const panel = document.getElementById("user-panel");
  const cardsEl = document.getElementById("question-cards");

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
    if (ms == null) return "—";
    const sec = Math.floor(ms / 1000);
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}m ${s}s`;
  }

  async function load() {
    const res = await fetch(`/api/admin/users/${uid}`);
    const data = await res.json();
    if (!res.ok) {
      panel.innerHTML = `<p class="msg error">${esc(data.error)}</p>`;
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

    if (!data.questions.length) {
      cardsEl.innerHTML = '<p class="q-meta">No questions yet.</p>';
      return;
    }

    cardsEl.innerHTML = data.questions
      .map((q) => {
        const img = q.has_image
          ? `<figure class="task1-figure"><img src="${esc(q.image_url)}" alt="Chart" class="task1-chart admin-q-thumb"></figure>`
          : "";
        const preview = esc((q.prompt || "").slice(0, 220)) + ((q.prompt || "").length > 220 ? "…" : "");
        const attemptsHtml = q.attempts.length
          ? `<ul class="admin-attempt-list">
              ${q.attempts
                .map(
                  (a, i) => `
                <li>
                  <span>Attempt ${q.attempts.length - i} · ${fmtDate(a.finished_at)} · ${a.final_words || 0} words · ${fmtMs(a.elapsed_ms)}</span>
                  <a class="btn secondary" href="/admin/writing/${a.id}?user_id=${uid}">View</a>
                </li>`
                )
                .join("")}
            </ul>`
          : '<p class="q-meta">No finished attempts yet.</p>';

        return `
        <article class="admin-q-card">
          <header class="admin-q-head">
            <div>
              <span class="task-badge">${esc(q.task_type)}</span>
              <strong>${esc(q.title)}</strong>
              <span class="q-meta"> · ${q.attempt_count} attempt(s)</span>
            </div>
            <a class="btn" href="/admin/questions/${q.id}/edit">Edit</a>
          </header>
          ${img}
          <p class="admin-q-preview">${preview}</p>
          <h4 class="admin-q-sub">Attempts</h4>
          ${attemptsHtml}
        </article>`;
      })
      .join("");
  }

  load();
})();
