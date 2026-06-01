(function () {
  const form = document.getElementById("setup-form");
  const msg = document.getElementById("msg");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    msg.textContent = "";
    const res = await fetch("/api/setup-admin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: document.getElementById("username").value.trim(),
        email: document.getElementById("email").value.trim(),
        password: document.getElementById("password").value,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      msg.textContent = data.error || "Failed";
      msg.className = "msg error";
      return;
    }
    window.location.href = data.redirect || "/admin";
  });
})();
