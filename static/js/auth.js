(function () {
  const form = document.getElementById("auth-form");
  const msg = document.getElementById("msg");
  const submitBtn = document.getElementById("submit-btn");
  const tabLogin = document.getElementById("tab-login");
  const tabRegister = document.getElementById("tab-register");
  let mode = "login";

  function setMode(m) {
    mode = m;
    tabLogin.classList.toggle("active", m === "login");
    tabRegister.classList.toggle("active", m === "register");
    submitBtn.textContent = m === "login" ? "Login" : "Register";
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
    submitBtn.disabled = true;
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        msg.textContent = data.error || "Something went wrong";
        msg.className = "msg error";
        return;
      }
      window.location.href = "/home";
    } catch {
      msg.textContent = "Network error";
      msg.className = "msg error";
    } finally {
      submitBtn.disabled = false;
    }
  });
})();
