(function () {
  const listEl = document.getElementById("user-list");

  document.getElementById("logout-btn").addEventListener("click", async () => {
    await fetch("/api/logout", { method: "POST" });
    window.location.href = "/login";
  });

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  async function load() {
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
          <strong>${esc(u.username)}</strong>${u.is_admin ? " <span class=\"badge\">admin</span>" : ""}
          <div class="q-meta">${esc(u.email || "no email")}${u.must_change_password ? " · must change password" : ""}</div>
        </div>
        <div class="actions">
          ${u.is_admin ? "" : `<a class="btn" href="/admin/users/${u.id}">View</a>`}
        </div>
      </li>`
      )
      .join("");
  }

  load();
})();
