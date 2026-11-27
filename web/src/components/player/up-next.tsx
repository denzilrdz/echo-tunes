import { X } from "lucide-react";
import { trackArt } from "@/lib/art";
import { cn } from "@/lib/cn";
import { useNow } from "@/lib/queries";
import type { Track } from "@/lib/types";
import { BROWSER, echoName, usePlayer } from "@/store/player";
import { Artwork } from "../ui/artwork";
import { Equalizer } from "../ui/bits";
import { IconButton } from "../ui/button";

/** The queue: this browser's (editable) or the target Echo's next songs. */
export function UpNext({ showCurrent = true }: { showCurrent?: boolean }) {
  const target = usePlayer((s) => s.target);
  const queue = usePlayer((s) => s.queue);
  const index = usePlayer((s) => s.index);
  const playing = usePlayer((s) => s.playing);
  const { playAt, removeAt } = usePlayer.getState();
  const now = useNow();
  if (target !== BROWSER) {
    const d = now.data?.devices.find((x) => x.id === target);
    const rows = d?.up_next ?? [];
    return (
      <div className="px-4">
        {showCurrent && d?.current && (
          <>
            <h3 className="px-2 pb-1 text-[13px] font-semibold text-fg-muted">Now playing</h3>
            <Row t={d.current} active playing={d.playing} />
          </>
        )}
        <h3 className="mt-3 px-2 pb-1 text-[13px] font-semibold text-fg-muted">
          Next on {echoName(d)}
          {d?.source ? ` · ${d.source}` : ""}
        </h3>
        {rows.length ? (
          rows.map((t, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: a queue can hold the same song twice
            <Row key={`${t.video_id}-${i}`} t={t} />
          ))
        ) : (
          <p className="px-2 py-6 text-sm text-fg-muted">
            {now.isLoading
              ? "Loading…"
              : "Nothing lined up yet. The Echo's radio adds songs as it goes."}
          </p>
        )}
      </div>
    );
  }
  const cur = queue[index];
  const upcoming = queue.slice(index + 1, index + 101);
  return (
    <div className="px-4">
      {showCurrent && cur && (
        <>
          <h3 className="px-2 pb-1 text-[13px] font-semibold text-fg-muted">Now playing</h3>
          <Row t={cur} active playing={playing} />
        </>
      )}
      <h3 className="mt-3 px-2 pb-1 text-[13px] font-semibold text-fg-muted">Up next</h3>
      {upcoming.length ? (
        upcoming.map((t, k) => {
          const i = index + 1 + k;
          return (
            <Row
              key={`${t.video_id}-${i}`}
              t={t}
              onPlay={() => void playAt(i)}
              onRemove={() => removeAt(i)}
            />
          );
        })
      ) : (
        <p className="px-2 py-6 text-sm text-fg-muted">
          Nothing queued. A radio of similar songs keeps it going.
        </p>
      )}
    </div>
  );
}

function Row({
  t,
  active,
  playing,
  onPlay,
  onRemove,
}: {
  t: Track;
  active?: boolean;
  playing?: boolean;
  onPlay?: () => void;
  onRemove?: () => void;
}) {
  const body = (
    <>
      <Artwork src={trackArt(t, 96)} size={44} className="size-11" />
      <span className="min-w-0 flex-1 text-left">
        <span className={cn("block truncate text-[15px] font-medium", active && "text-accent")}>
          {t.title}
        </span>
        <span className="block truncate text-[13px] text-fg-muted">{t.artist}</span>
      </span>
      {active && <Equalizer playing={!!playing} className="mr-2 text-accent" />}
    </>
  );
  return (
    <div className="flex h-14 items-center gap-1 rounded-[10px] hover:bg-fg/5">
      {onPlay ? (
        <button
          type="button"
          onClick={onPlay}
          className="flex min-w-0 flex-1 items-center gap-3 self-stretch px-2"
          aria-label={`Play ${t.title}`}
        >
          {body}
        </button>
      ) : (
        <div className="flex min-w-0 flex-1 items-center gap-3 px-2">{body}</div>
      )}
      {onRemove && (
        <IconButton label={`Remove ${t.title} from the queue`} size="sm" onClick={onRemove}>
          <X />
        </IconButton>
      )}
    </div>
  );
}
