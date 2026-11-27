// The player: where music goes (this browser or an Echo), the browser's own queue around one
// <audio> element, radio that keeps it going, lock-screen controls, and queueing on an Echo.

import { create } from "zustand";
import { ApiError, get, post, qs } from "@/lib/api";
import { trackArt } from "@/lib/art";
import { KEYS, load, save } from "@/lib/storage";
import type { EchoSummary, PlayerInfo, QueueMode, Track, TracksResponse } from "@/lib/types";
import { useConnection } from "./connection";
import { toast } from "./toast";
import { useUi } from "./ui";

export const BROWSER = "browser";
const MAX_QUEUE = 300;
const IDLE_AFTER = 6 * 3600; // seconds without news from an Echo: it's idle (matches the server)

export interface PlayerStore {
  info: PlayerInfo;
  infoAt: number; // Date.now() when info arrived (to advance an Echo's position)
  loaded: boolean;
  target: string;
  favourite: string | null;
  queue: Track[];
  index: number;
  source: string;
  playing: boolean;
  buffering: boolean;
  position: number; // seconds
  duration: number; // seconds
  setInfo: (info: PlayerInfo) => void;
  setTarget: (id: string) => void;
  setFavourite: (id: string) => void;
  play: (tracks: Track[], source: string, opts?: { radio?: boolean }) => Promise<void>;
  enqueue: (tracks: Track[], mode: Exclude<QueueMode, "now">, source: string) => Promise<void>;
  playAt: (i: number) => Promise<void>;
  removeAt: (i: number) => void;
  toggle: () => void;
  next: () => void;
  prev: () => void;
  seek: (seconds: number) => void;
  skipEcho: () => Promise<void>;
}

const EMPTY: PlayerInfo = { actions: false, experimental_skip: false, signed_in: false, echos: [] };

// One <audio> for the whole app (not in the DOM: it plays all the same, and survives
// navigation). The demo has no audio: a timer pretends to play instead.
export const audio: HTMLAudioElement | null = typeof Audio === "undefined" ? null : new Audio();
if (audio) audio.preload = "auto";
let fakeTimer: ReturnType<typeof setInterval> | null = null;
let fake = false;

const plain = (t: Track) => ({
  video_id: t.video_id,
  title: (t.title || "Unknown").slice(0, 200),
  artist: (t.artist || "").slice(0, 200),
  duration: t.duration ?? null,
});

export const echoName = (e: Pick<EchoSummary, "id" | "name"> | undefined): string =>
  e ? e.name || `Echo …${e.id.slice(-6)}` : "Echo";

export function echoIdle(e: EchoSummary | undefined, now = Date.now() / 1000): boolean {
  return !e?.current || (!e.playing && now - e.updated > IDLE_AFTER);
}

export const browserLabel = (): string =>
  typeof window !== "undefined" && window.matchMedia?.("(pointer: coarse)").matches
    ? "This phone"
    : "This browser";

export const usePlayer = create<PlayerStore>((set, getState) => {
  const s = () => getState();
  const onEcho = () => s().target !== BROWSER;
  const targetEcho = () => s().info.echos.find((e) => e.id === s().target);
  const needActions = (): boolean => {
    if (useConnection.getState().offline) {
      toast("Can't reach your echo-tunes server right now.", { tone: "error" });
      return false;
    }
    if (s().info.actions) return true;
    toast("Playing from here needs a dashboard password on the server.", { tone: "error" });
    return false;
  };

  let radioBusy = false;
  async function extendWithRadio(videoId: string): Promise<void> {
    if (radioBusy) return;
    radioBusy = true;
    try {
      const r = await get<TracksResponse>(`/api/browse/tracks${qs({ kind: "song", id: videoId })}`);
      const have = new Set(s().queue.map((t) => t.video_id));
      const more = r.tracks.filter((t) => !have.has(t.video_id));
      if (more.length) set({ queue: [...s().queue, ...more].slice(0, MAX_QUEUE) });
    } catch {
      /* the queue just ends */
    } finally {
      radioBusy = false;
    }
  }

  function stopFake() {
    if (fakeTimer) clearInterval(fakeTimer);
    fakeTimer = null;
  }

  function startFake(t: Track) {
    stopFake();
    fake = true;
    set({ playing: true, buffering: false, position: 0, duration: t.duration ?? 200 });
    fakeTimer = setInterval(() => {
      if (!s().playing) return;
      const pos = s().position + 1;
      if (pos >= s().duration) s().next();
      else set({ position: pos });
    }, 1000);
  }

  async function queueOnEcho(tracks: Track[], mode: QueueMode, source: string): Promise<void> {
    const echo = targetEcho();
    const name = echoName(echo ?? { id: s().target, name: "" });
    try {
      const r = await post<{ placed?: number; note?: string }>("/api/play/echo", {
        device: s().target,
        mode,
        source: source.slice(0, 120),
        tracks: tracks.slice(0, 200).map(plain),
      });
      const what = tracks.length === 1 ? `“${tracks[0]?.title}”` : `${tracks.length} songs`;
      const cur = echo?.current?.title;
      const when =
        mode === "queue"
          ? "at the end of the queue"
          : cur
            ? `after “${cur}”`
            : "after the current song";
      const full = r.note?.includes("full") ? ` ${r.note}` : "";
      toast(`${what} queued on ${name} · plays ${when}.${full}`, {
        tone: full ? "info" : "success",
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      const idle = err instanceof ApiError && (err.status === 409 || err.status === 404);
      toast(
        idle ? `${name} isn't playing echo-tunes. Start it once by voice, or play here.` : msg,
        {
          tone: "error",
          ...(idle
            ? {
                action: {
                  label: "Play here instead",
                  run: () => {
                    s().setTarget(BROWSER);
                    void s().play(tracks, source);
                  },
                },
              }
            : {}),
        },
      );
    }
  }

  return {
    info: EMPTY,
    infoAt: Date.now(),
    loaded: false,
    target: load<string | null>(KEYS.favourite, null) ?? BROWSER,
    favourite: load<string | null>(KEYS.favourite, null),
    queue: [],
    index: -1,
    source: "",
    playing: false,
    buffering: false,
    position: 0,
    duration: 0,

    setInfo: (info) => set({ info, infoAt: Date.now(), loaded: true }),

    setTarget: (id) => {
      const prev = s().target;
      set({ target: id });
      if (id !== BROWSER && prev !== id && !load(KEYS.echoTip, false)) {
        useUi.getState().open("echoTip");
      }
    },

    setFavourite: (id) => {
      save(KEYS.favourite, id);
      save(KEYS.welcomed, true);
      set({ favourite: id });
    },

    play: async (tracks, source, opts = {}) => {
      if (!tracks.length || !needActions()) return;
      if (onEcho()) return queueOnEcho(tracks, "now", source);
      set({ queue: tracks.slice(0, MAX_QUEUE), source });
      await s().playAt(0);
      const first = tracks[0];
      if (opts.radio && first) void extendWithRadio(first.video_id);
    },

    enqueue: async (tracks, mode, source) => {
      if (!tracks.length || !needActions()) return;
      if (onEcho()) return queueOnEcho(tracks, mode, source);
      const { queue, index } = s();
      if (index < 0) return s().play(tracks, source);
      const cur = queue[index];
      const ids = new Set(tracks.map((t) => t.video_id));
      const before = queue.slice(0, index).filter((t) => !ids.has(t.video_id));
      const rest = queue.slice(index + 1).filter((t) => !ids.has(t.video_id));
      const add = tracks.filter((t) => t.video_id !== cur?.video_id);
      const merged = [
        ...before,
        ...(cur ? [cur] : []),
        ...(mode === "queue" ? [...rest, ...add] : [...add, ...rest]),
      ].slice(0, MAX_QUEUE);
      set({ queue: merged, index: before.length });
      const what = tracks.length === 1 ? `“${tracks[0]?.title}”` : `${tracks.length} songs`;
      toast(mode === "queue" ? `${what} added to the queue` : `${what} plays next`, {
        tone: "success",
      });
    },

    playAt: async (i) => {
      const t = s().queue[i];
      if (!t) return;
      stopFake();
      fake = false;
      set({ index: i, position: 0, duration: t.duration ?? 0, buffering: true, playing: false });
      updateMediaSession();
      try {
        const r = await post<{ url?: string; demo?: boolean }>("/api/play/stream-link", {
          video_id: t.video_id,
        });
        if (s().queue[s().index]?.video_id !== t.video_id) return; // skipped meanwhile
        if (r.demo || !r.url || !audio) {
          startFake(t);
        } else {
          audio.src = r.url;
          await audio.play();
        }
        void post("/api/play/played", { track: plain(t), source: s().source.slice(0, 120) }).catch(
          () => {},
        );
      } catch (err) {
        set({ buffering: false, playing: false });
        const msg = err instanceof Error ? err.message : String(err);
        const name = (err as DOMException)?.name;
        if (name === "NotSupportedError" || name === "AbortError") {
          // the <audio> error event reports it (and skips)
        } else if (name === "NotAllowedError") {
          toast("Tap play to start: the browser blocked autoplay.");
        } else toast(`Couldn't play “${t.title}”: ${msg}`, { tone: "error" });
      }
      updateMediaSession();
      if (i >= s().queue.length - 3) void extendWithRadio(t.video_id);
    },

    removeAt: (i) => {
      const { queue, index } = s();
      if (i === index || i < 0 || i >= queue.length) return;
      set({ queue: queue.filter((_, k) => k !== i), index: i < index ? index - 1 : index });
    },

    toggle: () => {
      if (s().index < 0) return;
      if (fake) {
        set({ playing: !s().playing });
        updateMediaSession();
        return;
      }
      if (!audio) return;
      if (audio.paused) void audio.play().catch(() => {});
      else audio.pause();
    },

    next: () => {
      const { index, queue } = s();
      if (index + 1 < queue.length) void s().playAt(index + 1);
      else {
        set({ playing: false });
        if (fake) stopFake();
      }
    },

    prev: () => {
      if (s().position > 3) return s().seek(0);
      if (s().index > 0) void s().playAt(s().index - 1);
      else s().seek(0);
    },

    seek: (seconds) => {
      const t = Math.max(0, Math.min(seconds, s().duration || seconds));
      if (fake) set({ position: t });
      else if (audio && Number.isFinite(audio.duration)) audio.currentTime = t;
      set({ position: t });
    },

    skipEcho: async () => {
      try {
        const r = await post<{ note: string }>("/api/play/skip", { device: s().target });
        toast(r.note);
      } catch (err) {
        toast(err instanceof Error ? err.message : String(err), { tone: "error" });
      }
    },
  };
});

// ---------- the <audio> element -> the store ----------
if (audio) {
  const st = usePlayer.setState;
  let failures = 0; // songs in a row that wouldn't load
  audio.addEventListener("playing", () => {
    failures = 0;
    st({ playing: true, buffering: false });
  });
  audio.addEventListener("pause", () => st({ playing: false }));
  audio.addEventListener("waiting", () => st({ buffering: true }));
  audio.addEventListener("timeupdate", () => st({ position: audio.currentTime }));
  audio.addEventListener("durationchange", () => {
    if (Number.isFinite(audio.duration)) st({ duration: audio.duration });
  });
  audio.addEventListener("ended", () => usePlayer.getState().next());
  audio.addEventListener("error", () => {
    if (!audio.getAttribute("src")) return;
    st({ buffering: false, playing: false });
    failures++;
    if (failures >= 2) {
      // Probably not this song: the browser can't reach the server's public address.
      toast("Songs won't load in this browser. Is the public address reachable from here?", {
        tone: "error",
        action: { label: "Test play", run: () => location.assign("#/server/setup") },
      });
      return;
    }
    toast("This song couldn't be loaded; skipping.", { tone: "error" });
    setTimeout(() => usePlayer.getState().next(), 1500);
  });
  audio.addEventListener("play", updateMediaSession);
  audio.addEventListener("pause", updateMediaSession);
}

// ---------- lock screen and media keys ----------
function updateMediaSession(): void {
  if (typeof navigator === "undefined" || !("mediaSession" in navigator)) return;
  const { queue, index, playing } = usePlayer.getState();
  const t = queue[index];
  if (!t) return;
  const art = trackArt(t, 512);
  navigator.mediaSession.metadata = new MediaMetadata({
    title: t.title,
    artist: t.artist,
    artwork: art && !art.startsWith("data:") ? [{ src: art, sizes: "512x512" }] : [],
  });
  navigator.mediaSession.playbackState = playing ? "playing" : "paused";
}

if (typeof navigator !== "undefined" && "mediaSession" in navigator) {
  const p = () => usePlayer.getState();
  const handlers: [MediaSessionAction, MediaSessionActionHandler][] = [
    ["play", () => p().toggle()],
    ["pause", () => p().toggle()],
    ["nexttrack", () => p().next()],
    ["previoustrack", () => p().prev()],
    ["seekto", (d) => d.seekTime != null && p().seek(d.seekTime)],
  ];
  for (const [action, fn] of handlers) {
    try {
      navigator.mediaSession.setActionHandler(action, fn);
    } catch {
      /* not supported here */
    }
  }
  usePlayer.subscribe((st, old) => {
    if (st.playing !== old.playing || st.index !== old.index) updateMediaSession();
  });
}

// ---------- what the player bar shows ----------
export interface Showing {
  track: Track | null;
  playing: boolean;
  position: number;
  duration: number;
  where: string;
  onEcho: boolean;
  echo: EchoSummary | undefined;
  idle: boolean;
}

/** The song, progress and place to show: the target Echo's, or this browser's own. */
export function showing(st: PlayerStore, now = Date.now()): Showing {
  if (st.target === BROWSER) {
    const track = st.queue[st.index] ?? null;
    return {
      track,
      playing: st.playing,
      position: st.position,
      duration: st.duration || track?.duration || 0,
      where: browserLabel(),
      onEcho: false,
      echo: undefined,
      idle: false,
    };
  }
  const echo = st.info.echos.find((e) => e.id === st.target);
  const track = echo?.current ?? null;
  const dur = track?.duration ?? 0;
  let pos = (echo?.position_ms ?? 0) / 1000;
  if (echo?.playing) pos += (now - st.infoAt) / 1000;
  return {
    track,
    playing: !!echo?.playing,
    position: dur ? Math.min(pos, dur) : pos,
    duration: dur,
    where: echoName(echo ?? { id: st.target, name: "" }),
    onEcho: true,
    echo,
    idle: echoIdle(echo),
  };
}
