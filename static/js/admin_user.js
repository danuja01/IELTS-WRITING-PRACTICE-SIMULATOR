(function () {
  const uid = window.ADMIN_USER_ID;
  const panel = document.getElementById("user-panel");
  const groupsEl = document.getElementById("writing-groups");
  const qList = document.getElementById("question-list");

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

    if (!data.writing_groups.length) {
      groupsEl.innerHTML = '<li class="q-meta">No finished writings yet.</li>';
    } else {
      groupsEl.innerHTML = data.writing_groups
        .map(
          (g) => `
        <li>
          <div>
            <strong>${esc(g.title)}</strong>
            <div class="q-meta">${g.attempt_count} attempt(s) · last ${fmtDate(g.last_finished)}</div>
          </div>
          <a class="btn secondary" href="/admin/users/${uid}/history/${g.question_id}">View attempts</a>
        </li>`
        )
        .join("");
    }

    qList.innerHTML = data.questions.length
      ? data.questions
          .map(
            (q) => `
        <li>
          <div><strong>${esc(q.title)}</strong> <span class="q-meta">${q.task_type}</span></div>
          <a class="btn" href="/admin/questions/${q.id}/edit">Edit</a>
        </li>`
          )
          .join("")
      : '<li class="q-meta">No questions.</li>';
  }

  load();
})();
