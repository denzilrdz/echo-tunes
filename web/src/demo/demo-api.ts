// The public demo (GitHub Pages): no server, so this answers every API call the app makes with
// sample data, the way a real echo-tunes would. Nothing plays and nothing is sent anywhere.
//
// ?shots (screenshot mode, scripts/screenshots.py): made-up songs and generated artwork, so the
// README, landing page and social images never contain anyone's real album art or names.
// Extra screenshot switches: &sheet=now|devices|queue|welcome, &target=browser.

import { ApiError, setTransport } from "@/lib/api";
import { setThumbnails } from "@/lib/art";
import { pageParams } from "@/lib/params";
import type { Item, Kind, Track } from "@/lib/types";
import { usePlayer } from "@/store/player";
import { type Sheet, useUi } from "@/store/ui";

const params = pageParams();
const SHOTS = params.has("shots");

const REAL: [string, string, string, number][] = [
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
];
const MADE_UP: [string, string, number][] = [
  ["Neon Harbour", "The Paper Lanterns", 214],
  ["Monsoon Letters", "Aarav & The Tide", 247],
  ["Slow Satellites", "Juniper Vale", 231],
  ["Paper Kites", "Mira Okafor", 198],
  ["Goa After Rain", "Konkan Coast Collective", 262],
  ["Static Bloom", "Night Ferry", 225],
  ["Lighthouse Radio", "Ines Marlow", 241],
  ["Copper Skies", "The Late Arrivals", 209],
  ["Second Window", "Rafa Quinn", 256],
  ["Velvet Highway", "Saltwater Static", 233],
  ["Tidal Clock", "Noor & Ellis", 219],
  ["Northbound", "Harbour Lights", 244],
  ["Small Hours", "Odette Rain", 237],
];

const SONGS: Track[] = REAL.map(([video_id, title, artist, duration], i) => {
  const fake = MADE_UP[i];
  return SHOTS && fake
    ? { video_id, title: fake[0], artist: fake[1], duration: fake[2] }
    : { video_id, title, artist, duration };
});

// ---------- generated artwork ----------
const hash = (text: string): number => {
  let h = 7;
  for (const ch of text) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return h;
};

/** An abstract "album cover": a gradient, a sun or rings, and soft shapes. */
export function cover(seed: string): string {
  const h = hash(seed);
  const hue = h % 360;
  const hue2 = (hue + 40 + (h % 80)) % 360;
  const style = h % 4;
  const shapes = [
    `<circle cx='70' cy='34' r='20' fill='hsl(${(hue + 180) % 360} 90% 72% / .85)'/><path d='M0 74 Q25 58 50 70 T100 64 V100 H0Z' fill='hsl(${hue2} 60% 18% / .7)'/>`,
    `<g fill='none' stroke='hsl(0 0% 100% / .35)' stroke-width='1.4'><circle cx='50' cy='50' r='14'/><circle cx='50' cy='50' r='24'/><circle cx='50' cy='50' r='34'/><circle cx='50' cy='50' r='44'/></g><circle cx='50' cy='50' r='6' fill='hsl(0 0% 100% / .8)'/>`,
    `<rect x='14' y='14' width='44' height='44' rx='4' fill='hsl(${(hue + 150) % 360} 85% 65% / .8)' transform='rotate(-12 36 36)'/><rect x='42' y='42' width='44' height='44' rx='22' fill='hsl(${hue2} 80% 30% / .75)'/>`,
    `<path d='M0 60 L35 28 L58 50 L72 38 L100 66 V100 H0Z' fill='hsl(${hue2} 55% 14% / .75)'/><circle cx='26' cy='26' r='9' fill='hsl(48 100% 85% / .9)'/>`,
  ][style];
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='hsl(${hue} 75% 58%)'/><stop offset='1' stop-color='hsl(${hue2} 70% 24%)'/></linearGradient></defs><rect width='100' height='100' fill='url(#g)'/>${shapes}</svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

// ---------- browse data ----------
const songItem = (s: Track): Item => ({
  kind: "song",
  id: s.video_id,
  title: s.title,
  subtitle: s.artist,
  image: SHOTS ? cover(s.title) : null,
  duration: s.duration,
});
const list = (kind: Kind, title: string, subtitle: string): Item => ({
  kind,
  id: `${kind}-${title.replace(/\W+/g, "-")}`,
  title,
  subtitle,
  image: cover(title),
  duration: null,
});
const PLAYLISTS = [
  "Morning Commute",
  "Rainy Day Acoustic",
  "Late Night Drive",
  "Focus Flow",
  "Sunday Brunch",
  "Throwback Party",
].map((t) => list("playlist", t, "Playlist"));
const MIXES = ["My Supermix", "Discover Mix", "New Release Mix", "Replay Mix"].map((t) =>
  list("playlist", t, "Mixed for you"),
);
const CHARTS = [
  "Top 100 Songs",
  "Trending Now",
  "Top Music Videos",
  "Hindi Top 50",
  "Indie Rising",
].map((t) => list("playlist", t, "Chart"));
const ARTISTS = [
  "Juniper Vale",
  "Mira Okafor",
  "Night Ferry",
  "Ines Marlow",
  "Rafa Quinn",
  "Odette Rain",
].map((t) => list("artist", t, "Artist"));
const ALBUMS = ["Paper Kites", "Harbour Lights", "Copper Skies", "Second Window"].map((t) =>
  list("album", t, "Album · 2026"),
);
const MOODS = [
  {
    title: "Moods & moments",
    categories: [
      "Chill",
      "Commute",
      "Energy boosters",
      "Feel good",
      "Focus",
      "Party",
      "Romance",
      "Sleep",
      "Workout",
    ].map((t) => ({ title: t, params: `demo-${t.replace(/\W+/g, "-")}` })),
  },
  {
    title: "Genres",
    categories: [
      "Bollywood",
      "Indie",
      "Pop",
      "Hip-hop",
      "Jazz",
      "Classical",
      "Electronic",
      "Rock",
    ].map((t) => ({
      title: t,
      params: `demo-${t.replace(/\W+/g, "-")}`,
    })),
  },
];
const tracksFor = (id: string): Track[] => {
  const h = hash(id) % SONGS.length;
  return [...SONGS.slice(h), ...SONGS.slice(0, h)].map((s) => ({
    ...s,
    image: SHOTS ? cover(s.title) : null,
  }));
};

const titleOf = (id: string): string =>
  id === "LM"
    ? "Liked songs"
    : id
        .replace(/^(playlist|album|artist)-/, "")
        .replace(/-demo-.*$/, "")
        .replaceAll("-", " ") || "Songs";

// ---------- Echos, history, stats ----------
const loaded = Date.now() / 1000;
const ECHOS = [
  { id: "DEMO0LIVING1", name: "Living room" },
  { id: "DEMO0KITCHEN", name: "Kitchen" },
  { id: "DEMO0BEDROOM", name: "Bedroom" },
];
const DEVICES = [...ECHOS, { id: "browser", name: "Web player" }];
const HISTORY_DAYS = 15;
const SOURCES = SHOTS
  ? ['Asked for "neon harbour"', "Radio after Neon Harbour", "Playlist: Road Trip", "Liked songs"]
  : [
      'Asked for "blinding lights"',
      "Radio after Blinding Lights",
      "Playlist: Road Trip",
      "Liked songs",
    ];

let seed = 7; // seeded, so the demo looks the same on every visit
const rand = () => {
  seed = (seed * 16807) % 2147483647;
  return (seed - 1) / 2147483646;
};
const pick = <T>(a: T[]): T => a[Math.floor(rand() * a.length)] as T;

const plays: Record<string, unknown>[] = [];
for (let t = loaded - HISTORY_DAYS * 86400; t < loaded - 600; t += 1800 + rand() * 9000) {
  const hour = new Date(t * 1000).getHours();
  if (hour < 7 || hour > 23) continue; // nobody listens at 3 am
  const s = pick(SONGS);
  const d = pick(DEVICES);
  const r = rand();
  const status = r < 0.78 ? "finished" : r < 0.9 ? "skipped" : r < 0.97 ? "stopped" : "failed";
  const dur = s.duration ?? 200;
  const played = status === "finished" ? dur * 1000 : Math.round(rand() * dur * 1000);
  plays.push({
    id: plays.length + 1,
    device: d.id,
    device_name: d.name,
    ...s,
    source: d.id === "browser" ? "Dashboard player" : pick(SOURCES),
    started: t,
    ended: t + played / 1000,
    played_ms: played,
    status,
  });
}
plays.reverse();

function now() {
  const t = Date.now() / 1000;
  const playingFor = (t - loaded) % 200;
  const img = (s: Track) => ({ ...s, image: SHOTS ? cover(s.title) : null });
  return {
    time: t,
    devices: [
      {
        id: "DEMO0LIVING1",
        name: "Living room",
        playing: true,
        position_ms: Math.round((61 + playingFor) * 1000),
        updated: t - 5,
        source: SHOTS ? "Radio after Neon Harbour" : "Radio after Blinding Lights",
        shuffle: false,
        loop: false,
        queue_length: 26,
        queue_position: 3,
        current: img(SONGS[5] as Track),
        up_next: SONGS.slice(6, 12).map(img),
      },
      {
        id: "DEMO0KITCHEN",
        name: "Kitchen",
        playing: false,
        position_ms: 94000,
        updated: t - 3600,
        source: "Playlist: Road Trip",
        shuffle: true,
        loop: false,
        queue_length: 12,
        queue_position: 4,
        current: img(SONGS[3] as Track),
        up_next: [SONGS[4], SONGS[0], SONGS[9]].map((s) => img(s as Track)),
      },
      {
        id: "DEMO0BEDROOM",
        name: "Bedroom",
        playing: false,
        position_ms: 120000,
        updated: t - 2 * 86400,
        source: "Liked songs",
        shuffle: false,
        loop: false,
        queue_length: 40,
        queue_position: 9,
        current: img(SONGS[10] as Track),
        up_next: [],
      },
    ],
  };
}

const within = (days: number, device: string | null) =>
  plays.filter(
    (p) =>
      (p.started as number) >= Date.now() / 1000 - days * 86400 && (!device || p.device === device),
  );

function stats(days: number, device: string | null) {
  const rows = within(days, device);
  const count = (key: string) => {
    const m = new Map<unknown, number>();
    for (const r of rows) m.set(r[key], (m.get(r[key]) ?? 0) + 1);
    return [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10);
  };
  const perDay = new Map<string, number>();
  for (const r of rows) {
    const d = new Date((r.started as number) * 1000);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    perDay.set(key, (perDay.get(key) ?? 0) + 1);
  }
  return {
    days,
    plays: rows.length,
    listened_minutes: Math.round(rows.reduce((a, r) => a + (r.played_ms as number), 0) / 60000),
    songs: new Set(rows.map((r) => r.video_id)).size,
    artists: new Set(rows.map((r) => r.artist)).size,
    top_songs: count("video_id").map(([id, n]) => ({
      ...SONGS.find((s) => s.video_id === id),
      plays: n,
    })),
    top_artists: count("artist").map(([artist, n]) => ({ artist, plays: n })),
    per_day: [...perDay.entries()].sort().map(([day, n]) => ({ day, plays: n })),
  };
}

const CHECKS = [
  ["Configuration", "Public address https://music.example.com, 1 skill ID(s)"],
  ["Data folder", "/data is writable"],
  ["Deno (JavaScript for yt-dlp)", "deno 2.9.8"],
  ["yt-dlp", "2026.11.23 (3 days old)"],
  ["YouTube Music search", "found a song for a test search"],
  ["Audio from YouTube", "downloaded in 3.4s"],
  ["Public address", "https://music.example.com/healthz answered over HTTPS"],
  ["Alexa has reached this server", "last request 2 min ago"],
  ["YouTube Music account", "Signed in: your library is available"],
].map(([name, detail]) => ({ name, status: "ok", detail, hint: "", link: "" }));

function player() {
  return {
    actions: true,
    experimental_skip: false,
    signed_in: true,
    echos: now().devices.map((d) => ({
      id: d.id,
      name: d.name,
      playing: d.playing,
      current: d.current,
      updated: d.updated,
      position_ms: d.position_ms,
    })),
  };
}

async function answer(method: "GET" | "POST", path: string, body?: unknown): Promise<unknown> {
  await new Promise((r) => setTimeout(r, SHOTS ? 0 : 120 + Math.random() * 180)); // feel real
  const url = new URL(path, "http://demo");
  const q = url.searchParams;
  const days = Number(q.get("days") || 7);
  const b = (body ?? {}) as Record<string, unknown>;
  switch (`${method} ${url.pathname}`) {
    case "GET /api/player":
      return player();
    case "GET /api/browse/home":
      return {
        sections: [
          { title: "Quick picks", items: SONGS.slice(0, 12).map(songItem) },
          { title: "Mixed for you", items: MIXES },
          { title: "Playlists for your mood", items: PLAYLISTS },
          { title: "New albums", items: ALBUMS },
        ],
      };
    case "GET /api/browse/explore":
      return { charts: CHARTS, artists: ARTISTS, moods: MOODS };
    case "GET /api/browse/library":
      return {
        items: [
          { ...list("playlist", "Liked songs", "Your likes"), id: "LM" },
          ...PLAYLISTS.slice(0, 5),
          ...MIXES.slice(0, 2),
        ],
      };
    case "GET /api/browse/mood":
      return { items: PLAYLISTS.map((p) => ({ ...p, id: `${p.id}-${q.get("params")}` })) };
    case "GET /api/browse/tracks":
      return { title: titleOf(q.get("id") ?? ""), tracks: tracksFor(q.get("id") ?? "") };
    case "GET /api/search": {
      const term = (q.get("q") ?? "").toLowerCase();
      const kind = q.get("kind") ?? "song";
      if (kind === "video") {
        const hits = SONGS.filter((s) => `${s.title} ${s.artist}`.toLowerCase().includes(term));
        const videos = [...hits, ...SONGS.filter((s) => !hits.includes(s))].slice(0, 8);
        return {
          kind,
          items: videos.map((s) => ({ ...songItem(s), title: `${s.title} (live)` })),
        };
      }
      if (kind === "song") {
        const hits = SONGS.filter((s) => `${s.title} ${s.artist}`.toLowerCase().includes(term));
        return {
          kind,
          items: [...hits, ...SONGS.filter((s) => !hits.includes(s))].slice(0, 12).map(songItem),
        };
      }
      const pool = kind === "album" ? ALBUMS : kind === "artist" ? ARTISTS : PLAYLISTS;
      const hits = pool.filter((i) => i.title.toLowerCase().includes(term));
      return { kind, items: [...hits, ...pool.filter((i) => !hits.includes(i))] };
    }
    case "POST /api/play/stream-link":
      return { demo: true };
    case "POST /api/play/played":
      return { status: "ok" };
    case "POST /api/play/echo": {
      if (b.device === "DEMO0BEDROOM")
        throw new ApiError("Start something on this Echo by voice first.", 409);
      const n = Array.isArray(b.tracks) ? b.tracks.length : 0;
      return {
        placed: n,
        note: b.mode === "queue" ? "Added to the end." : "Plays after the current song.",
      };
    }
    case "POST /api/play/skip":
      return { cut: 0, note: "Demo: on your server this skips (if turned on)." };
    case "POST /api/history/clear":
      return { removed: 0 };
    case "POST /api/test-play":
    case "GET /api/test-play":
      return { demo: true };
    case "POST /api/logout":
    case "POST /api/logout/all":
      return { status: "ok" };
    case "GET /api/now":
      return now();
    case "GET /api/devices":
      return DEVICES;
    case "GET /api/history": {
      let rows = within(days, q.get("device"));
      const term = (q.get("q") ?? "").toLowerCase();
      if (term) rows = rows.filter((r) => `${r.title} ${r.artist}`.toLowerCase().includes(term));
      const off = Number(q.get("offset") || 0);
      const lim = Number(q.get("limit") || 50);
      return { enabled: true, days: HISTORY_DAYS, plays: rows.slice(off, off + lim) };
    }
    case "GET /api/stats":
      return stats(days, q.get("device"));
    case "GET /api/health":
      return {
        status: "ok",
        version: "0.4 (demo)",
        uptime_seconds: Math.round(Date.now() / 1000 - loaded + 3 * 86400),
        memory_mb: 78.4,
        youtube: "ok",
        last_audio_ok: Date.now() / 1000 - 40,
        last_audio_error: null,
        last_error: "",
        signed_in: true,
        history_days: HISTORY_DAYS,
        history_plays: plays.length,
      };
    case "GET /api/setup":
      return { status: "ok", checks: CHECKS, time: Date.now() / 1000 - 30 };
    default:
      throw new ApiError(`The demo has no ${method} ${url.pathname}`, 404);
  }
}

export function install(): void {
  setTransport(answer);
  if (!SHOTS) return;
  setThumbnails((id) => cover(SONGS.find((s) => s.video_id === id)?.title ?? id));
  // Screenshots: a favourite Echo, a song in the browser queue, and an optional open sheet.
  const target = params.get("target") === "browser" ? "browser" : "DEMO0LIVING1";
  usePlayer.setState({ favourite: "DEMO0LIVING1", target });
  if (target === "browser") {
    const queue = SONGS.slice(0, 8).map((s) => ({ ...s, image: cover(s.title) }));
    usePlayer.setState({
      queue,
      index: 0,
      source: "Quick picks",
      playing: true,
      position: 74,
      duration: queue[0]?.duration ?? 200,
    });
  }
  const sheet = params.get("sheet");
  if (sheet && ["now", "devices", "queue", "welcome"].includes(sheet)) {
    setTimeout(() => useUi.getState().open(sheet as Sheet), 300);
  }
}
