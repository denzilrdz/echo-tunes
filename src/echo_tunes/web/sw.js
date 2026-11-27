// echo-tunes service worker: makes the dashboard installable as an app and keeps its shell
// (page, styles, scripts, icons) available when the network blips. Always network first, so
// an update shows up on the next load. Only the pages "/" and "/login", files under /static/
// and the manifest are ever cached: never the API or /metrics, even when opened as a page
// (they hold your history and must not outlive signing out), nor audio or images.
"use strict";
const CACHE = "echo-tunes-shell-v3";
const PAGES = ["/", "/login"];
const SHELL = ["/static/app.css", "/static/app.js", "/static/player.js", "/static/login.js", "/static/icon.svg", "/manifest.webmanifest"];

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
  const page = req.mode === "navigate" && PAGES.includes(url.pathname);
  const file = url.pathname.startsWith("/static/") || url.pathname === "/manifest.webmanifest";
  if (!page && !file) return; // /api, /metrics, anything else: always live, never stored
  const key = page ? url.pathname : req;
  event.respondWith(
    fetch(req)
      .then((resp) => {
        if (resp.ok && !resp.redirected && resp.type === "basic") {
          const copy = resp.clone();
          caches.open(CACHE).then((c) => c.put(key, copy));
        }
        return resp;
      })
      .catch(() => caches.match(key).then((hit) => hit || Response.error())),
  );
});
