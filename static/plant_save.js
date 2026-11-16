// Save / unsave the plant the reader is looking at.
(function () {
  var row = document.querySelector(".plant-save");
  if (!row) return;
  var btn = document.getElementById("savebtn");
  var msg = document.getElementById("savemsg");
  var fnf = row.getAttribute("data-fnf");
  var token = null;
  try { token = localStorage.getItem("pb_token"); } catch (e) {}
  if (!token) {
    btn.textContent = "Sign in to save";
    btn.addEventListener("click", function () { window.location.href = "/login"; });
    return;
  }
  fetch("/api/saved", {
    headers: { Authorization: "Bearer " + token }
  }).then(function (r) { return r.json(); }).then(function (body) {
    var items = body.items || [];
    var mine = items.some(function (i) { return String(i.fnfnum) === String(fnf); });
    btn.textContent = mine ? "Remove from saved" : "Save plant";
    btn.dataset.saved = mine ? "1" : "0";
  }).catch(function () {});
  btn.addEventListener("click", function () {
    var saved = btn.dataset.saved === "1";
    var opts = saved
      ? { method: "DELETE", headers: { Authorization: "Bearer " + token } }
      : { method: "POST",
          headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
          body: JSON.stringify({ fnfnum: Number(fnf) }) };
    fetch(saved ? "/api/saved/" + fnf : "/api/saved", opts).then(function (r) {
      if (r.ok || r.status === 200) {
        btn.dataset.saved = saved ? "0" : "1";
        btn.textContent = saved ? "Save plant" : "Remove from saved";
        msg.textContent = saved ? "Removed." : "Saved. Find it under My saved.";
      } else {
        msg.textContent = "Could not update. Try again.";
      }
    }).catch(function () { msg.textContent = "Network error."; });
  });
})();
