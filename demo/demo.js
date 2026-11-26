// Sample data for the public dashboard demo (GitHub Pages). Nothing here talks to a server or
// plays music: it answers the dashboard's API calls the way a real echo-tunes would.
"use strict";
(() => {
  const SONGS = [
    ["4NRXx6U8ABQ", "Blinding Lights", "The Weeknd", 200],
    ["fJ9rUzIMcZQ", "Bohemian Rhapsody", "Queen", 355],
    ["kJQP7kiw5Fk", "Despacito", "Luis Fonsi, Daddy Yankee", 282],
    ["fsiPzT50ZiM", "Tum Hi Ho", "Arijit Singh", 262],
    ["pLrQZAaJWP0", "Janam Janam", "Arijit Singh", 238],
    ["JGwWNGJdvx8", "Shape of You", "Ed Sheeran", 263],
    ["RgKAFK5djSk", "See You Again", "Wiz Khalifa, Charlie Puth", 237],
    ["09R8_2nJtjg", "Sugar", "Maroon 5", 235],
    ["hT_nvWreIhg", "Counting Stars", "OneRepublic", 257],
    ["YQHsXMglC9A", "Hello", "Adele", 366],
    ["2Vv-BfVoq4g", "Perfect", "Ed Sheeran", 263],
    ["CevxZvSJLk8", "Roar", "Katy Perry", 269],
    ["OPf0YbXqDm0", "Uptown Funk", "Mark Ronson, Bruno Mars", 270],
  ].map(([video_id, title, artist, duration]) => ({ video_id, title, artist, duration }));
  // Screenshot mode (demo/?shots): made-up songs and generated artwork, so the README and
  // social images never contain anyone's real album art or names.
  if (new URLSearchParams(location.search).has("shots")) {
    const MADE_UP = [
      ["Neon Harbour", "The Paper Lanterns", 214], ["Monsoon Letters", "Aarav & The Tide", 247],
      ["Slow Satellites", "Juniper Vale", 231], ["Paper Kites", "Mira Okafor", 198],
      ["Goa After Rain", "Konkan Coast Collective", 262], ["Static Bloom", "Night Ferry", 225],
      ["Lighthouse Radio", "Ines Marlow", 241], ["Copper Skies", "The Late Arrivals", 209],
      ["Second Window", "Rafa Quinn", 256], ["Velvet Highway", "Saltwater Static", 233],
      ["Tidal Clock", "Noor & Ellis", 219], ["Northbound", "Harbour Lights", 244],
      ["Small Hours", "Odette Rain", 237],
    ];
    MADE_UP.forEach(([title, artist, duration], i) => Object.assign(SONGS[i], { title, artist, duration }));
    const HUES = [12, 200, 265, 150, 32, 320, 185, 45, 230, 345, 95, 280, 170];
    const art = new Map(SONGS.map((s, i) => [s.video_id, HUES[i]]));
    window.ECHO_TUNES_THUMB = (id) => {
      const h = art.get(id) ?? 210;
      const svg = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 160 90'><defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='hsl(${h},70%,55%)'/><stop offset='1' stop-color='hsl(${(h + 60) % 360},65%,30%)'/></linearGradient></defs><rect width='160' height='90' fill='url(#g)'/><circle cx='122' cy='28' r='18' fill='hsla(0,0%,100%,.18)'/><circle cx='40' cy='70' r='30' fill='hsla(0,0%,0%,.12)'/></svg>`;
      return `data:image/svg+xml,${encodeURIComponent(svg)}`;
    };
    document.documentElement.classList.add("shots");
  }
  const DEVICES = [{ id: "DEMO0LIVING1", name: "Living room" }, { id: "DEMO0KITCHEN", name: "Kitchen" }];
  const SHOTS = new URLSearchParams(location.search).has("shots");
  const SOURCES = SHOTS
    ? ['Asked for "neon harbour"', "Radio after Neon Harbour", "Playlist: Road Trip", "Liked songs"]
    : ['Asked for "blinding lights"', "Radio after Blinding Lights", "Playlist: Road Trip", "Liked songs"];
  const HISTORY_DAYS = 15;
  const loaded = Date.now() / 1000;

  // A small seeded random generator, so the demo looks the same on every visit.
  let seed = 7;
  const rand = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;
  const pick = (a) => a[Math.floor(rand() * a.length)];

  const plays = [];
  for (let t = loaded - HISTORY_DAYS * 86400; t < loaded - 600; t += 1800 + rand() * 9000) {
    const hour = new Date(t * 1000).getHours();
    if (hour < 7 || hour > 23) continue; // nobody listens at 3 am
    const s = pick(SONGS), d = pick(DEVICES), r = rand();
    const status = r < 0.78 ? "finished" : r < 0.9 ? "skipped" : r < 0.97 ? "stopped" : "failed";
    const played = status === "finished" ? s.duration * 1000 : Math.round(rand() * s.duration * 1000);
    plays.push({ id: plays.length + 1, device: d.id, device_name: d.name, ...s, source: pick(SOURCES), started: t, ended: t + played / 1000, played_ms: played, status });
  }
  plays.reverse();

  const now = () => {
    const t = Date.now() / 1000, playingFor = (t - loaded) % 200;
    return {
      time: t,
      devices: [
        { id: "DEMO0LIVING1", name: "Living room", playing: true, position_ms: Math.round((61 + playingFor) * 1000), updated: t - 5,
          source: SHOTS ? "Radio after Neon Harbour" : "Radio after Blinding Lights", shuffle: false, loop: false, queue_length: 26, queue_position: 3,
          current: SONGS[5], up_next: SONGS.slice(6, 12) },
        { id: "DEMO0KITCHEN", name: "Kitchen", playing: false, position_ms: 94000, updated: t - 3600,
          source: "Playlist: Road Trip", shuffle: true, loop: false, queue_length: 12, queue_position: 4,
          current: SONGS[3], up_next: [SONGS[4], SONGS[0], SONGS[9]] },
      ],
    };
  };

  const within = (days, device) => plays.filter((p) => p.started >= Date.now() / 1000 - days * 86400 && (!device || p.device === device));

  const stats = (days, device) => {
    const rows = within(days, device), count = (key) => {
      const m = new Map();
      for (const r of rows) m.set(r[key], (m.get(r[key]) || 0) + 1);
      return [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10);
    };
    const perDay = new Map();
    for (const r of rows) {
      const d = new Date(r.started * 1000);
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      perDay.set(key, (perDay.get(key) || 0) + 1);
    }
    return {
      days, plays: rows.length, listened_minutes: Math.round(rows.reduce((a, r) => a + r.played_ms, 0) / 60000),
      songs: new Set(rows.map((r) => r.video_id)).size, artists: new Set(rows.map((r) => r.artist)).size,
      top_songs: count("video_id").map(([id, n]) => ({ ...SONGS.find((s) => s.video_id === id), plays: n })),
      top_artists: count("artist").map(([artist, n]) => ({ artist, plays: n })),
      per_day: [...perDay.entries()].sort().map(([day, n]) => ({ day, plays: n })),
    };
  };

  const CHECKS = [
    ["Configuration", "ok", "Public address https://music.example.com, 1 skill ID(s)"],
    ["Data folder", "ok", "/data is writable"],
    ["Deno (JavaScript for yt-dlp)", "ok", "deno 2.9.8"],
    ["yt-dlp", "ok", "2026.11.23 (3 days old)"],
    ["YouTube Music search", "ok", "found Never Gonna Give You Up by Rick Astley"],
    ["Audio from YouTube", "ok", "downloaded in 3.4s"],
    ["Public address", "ok", "https://music.example.com/healthz answered over HTTPS"],
    ["Alexa has reached this server", "ok", "last request 2 min ago"],
    ["YouTube Music account", "ok", "Signed in: your library is available"],
  ].map(([name, status, detail]) => ({ name, status, detail, hint: "", link: "" }));

  window.ECHO_TUNES_DEMO = async (path) => {
    const url = new URL(path, "http://demo"), q = url.searchParams, days = Number(q.get("days") || 7);
    switch (url.pathname) {
      case "/api/now": return now();
      case "/api/devices": return DEVICES;
      case "/api/history": {
        let rows = within(days, q.get("device"));
        const term = (q.get("q") || "").toLowerCase();
        if (term) rows = rows.filter((r) => r.title.toLowerCase().includes(term) || r.artist.toLowerCase().includes(term));
        const off = Number(q.get("offset") || 0), lim = Number(q.get("limit") || 50);
        return { enabled: true, days: HISTORY_DAYS, plays: rows.slice(off, off + lim) };
      }
      case "/api/stats": return stats(days, q.get("device"));
      case "/api/health":
        return { status: "ok", version: "0.2 (demo)", uptime_seconds: Math.round(Date.now() / 1000 - loaded + 3 * 86400), memory_mb: 78.4,
                 youtube: "ok", last_audio_ok: Date.now() / 1000 - 40, last_audio_error: null, last_error: "", signed_in: true,
                 history_days: HISTORY_DAYS, history_plays: plays.length };
      case "/api/setup": return { status: "ok", checks: CHECKS, time: Date.now() / 1000 - 30 };
      case "/api/test-play": return { demo: true };
      default: throw new Error(`demo has no ${url.pathname}`);
    }
  };
})();
