import { Pause, Play, SkipBack, SkipForward } from "lucide-react";
import { cn } from "@/lib/cn";
import { useTick } from "@/lib/hooks";
import { type Showing, showing, usePlayer } from "@/store/player";
import { IconButton } from "../ui/button";

/** What's playing on the current target, ticking once a second for an Echo. */
export function useShowing(): Showing {
  const st = usePlayer();
  const s = showing(st);
  useTick(s.onEcho && s.playing);
  return showing(st);
}

/** Why a control is off, said where the control is (not hidden). */
export const ECHO_PAUSE = "On an Echo, say “Alexa, pause” or use its buttons";
export const ECHO_PREV = "On an Echo, say “Alexa, previous” to go back";

/** Previous · play/pause · next, honest about what an Echo allows. */
export function TransportControls({ size = "md" }: { size?: "md" | "lg" }) {
  const s = useShowing();
  const { toggle, next, prev, skipEcho } = usePlayer.getState();
  const skip = usePlayer((st) => st.info.experimental_skip);
  const actions = usePlayer((st) => st.info.actions);
  const big = size === "lg";
  const echo = s.onEcho;
  return (
    <div className={big ? "flex items-center justify-center gap-6" : "flex items-center gap-2"}>
      <IconButton
        label={echo ? ECHO_PREV : "Previous"}
        size={big ? "lg" : "md"}
        disabled={echo || !s.track}
        onClick={prev}
        className={big ? "text-fg" : ""}
      >
        <SkipBack className="fill-current" />
      </IconButton>
      <IconButton
        label={echo ? ECHO_PAUSE : s.playing ? "Pause" : "Play"}
        size={big ? "xl" : "md"}
        variant="solid"
        disabled={echo || !s.track}
        onClick={toggle}
        className={cn(
          big && "size-[72px] [&_svg]:size-8",
          echo && "border border-fg/25 bg-transparent text-fg/35 disabled:opacity-100",
        )}
      >
        {s.playing ? (
          <Pause className="fill-current" />
        ) : (
          <Play className="translate-x-[1px] fill-current" />
        )}
      </IconButton>
      <IconButton
        label={
          echo
            ? skip
              ? "Skip now (beta): cuts the current song's stream"
              : "Skipping an Echo from here needs ECHO_TUNES_EXPERIMENTAL_SKIP; say “Alexa, next”"
            : "Next"
        }
        size={big ? "lg" : "md"}
        disabled={echo ? !skip || !actions || !s.track : !s.track}
        onClick={() => (echo ? void skipEcho() : next())}
        className={big ? "text-fg" : ""}
      >
        <SkipForward className="fill-current" />
      </IconButton>
    </div>
  );
}
