// echo-tunes dashboard. No libraries; every piece of text is inserted with textContent,
// never as HTML, so song titles can't inject markup.
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const el = (tag, props = {}, ...kids) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else n.setAttribute(k, v);
  }
  for (const kid of kids) if (kid != null) n.append(kid);
  return n;
};
// The public demo (GitHub Pages) has no server: demo.js answers these calls with sample data.
const DEMO = typeof window.ECHO_TUNES_DEMO === "function" ? window.ECHO_TUNES_DEMO : null;
const api = async (path) => {
  if (DEMO) return DEMO(path);
  const r = await fetch(path, { headers: { Accept: "application/json" }, cache: "no-store" });
  if (!r.ok && r.status !== 503) throw new Error(`${path}: ${r.status}`);
  return r.json();
};
const thumb = (id, size = "mqdefault") =>
  (window.ECHO_TUNES_THUMB ? window.ECHO_TUNES_THUMB(id) : `https://i.ytimg.com/vi/${encodeURIComponent(id)}/${size}.jpg`);
const mmss = (ms) => {
  if (ms == null || Number.isNaN(ms)) return "–";
  const s = Math.max(0, Math.round(ms / 1000));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
};
const ago = (t) => {
  const s = Math.round(Date.now() / 1000 - t);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
};
const clock = (t) => new Date(t * 1000).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" });
const echoName = (d) => d.name || d.device_name || `Echo …${(d.id || d.device || "").slice(-6)}`;

const state = { tab: "now", now: null, health: null, devices: [], history: { offset: 0, rows: [] }, keepDays: 15 };

// ---------- tabs ----------
for (const b of document.querySelectorAll(".tabs button")) {
  b.addEventListener("click", () => show(b.dataset.tab));
}
function show(tab) {
  state.tab = tab;
  for (const b of document.querySelectorAll(".tabs button")) b.setAttribute("aria-selected", String(b.dataset.tab === tab));
  for (const s of document.querySelectorAll("main > section")) s.hidden = s.id !== `tab-${tab}`;
  history.replaceState(null, "", `#${tab}`);
  refresh();
}

// ---------- header status ----------
function renderStatus(h) {
  const box = $("#status");
  box.replaceChildren(
    el("span", { class: `chip ${h.status === "ok" ? "ok" : "warn"}`, text: h.status === "ok" ? "Healthy" : "Degraded" }),
    el("span", { class: `chip ${h.youtube === "failing" ? "bad" : "plain"}`, text: `YouTube: ${h.youtube}` }),
    el("span", { class: "chip plain", text: h.signed_in ? "Signed in to YouTube Music" : "Not signed in" }),
    el("span", { class: "chip plain", text: `${h.memory_mb} MB` }),
  );
  $("#version").textContent = `v${h.version}`;
  $("#keep").textContent = h.history_days ? `${h.history_days} days` : "off";
}

// ---------- now playing ----------
function renderNow(data) {
  const box = $("#devices");
  if (!data.devices.length) {
    box.replaceChildren(el("div", { class: "card empty" },
      el("big", { text: "♪" }),
      el("p", { text: "Nothing has played yet." }),
      el("p", { class: "muted", text: "Say “Alexa, ask my tunes to play …” and it appears here." })));
    return;
  }
  box.replaceChildren(...data.devices.map(deviceCard));
}
function deviceCard(d) {
  const card = $("#device-card").content.firstElementChild.cloneNode(true);
  const cur = d.current;
  $(".who", card).textContent = echoName(d);
  const st = $(".state", card);
  st.textContent = d.playing ? "● Playing" : `Paused · ${ago(d.updated)}`;
  st.classList.toggle("playing", d.playing);
  $(".art", card).src = thumb(cur.video_id);
  $(".title", card).textContent = cur.title;
  $(".artist", card).textContent = cur.artist;
  $(".source", card).textContent = d.source || "Queue";
  $(".modes", card).textContent = [d.shuffle && "Shuffle", d.loop && "Loop", `Song ${d.queue_position} of ${d.queue_length}`].filter(Boolean).join(" · ");
  card.dataset.position = d.position_ms;
  card.dataset.duration = (cur.duration || 0) * 1000;
  card.dataset.playing = d.playing ? "1" : "";
  card.dataset.at = Date.now();
  tickCard(card);
  const q = $(".queue", card);
  if (!d.up_next.length) $(".next-h", card).hidden = true;
  d.up_next.forEach((t, i) => q.append(el("li", {},
    el("span", { class: "n", text: String(i + 1) }),
    el("img", { class: "thumb", src: thumb(t.video_id, "default"), alt: "", loading: "lazy", width: "48", height: "36" }),
    el("span", { class: "t" }, el("b", { text: t.title }), el("span", { text: t.artist })),
    el("span", { class: "dur", text: t.duration ? mmss(t.duration * 1000) : "" }))));
  return card;
}
function tickCard(card) {
  const dur = Number(card.dataset.duration);
  let pos = Number(card.dataset.position);
  if (card.dataset.playing) pos += Date.now() - Number(card.dataset.at);
  if (dur) pos = Math.min(pos, dur);
  $(".pos", card).textContent = mmss(pos);
  $(".dur", card).textContent = dur ? mmss(dur) : "";
  const pct = dur ? (100 * pos) / dur : 0;
  $(".bar", card).style.width = `${pct}%`;
  $(".progress", card).setAttribute("aria-valuenow", String(Math.round(pct)));
}
setInterval(() => document.querySelectorAll("#devices .device").forEach(tickCard), 1000);

// ---------- filters ----------
function fillFilters() {
  const ranges = [[1, "Last 24 hours"], [7, "Last 7 days"], [15, "Last 15 days"], [30, "Last 30 days"], [90, "Last 90 days"]]
    .filter(([d]) => d <= state.keepDays);
  if (!ranges.some(([d]) => d === state.keepDays)) ranges.push([state.keepDays, `All (${state.keepDays} days)`]);
  for (const form of [$("#history-filters"), $("#stats-filters")]) {
    const days = form.elements.days, dev = form.elements.device;
    const keepDay = days.value, keepDev = dev.value;
    days.replaceChildren(...ranges.map(([d, t]) => el("option", { value: String(d), text: t })));
    days.value = keepDay || String(Math.min(7, state.keepDays));
    dev.replaceChildren(el("option", { value: "", text: "All Echos" }), ...state.devices.map((d) => el("option", { value: d.id, text: echoName(d) })));
    dev.value = keepDev;
  }
}
let searchTimer;
$("#history-filters").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => loadHistory(true), 250); });
$("#history-filters").addEventListener("submit", (e) => e.preventDefault());
$("#stats-filters").addEventListener("change", () => loadStats());
$("#history-more").addEventListener("click", () => loadHistory(false));

// ---------- history ----------
const STATUS = { finished: ["plain", "Played"], playing: ["ok", "Playing"], stopped: ["plain", "Paused"], skipped: ["warn", "Skipped"], failed: ["bad", "Failed"] };
async function loadHistory(reset) {
  const f = $("#history-filters").elements;
  if (reset) state.history = { offset: 0, rows: [] };
  const p = new URLSearchParams({ limit: "50", offset: String(state.history.offset), days: f.days.value });
  if (f.device.value) p.set("device", f.device.value);
  if (f.q.value.trim()) p.set("q", f.q.value.trim());
  const data = await api(`/api/history?${p}`);
  state.history.rows.push(...data.plays);
  state.history.offset += data.plays.length;
  const body = $("#history-rows");
  body.replaceChildren(...state.history.rows.map((r) => {
    const [cls, label] = STATUS[r.status] || ["plain", r.status];
    const listened = r.played_ms != null ? `${mmss(r.played_ms)}${r.duration ? ` / ${mmss(r.duration * 1000)}` : ""}` : "–";
    return el("tr", {},
      el("td", { class: "when" }, document.createTextNode(clock(r.started)), el("small", { text: ago(r.started) })),
      el("td", { class: "song-cell" }, el("div", { class: "song" },
        el("img", { class: "thumb", src: thumb(r.video_id, "default"), alt: "", loading: "lazy", width: "48", height: "36" }),
        el("span", { class: "t" }, el("b", { text: r.title }), el("span", { text: r.artist })))),
      el("td", { text: echoName(r) }),
      el("td", { class: "muted", text: r.source }),
      el("td", { class: "dur", text: listened }),
      el("td", {}, el("span", { class: `chip ${cls}`, text: label })));
  }));
  const empty = $("#history-empty");
  empty.hidden = state.history.rows.length > 0;
  empty.textContent = data.enabled ? "No songs in this period." : "History is turned off (ECHO_TUNES_HISTORY_DAYS=0).";
  $("#history-more").hidden = data.plays.length < 50;
}

// ---------- stats ----------
async function loadStats() {
  const f = $("#stats-filters").elements;
  const p = new URLSearchParams({ days: f.days.value });
  if (f.device.value) p.set("device", f.device.value);
  const s = await api(`/api/stats?${p}`);
  const hours = s.listened_minutes / 60;
  $("#stat-tiles").replaceChildren(
    tile("Plays", s.plays, `in ${s.days} day${s.days === 1 ? "" : "s"}`),
    tile("Listening time", hours >= 1 ? `${hours.toFixed(1)} h` : `${s.listened_minutes} min`, `≈ ${Math.round(s.listened_minutes / Math.max(1, s.days))} min a day`),
    tile("Different songs", s.songs, ""),
    tile("Different artists", s.artists, ""));
  ranked($("#top-songs"), s.top_songs.map((t) => [t.title, t.artist, t.plays]));
  ranked($("#top-artists"), s.top_artists.map((a) => [a.artist, "", a.plays]));
  chart($("#per-day"), s.per_day, s.days);
}
function tile(k, v, sub) {
  return el("div", { class: "tile" }, el("div", { class: "k", text: k }), el("div", { class: "v", text: String(v) }), el("div", { class: "s", text: sub }));
}
function ranked(list, items) {
  if (!items.length) { list.replaceChildren(el("li", { class: "muted", text: "Nothing yet." })); return; }
  const max = Math.max(...items.map((i) => i[2]));
  list.replaceChildren(...items.map(([a, b, n]) => {
    const meter = el("div", { class: "meter" }, el("div"));
    meter.firstChild.style.width = `${(100 * n) / max}%`;
    return el("li", {}, el("div", { class: "row" }, el("span", { class: "t" }, el("b", { text: a }), b ? el("span", { text: b }) : null), el("span", { class: "dur", text: `${n}×` })), meter);
  }));
}
function chart(box, rows, days) {
  const ns = "http://www.w3.org/2000/svg";
  const byDay = new Map(rows.map((r) => [r.day, r.plays]));
  const list = [];
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(Date.now() - i * 86400000);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    list.push([key, byDay.get(key) || 0, d]);
  }
  const W = Math.max(320, Math.round(box.clientWidth || 800)), H = 200, pad = 22, max = Math.max(1, ...list.map((x) => x[1]));
  const bw = (W - pad) / list.length;
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `Plays per day over ${days} days, most ${max}`);
  list.forEach(([key, n, d], i) => {
    const h = ((H - pad - 8) * n) / max;
    const r = document.createElementNS(ns, "rect");
    Object.entries({ x: pad + i * bw + bw * 0.15, y: H - pad - h, width: bw * 0.7, height: Math.max(h, n ? 2 : 0), rx: 3, class: "b" }).forEach(([k, v]) => r.setAttribute(k, v));
    const t = document.createElementNS(ns, "title");
    t.textContent = `${d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" })}: ${n} play${n === 1 ? "" : "s"}`;
    r.append(t);
    svg.append(r);
    if (list.length <= 15 || i % Math.ceil(list.length / 12) === 0) {
      const lb = document.createElementNS(ns, "text");
      lb.setAttribute("x", pad + i * bw + bw / 2); lb.setAttribute("y", H - 6); lb.setAttribute("text-anchor", "middle");
      lb.textContent = list.length <= 7 ? d.toLocaleDateString([], { weekday: "short" }) : String(d.getDate());
      svg.append(lb);
    }
  });
  const top = document.createElementNS(ns, "text");
  top.setAttribute("x", 0); top.setAttribute("y", 12); top.textContent = String(max);
  svg.append(top);
  box.replaceChildren(svg);
}

// ---------- monitoring ----------
function renderMonitor(h) {
  $("#health-tiles").replaceChildren(
    tile("Status", h.status === "ok" ? "Healthy" : "Degraded", h.last_error || "all checks passing"),
    tile("YouTube audio", h.youtube, h.last_audio_ok ? `last OK ${ago(h.last_audio_ok)}` : "no songs yet"),
    tile("Uptime", mmss(h.uptime_seconds * 1000), `memory ${h.memory_mb} MB`),
    tile("History", h.history_plays, `plays kept · ${h.history_days} days`));
  const base = DEMO ? "http://your-server:8081" : location.origin;
  const recipes = [
    ["Uptime Kuma: is it up and healthy?", "Monitor type: HTTP(s) - Json Query", `URL:            ${base}/api/health\nJSON query:     status\nExpected value: ok\nInterval:       60 s`],
    ["Uptime Kuma: is the public side reachable?", "Monitor type: HTTP(s) (from outside your network if you can)", "URL: https://<your public address>/healthz"],
    ["Prometheus scrape config", "Then graph it in Grafana; metric names start with echo_tunes_.", `- job_name: echo-tunes\n  scrape_interval: 30s\n  metrics_path: /metrics\n  static_configs:\n    - targets: ["${DEMO ? "your-server:8081" : location.host}"]${!DEMO && location.protocol === "https:" ? "\n  scheme: https" : ""}`],
    ["Home Assistant: now-playing sensor", "configuration.yaml (REST sensor)", `rest:\n  - resource: ${base}/api/now\n    scan_interval: 15\n    sensor:\n      - name: "echo-tunes now playing"\n        value_template: "{{ value_json.devices[0].current.title if value_json.devices else 'Nothing' }}"`],
  ];
  $("#recipes").replaceChildren(...recipes.flatMap(([title, note, code]) => {
    const btn = el("button", { class: "ghost copy", type: "button", text: "Copy" });
    btn.addEventListener("click", async () => { try { await navigator.clipboard.writeText(code); btn.textContent = "Copied"; } catch { btn.textContent = "Select and copy"; } });
    return [el("dt", { text: title }), el("dd", {}, el("span", { class: "muted", text: note }), btn, el("pre", { text: code }))];
  }));
}

// ---------- setup ----------
const ICON = { ok: "✓", warn: "!", fail: "✗", info: "i" };
async function loadSetup(force) {
  const btn = $("#setup-rerun");
  btn.disabled = true;
  $("#setup-summary").textContent = "Running checks… (YouTube can take a few seconds)";
  try {
    const r = await api(`/api/setup${force ? "?refresh=1" : ""}`);
    const counts = r.checks.reduce((a, c) => ((a[c.status] = (a[c.status] || 0) + 1), a), {});
    $("#setup-summary").textContent = r.status === "ok"
      ? `Everything works (${counts.ok || 0} checks passed). Checked ${ago(r.time)}.`
      : `${counts.fail || 0} problem(s), ${counts.warn || 0} warning(s). Checked ${ago(r.time)}.`;
    $("#setup-checks").replaceChildren(...r.checks.map((c) => {
      const body = el("div", {}, el("b", { text: c.name }), el("div", { class: "d", text: c.detail }));
      if (c.hint && c.status !== "ok") {
        const hint = el("div", { class: "h", text: c.hint + " " });
        if (c.link) hint.append(el("a", { href: c.link, rel: "noreferrer", target: "_blank", text: c.status === "info" ? "Learn more" : "How to fix" }));
        body.append(hint);
      }
      return el("li", { class: c.status }, el("span", { class: "icon", "aria-label": c.status, text: ICON[c.status] || "?" }), body);
    }));
  } catch (err) {
    $("#setup-summary").textContent = "Couldn't run the checks.";
    console.warn(err);
  } finally {
    btn.disabled = false;
  }
}
$("#setup-rerun").addEventListener("click", () => loadSetup(true));
$("#test-play").addEventListener("click", async () => {
  const btn = $("#test-play"), status = $("#test-status"), audio = $("#test-audio");
  btn.disabled = true;
  status.textContent = "Getting the song (a few seconds the first time)…";
  try {
    const t = await api("/api/test-play");
    if (t.demo) { status.textContent = "This is the demo: on your own server, a song plays here through your public address."; return; }
    audio.hidden = false;
    audio.src = t.url;
    audio.onplaying = () => { status.textContent = `▶ Playing “${t.title}” by ${t.artist} via ${new URL(t.url).host}. It works.`; };
    audio.onerror = () => { status.textContent = "✗ The browser couldn't load the audio through the public address. Check the Setup list."; };
    await audio.play();
  } catch (err) {
    status.textContent = "✗ Couldn't start the test song.";
    console.warn(err);
  } finally {
    btn.disabled = false;
  }
});

// ---------- refresh loop ----------
async function refresh() {
  try {
    const [health, devices] = await Promise.all([api("/api/health"), api("/api/devices")]);
    state.health = health;
    state.keepDays = Math.max(1, health.history_days || 1);
    const changed = JSON.stringify(devices) !== JSON.stringify(state.devices);
    state.devices = devices;
    renderStatus(health);
    if (changed || !$("#history-filters").elements.days.options.length) fillFilters();
    if (state.tab === "now") renderNow(await api("/api/now"));
    if (state.tab === "history" && (changed || !state.history.rows.length)) await loadHistory(true);
    if (state.tab === "stats") await loadStats();
    if (state.tab === "monitor") renderMonitor(health);
    if (state.tab === "setup" && !$("#setup-checks").children.length) await loadSetup(false);
  } catch (err) {
    $("#status").replaceChildren(el("span", { class: "chip bad", text: "Can't reach echo-tunes" }));
    console.warn(err);
  }
}
setInterval(() => { if (!document.hidden && (state.tab === "now" || state.tab === "monitor")) refresh(); }, 5000);
setInterval(() => { if (!document.hidden && state.tab === "history") loadHistory(true).catch(() => {}); }, 30000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
show((location.hash.slice(1) in { now: 1, history: 1, stats: 1, monitor: 1, setup: 1 }) ? location.hash.slice(1) : "now");
