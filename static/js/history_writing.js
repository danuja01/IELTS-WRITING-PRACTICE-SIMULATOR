(function () {
  const wid = window.HISTORY_WRITING_ID;
  const root = document.getElementById("detail-root");

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s ?? "";
    return d.innerHTML;
  }

  function fmtMs(ms) {
    if (ms == null) return "—";
    const sec = Math.floor(ms / 1000);
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}m ${s}s`;
  }

  function pct(part, total) {
    if (!total) return "0";
    return ((part / total) * 100).toFixed(1);
  }

  async function load() {
    const res = await fetch(`/api/writings/${wid}`);
    const w = await res.json();
    if (!res.ok) {
      root.innerHTML = `<p class="msg error">${esc(w.error)}</p>`;
      return;
    }
    const stats = w.paragraph_stats || [];
    const totalParaTime = stats.reduce((s, p) => s + (p.time_ms || 0), 0) || w.elapsed_ms || 1;

    let paraTable = "";
    if (stats.length) {
      paraTable = `
        <table class="para-table">
          <thead><tr><th>#</th><th>Time</th><th>%</th><th>Words</th><th>Preview</th></tr></thead>
          <tbody>
            ${stats
              .map(
                (p, i) => `
              <tr>
                <td>${i + 1}</td>
                <td>${fmtMs(p.time_ms)}</td>
                <td>${pct(p.time_ms, totalParaTime)}%</td>
                <td>${p.words ?? "—"}</td>
                <td class="preview-cell">${esc((p.text || p.preview || "").slice(0, 80))}</td>
              </tr>`
              )
              .join("")}
          </tbody>
        </table>`;
    } else {
      paraTable = '<p class="q-meta">No paragraph timing recorded for this attempt.</p>';
    }

    root.innerHTML = `
      <section class="panel">
        <h2>${esc(w.question_title || "Writing")}</h2>
        <div class="stat-grid">
          <div class="stat-row"><span>Finished</span><strong>${esc(w.finished_at)}</strong></div>
          <div class="stat-row"><span>Total time</span><strong>${fmtMs(w.elapsed_ms)}</strong></div>
          <div class="stat-row"><span>Words</span><strong>${w.final_words || 0}</strong></div>
          <div class="stat-row"><span>At exam limit</span><strong>${w.words_at_40min != null ? w.words_at_40min + " words" : "—"}</strong></div>
        </div>
      </section>
      <section class="panel">
        <h2>Time per paragraph</h2>
        ${paraTable}
      </section>
      <section class="panel">
        <h2>Your answer</h2>
        <pre class="essay-readonly">${esc(w.content)}</pre>
      </section>`;
  }

  load();
})();
