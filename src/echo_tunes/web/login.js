// Sign-in page: sends the password once; the server answers with a long-lived session cookie.
"use strict";
const form = document.getElementById("login");
const error = document.getElementById("login-error");
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const button = form.querySelector("button");
  button.disabled = true;
  error.hidden = true;
  try {
    const r = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ password: form.elements.password.value }),
      credentials: "same-origin",
    });
    if (r.ok) { location.replace("/#play"); return; }
    const data = await r.json().catch(() => ({}));
    error.textContent = typeof data.detail === "string" ? data.detail : `Couldn't sign in (${r.status}).`;
  } catch {
    error.textContent = "Can't reach echo-tunes.";
  }
  error.hidden = false;
  button.disabled = false;
  form.elements.password.select();
});
if ("serviceWorker" in navigator && window.isSecureContext) navigator.serviceWorker.register("/sw.js").catch(() => {});
