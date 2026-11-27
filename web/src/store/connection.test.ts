import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { get, setTransport } from "@/lib/api";
import { resetConnection, setHealthCheck, useConnection } from "./connection";

const conn = () => useConnection.getState();

beforeEach(() => {
  vi.useFakeTimers();
  resetConnection();
  setTransport(null);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("connection", () => {
  it("one failure is a blip; two in a row mean the server can't be reached", () => {
    conn().failed();
    expect(conn().offline).toBe(false);
    conn().succeeded();
    conn().failed();
    expect(conn().offline).toBe(false);
    conn().failed();
    expect(conn().offline).toBe(true);
  });

  it("retries by itself every 10 s, then 20, 40, at most 60, and clears when it answers", async () => {
    let up = false;
    const health = vi.fn(async () => up);
    setHealthCheck(health);
    conn().failed();
    conn().failed();
    expect(conn().retryIn).toBe(10_000);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(health).toHaveBeenCalledTimes(1);
    expect(conn().offline).toBe(true);
    expect(conn().retryIn).toBe(20_000);
    await vi.advanceTimersByTimeAsync(20_000);
    expect(conn().retryIn).toBe(40_000);
    await vi.advanceTimersByTimeAsync(40_000);
    expect(conn().retryIn).toBe(60_000);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(conn().retryIn).toBe(60_000);
    up = true;
    await vi.advanceTimersByTimeAsync(60_000);
    expect(conn().offline).toBe(false);
    expect(conn().failures).toBe(0);
  });

  it("Try again checks at once", async () => {
    setHealthCheck(async () => true);
    conn().failed();
    conn().failed();
    await conn().retryNow();
    expect(conn().offline).toBe(false);
  });

  it("only network failures count: an HTTP error means the server is there", async () => {
    vi.stubGlobal("fetch", async () => {
      throw new TypeError("Failed to fetch");
    });
    await expect(get("/api/now")).rejects.toMatchObject({ status: 0 });
    await expect(get("/api/now")).rejects.toMatchObject({ status: 0 });
    expect(conn().offline).toBe(true);
    vi.stubGlobal("fetch", async () => Response.json({ detail: "nope" }, { status: 500 }));
    await expect(get("/api/now")).rejects.toMatchObject({ status: 500 });
    expect(conn().offline).toBe(false);
  });
});
