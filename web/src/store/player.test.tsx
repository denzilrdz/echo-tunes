import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TrackList } from "@/components/music";
import { ApiError, setTransport } from "@/lib/api";
import type { PlayerInfo, Track } from "@/lib/types";
import { BROWSER, echoIdle, showing, usePlayer } from "./player";
import { useToasts } from "./toast";
import { useUi } from "./ui";

vi.mock("@tanstack/react-router", () => ({ useNavigate: () => vi.fn() }));

const song = (n: number): Track => ({
  video_id: `vid${String(n).padStart(8, "0")}`,
  title: `Song ${n}`,
  artist: "Artist",
  duration: 200,
});
const now = Date.now() / 1000;
const INFO: PlayerInfo = {
  actions: true,
  experimental_skip: false,
  signed_in: false,
  echos: [
    {
      id: "LIVINGROOM01",
      name: "Living room",
      playing: true,
      current: song(9),
      updated: now,
      position_ms: 1000,
    },
    {
      id: "BEDROOM00001",
      name: "Bedroom",
      playing: false,
      current: null,
      updated: now - 9e5,
      position_ms: 0,
    },
  ],
};

let calls: { method: string; path: string; body: unknown }[] = [];
beforeEach(() => {
  calls = [];
  setTransport(async (method, path, body) => {
    calls.push({ method, path, body });
    if (path === "/api/play/echo" && (body as { device: string }).device === "BEDROOM00001")
      throw new ApiError("Start something on this Echo by voice first.", 409);
    if (path === "/api/play/stream-link") return { demo: true };
    if (path.startsWith("/api/browse/tracks")) return { title: "", tracks: [] };
    return { status: "ok", note: "Plays after the current song." };
  });
  usePlayer.setState({ info: INFO, target: BROWSER, favourite: null, queue: [], index: -1 });
  useToasts.setState({ toasts: [] });
  useUi.setState({ sheet: null });
});
afterEach(() => setTransport(null));

const lastToast = () => useToasts.getState().toasts.at(-1);

describe("player", () => {
  it("remembers the favourite device", () => {
    usePlayer.getState().setFavourite("LIVINGROOM01");
    expect(JSON.parse(localStorage.getItem("et.favourite") ?? "null")).toBe("LIVINGROOM01");
    expect(localStorage.getItem("et.welcomed")).toBe("true");
  });

  it("plays in the browser, then queues next and at the end", async () => {
    const p = usePlayer.getState();
    await p.play([song(1), song(2), song(3)], "Playlist: x");
    expect(usePlayer.getState().index).toBe(0);
    expect(calls.some((c) => c.path === "/api/play/played")).toBe(true);
    await p.enqueue([song(7)], "next", "x");
    await p.enqueue([song(8)], "queue", "x");
    expect(usePlayer.getState().queue.map((t) => t.title)).toEqual([
      "Song 1",
      "Song 7",
      "Song 2",
      "Song 3",
      "Song 8",
    ]);
    p.removeAt(1);
    expect(usePlayer.getState().queue.map((t) => t.title)[1]).toBe("Song 2");
  });

  it("queues on an Echo and says when it plays", async () => {
    usePlayer.setState({ target: "LIVINGROOM01" });
    await usePlayer.getState().play([song(1)], "Search: x");
    const call = calls.find((c) => c.path === "/api/play/echo");
    expect(call?.body).toMatchObject({ device: "LIVINGROOM01", mode: "now" });
    expect(lastToast()?.text).toContain("queued on Living room · plays after “Song 9”");
  });

  it("offers to play here when the Echo is idle", async () => {
    usePlayer.setState({ target: "BEDROOM00001" });
    await usePlayer.getState().enqueue([song(1)], "next", "x");
    const t = lastToast();
    expect(t?.tone).toBe("error");
    expect(t?.action?.label).toBe("Play here instead");
    t?.action?.run();
    expect(usePlayer.getState().target).toBe(BROWSER);
  });

  it("refuses actions without a dashboard password, and says why", async () => {
    usePlayer.setState({ info: { ...INFO, actions: false } });
    await usePlayer.getState().play([song(1)], "x");
    expect(calls).toEqual([]);
    expect(lastToast()?.text).toContain("dashboard password");
  });

  it("shows the target Echo's song and knows idle Echos", () => {
    usePlayer.setState({ target: "LIVINGROOM01" });
    const s = showing(usePlayer.getState());
    expect(s.onEcho && s.track?.title).toBe("Song 9");
    expect(echoIdle(INFO.echos[1])).toBe(true);
    expect(echoIdle(INFO.echos[0])).toBe(false);
  });

  it("explains Echo playback the first time an Echo is chosen", () => {
    usePlayer.getState().setTarget("LIVINGROOM01");
    expect(useUi.getState().sheet).toBe("echoTip");
  });
});

describe("song rows", () => {
  it("say where they play, and are off without a password", () => {
    usePlayer.setState({ target: "LIVINGROOM01" });
    const { unmount } = render(<TrackList tracks={[song(1)]} source="x" />);
    expect(screen.getByRole("button", { name: "Play next Song 1 by Artist" })).toBeEnabled();
    unmount();
    usePlayer.setState({ target: BROWSER, info: { ...INFO, actions: false } });
    render(<TrackList tracks={[song(1)]} source="x" />);
    expect(screen.getByRole("button", { name: "Play Song 1 by Artist" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "More for Song 1" })).toBeInTheDocument();
  });
});
