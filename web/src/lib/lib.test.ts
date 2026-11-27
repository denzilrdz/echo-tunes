import { afterEach, describe, expect, it, vi } from "vitest";
import { testPlay } from "@/routes/server";
import { ApiError, get, post, setTransport } from "./api";
import { sized, tint } from "./art";
import { ago, mmss } from "./format";
import { applyAccent, applyTheme, setTheme } from "./theme";

afterEach(() => {
  setTransport(null);
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("format", () => {
  it("formats times", () => {
    expect(mmss(0)).toBe("0:00");
    expect(mmss(221_000)).toBe("3:41");
    expect(mmss(3_723_000)).toBe("1:02:03");
    expect(mmss(null)).toBe("–");
    expect(ago(1000, 1030)).toBe("just now");
    expect(ago(1000, 1000 + 7200)).toBe("2 h ago");
  });
});

describe("artwork", () => {
  it("asks Google for the size it draws", () => {
    expect(sized("https://lh3.googleusercontent.com/x=w60-h60-l90-rj", 544)).toBe(
      "https://lh3.googleusercontent.com/x=w544-h544-l90-rj",
    );
    expect(sized("https://i.ytimg.com/vi/abc/mqdefault.jpg", 544)).toBe(
      "https://i.ytimg.com/vi/abc/mqdefault.jpg",
    );
  });

  it("keeps the tint calm: dark L 0.30-0.45, light L 0.85-0.92, limited chroma", () => {
    const dark = tint([255, 0, 0], "dark") ?? "";
    const light = tint([255, 0, 0], "light") ?? "";
    const [, dl, dc] = dark.match(/oklch\(([\d.]+) ([\d.]+)/) ?? [];
    const [, ll, lc] = light.match(/oklch\(([\d.]+) ([\d.]+)/) ?? [];
    expect(Number(dl)).toBeGreaterThanOrEqual(0.3);
    expect(Number(dl)).toBeLessThanOrEqual(0.45);
    expect(Number(dc)).toBeLessThanOrEqual(0.12);
    expect(Number(ll)).toBeGreaterThanOrEqual(0.85);
    expect(Number(ll)).toBeLessThanOrEqual(0.92);
    expect(Number(lc)).toBeLessThanOrEqual(0.12);
    expect(tint(null, "dark")).toBeNull();
  });
});

describe("theme", () => {
  it("keeps the PWA's theme-color on the page background, never the accent", () => {
    const meta = (attrs: Record<string, string>) => {
      const m = document.createElement("meta");
      for (const [k, v] of Object.entries(attrs)) m.setAttribute(k, v);
      document.head.append(m);
    };
    meta({ name: "theme-color", content: "#0B0B0F", media: "(prefers-color-scheme: dark)" });
    meta({ name: "theme-color", content: "#FAFAFB", media: "(prefers-color-scheme: light)" });
    meta({ name: "echo-tunes-accent", content: "#aa3300" });
    setTheme("light");
    const metas = [...document.querySelectorAll('meta[name="theme-color"]')];
    expect(metas.map((m) => m.getAttribute("content"))).toEqual(["#FAFAFB", "#FAFAFB"]);
    expect(document.documentElement.dataset.theme).toBe("light");
    setTheme("system");
    expect(metas.map((m) => m.getAttribute("content"))).toEqual(["#0B0B0F", "#FAFAFB"]);
    applyAccent();
    const style = document.documentElement.style;
    expect(style.getPropertyValue("--accent-custom")).toBe("#aa3300");
    expect(style.getPropertyValue("--accent-custom-fg")).toBe("#FFFFFF");
    expect(metas.map((m) => m.getAttribute("content"))).not.toContain("#aa3300");
    applyTheme("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});

describe("api", () => {
  it("sends actions as same-origin JSON and reports the server's message", async () => {
    const fetch = vi.fn(async () =>
      Response.json({ detail: "Start something on this Echo by voice first." }, { status: 409 }),
    );
    vi.stubGlobal("fetch", fetch);
    await expect(post("/api/play/echo", { device: "x" })).rejects.toMatchObject({
      status: 409,
      message: "Start something on this Echo by voice first.",
    });
    const [, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
    expect(init.credentials).toBe("same-origin");
  });

  it("goes to the sign-in page on 401", async () => {
    vi.stubGlobal("fetch", async () => Response.json({ detail: "sign in" }, { status: 401 }));
    const replace = vi.fn();
    vi.stubGlobal("location", { ...window.location, replace });
    await expect(get("/api/now")).rejects.toBeInstanceOf(ApiError);
    expect(replace).toHaveBeenCalledWith("/login");
  });

  it("test play uses POST, and GET on older servers (405)", async () => {
    const calls: string[] = [];
    setTransport(async (method) => {
      calls.push(method);
      if (method === "POST") throw new ApiError("Method Not Allowed", 405);
      return { url: "https://music.example.com/stream/x.m4a" };
    });
    await expect(testPlay()).resolves.toMatchObject({ url: expect.stringContaining("example") });
    expect(calls).toEqual(["POST", "GET"]);
  });
});
