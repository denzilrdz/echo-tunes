// Can the app reach its server? Network failures (no answer at all, not an HTTP error) are
// counted; two in a row mean "unreachable": the app shows a full explanation, keeps what it
// already has on screen, turns actions off, and checks /api/health again with a growing
// pause (10 s, 20 s, 40 s, at most 60 s) until the server answers.
//
// The usual cause at home: a browser or phone using its own "secure DNS" / "Private DNS"
// provider resolves the dashboard's name to the public address instead of the LAN one.

import { create } from "zustand";

export const FAILURES_TO_OFFLINE = 2;
const FIRST_RETRY_MS = 10_000;
const MAX_RETRY_MS = 60_000;

type Check = () => Promise<boolean>;

interface ConnectionStore {
  failures: number; // network failures in a row
  offline: boolean;
  checking: boolean;
  retryIn: number; // ms until the next automatic check (0 while online)
  nextRetryAt: number;
  failed: () => void;
  succeeded: () => void;
  retryNow: () => Promise<void>;
}

let timer: ReturnType<typeof setTimeout> | null = null;
let check: Check = async () => false;

/** How to ask the server if it's there (set by api.ts: a GET of /api/health). */
export function setHealthCheck(fn: Check): void {
  check = fn;
}

export const useConnection = create<ConnectionStore>((set, get) => {
  const schedule = (delay: number) => {
    if (timer) clearTimeout(timer);
    set({ retryIn: delay, nextRetryAt: Date.now() + delay });
    timer = setTimeout(() => void get().retryNow(), delay);
  };
  return {
    failures: 0,
    offline: false,
    checking: false,
    retryIn: 0,
    nextRetryAt: 0,
    failed: () => {
      const failures = get().failures + 1;
      const offline = failures >= FAILURES_TO_OFFLINE;
      set({ failures, offline });
      if (offline && !get().checking && !timer) schedule(FIRST_RETRY_MS);
    },
    succeeded: () => {
      if (timer) clearTimeout(timer);
      timer = null;
      if (get().failures || get().offline) set({ failures: 0, offline: false, retryIn: 0 });
    },
    retryNow: async () => {
      if (timer) clearTimeout(timer);
      timer = null;
      if (get().checking) return;
      set({ checking: true });
      let ok = false;
      try {
        ok = await check();
      } catch {
        ok = false;
      }
      set({ checking: false });
      if (ok) {
        get().succeeded();
        return;
      }
      if (!get().offline)
        set({ offline: true, failures: Math.max(get().failures, FAILURES_TO_OFFLINE) });
      schedule(Math.min(MAX_RETRY_MS, Math.max(FIRST_RETRY_MS, get().retryIn * 2)));
    },
  };
});

/** For tests: forget everything. */
export function resetConnection(): void {
  if (timer) clearTimeout(timer);
  timer = null;
  useConnection.setState({
    failures: 0,
    offline: false,
    checking: false,
    retryIn: 0,
    nextRetryAt: 0,
  });
}
