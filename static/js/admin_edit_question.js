(function () {
  const qid = window.ADMIN_QUESTION_ID;
  const form = document.getElementById("edit-form");
  const taskSelect = document.getElementById("q-task");
  const imageBlock = document.getElementById("task1-image-block");
  const catSelect = document.getElementById("q-category");
  const msg = document.getElementById("form-msg");

  taskSelect.addEventListener("change", () => {
    imageBlock.hidden = taskSelect.value !== "task1";
  });

  async function load() {
    const res = await fetch(`/api/admin/questions/${qid}`);
    const data = await res.json();
    if (!res.ok) {
      msg.textContent = data.error || "Not found";
      return;
    }
    const q = data.question;
    document.getElementById("q-title").value = q.title;
    document.getElementById("q-prompt").value = q.prompt;
    taskSelect.value = q.task_type;
    imageBlock.hidden = q.task_type !== "task1";
    catSelect.innerHTML =
      '<option value="">Uncategorized</option>' +
      data.categories
        .map(
          (c) =>
            `<option value="${c.id}"${c.id === q.category_id ? " selected" : ""}>${c.name}</option>`
        )
        .join("");
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData();
    fd.append("title", document.getElementById("q-title").value.trim());
    fd.append("prompt", document.getElementById("q-prompt").value.trim());
    fd.append("task_type", taskSelect.value);
    fd.append("category_id", catSelect.value || "");
    const img = document.getElementById("q-image").files[0];
    if (img) fd.append("image", img);
    const res = await fetch(`/api/admin/questions/${qid}`, { method: "PUT", body: fd });
    const data = await res.json();
    msg.textContent = res.ok ? "Saved." : data.error || "Failed";
    msg.className = res.ok ? "msg" : "msg error";
  });

  load();
})();
