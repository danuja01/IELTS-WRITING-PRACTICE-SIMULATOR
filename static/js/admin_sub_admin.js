(function () {
  const uid = window.SUB_ADMIN_USER_ID;
  const panel = document.getElementById("sub-admin-panel");

  document.getElementById("logout-btn").addEventListener("click", async () => {
    await fetch("/api/logout", { method: "POST" });
    window.location.href = "/login";
  });

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s ?? "";
    return d.innerHTML;
  }

  async function load() {
    const meRes = await fetch("/api/admin/me");
    if (meRes.status === 401) {
      window.location.href = "/login";
      return;
    }
    const me = await meRes.json();
    if (!me.is_admin) {
      panel.innerHTML = '<p class="msg error">Full admin access required.</p>';
      return;
    }

    const res = await fetch(`/api/admin/users/${uid}`);
    const data = await res.json();
    if (!res.ok) {
      panel.innerHTML = `<p class="msg error">${esc(data.error || "Failed to load")}</p>`;
      return;
    }
    const u = data.user;
    if (!u.is_sub_admin) {
      panel.innerHTML = '<p class="msg error">This user is not a sub-admin.</p>';
      return;
    }

    const labels = me.permission_labels || {};
    const perms = u.permissions || {};
    const checks = Object.keys(labels)
      .map(
        (key) => `
        <label class="perm-row">
          <input type="checkbox" name="perm" value="${esc(key)}"${perms[key] ? " checked" : ""}>
          ${esc(labels[key] || key)}
        </label>`
      )
      .join("");

    panel.innerHTML = `
      <h2>${esc(u.username)} <span class="badge">sub-admin</span></h2>
      <p class="q-meta">${esc(u.email || "no email")}</p>
      <form id="perm-form" class="perm-form">
        <h3>Capabilities</h3>
        <p class="q-meta">Sub-admins can always view students, their questions, and attempts. Enable extra actions below.</p>
        ${checks}
        <div class="actions" style="margin-top:1rem">
          <button type="submit">Save permissions</button>
          <button type="button" id="remove-sub-admin" class="secondary">Remove sub-admin role</button>
        </div>
      </form>
      <p class="msg" id="perm-msg"></p>`;

    document.getElementById("perm-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const permissions = {};
      panel.querySelectorAll('input[name="perm"]').forEach((el) => {
        permissions[el.value] = el.checked;
      });
      const r = await fetch(`/api/admin/users/${uid}/sub-admin-permissions`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ permissions }),
      });
      const d = await r.json();
      const msg = document.getElementById("perm-msg");
      msg.textContent = r.ok ? "Permissions saved." : d.error || "Failed";
      msg.className = r.ok ? "msg" : "msg error";
    });

    document.getElementById("remove-sub-admin").addEventListener("click", async () => {
      if (!confirm(`Remove sub-admin role from ${u.username}? They will become a regular student.`)) return;
      const r = await fetch(`/api/admin/users/${uid}/sub-admin`, { method: "DELETE" });
      const d = await r.json();
      if (r.ok) {
        window.location.href = "/admin";
      } else {
        alert(d.error || "Failed");
      }
    });
  }

  load();
})();
