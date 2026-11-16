// Header account chip: shows the signed-in email or a Sign-in link.
(function () {
  var el = document.getElementById("acct");
  if (!el) return;
  var token = null;
  try { token = localStorage.getItem("pb_token"); } catch (e) {}
  if (!token) return;
  fetch("/api/auth/me", { headers: { Authorization: "Bearer " + token } })
    .then(function (r) { return r.json().then(function (b) { return { code: r.status, body: b }; }); })
    .then(function (res) {
      if (res.code === 200) {
        var email = res.body.user && res.body.user.email ? res.body.user.email : "";
        el.innerHTML = '<span class="whoami">' + email.replace(/</g, "&lt;") +
          '</span> <a href="#" id="signout">Sign out</a>';
        document.getElementById("signout").addEventListener("click", function (ev) {
          ev.preventDefault();
          try { localStorage.removeItem("pb_token"); } catch (e) {}
          window.location.href = "/";
        });
      } else {
        try { localStorage.removeItem("pb_token"); } catch (e) {}
      }
    })
    .catch(function () {});
})();
