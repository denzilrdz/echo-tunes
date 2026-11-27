// Shapes of the dashboard's JSON API (src/echo_tunes/dashboard.py).

export type Kind = "song" | "album" | "artist" | "playlist";

/** A browse or search result (music/browse.py Item.to_dict). */
export interface Item {
  kind: Kind;
  id: string; // video ID for songs; playlist, album browse or artist channel ID otherwise
  title: string;
  subtitle: string;
  image: string | null;
  duration: number | null;
}

export interface Track {
  video_id: string;
  title: string;
  artist: string;
  duration: number | null;
  image?: string | null;
}

export interface EchoSummary {
  id: string;
  name: string;
  playing: boolean;
  current: Track | null;
  updated: number;
  position_ms: number;
}

export interface PlayerInfo {
  actions: boolean;
  experimental_skip: boolean;
  signed_in: boolean;
  echos: EchoSummary[];
}

export interface NowDevice extends EchoSummary {
  source: string;
  shuffle: boolean;
  loop: boolean;
  queue_length: number;
  queue_position: number;
  up_next: Track[];
}

export interface NowResponse {
  time: number;
  devices: NowDevice[];
}

export interface Health {
  status: "ok" | "degraded";
  version: string;
  uptime_seconds: number;
  memory_mb: number;
  youtube: "ok" | "failing" | "unknown";
  last_audio_ok: number | null;
  last_audio_error: number | null;
  last_error: string;
  signed_in: boolean;
  history_days: number;
  history_plays: number;
}

export interface HistoryRow {
  id: number;
  device: string;
  device_name: string;
  video_id: string;
  title: string;
  artist: string;
  duration: number | null;
  source: string;
  started: number;
  ended: number | null;
  played_ms: number | null;
  status: "finished" | "playing" | "stopped" | "skipped" | "failed" | string;
}

export interface HistoryResponse {
  enabled: boolean;
  days: number;
  plays: HistoryRow[];
}

export interface Stats {
  days: number;
  plays: number;
  listened_minutes: number;
  songs: number;
  artists: number;
  top_songs: { video_id: string; title: string; artist: string; plays: number }[];
  top_artists: { artist: string; plays: number }[];
  per_day: { day: string; plays: number }[];
}

export interface SetupCheck {
  name: string;
  status: "ok" | "warn" | "fail" | "info";
  detail: string;
  hint: string;
  link: string;
}

export interface SetupResult {
  status: string;
  checks: SetupCheck[];
  time: number;
}

export interface Device {
  id: string;
  name: string;
}

export interface MoodGroup {
  title: string;
  categories: { title: string; params: string }[];
}

export interface Explore {
  charts: Item[];
  artists: Item[];
  moods: MoodGroup[];
}

export interface HomeResponse {
  sections: { title: string; items: Item[] }[];
}

export interface TracksResponse {
  title: string;
  tracks: Track[];
}

export interface TestPlay {
  url?: string;
  title?: string;
  artist?: string;
  demo?: boolean;
  error?: string;
}

export type QueueMode = "now" | "next" | "queue";
