// The saved-plants page: lists the signed-in user's saved plants and notes.
(function () {
  var list = document.getElementById("savedlist");
  var msg = document.getElementById("savedmsg");
  var hint = document.getElementById("signin-hint");
  var token = null;
  try { token = localStorage.getItem("pb_token"); } catch (e) {}

  function signedOut(text) {
    hint.hidden = false;
    list.hidden = true;
    msg.hidden = true;
    hint.innerHTML = '<a href="/login">Sign in</a> to see plants you have saved.';
    if (text) hint.innerHTML = text + ' <a href="/login">Sign in</a> to see your saved plants.';
  }

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function render(items) {
    hint.hidden = true;
    list.hidden = false;
    msg.hidden = items.length ? true : false;
    if (!items.length) {
      msg.textContent = "Nothing saved yet. Open any plant page and press Save to keep it here.";
      return;
    }
    list.innerHTML = items.map(function (it) {
      var name = it.taxon ? ('<a href="/plant/' + it.fnfnum + '">' + esc(it.taxon) + "</a>") : "(plant no longer in the dataset)";
      return '<article class="savedcard"><h3>' + name + "</h3>" +
        '<p class="meta">Saved ' + esc(it.saved_at) + "</p>" +
        '<textarea class="notefield" data-fnf="' + it.fnfnum + '" maxlength="2000" placeholder="Your note (only you see this)">' + esc(it.note) + "</textarea>" +
        '<div class="saverow"><button class="notebtn" data-fnf="' + it.fnfnum + '">Save note</button>' +
        '<button class="removebtn" data-fnf="' + it.fnfnum + '">Remove</button></div></article>';
    }).join("");
  }

  function load() {
    if (!token) { signedOut(""); return; }
    fetch("/api/saved", { headers: { Authorization: "Bearer " + token } })
      .then(function (r) { return r.json().then(function (b) { return { code: r.status, body: b }; }); })
      .then(function (res) {
        if (res.code === 200) { render(res.body.items || []); }
        else { signedOut("Your session expired."); }
      })
      .catch(function () { msg.hidden = false; msg.textContent = "Network error loading saved plants."; });
  }

  list.addEventListener("click", function (ev) {
    var t = ev.target;
    var fnf = t.getAttribute && t.getAttribute("data-fnf");
    if (!fnf || !token) return;
    if (t.classList.contains("notebtn")) {
      var field = list.querySelector('textarea[data-fnf="' + fnf + '"]');
      fetch("/api/saved/" + fnf + "/note", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
        body: JSON.stringify({ note: field.value })
      }).then(function (r) {
        t.textContent = r.ok ? "Note saved" : "Could not save";
        setTimeout(function () { t.textContent = "Save note"; }, 2000);
      });
    } else if (t.classList.contains("removebtn")) {
      fetch("/api/saved/" + fnf, { method: "DELETE", headers: { Authorization: "Bearer " + token } })
        .then(load);
    }
  });

  load();
})();
