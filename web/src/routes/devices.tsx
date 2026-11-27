import { Check, Mic, Speaker, Star } from "lucide-react";
import type * as React from "react";
import { PageHeader, ServerLink } from "@/components/page";
import { TargetIcon } from "@/components/player/bars";
import { Progress } from "@/components/player/progress";
import { Artwork } from "@/components/ui/artwork";
import { EmptyState, Equalizer, Skeleton } from "@/components/ui/bits";
import { Button } from "@/components/ui/button";
import { trackArt } from "@/lib/art";
import { cn } from "@/lib/cn";
import { ago } from "@/lib/format";
import { useArtColour, useTick } from "@/lib/hooks";
import { useNow } from "@/lib/queries";
import type { EchoSummary, NowDevice, Track } from "@/lib/types";
import { BROWSER, browserLabel, echoIdle, echoName, usePlayer } from "@/store/player";

/** One card per place music can play: this browser and every Echo. */
export function DevicesPage() {
  const echos = usePlayer((s) => s.info.echos);
  const loaded = usePlayer((s) => s.loaded);
  const now = useNow();
  const details = new Map((now.data?.devices ?? []).map((d) => [d.id, d]));
  return (
    <div>
      <PageHeader
        title="Devices"
        subtitle="Where music plays, and what's on each"
        actions={<ServerLink />}
      />
      <div className="grid gap-4 px-4 md:px-8 xl:grid-cols-2">
        <BrowserCard />
        {!loaded && [0, 1].map((i) => <Skeleton key={i} className="h-[236px] rounded-[20px]" />)}
        {echos.map((e) => (
          <EchoCard key={e.id} echo={e} detail={details.get(e.id)} />
        ))}
      </div>
      {loaded && !echos.length && (
        <EmptyState icon={Mic} title="No Echo yet">
          Echos appear here after they've played something from echo-tunes. Say “Alexa, ask my tunes
          to play …” once.
        </EmptyState>
      )}
      <p className="mx-4 mt-6 max-w-2xl text-[13px] text-fg-muted md:mx-8">
        Alexa only lets a skill change what an Echo plays when the Echo checks in, so songs you pick
        play after the current song. Pausing and going back stay with your voice.
      </p>
    </div>
  );
}

function Badge({
  children,
  tone = "plain",
}: {
  children: React.ReactNode;
  tone?: "plain" | "ok" | "beta";
}) {
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center gap-1 rounded-full px-2.5 text-[11.5px] font-semibold",
        tone === "ok" && "bg-success/14 text-success",
        tone === "beta" && "bg-warning/14 text-warning",
        tone === "plain" && "bg-fg/8 text-fg-muted",
      )}
    >
      {children}
    </span>
  );
}

function Shell({
  id,
  name,
  track,
  children,
  badges,
  status,
  playing,
}: {
  id: string;
  name: string;
  track: Track | null | undefined;
  children?: React.ReactNode;
  badges: React.ReactNode;
  status: React.ReactNode;
  playing: boolean;
}) {
  const target = usePlayer((s) => s.target);
  const favourite = usePlayer((s) => s.favourite);
  const { setTarget, setFavourite } = usePlayer.getState();
  const colour = useArtColour(track ? trackArt(track, 120) : null);
  const selected = target === id;
  const onEcho = id !== BROWSER;
  return (
    <article
      aria-label={name}
      className={cn(
        "relative overflow-hidden rounded-[20px] border bg-surface p-5 shadow-elevated transition-colors",
        selected ? "border-accent/60" : "border-border",
      )}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-70 transition-[background] duration-500"
        style={
          colour
            ? { background: `linear-gradient(135deg, ${colour} 0%, transparent 65%)` }
            : undefined
        }
      />
      <div className="relative">
        <div className="flex items-center gap-3">
          <span
            className={cn(
              "grid size-10 shrink-0 place-items-center rounded-full",
              selected ? "bg-accent text-accent-fg" : "bg-fg/8 text-fg-muted",
            )}
          >
            {playing ? <Equalizer playing /> : <TargetIcon onEcho={onEcho} className="size-5" />}
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="flex items-center gap-2 truncate text-[17px] font-bold">
              {name}
              {favourite === id && (
                <Star className="size-4 fill-warning text-warning" aria-label="Favourite" />
              )}
            </h2>
            <p className="truncate text-[13px] text-fg-muted">{status}</p>
          </div>
        </div>
        <div className="mt-4 flex items-center gap-4">
          <Artwork
            src={track ? trackArt(track, 200) : null}
            size={96}
            className="size-20 shadow-lg md:size-24"
          />
          <div className="min-w-0 flex-1">
            <div className="truncate text-[16px] font-semibold">
              {track?.title ?? "Nothing playing"}
            </div>
            <div className="truncate text-[14px] text-fg-muted">{track?.artist ?? "—"}</div>
            {children}
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-1.5">{badges}</div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button
            variant={selected ? "secondary" : "primary"}
            size="sm"
            aria-pressed={selected}
            onClick={() => setTarget(id)}
          >
            {selected ? <Check /> : <Speaker />}
            {selected ? "Selected" : onEcho ? "Play here" : `Play on ${name.toLowerCase()}`}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            aria-pressed={favourite === id}
            onClick={() => setFavourite(id)}
            disabled={favourite === id}
          >
            <Star className={favourite === id ? "fill-current text-warning" : ""} />
            {favourite === id ? "Favourite" : "Make favourite"}
          </Button>
        </div>
      </div>
    </article>
  );
}

function BrowserCard() {
  const st = usePlayer();
  const track = st.queue[st.index] ?? null;
  const name = browserLabel();
  return (
    <Shell
      id={BROWSER}
      name={name}
      track={track}
      playing={st.playing}
      status={track ? (st.playing ? "Playing" : "Paused") : "Ready"}
      badges={
        <>
          <Badge tone="ok">Play · pause · seek</Badge>
          <Badge tone="ok">Lock-screen controls</Badge>
          <Badge>Radio keeps going</Badge>
        </>
      }
    >
      {track && <Progress className="mt-2" position={st.position} duration={st.duration} />}
    </Shell>
  );
}

function EchoCard({ echo, detail }: { echo: EchoSummary; detail: NowDevice | undefined }) {
  const infoAt = usePlayer((s) => s.infoAt);
  const skip = usePlayer((s) => s.info.experimental_skip);
  useTick(echo.playing);
  const idle = echoIdle(echo);
  const dur = echo.current?.duration ?? 0;
  const pos = Math.min(
    dur || Infinity,
    echo.position_ms / 1000 + (echo.playing ? (Date.now() - infoAt) / 1000 : 0),
  );
  const status = echo.playing
    ? `Playing${detail?.source ? ` · ${detail.source}` : ""}`
    : idle
      ? `Idle · last played ${ago(echo.updated)}`
      : `Paused · ${ago(echo.updated)}`;
  const next = detail?.up_next.slice(0, 3) ?? [];
  return (
    <Shell
      id={echo.id}
      name={echoName(echo)}
      track={echo.current}
      playing={echo.playing}
      status={status}
      badges={
        <>
          <Badge tone="ok">Queue songs</Badge>
          <Badge>Voice pause</Badge>
          {skip && <Badge tone="beta">Skip now · beta</Badge>}
          {detail?.shuffle && <Badge>Shuffle</Badge>}
          {detail?.loop && <Badge>Loop</Badge>}
        </>
      }
    >
      {echo.current && <Progress className="mt-2" position={pos} duration={dur} />}
      {idle && (
        <p className="mt-2 text-[12.5px] text-fg-muted">
          Start it once by voice: “Alexa, ask my tunes to play …”
        </p>
      )}
      {next.length > 0 && (
        <div className="mt-2 hidden text-[12.5px] text-fg-muted sm:block">
          <span className="font-semibold text-fg">Up next:</span>{" "}
          {next.map((t) => t.title).join(" · ")}
        </div>
      )}
    </Shell>
  );
}
