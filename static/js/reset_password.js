(function () {
  const form = document.getElementById("reset-form");
  const msg = document.getElementById("msg");
  const submitBtn = document.getElementById("submit-btn");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    msg.textContent = "";
    msg.className = "msg";
    const email = document.getElementById("email").value.trim();
    const code = document.getElementById("code").value.trim();
    const password = document.getElementById("password").value;
    const confirm = document.getElementById("confirm").value;
    submitBtn.disabled = true;
    try {
      const res = await fetch("/api/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, code, password, confirm }),
      });
      const data = await res.json();
      if (!res.ok) {
        msg.textContent = data.error || "Something went wrong";
        msg.className = "msg error";
        return;
      }
      msg.textContent = data.message || "Password updated.";
      msg.className = "msg";
      if (data.redirect) {
        setTimeout(() => {
          window.location.href = data.redirect;
        }, 1200);
      }
    } catch {
      msg.textContent = "Network error";
      msg.className = "msg error";
    } finally {
      submitBtn.disabled = false;
    }
  });
})();
