// Light, dark or follow the system. boot.js applies the saved choice before the first paint;
// this keeps it in step afterwards (system changes, the Settings switch). The PWA's title and
// status bar follow through the theme-color meta tags.

import { pageParams } from "./params";

export type ThemeChoice = "system" | "light" | "dark";

const BG = { dark: "#0B0B0F", light: "#FAFAFB" } as const;
const media = () => window.matchMedia("(prefers-color-scheme: dark)");

export function savedTheme(): ThemeChoice {
  try {
    const v = localStorage.getItem("et.theme");
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

export function forcedTheme(): ThemeChoice | null {
  const v = pageParams().get("theme");
  return v === "light" || v === "dark" ? v : null;
}

export function applyTheme(choice: ThemeChoice = forcedTheme() ?? savedTheme()): "light" | "dark" {
  const dark = choice === "dark" || (choice === "system" && media().matches);
  const mode = dark ? "dark" : "light";
  const root = document.documentElement;
  root.dataset.theme = mode;
  root.style.colorScheme = mode;
  for (const m of document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')) {
    // With a manual choice both tags carry the chosen background; otherwise each its own.
    const own = (m.getAttribute("media") ?? "").includes("dark") ? BG.dark : BG.light;
    m.setAttribute("content", choice === "system" ? own : BG[mode]);
  }
  window.dispatchEvent(new CustomEvent("et-theme", { detail: mode }));
  return mode;
}

export function setTheme(choice: ThemeChoice): void {
  try {
    if (choice === "system") localStorage.removeItem("et.theme");
    else localStorage.setItem("et.theme", choice);
  } catch {
    /* not saved; still applied */
  }
  applyTheme(choice);
}

export function watchSystemTheme(): void {
  media().addEventListener("change", () => {
    if ((forcedTheme() ?? savedTheme()) === "system") applyTheme("system");
  });
}

export const currentMode = (): "light" | "dark" =>
  document.documentElement.dataset.theme === "light" ? "light" : "dark";

/** ECHO_TUNES_APP_COLOR: the server puts it in a meta tag; it only changes the accent. */
export function applyAccent(): void {
  const meta = document.querySelector<HTMLMetaElement>('meta[name="echo-tunes-accent"]');
  const hex = meta?.content.trim() ?? "";
  if (!/^#[0-9a-fA-F]{6}$/.test(hex)) return;
  const n = Number.parseInt(hex.slice(1), 16);
  const lin = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  const lum = 0.2126 * lin(n >> 16) + 0.7152 * lin((n >> 8) & 255) + 0.0722 * lin(n & 255);
  const root = document.documentElement.style;
  root.setProperty("--accent-custom", hex);
  // Black or white text on it, whichever reads better.
  root.setProperty("--accent-custom-fg", lum > 0.36 ? "#0B0B0F" : "#FFFFFF");
}
