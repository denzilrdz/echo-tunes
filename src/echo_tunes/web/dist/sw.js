// echo-tunes service worker: makes the web player installable and keeps its shell available
// when the network blips. Only the pages "/" and "/login", files under /static/ and /assets/
// and the manifest are ever cached: never the API or /metrics, even when opened as a page
// (they hold your history and must not outlive signing out), nor audio or images.
// Pages and /static/ are network first (an update shows up on the next load); files under
// /assets/ have a content hash in their name, so a cached copy is always right.

const CACHE = "echo-tunes-shell-v4";
const PAGES = ["/", "/login"];
const SHELL = ["/static/icon.svg", "/static/boot.js", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((c) => c.addAll(SHELL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

const save = (key, resp) => {
  if (resp.ok && !resp.redirected && resp.type === "basic") {
    const copy = resp.clone();
    caches.open(CACHE).then((c) => c.put(key, copy));
  }
  return resp;
};

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/assets/")) {
    event.respondWith(caches.match(req).then((hit) => hit || fetch(req).then((r) => save(req, r))));
    return;
  }
  const page = req.mode === "navigate" && PAGES.includes(url.pathname);
  const file = url.pathname.startsWith("/static/") || url.pathname === "/manifest.webmanifest";
  if (!page && !file) return; // /api, /metrics, anything else: always live, never stored
  const key = page ? url.pathname : req;
  event.respondWith(
    fetch(req)
      .then((resp) => save(key, resp))
      .catch(() => caches.match(key).then((hit) => hit || Response.error())),
  );
});
