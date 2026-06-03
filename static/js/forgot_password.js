(function () {
  const form = document.getElementById("forgot-form");
  const msg = document.getElementById("msg");
  const submitBtn = document.getElementById("submit-btn");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    msg.textContent = "";
    msg.className = "msg";
    const email = document.getElementById("email").value.trim();
    submitBtn.disabled = true;
    try {
      const res = await fetch("/api/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await res.json();
      if (!res.ok) {
        msg.textContent = data.error || "Something went wrong";
        msg.className = "msg error";
        return;
      }
      msg.textContent = data.message || "Check your email for a reset code.";
      msg.className = "msg";
      const resetUrl = `/reset-password?email=${encodeURIComponent(email)}`;
      msg.innerHTML = `${data.message || "Check your email."} <a href="${resetUrl}">Enter code →</a>`;
      msg.className = "msg";
    } catch {
      msg.textContent = "Network error";
      msg.className = "msg error";
    } finally {
      submitBtn.disabled = false;
    }
  });
})();
