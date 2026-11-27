import { useEffect, useState, useSyncExternalStore } from "react";
import { dominantColour, tint } from "./art";
import { currentMode } from "./theme";

/** "light" or "dark", following the Settings switch and the system. */
export function useMode(): "light" | "dark" {
  return useSyncExternalStore(
    (cb) => {
      window.addEventListener("et-theme", cb);
      return () => window.removeEventListener("et-theme", cb);
    },
    currentMode,
    () => "dark",
  );
}

/** A calm colour from a cover, for gradients: a CSS colour, or null until it's known. */
export function useArtColour(url: string | null | undefined): string | null {
  const mode = useMode();
  const [colour, setColour] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    if (!url) {
      setColour(null);
      return;
    }
    void dominantColour(url).then((rgb) => {
      if (live) setColour(tint(rgb, mode));
    });
    return () => {
      live = false;
    };
  }, [url, mode]);
  return colour;
}

export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (cb) => {
      const m = window.matchMedia(query);
      m.addEventListener("change", cb);
      return () => m.removeEventListener("change", cb);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}

/** Re-render every `ms` while `active` (progress bars of things playing elsewhere). */
export function useTick(active: boolean, ms = 1000): number {
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setN((x) => x + 1), ms);
    return () => clearInterval(id);
  }, [active, ms]);
  return n;
}

export function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}
