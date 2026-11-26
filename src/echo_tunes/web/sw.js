// echo-tunes service worker: makes the dashboard installable as an app and keeps its shell
// (page, styles, scripts, icons) available when the network blips. Always network first, so
// an update shows up on the next load; the API, audio and YouTube images are never cached.
"use strict";
const CACHE = "echo-tunes-shell-v1";
const SHELL = ["/", "/static/app.css", "/static/app.js", "/static/player.js", "/static/icon.svg", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;
  const shell = req.mode === "navigate" || url.pathname.startsWith("/static/") || url.pathname === "/manifest.webmanifest";
  if (!shell) return; // /api, /metrics: always live
  event.respondWith(
    fetch(req)
      .then((resp) => {
        if (resp.ok) {
          const copy = resp.clone();
          caches.open(CACHE).then((c) => c.put(req.mode === "navigate" ? "/" : req, copy));
        }
        return resp;
      })
      .catch(() => caches.match(req.mode === "navigate" ? "/" : req).then((hit) => hit || Response.error())),
  );
});
