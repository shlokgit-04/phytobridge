// Shared auth behavior for the sign-in and register pages.
(function () {
  var form = document.getElementById("authform");
  if (!form) return;
  var msg = document.getElementById("msg");
  var isRegister = form.dataset.mode === "register";
  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    msg.textContent = "";
    var email = form.email.value.trim();
    var password = form.password.value;
    var url = isRegister ? "/api/auth/register" : "/api/auth/login";
    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: email, password: password })
    }).then(function (r) { return r.json().then(function (b) { return { code: r.status, body: b }; }); })
      .then(function (res) {
        if (res.code === 200 && res.body.token) {
          try { localStorage.setItem("pb_token", res.body.token); } catch (e) {}
          window.location.href = "/saved";
        } else {
          msg.textContent = res.body.error || "Something went wrong. Try again.";
        }
      })
      .catch(function () { msg.textContent = "Network error. Try again."; });
  });
})();
