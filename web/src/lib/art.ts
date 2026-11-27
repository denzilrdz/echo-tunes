// Artwork URLs and the colour pulled from them for the tinted headers and the Now Playing sheet.

import type { Item, Track } from "./types";

type ThumbFn = (videoId: string) => string;
let demoThumb: ThumbFn | null = null;
/** The demo's screenshot mode replaces every song's artwork with generated pictures. */
export function setThumbnails(fn: ThumbFn | null): void {
  demoThumb = fn;
}

/** A YouTube video thumbnail. Music videos are 16:9 with the square cover in the middle. */
export function thumb(videoId: string, size: "small" | "large" = "small"): string {
  if (demoThumb) return demoThumb(videoId);
  const name = size === "large" ? "hqdefault" : "mqdefault";
  return `https://i.ytimg.com/vi/${encodeURIComponent(videoId)}/${name}.jpg`;
}

/** Google image URLs carry their size (=w120-h120...): ask for the size we draw. */
export function sized(url: string, px: number): string {
  return url.replace(/=w\d+-h\d+(-[a-z0-9-]+)?$/i, `=w${px}-h${px}-l90-rj`);
}

export function trackArt(t: Pick<Track, "video_id" | "image">, px = 120): string {
  if (t.image) return sized(t.image, px);
  return thumb(t.video_id, px > 200 ? "large" : "small");
}

export function itemArt(item: Item, px = 240): string {
  if (item.image) return sized(item.image, px);
  if (item.kind === "song") return thumb(item.id, px > 200 ? "large" : "small");
  return "";
}

/** i.ytimg.com thumbnails letterbox the cover: zoom so a square frame shows just the cover. */
export const isVideoThumb = (url: string): boolean =>
  url.includes("i.ytimg.com/vi/") && !url.includes("maxres");

// ---------- colour ----------
const cache = new Map<string, [number, number, number] | null>();

/** The cover's dominant colourful hue as RGB, or null when the image can't be read. */
export function dominantColour(url: string): Promise<[number, number, number] | null> {
  if (!url) return Promise.resolve(null);
  if (cache.has(url)) return Promise.resolve(cache.get(url) ?? null);
  return new Promise((resolve) => {
    const img = new Image();
    // Google's image hosts allow anonymous CORS reads; a host that doesn't simply fails here
    // (this image is separate from the one on screen, so nothing visible breaks).
    if (!url.startsWith("data:")) img.crossOrigin = "anonymous";
    img.decoding = "async";
    img.onload = () => {
      let rgb: [number, number, number] | null = null;
      try {
        rgb = pick(img);
      } catch {
        rgb = null; // tainted canvas
      }
      if (cache.size > 300) cache.clear();
      cache.set(url, rgb);
      resolve(rgb);
    };
    img.onerror = () => {
      cache.set(url, null);
      resolve(null);
    };
    img.src = url;
  });
}

function pick(img: HTMLImageElement): [number, number, number] | null {
  const size = 24;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return null;
  // Middle of the picture only: thumbnails have black bars at the edges.
  const w = img.naturalWidth || size;
  const h = img.naturalHeight || size;
  const side = Math.min(w, h) * 0.8;
  ctx.drawImage(img, (w - side) / 2, (h - side) / 2, side, side, 0, 0, size, size);
  const data = ctx.getImageData(0, 0, size, size).data;
  const buckets = new Map<number, { n: number; r: number; g: number; b: number; s: number }>();
  let ar = 0;
  let ag = 0;
  let ab = 0;
  let count = 0;
  for (let i = 0; i < data.length; i += 4) {
    const r = data[i] ?? 0;
    const g = data[i + 1] ?? 0;
    const b = data[i + 2] ?? 0;
    ar += r;
    ag += g;
    ab += b;
    count++;
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    const sat = max === 0 ? 0 : (max - min) / max;
    if (sat < 0.22 || max < 40 || max > 250) continue; // greys, near-black, blown highlights
    const hue = hueOf(r, g, b);
    const key = Math.round(hue / 24);
    const bucket = buckets.get(key) ?? { n: 0, r: 0, g: 0, b: 0, s: 0 };
    bucket.n++;
    bucket.r += r;
    bucket.g += g;
    bucket.b += b;
    bucket.s += sat;
    buckets.set(key, bucket);
  }
  let best: { n: number; r: number; g: number; b: number; s: number } | null = null;
  for (const v of buckets.values())
    if (!best || v.n * (0.5 + v.s / v.n) > best.n * (0.5 + best.s / best.n)) best = v;
  if (best && best.n >= 8) return [best.r / best.n, best.g / best.n, best.b / best.n];
  return count ? [ar / count, ag / count, ab / count] : null;
}

function hueOf(r: number, g: number, b: number): number {
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const d = max - min || 1;
  let h = 0;
  if (max === r) h = ((g - b) / d) % 6;
  else if (max === g) h = (b - r) / d + 2;
  else h = (r - g) / d + 4;
  return (h * 60 + 360) % 360;
}

// sRGB -> OKLCH and back, to keep the tint calm and readable in either theme.
function toOklch([r, g, b]: [number, number, number]): [number, number, number] {
  const lin = (c: number) => {
    const s = c / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  const [lr, lg, lb] = [lin(r), lin(g), lin(b)];
  const l = Math.cbrt(0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb);
  const m = Math.cbrt(0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb);
  const s = Math.cbrt(0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb);
  const L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
  const A = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const B = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  return [L, Math.hypot(A, B), (Math.atan2(B, A) * 180) / Math.PI];
}

/** A CSS colour for the theme: dark L 0.30-0.45, light L 0.85-0.92, chroma at most 0.12. */
export function tint(rgb: [number, number, number] | null, mode: "light" | "dark"): string | null {
  if (!rgb) return null;
  const [L, C, H] = toOklch(rgb);
  const l = mode === "dark" ? clamp(L * 0.6, 0.3, 0.45) : clamp(0.85 + L * 0.07, 0.85, 0.92);
  const c = clamp(C, 0, 0.12);
  return `oklch(${l.toFixed(3)} ${c.toFixed(3)} ${H.toFixed(1)})`;
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
