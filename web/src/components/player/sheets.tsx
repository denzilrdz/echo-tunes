import { ChevronDown, Info, ListMusic, Mic, Speaker, Star } from "lucide-react";
import { useState } from "react";
import { trackArt } from "@/lib/art";
import { cn } from "@/lib/cn";
import { ago } from "@/lib/format";
import { useArtColour } from "@/lib/hooks";
import { useTarget } from "@/lib/play";
import { KEYS, save } from "@/lib/storage";
import type { EchoSummary } from "@/lib/types";
import { BROWSER, browserLabel, echoIdle, echoName, usePlayer } from "@/store/player";
import { useUi } from "@/store/ui";
import { Artwork } from "../ui/artwork";
import { Equalizer } from "../ui/bits";
import { Button, IconButton } from "../ui/button";
import { Sheet } from "../ui/sheet";
import { TargetIcon } from "./bars";
import { TransportControls, useShowing } from "./controls";
import { Progress } from "./progress";
import { UpNext } from "./up-next";

const VOICE = "“Alexa, ask my tunes to play …”";

/** The full-screen Now Playing view: artwork-coloured, with honest Echo controls. */
export function NowPlayingSheet() {
  const sheet = useUi((u) => u.sheet);
  const { open, close } = useUi.getState();
  const s = useShowing();
  const seek = usePlayer((st) => st.seek);
  const skip = usePlayer((st) => st.info.experimental_skip);
  const setTarget = usePlayer((st) => st.setTarget);
  const [queue, setQueue] = useState(false);
  const art = s.track ? trackArt(s.track, 720) : null;
  const colour = useArtColour(s.track ? trackArt(s.track, 120) : null);
  return (
    <Sheet
      open={sheet === "now"}
      onOpenChange={(o) => (o ? open("now") : close())}
      title="Now playing"
      layout="full"
      bare
      style={colour ? ({ "--np-art": colour } as React.CSSProperties) : undefined}
      className="bg-bg"
    >
      <div className="relative flex min-h-full flex-col overflow-hidden">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(130%_70%_at_50%_0%,var(--np-art,var(--art))_0%,transparent_75%)] opacity-90 transition-[background] duration-500"
        />
        {art && (
          <img
            src={art}
            alt=""
            aria-hidden
            className="pointer-events-none absolute -top-[10%] left-1/2 h-[60%] w-[140%] -translate-x-1/2 object-cover opacity-25 blur-[60px] saturate-150"
          />
        )}
        <div className="relative mx-auto flex w-full max-w-[560px] flex-1 flex-col px-6 pt-[max(12px,env(safe-area-inset-top))] pb-[max(20px,env(safe-area-inset-bottom))]">
          <div className="flex items-center gap-2">
            <IconButton label="Close" onClick={close} className="-ml-2 text-fg">
              <ChevronDown className="size-7" />
            </IconButton>
            <button
              type="button"
              className="mx-auto flex min-w-0 flex-col items-center rounded-[12px] px-3 py-1 hover:bg-fg/5"
              onClick={() => open("devices")}
            >
              <span className="text-[11px] font-semibold tracking-[0.12em] text-fg-muted uppercase">
                Playing on
              </span>
              <span
                className={cn(
                  "flex items-center gap-1.5 truncate text-[14px] font-semibold",
                  s.onEcho && "text-accent",
                )}
              >
                <TargetIcon onEcho={s.onEcho} className="size-4" />
                {s.where}
                {s.onEcho && <span className="font-normal text-fg-muted">· Echo</span>}
              </span>
            </button>
            <IconButton
              label={queue ? "Show artwork" : "Up next"}
              onClick={() => setQueue((q) => !q)}
              className={cn("-mr-2", queue && "bg-fg/10 text-fg")}
            >
              <ListMusic />
            </IconButton>
          </div>

          {queue ? (
            <div className="thin-scroll -mx-4 mt-4 min-h-0 flex-1 overflow-y-auto">
              <UpNext />
            </div>
          ) : (
            <div className="flex flex-1 flex-col justify-center py-6">
              <div className="mx-auto w-full max-w-[min(84vw,420px,48dvh)]">
                <Artwork
                  key={art ?? "none"}
                  src={art}
                  size={420}
                  eager
                  className="art-fade aspect-square w-full rounded-[18px] shadow-[0_30px_60px_-20px_rgb(0_0_0/0.6)]"
                />
              </div>
            </div>
          )}

          <div className="mt-auto">
            <div className="min-w-0">
              <h2 className="truncate text-[22px] font-bold tracking-tight md:text-[26px]">
                {s.track?.title ?? "Nothing playing"}
              </h2>
              <p className="truncate text-[16px] text-fg-muted">
                {s.track?.artist ??
                  (s.onEcho ? `Nothing from echo-tunes on ${s.where} yet` : "Pick a song to start")}
              </p>
            </div>
            <Progress
              className="mt-4"
              tone="onArt"
              position={s.position}
              duration={s.duration}
              onSeek={s.onEcho ? undefined : seek}
            />
            <div className="mt-3">
              <TransportControls size="lg" />
            </div>
            {s.onEcho && (
              <p className="mt-4 flex items-start justify-center gap-2 text-center text-[13px] text-fg-muted">
                <Mic className="mt-0.5 size-4 shrink-0" aria-hidden />
                <span>
                  Say “Alexa, pause” or “Alexa, previous”. Songs you pick play after this one
                  {skip ? "; skip now is in beta." : "."}
                </span>
              </p>
            )}
            {s.onEcho && s.idle && (
              <div className="mt-4 rounded-[14px] bg-fg/6 p-4 text-[14px]">
                <p>
                  <b>{s.where}</b> isn't playing echo-tunes. Start it once by voice: {VOICE}. A web
                  page can't wake an idle Echo.
                </p>
                <Button
                  size="sm"
                  variant="primary"
                  className="mt-3"
                  onClick={() => setTarget(BROWSER)}
                >
                  Play here instead
                </Button>
              </div>
            )}
            <div className="mt-5 flex justify-center gap-3">
              <Button variant="ghost" size="sm" onClick={() => setQueue((q) => !q)}>
                <ListMusic /> {queue ? "Artwork" : "Up next"}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => open("devices")}>
                <Speaker /> Devices
              </Button>
            </div>
          </div>
        </div>
      </div>
    </Sheet>
  );
}

export function QueueSheet() {
  const sheet = useUi((u) => u.sheet);
  const { open, close } = useUi.getState();
  const { name } = useTarget();
  return (
    <Sheet
      open={sheet === "queue"}
      onOpenChange={(o) => (o ? open("queue") : close())}
      title="Up next"
      description={`Playing on ${name}`}
    >
      <div className="pb-6">
        <UpNext />
      </div>
    </Sheet>
  );
}

// ---------- devices ----------

interface Target {
  id: string;
  name: string;
  echo?: EchoSummary;
}

function useTargets(): Target[] {
  const echos = usePlayer((s) => s.info.echos);
  return [
    { id: BROWSER, name: browserLabel() },
    ...echos.map((e) => ({ id: e.id, name: echoName(e), echo: e })),
  ];
}

function TargetRow({
  t,
  selected,
  favourite,
  onPick,
  onFavourite,
}: {
  t: Target;
  selected: boolean;
  favourite: boolean;
  onPick: () => void;
  onFavourite?: () => void;
}) {
  const onEcho = t.id !== BROWSER;
  const idle = onEcho && echoIdle(t.echo);
  const status = !onEcho
    ? "Plays here, with lock-screen controls"
    : t.echo?.playing && t.echo.current
      ? `${t.echo.current.title} · ${t.echo.current.artist}`
      : idle
        ? `Idle${t.echo?.updated ? ` · last played ${ago(t.echo.updated)}` : ""}`
        : t.echo?.current
          ? `Paused · ${t.echo.current.title}`
          : "Idle";
  return (
    <div
      className={cn(
        "flex items-center gap-1 rounded-[14px] p-1 transition-colors",
        selected ? "bg-accent-soft" : "hover:bg-surface-2",
      )}
    >
      <button
        type="button"
        onClick={onPick}
        aria-pressed={selected}
        className="flex min-w-0 flex-1 items-center gap-3 rounded-[12px] p-2 text-left"
      >
        <span
          className={cn(
            "grid size-11 shrink-0 place-items-center rounded-full",
            selected ? "bg-accent text-accent-fg" : "bg-surface-2 text-fg-muted",
          )}
        >
          {onEcho && t.echo?.playing ? (
            <Equalizer playing />
          ) : (
            <TargetIcon onEcho={onEcho} className="size-5" />
          )}
        </span>
        <span className="min-w-0 flex-1">
          <span
            className={cn(
              "flex items-center gap-2 text-[15px] font-semibold",
              selected && "text-accent",
            )}
          >
            <span className="truncate">{t.name}</span>
            {favourite && (
              <Star
                className="size-3.5 shrink-0 fill-current text-warning"
                aria-label="Favourite"
              />
            )}
          </span>
          <span className="block truncate text-[13px] text-fg-muted">{status}</span>
        </span>
      </button>
      {onFavourite && (
        <IconButton
          label={favourite ? `${t.name} is your favourite` : `Make ${t.name} your favourite`}
          onClick={onFavourite}
          className={favourite ? "text-warning" : ""}
          aria-pressed={favourite}
        >
          <Star className={favourite ? "fill-current" : ""} />
        </IconButton>
      )}
    </div>
  );
}

/** Spotify-Connect-style picker: where music plays, and which device is the favourite. */
export function DeviceSheet() {
  const sheet = useUi((u) => u.sheet);
  const { open, close } = useUi.getState();
  const target = usePlayer((s) => s.target);
  const favourite = usePlayer((s) => s.favourite);
  const { setTarget, setFavourite } = usePlayer.getState();
  const targets = useTargets();
  const current = targets.find((t) => t.id === target);
  const idle = current && current.id !== BROWSER && echoIdle(current.echo);
  return (
    <Sheet
      open={sheet === "devices"}
      onOpenChange={(o) => (o ? open("devices") : close())}
      title="Play on"
      description="Pick where music plays. The star marks your favourite: it's chosen every time you open the app."
    >
      <div className="space-y-1 px-3 pb-4">
        {targets.map((t) => (
          <TargetRow
            key={t.id}
            t={t}
            selected={t.id === target}
            favourite={t.id === favourite}
            onPick={() => {
              setTarget(t.id);
              if (!useUi.getState().sheet || useUi.getState().sheet === "devices") close();
            }}
            onFavourite={() => setFavourite(t.id)}
          />
        ))}
        {targets.length === 1 && (
          <p className="flex gap-2 px-3 pt-3 text-[13px] text-fg-muted">
            <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
            <span>
              Echos show up here after they've played something from echo-tunes. Say {VOICE} once.
            </span>
          </p>
        )}
        {idle && (
          <div className="mx-1 mt-3 rounded-[14px] bg-surface-2 p-4 text-[14px]">
            <b>{current?.name}</b> is idle. Start it once by voice: {VOICE}. Then you can queue
            songs on it from here.
          </div>
        )}
      </div>
    </Sheet>
  );
}

/** First run: "Where should music play?" */
export function WelcomeSheet() {
  const sheet = useUi((u) => u.sheet);
  const { open, close } = useUi.getState();
  const { setTarget, setFavourite } = usePlayer.getState();
  const targets = useTargets();
  const pick = (id: string) => {
    setFavourite(id);
    close(); // first: choosing an Echo may open the one-time Echo explainer
    setTarget(id);
  };
  return (
    <Sheet
      open={sheet === "welcome"}
      onOpenChange={(o) => {
        if (o) open("welcome");
        else {
          save(KEYS.welcomed, true);
          close();
        }
      }}
      title="Where should music play?"
      description="Pick your favourite. It's selected every time you open echo-tunes, and you can switch any time."
    >
      <div className="space-y-1 px-3 pb-6">
        {targets.map((t) => (
          <TargetRow
            key={t.id}
            t={t}
            selected={false}
            favourite={false}
            onPick={() => pick(t.id)}
          />
        ))}
        {targets.length === 1 && (
          <p className="px-3 pt-3 text-[13px] text-fg-muted">
            No Echo has played echo-tunes yet. Say {VOICE} and it appears here.
          </p>
        )}
      </div>
    </Sheet>
  );
}

/** One-time note the first time an Echo is chosen. */
export function EchoTipSheet() {
  const sheet = useUi((u) => u.sheet);
  const { open, close } = useUi.getState();
  const done = () => {
    save(KEYS.echoTip, true);
    close();
  };
  return (
    <Sheet
      open={sheet === "echoTip"}
      onOpenChange={(o) => (o ? open("echoTip") : done())}
      title="Playing on an Echo"
    >
      <div className="px-5 pb-6 text-[15px]">
        <ul className="space-y-3 text-fg-muted">
          <li className="flex gap-3">
            <ListMusic className="mt-0.5 size-5 shrink-0 text-accent" aria-hidden />
            <span>
              <b className="text-fg">Your picks play after the current song.</b> Alexa only lets a
              skill change the music when the Echo checks in.
            </span>
          </li>
          <li className="flex gap-3">
            <Mic className="mt-0.5 size-5 shrink-0 text-accent" aria-hidden />
            <span>
              <b className="text-fg">Use your voice to pause or go back:</b> “Alexa, pause”, “Alexa,
              previous”.
            </span>
          </li>
        </ul>
        <Button variant="primary" className="mt-6 w-full" onClick={done}>
          Got it
        </Button>
      </div>
    </Sheet>
  );
}

/** Every app-wide sheet; loaded on demand (see AppShell). */
export default function AllSheets() {
  return (
    <>
      <NowPlayingSheet />
      <QueueSheet />
      <DeviceSheet />
      <WelcomeSheet />
      <EchoTipSheet />
    </>
  );
}
