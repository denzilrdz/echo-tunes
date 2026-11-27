// localStorage that never throws (private windows, blocked storage): a missing value is fine.

export function load<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export function save(key: string, value: unknown): void {
  try {
    if (value === null || value === undefined) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable: the choice lasts until the page closes */
  }
}

export const KEYS = {
  favourite: "et.favourite", // "browser" or an Echo's short ID
  welcomed: "et.welcomed", // the "Where should music play?" sheet was answered
  echoTip: "et.echoTip", // the one-time "Echo plays your picks after the current song" note
  theme: "et.theme", // stored as a plain string by boot.js's reader, see theme.ts
  recent: "et.recentSearches",
} as const;
