// echo-tunes player: search and browse YouTube Music, play in this browser or line songs up on
// an Echo. Uses the helpers from app.js ($, el, api, thumb, mmss, DEMO, state). Text is only
// ever inserted with textContent.
"use strict";
(() => {

const P = {
  info: { actions: false, experimental_skip: false, signed_in: false, echos: [] },
  target: "browser",
  kind: "song",
  query: "",
  view: null, // what #p-view shows: {type: "home"} | {type: "search"} | {type: "list", ...}
  queue: [], // browser queue: tracks {video_id, title, artist, duration, image?}
  index: -1,
  source: "",
  demoTimer: null,
};
const audio = $("#p-audio");

// ---------- API ----------
async function post(path, body) {
  if (DEMO) return DEMO(path, body);
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body || {}),
    cache: "no-store",
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Error ${r.status}`);
  return data;
}
async function get(path) {
  if (DEMO) return DEMO(path);
  const r = await fetch(path, { headers: { Accept: "application/json" }, cache: "no-store" });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Error ${r.status}`);
  return data;
}
let toastTimer;
function toast(text, bad = false) {
  const t = $("#toast");
  t.textContent = text;
  t.classList.toggle("bad", bad);
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 4000);
}
const art = (item) => item.image || ((item.video_id || item.kind === "song") ? thumb(item.video_id || item.id) : "");
const toTrack = (item) => ({ video_id: item.id, title: item.title, artist: item.subtitle, duration: item.duration, image: item.image });

// ---------- target (this browser or an Echo) ----------
function renderTargets() {
  const sel = $("#p-target");
  const keep = P.target;
  sel.replaceChildren(
    el("option", { value: "browser", text: "This browser" }),
    ...P.info.echos.map((e) => el("option", { value: e.id, text: `${echoName(e)}${e.playing ? " · playing" : ""}` })));
  sel.value = [...sel.options].some((o) => o.value === keep) ? keep : "browser";
  P.target = sel.value;
  $("#p-lock").hidden = P.info.actions;
  $("#p-echo-note").hidden = P.target === "browser" || !P.info.actions;
  renderBar();
}
$("#p-target").addEventListener("change", (e) => {
  P.target = e.target.value;
  $("#p-echo-note").hidden = P.target === "browser" || !P.info.actions;
  renderBar();
});
const onEcho = () => P.target !== "browser";
const currentEcho = () => P.info.echos.find((e) => e.id === P.target);

// ---------- views ----------
function setView(view) {
  P.view = view;
  $("#p-kinds").hidden = view.type !== "search";
  renderView();
}
async function renderView() {
  const box = $("#p-view");
  const v = P.view;
  box.replaceChildren(el("p", { class: "muted", text: "Loading…" }));
  try {
    if (v.type === "home") return renderHome(box);
    if (v.type === "search") return renderSearch(box);
    if (v.type === "list") return renderList(box, v);
    if (v.type === "mood") return renderMood(box, v);
  } catch (err) {
    box.replaceChildren(el("div", { class: "card empty" }, el("p", { text: err.message || "Something went wrong." }),
      el("button", { class: "ghost", type: "button", text: "Try again" })));
    box.querySelector("button").addEventListener("click", renderView);
  }
}

async function renderHome(box) {
  const [home, explore, lib] = await Promise.all([
    get("/api/browse/home").catch(() => ({ sections: [] })),
    get("/api/browse/explore").catch(() => ({ charts: [], artists: [], moods: [] })),
    P.info.signed_in ? get("/api/browse/library").catch(() => ({ items: [] })) : { items: [] },
  ]);
  const rows = [];
  if (lib.items.length) rows.push(row("Your library", lib.items));
  for (const s of home.sections) rows.push(row(s.title, s.items));
  if (explore.charts.length) rows.push(row("Trending", explore.charts));
  if (explore.artists.length) rows.push(row("Top artists", explore.artists));
  for (const m of explore.moods) {
    rows.push(el("section", { class: "p-row" }, el("h2", { text: m.title }),
      el("div", { class: "p-chips" }, ...m.categories.map((c) => {
        const b = el("button", { type: "button", class: "chip-btn", text: c.title });
        b.addEventListener("click", () => setView({ type: "mood", title: c.title, params: c.params }));
        return b;
      }))));
  }
  box.replaceChildren(...(rows.length ? rows : [el("div", { class: "card empty" }, el("p", { text: "YouTube Music didn't answer. Try searching." }))]));
}

function row(title, items) {
  return el("section", { class: "p-row" }, el("h2", { text: title }), el("div", { class: "p-shelf" }, ...items.map(card)));
}
function card(item) {
  const c = el("button", { type: "button", class: `p-card k-${item.kind}`, title: `${item.title}${item.subtitle ? ` · ${item.subtitle}` : ""}` },
    el("img", { src: art(item), alt: "", loading: "lazy", width: "160", height: "160" }),
    el("b", { text: item.title }),
    el("span", { text: item.subtitle || item.kind }));
  c.addEventListener("click", () => open(item));
  return c;
}
function open(item) {
  if (item.kind === "song") return playItems([toTrack(item)], `Song: ${item.title}`, { radio: true });
  setView({ type: "list", kind: item.kind, id: item.id, title: item.title, subtitle: item.subtitle, image: item.image });
}

async function renderSearch(box) {
  const data = await get(`/api/search?${new URLSearchParams({ q: P.query, kind: P.kind })}`);
  if (!data.items.length) { box.replaceChildren(el("div", { class: "card empty" }, el("p", { text: `Nothing found for “${P.query}”.` }))); return; }
  if (P.kind === "song") {
    box.replaceChildren(el("div", { class: "card" }, trackList(data.items.map(toTrack), `Search: ${P.query}`)));
  } else {
    box.replaceChildren(el("div", { class: "p-grid" }, ...data.items.map(card)));
  }
}

async function renderMood(box, v) {
  const data = await get(`/api/browse/mood?${new URLSearchParams({ params: v.params })}`);
  box.replaceChildren(backLink(), el("h1", { class: "p-h1", text: v.title }), el("div", { class: "p-grid" }, ...data.items.map(card)));
}

async function renderList(box, v) {
  const data = await get(`/api/browse/tracks?${new URLSearchParams({ kind: v.kind, id: v.id })}`);
  const title = v.title || data.title;
  const tracks = data.tracks;
  const source = `${v.kind === "album" ? "Album" : v.kind === "artist" ? "Artist" : "Playlist"}: ${title}`;
  const head = el("div", { class: "p-head" },
    el("img", { class: "p-cover", src: v.image || (tracks[0] ? thumb(tracks[0].video_id) : ""), alt: "", width: "180", height: "180" }),
    el("div", {},
      el("span", { class: "chip plain", text: v.kind }),
      el("h1", { class: "p-h1", text: title }),
      el("p", { class: "muted", text: `${v.subtitle ? `${v.subtitle} · ` : ""}${tracks.length} songs` }),
      el("div", { class: "p-actions" },
        actionBtn("▶ Play", "primary", () => playItems(tracks, source)),
        actionBtn("Shuffle", "ghost", () => playItems(shuffled(tracks), `${source} (shuffled)`)),
        actionBtn("Play next", "ghost", () => queueItems(tracks, "next", source)),
        actionBtn("Add to queue", "ghost", () => queueItems(tracks, "queue", source)))));
  box.replaceChildren(backLink(), head, el("div", { class: "card" }, trackList(tracks, source)));
}
function backLink() {
  const b = el("button", { type: "button", class: "ghost back", text: "← Back" });
  b.addEventListener("click", () => setView(P.query ? { type: "search" } : { type: "home" }));
  return b;
}
function actionBtn(text, cls, fn) {
  const b = el("button", { type: "button", class: cls, text });
  b.addEventListener("click", fn);
  b.dataset.action = "1";
  b.disabled = !P.info.actions;
  return b;
}
function shuffled(list) {
  const a = list.slice();
  for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
  return a;
}
function trackList(tracks, source) {
  if (!tracks.length) return el("p", { class: "muted", text: "No playable songs here." });
  return el("ol", { class: "queue p-tracks" }, ...tracks.map((t, i) => {
    const li = el("li", {},
      el("span", { class: "n", text: String(i + 1) }),
      el("img", { class: "thumb", src: t.image || thumb(t.video_id, "default"), alt: "", loading: "lazy", width: "48", height: "36" }),
      el("span", { class: "t" }, el("b", { text: t.title }), el("span", { text: t.artist })),
      el("span", { class: "p-row-actions" },
        mini("▶", `Play ${t.title}`, () => playItems(tracks.slice(i), source)),
        mini("Next", `Play ${t.title} next`, () => queueItems([t], "next", source)),
        mini("+", `Add ${t.title} to the queue`, () => queueItems([t], "queue", source)),
        mini("Radio", `Start radio from ${t.title}`, () => playItems([t], `Radio after ${t.title}`, { radio: true })),
        el("span", { class: "dur", text: t.duration ? mmss(t.duration * 1000) : "" })));
    li.addEventListener("dblclick", () => playItems(tracks.slice(i), source));
    return li;
  }));
}
function mini(text, label, fn) {
  const b = el("button", { type: "button", class: "mini", text, "aria-label": label, title: label });
  b.addEventListener("click", (e) => { e.stopPropagation(); fn(); });
  b.disabled = !P.info.actions;
  return b;
}

// ---------- search ----------
let searchTimer;
$("#p-search").addEventListener("submit", (e) => { e.preventDefault(); runSearch(); });
$("#p-search").elements.q.addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(runSearch, 450); });
function runSearch() {
  P.query = $("#p-search").elements.q.value.trim();
  setView(P.query ? { type: "search" } : { type: "home" });
}
for (const b of document.querySelectorAll("#p-kinds button")) {
  b.addEventListener("click", () => {
    P.kind = b.dataset.kind;
    for (const x of document.querySelectorAll("#p-kinds button")) x.setAttribute("aria-selected", String(x === b));
    renderView();
  });
}

// ---------- playing ----------
async function playItems(tracks, source, { radio = false } = {}) {
  if (!P.info.actions) { toast("Set a dashboard password to play from here.", true); return; }
  if (!tracks.length) return;
  if (onEcho()) return queueItems(tracks, "now", source);
  P.queue = tracks.slice(0, 200);
  P.source = source;
  await playAt(0);
  if (radio) extendWithRadio(tracks[0].video_id);
}
async function queueItems(tracks, mode, source) {
  if (!P.info.actions) { toast("Set a dashboard password to play from here.", true); return; }
  if (onEcho()) {
    try {
      const r = await post("/api/play/echo", { device: P.target, mode, source, tracks: tracks.slice(0, 200).map(plain) });
      const e = currentEcho();
      toast(`${tracks.length === 1 ? `“${tracks[0].title}”` : `${tracks.length} songs`} → ${e ? echoName(e) : "Echo"}. ${r.note}`);
    } catch (err) { toast(err.message, true); }
    return;
  }
  if (P.index < 0) return playItems(tracks, source);
  const ids = new Set(tracks.map((t) => t.video_id));
  const cur = P.queue[P.index];
  const rest = P.queue.slice(P.index + 1).filter((t) => !ids.has(t.video_id));
  const add = tracks.filter((t) => t.video_id !== cur.video_id);
  P.queue = [...P.queue.slice(0, P.index + 1).filter((t, i) => i === P.index || !ids.has(t.video_id)), ...(mode === "queue" ? [...rest, ...add] : [...add, ...rest])].slice(0, 300);
  P.index = P.queue.indexOf(cur);
  renderQueue();
  toast(mode === "queue" ? "Added to the queue." : "Plays next.");
}
const plain = (t) => ({ video_id: t.video_id, title: (t.title || "").slice(0, 200), artist: (t.artist || "").slice(0, 200), duration: t.duration || null });

async function playAt(i) {
  if (i < 0 || i >= P.queue.length) return;
  P.index = i;
  const t = P.queue[i];
  renderBar();
  renderQueue();
  try {
    const { url, demo } = await post("/api/play/stream-link", { video_id: t.video_id });
    if (demo || !url) return demoPlay(t);
    audio.src = url;
    await audio.play();
    post("/api/play/played", { track: plain(t), source: P.source }).catch(() => {});
  } catch (err) {
    toast(`Couldn't play “${t.title}”: ${err.message}`, true);
  }
  if (P.index >= P.queue.length - 2) extendWithRadio(t.video_id);
}
let radioBusy = false;
async function extendWithRadio(videoId) {
  if (radioBusy) return;
  radioBusy = true;
  try {
    const r = await get(`/api/browse/tracks?${new URLSearchParams({ kind: "song", id: videoId })}`);
    const have = new Set(P.queue.map((t) => t.video_id));
    P.queue.push(...r.tracks.filter((t) => !have.has(t.video_id)));
    renderQueue();
  } catch { /* the queue just ends */ } finally { radioBusy = false; }
}
function demoPlay(t) {
  // The public demo has no server: pretend to play so the controls can be tried.
  clearInterval(P.demoTimer);
  P.demo = { pos: 0, dur: (t.duration || 200), playing: true };
  P.demoTimer = setInterval(() => { if (P.demo.playing) { P.demo.pos += 1; if (P.demo.pos >= P.demo.dur) next(); renderProgress(); } }, 1000);
  renderBar();
}
const next = () => (P.index + 1 < P.queue.length ? playAt(P.index + 1) : null);
const prev = () => {
  const pos = DEMO && P.demo ? P.demo.pos : audio.currentTime;
  if (pos > 3) { if (DEMO && P.demo) P.demo.pos = 0; else audio.currentTime = 0; return; }
  if (P.index > 0) playAt(P.index - 1);
};
const toggle = () => {
  if (DEMO && P.demo) { P.demo.playing = !P.demo.playing; renderBar(); return; }
  if (audio.paused) audio.play(); else audio.pause();
};
audio.addEventListener("ended", next);
audio.addEventListener("play", renderBar);
audio.addEventListener("pause", renderBar);
audio.addEventListener("timeupdate", renderProgress);
audio.addEventListener("error", () => { if (audio.src) toast("This song couldn't be loaded; skipping.", true); setTimeout(next, 1500); });

$("#p-play").addEventListener("click", () => { if (!onEcho()) toggle(); });
$("#p-next").addEventListener("click", async () => {
  if (!onEcho()) return next();
  try { const r = await post("/api/play/skip", { device: P.target }); toast(r.note); } catch (err) { toast(err.message, true); }
});
$("#p-prev").addEventListener("click", () => { if (!onEcho()) prev(); });
$("#p-range").addEventListener("input", (e) => {
  const frac = Number(e.target.value) / 1000;
  if (DEMO && P.demo) { P.demo.pos = Math.round(frac * P.demo.dur); return; }
  if (audio.duration) audio.currentTime = frac * audio.duration;
});

// ---------- the bar ----------
function renderBar() {
  const bar = $("#p-bar");
  let t = null, playing = false, where = "";
  if (onEcho()) {
    const e = currentEcho();
    t = e && e.current;
    playing = !!(e && e.playing);
    where = e ? `On ${echoName(e)}` : "";
  } else if (P.index >= 0) {
    t = P.queue[P.index];
    playing = DEMO && P.demo ? P.demo.playing : !audio.paused;
    where = "This browser";
  }
  bar.hidden = !t;
  document.body.classList.toggle("has-bar", !!t);
  if (!t) return;
  $("#p-art").src = t.image || thumb(t.video_id);
  $("#p-title").textContent = t.title;
  $("#p-artist").textContent = t.artist;
  $("#p-where").textContent = where;
  const play = $("#p-play");
  play.textContent = playing ? "⏸" : "▶";
  play.setAttribute("aria-label", playing ? "Pause" : "Play");
  const echo = onEcho();
  for (const id of ["#p-play", "#p-prev"]) {
    $(id).disabled = echo;
    $(id).title = echo ? "On an Echo, use your voice or the Echo's buttons" : "";
  }
  $("#p-next").disabled = echo && !P.info.experimental_skip;
  $("#p-next").title = echo ? (P.info.experimental_skip ? "Skip now (experimental)" : "Skipping from here needs ECHO_TUNES_EXPERIMENTAL_SKIP") : "";
  $("#p-range").disabled = echo;
  renderProgress();
  updateMediaSession(t, playing);
}
function renderProgress() {
  let pos = 0, dur = 0;
  if (onEcho()) {
    const e = currentEcho();
    if (e && e.current) {
      dur = (e.current.duration || 0);
      const ref = P.echoAt ? (Date.now() - P.echoAt) / 1000 : 0;
      pos = Math.min(dur || Infinity, (e.position_ms || 0) / 1000 + (e.playing ? ref : 0));
    }
  } else if (DEMO && P.demo) {
    pos = P.demo.pos; dur = P.demo.dur;
  } else {
    pos = audio.currentTime || 0; dur = audio.duration || (P.queue[P.index] || {}).duration || 0;
  }
  $("#p-pos").textContent = mmss(pos * 1000);
  $("#p-dur").textContent = dur ? mmss(dur * 1000) : "–";
  if (document.activeElement !== $("#p-range")) $("#p-range").value = String(dur ? Math.round((1000 * pos) / dur) : 0);
}
setInterval(() => { if (onEcho()) renderProgress(); }, 1000);

function renderQueue() {
  const list = $("#p-queue-list");
  if (onEcho()) {
    const e = currentEcho();
    list.replaceChildren(el("li", { class: "muted", text: e ? "The Echo's queue is on the Now playing tab." : "" }));
    return;
  }
  const upcoming = P.queue.slice(P.index + 1, P.index + 51);
  if (!upcoming.length) { list.replaceChildren(el("li", { class: "muted", text: "Nothing queued. Radio adds songs as you go." })); return; }
  list.replaceChildren(...upcoming.map((t, k) => {
    const i = P.index + 1 + k;
    const rm = mini("✕", `Remove ${t.title}`, () => { P.queue.splice(i, 1); renderQueue(); });
    const li = el("li", {},
      el("span", { class: "n", text: String(k + 1) }),
      el("img", { class: "thumb", src: t.image || thumb(t.video_id, "default"), alt: "", loading: "lazy", width: "48", height: "36" }),
      el("span", { class: "t" }, el("b", { text: t.title }), el("span", { text: t.artist })),
      rm);
    li.addEventListener("dblclick", () => playAt(i));
    return li;
  }));
}
$("#p-queue-btn").addEventListener("click", () => {
  const q = $("#p-queue");
  q.hidden = !q.hidden;
  $("#p-queue-btn").setAttribute("aria-expanded", String(!q.hidden));
  renderQueue();
});
$("#p-queue-close").addEventListener("click", () => { $("#p-queue").hidden = true; $("#p-queue-btn").setAttribute("aria-expanded", "false"); });

// Lock-screen and keyboard media keys.
function updateMediaSession(t, playing) {
  if (!("mediaSession" in navigator) || onEcho()) return;
  navigator.mediaSession.metadata = new MediaMetadata({ title: t.title, artist: t.artist, artwork: t.image ? [{ src: t.image }] : [] });
  navigator.mediaSession.playbackState = playing ? "playing" : "paused";
}
if ("mediaSession" in navigator) {
  navigator.mediaSession.setActionHandler("play", () => toggle());
  navigator.mediaSession.setActionHandler("pause", () => toggle());
  navigator.mediaSession.setActionHandler("nexttrack", () => next());
  navigator.mediaSession.setActionHandler("previoustrack", () => prev());
}

// ---------- clear history (History tab) ----------
let clearArmed = 0;
$("#history-clear").addEventListener("click", async () => {
  const b = $("#history-clear");
  if (Date.now() - clearArmed > 4000) {
    clearArmed = Date.now();
    b.textContent = "Click again to delete all history";
    setTimeout(() => { if (Date.now() - clearArmed >= 4000) b.textContent = "Clear history"; }, 4100);
    return;
  }
  clearArmed = 0;
  b.textContent = "Clear history";
  try {
    const r = await post("/api/history/clear", {});
    toast(`Deleted ${r.removed} plays from the history.`);
    loadHistory(true);
  } catch (err) { toast(err.message, true); }
});

// ---------- refresh (called by app.js) ----------
async function playerRefresh() {
  try {
    P.info = await get("/api/player");
    P.echoAt = Date.now();
  } catch { return; }
  $("#history-clear").hidden = !P.info.actions;
  renderTargets();
  if (!P.view) {
    setView({ type: "home" });
    // Screenshot mode of the public demo: start a made-up song so the player bar shows.
    if (DEMO && Array.isArray(window.ECHO_TUNES_DEMO_AUTOPLAY)) playItems(window.ECHO_TUNES_DEMO_AUTOPLAY, "Quick picks");
  }
  for (const b of document.querySelectorAll("[data-action], .mini")) b.disabled = !P.info.actions;
}
window.playerRefresh = playerRefresh; // app.js calls it on every refresh
playerRefresh();
})();
