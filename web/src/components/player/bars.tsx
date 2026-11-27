import {
  ChevronUp,
  ListMusic,
  MonitorSpeaker,
  Pause,
  Play,
  Smartphone,
  Speaker,
} from "lucide-react";
import { useRef } from "react";
import { trackArt } from "@/lib/art";
import { cn } from "@/lib/cn";
import { useArtColour, useMediaQuery } from "@/lib/hooks";
import { useTarget } from "@/lib/play";
import { usePlayer } from "@/store/player";
import { useUi } from "@/store/ui";
import { Artwork } from "../ui/artwork";
import { Equalizer } from "../ui/bits";
import { IconButton } from "../ui/button";
import { ECHO_PAUSE, TransportControls, useShowing } from "./controls";
import { usePanel } from "./now-panel";
import { Progress, ProgressLine } from "./progress";

export function TargetIcon({ onEcho, className }: { onEcho: boolean; className?: string }) {
  const coarse = typeof window !== "undefined" && window.matchMedia("(pointer: coarse)").matches;
  const Icon = onEcho ? Speaker : coarse ? Smartphone : MonitorSpeaker;
  return <Icon className={className} aria-hidden />;
}

/** "Playing on Living room": always visible, opens the device picker. */
export function DevicePill({ className }: { className?: string }) {
  const { onEcho, name } = useTarget();
  const s = useShowing();
  const open = useUi((u) => u.open);
  return (
    <button
      type="button"
      onClick={() => open("devices")}
      aria-label={`Playing on ${name}. Choose where music plays`}
      className={cn(
        "inline-flex h-9 max-w-full items-center gap-2 rounded-full px-3 text-[13px] font-semibold transition-colors",
        onEcho
          ? "bg-accent-soft text-accent hover:brightness-110"
          : "bg-surface-2 text-fg hover:bg-surface-3",
        className,
      )}
    >
      {s.playing && onEcho ? (
        <Equalizer playing className="text-accent" />
      ) : (
        <TargetIcon onEcho={onEcho} className="size-4 shrink-0" />
      )}
      <span className="truncate">{name}</span>
    </button>
  );
}

/** Phones: the floating mini-player above the tab bar. Tap or swipe up for Now Playing. */
export function MiniPlayer() {
  const s = useShowing();
  const { name, onEcho } = useTarget();
  const open = useUi((u) => u.open);
  const toggle = usePlayer((st) => st.toggle);
  const art = s.track ? trackArt(s.track, 120) : null;
  const colour = useArtColour(art);
  const startY = useRef<number | null>(null);
  return (
    <div
      className="fixed inset-x-0 bottom-[calc(64px+env(safe-area-inset-bottom))] z-40 bg-gradient-to-t from-bg via-bg/95 to-bg/0 px-2 pt-3 pb-1 lg:hidden"
      onPointerDown={(e) => {
        startY.current = e.clientY;
      }}
      onPointerUp={(e) => {
        if (startY.current !== null && startY.current - e.clientY > 30) open("now");
        startY.current = null;
      }}
    >
      <div
        className="relative overflow-hidden rounded-[14px] border border-border/60 bg-elevated shadow-pop"
        style={
          colour
            ? { backgroundColor: `color-mix(in oklch, ${colour} 70%, var(--elevated))` }
            : undefined
        }
      >
        <ProgressLine position={s.position} duration={s.duration} />
        <div className="flex h-14 items-center gap-3 pr-1 pl-2">
          <button
            type="button"
            className="flex min-w-0 flex-1 items-center gap-3 text-left"
            onClick={() => open("now")}
            aria-label={
              s.track ? `Now playing: ${s.track.title}. Open the player` : "Open the player"
            }
          >
            <Artwork src={art} size={44} className="size-10" eager />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[14px] font-semibold">
                {s.track ? s.track.title : "Nothing playing"}
              </span>
              <span className="block truncate text-[12.5px] text-fg-muted">
                {s.track
                  ? s.track.artist
                  : `Pick a song to play on ${onEcho ? name : name.toLowerCase()}`}
              </span>
            </span>
          </button>
          {!onEcho && s.track && (
            <IconButton label={s.playing ? "Pause" : "Play"} onClick={toggle} className="text-fg">
              {s.playing ? <Pause className="fill-current" /> : <Play className="fill-current" />}
            </IconButton>
          )}
          {onEcho && s.track && (
            <span className="grid size-11 place-items-center text-accent" title={ECHO_PAUSE}>
              <Equalizer playing={s.playing} />
            </span>
          )}
          <IconButton label={`Playing on ${name}. Choose a device`} onClick={() => open("devices")}>
            <TargetIcon onEcho={onEcho} className={onEcho ? "text-accent" : ""} />
          </IconButton>
        </div>
        <button
          type="button"
          onClick={() => open("devices")}
          className={cn(
            "flex h-6 w-full items-center gap-1.5 px-3 pb-1 text-[11.5px] font-semibold",
            onEcho ? "text-accent" : "text-fg-muted",
          )}
        >
          <TargetIcon onEcho={onEcho} className="size-3.5" />
          <span className="truncate">
            {onEcho ? `Playing on ${name}` : `Playing on ${name.toLowerCase()}`}
            {s.idle ? " · idle" : ""}
          </span>
        </button>
      </div>
    </div>
  );
}

/** Desktop: the player bar along the bottom. */
export function PlayerBar() {
  const s = useShowing();
  const open = useUi((u) => u.open);
  const seek = usePlayer((st) => st.seek);
  const panel = usePanel((p) => p.open);
  const togglePanel = usePanel((p) => p.toggle);
  const wide = useMediaQuery("(min-width: 1280px)");
  const art = s.track ? trackArt(s.track, 120) : null;
  return (
    <div className="fixed inset-x-0 bottom-0 z-40 hidden h-20 items-center gap-4 border-t border-border bg-surface/95 px-4 backdrop-blur-xl lg:flex">
      <button
        type="button"
        onClick={() => open("now")}
        className="flex w-[28%] min-w-0 items-center gap-3 rounded-[12px] p-1 text-left hover:bg-surface-2"
        aria-label="Open Now Playing"
      >
        <Artwork src={art} size={56} className="size-14" eager />
        <span className="min-w-0">
          <span className="block truncate text-[14px] font-semibold">
            {s.track?.title ?? "Nothing playing"}
          </span>
          <span className="block truncate text-[13px] text-fg-muted">
            {s.track?.artist ?? "Search or pick something on Home"}
          </span>
        </span>
        {s.track && <ChevronUp className="ml-1 size-4 shrink-0 text-fg-subtle" aria-hidden />}
      </button>
      <div className="flex max-w-[640px] flex-1 flex-col items-center">
        <TransportControls />
        <Progress
          className="-mt-1"
          position={s.position}
          duration={s.duration}
          onSeek={s.onEcho ? undefined : seek}
        />
      </div>
      <div className="flex w-[28%] items-center justify-end gap-1">
        <IconButton
          label="Up next"
          aria-pressed={wide ? panel : undefined}
          className={wide && panel ? "text-accent" : ""}
          onClick={() => (wide ? togglePanel() : open("queue"))}
        >
          <ListMusic />
        </IconButton>
        <DevicePill className="max-w-[220px]" />
      </div>
    </div>
  );
}
