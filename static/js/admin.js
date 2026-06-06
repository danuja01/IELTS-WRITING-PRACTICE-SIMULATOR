(function () {
  const listEl = document.getElementById("user-list");
  const subAdminSection = document.getElementById("sub-admin-section");
  const createForm = document.getElementById("create-sub-admin-form");

  document.getElementById("logout-btn").addEventListener("click", async () => {
    await fetch("/api/logout", { method: "POST" });
    window.location.href = "/login";
  });

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function roleBadge(u) {
    if (u.is_admin) return ' <span class="badge">admin</span>';
    if (u.is_sub_admin) return ' <span class="badge badge-sub">sub-admin</span>';
    return "";
  }

  function userActions(u, isFullAdmin) {
    if (u.is_admin) return "";
    if (u.is_sub_admin) {
      return isFullAdmin
        ? `<a class="btn secondary" href="/admin/sub-admins/${u.id}">Manage</a>`
        : "";
    }
    return `<a class="btn" href="/admin/users/${u.id}">View</a>`;
  }

  function renderCreateForm(labels) {
    if (!createForm) return;
    const checks = Object.entries(labels)
      .map(
        ([key, label]) => `
        <label class="perm-row">
          <input type="checkbox" name="perm" value="${esc(key)}">
          ${esc(label)}
        </label>`
      )
      .join("");
    createForm.innerHTML = `
      <h3>Add sub-admin</h3>
      <p class="q-meta">Sub-admins can view students, questions, and attempts. Grant optional capabilities below.</p>
      <div class="inline-form">
        <label>Username <input type="text" id="sa-username" required minlength="2"></label>
        <label>Email <input type="email" id="sa-email" required></label>
        <label>Password <input type="password" id="sa-password" required minlength="4"></label>
      </div>
      <div class="perm-form">${checks}</div>
      <div class="actions" style="margin-top:0.75rem">
        <button type="submit">Create sub-admin</button>
      </div>
      <p class="msg" id="create-sa-msg"></p>`;

    createForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const permissions = {};
      createForm.querySelectorAll('input[name="perm"]').forEach((el) => {
        permissions[el.value] = el.checked;
      });
      const res = await fetch("/api/admin/sub-admins", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: document.getElementById("sa-username").value.trim(),
          email: document.getElementById("sa-email").value.trim(),
          password: document.getElementById("sa-password").value,
          permissions,
        }),
      });
      const data = await res.json();
      const msg = document.getElementById("create-sa-msg");
      msg.textContent = res.ok ? "Sub-admin created." : data.error || "Failed";
      msg.className = res.ok ? "msg" : "msg error";
      if (res.ok) {
        createForm.reset();
        loadUsers(true);
      }
    });
  }

  async function loadUsers(isFullAdmin) {
    const res = await fetch("/api/admin/users");
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    const users = await res.json();
    listEl.innerHTML = users
      .map(
        (u) => `
      <li>
        <div>
          <strong>${esc(u.username)}</strong>${roleBadge(u)}
          <div class="q-meta">${esc(u.email || "no email")}${u.must_change_password ? " · must change password" : ""}</div>
        </div>
        <div class="actions">
          ${userActions(u, isFullAdmin)}
        </div>
      </li>`
      )
      .join("");
  }

  async function load() {
    const meRes = await fetch("/api/admin/me");
    if (meRes.status === 401) {
      window.location.href = "/login";
      return;
    }
    const me = await meRes.json();
    const isFullAdmin = !!me.is_admin;
    if (subAdminSection) {
      subAdminSection.hidden = !isFullAdmin;
    }
    if (isFullAdmin && createForm) {
      renderCreateForm(me.permission_labels || {});
    }
    await loadUsers(isFullAdmin);
  }

  load();
})();
