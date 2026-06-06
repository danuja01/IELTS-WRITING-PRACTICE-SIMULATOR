(function () {
  const form = document.getElementById("ai-settings-form");
  const keyInput = document.getElementById("openai-key");
  const statusEl = document.getElementById("key-status");
  const msgEl = document.getElementById("settings-msg");
  const removeBtn = document.getElementById("remove-key-btn");

  function showMsg(text, isError) {
    msgEl.textContent = text;
    msgEl.className = isError ? "msg error" : "msg ok";
  }

  async function loadStatus() {
    const res = await fetch("/api/settings/ai");
    const data = await res.json();
    if (!res.ok) {
      statusEl.textContent = data.error || "Could not load settings";
      return;
    }
    if (data.configured) {
      statusEl.textContent = `Configured (${data.masked_key}) · updated ${data.updated_at || ""}`;
      removeBtn.hidden = false;
    } else {
      statusEl.textContent = "No API key saved yet.";
      removeBtn.hidden = true;
    }
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const key = keyInput.value.trim();
    if (!key) {
      showMsg("Enter your OpenAI API key.", true);
      return;
    }
    const res = await fetch("/api/settings/ai", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ openai_api_key: key }),
    });
    const data = await res.json();
    if (!res.ok) {
      showMsg(data.error || "Save failed", true);
      return;
    }
    keyInput.value = "";
    showMsg("API key saved.", false);
    loadStatus();
  });

  removeBtn.addEventListener("click", async () => {
    if (!confirm("Remove your saved OpenAI API key?")) return;
    const res = await fetch("/api/settings/ai", { method: "DELETE" });
    const data = await res.json();
    if (!res.ok) {
      showMsg(data.error || "Remove failed", true);
      return;
    }
    showMsg("API key removed.", false);
    loadStatus();
  });

  loadStatus();
})();
