// Talks to the dashboard's JSON API. The public demo (GitHub Pages) has no server: it swaps in
// a fake transport (src/demo/demo-api.ts) before the app starts.

import { setHealthCheck, useConnection } from "@/store/connection";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export type Transport = (method: "GET" | "POST", path: string, body?: unknown) => Promise<unknown>;

let fake: Transport | null = null;

/** Replace the network with a function (the demo, tests). */
export function setTransport(t: Transport | null): void {
  fake = t;
}

export const isDemo = (): boolean => fake !== null;

/** Where the sign-in page is; also where a 401 sends you. */
export function goToSignIn(): void {
  location.replace("/login");
}

async function request<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
  if (fake) return (await fake(method, path, body)) as T;
  const init: RequestInit = {
    method,
    headers: { Accept: "application/json" },
    cache: "no-store",
    credentials: "same-origin",
  };
  if (method === "POST") {
    init.headers = { ...init.headers, "Content-Type": "application/json" };
    init.body = JSON.stringify(body ?? {});
  }
  let r: Response;
  try {
    r = await fetch(path, init);
  } catch {
    useConnection.getState().failed(); // no answer at all (not an HTTP error)
    throw new ApiError("Can't reach your echo-tunes server.", 0);
  }
  useConnection.getState().succeeded();
  if (r.status === 401 && path !== "/api/login") {
    goToSignIn();
    throw new ApiError("Signed out", 401);
  }
  const data: unknown = await r.json().catch(() => ({}));
  // /api/health answers 503 with a full report when YouTube is failing: still useful.
  if (!r.ok && !(r.status === 503 && path === "/api/health")) {
    const detail = (data as { detail?: unknown }).detail;
    throw new ApiError(typeof detail === "string" ? detail : `Error ${r.status}`, r.status);
  }
  return data as T;
}

export const get = <T>(path: string): Promise<T> => request<T>("GET", path);
export const post = <T>(path: string, body?: unknown): Promise<T> => request<T>("POST", path, body);

export const qs = (params: Record<string, string | number | null | undefined>): string => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params))
    if (v !== null && v !== undefined && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
};

// The connection screen's "Try again": any answer from /api/health means the server is there.
setHealthCheck(async () => {
  if (fake) return true;
  try {
    await fetch("/api/health", { cache: "no-store", credentials: "same-origin" });
    return true;
  } catch {
    return false;
  }
});
