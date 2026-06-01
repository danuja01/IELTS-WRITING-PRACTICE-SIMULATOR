(function () {
  const listEl = document.getElementById("group-list");

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
    const res = await fetch("/api/writings?grouped=1");
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    const groups = await res.json();
    if (!groups.length) {
      listEl.innerHTML = '<li class="q-meta">No completed writings yet.</li>';
      return;
    }
    listEl.innerHTML = groups
      .map(
        (g) => `
      <li>
        <div>
          <strong>${esc(g.title)}</strong>
          <div class="q-meta">${g.task_type} · ${g.attempt_count} attempt(s) · best ${g.best_words || 0} words · last ${fmtDate(g.last_finished)}</div>
        </div>
        <a class="btn" href="/history/${g.question_id}">View tries</a>
      </li>`
      )
      .join("");
  }

  load();
})();
