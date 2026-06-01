(function () {
  const form = document.getElementById("change-form");
  const msg = document.getElementById("msg");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    msg.textContent = "";
    const res = await fetch("/api/change-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        password: document.getElementById("password").value,
        confirm: document.getElementById("confirm").value,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      msg.textContent = data.error || "Failed";
      msg.className = "msg error";
      return;
    }
    window.location.href = data.redirect || "/home";
  });
})();
