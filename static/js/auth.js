(function () {
  const form = document.getElementById("auth-form");
  const msg = document.getElementById("msg");
  const submitBtn = document.getElementById("submit-btn");
  const tabLogin = document.getElementById("tab-login");
  const tabRegister = document.getElementById("tab-register");
  const emailWrap = document.getElementById("email-wrap");
  const emailInput = document.getElementById("email");
  let mode = "login";

  function setMode(m) {
    mode = m;
    tabLogin.classList.toggle("active", m === "login");
    tabRegister.classList.toggle("active", m === "register");
    submitBtn.textContent = m === "login" ? "Login" : "Register";
    emailWrap.hidden = m !== "register";
    emailInput.required = m === "register";
    const forgotWrap = document.getElementById("forgot-link-wrap");
    if (forgotWrap) forgotWrap.hidden = m !== "login";
    msg.textContent = "";
    msg.className = "msg";
  }

  tabLogin.addEventListener("click", () => setMode("login"));
  tabRegister.addEventListener("click", () => setMode("register"));

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    msg.textContent = "";
    const username = document.getElementById("username").value.trim();
    const password = document.getElementById("password").value;
    const url = mode === "login" ? "/api/login" : "/api/register";
    const body = { username, password };
    if (mode === "register") body.email = emailInput.value.trim();
    submitBtn.disabled = true;
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) {
        msg.textContent = data.error || "Something went wrong";
        msg.className = "msg error";
        return;
      }
      window.location.href = data.redirect || "/home";
    } catch {
      msg.textContent = "Network error";
      msg.className = "msg error";
    } finally {
      submitBtn.disabled = false;
    }
  });
})();
