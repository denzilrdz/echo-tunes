import { ListEnd, ListStart, Play, Radio, UserRound } from "lucide-react";
import type * as React from "react";
import { itemArt, trackArt } from "@/lib/art";
import { cn } from "@/lib/cn";
import { mmss } from "@/lib/format";
import { itemToTrack, useOpenItem, useTarget } from "@/lib/play";
import type { Item, Track } from "@/lib/types";
import { BROWSER, usePlayer } from "@/store/player";
import { Artwork, LikedArt } from "./ui/artwork";
import { Equalizer, SectionTitle, Skeleton } from "./ui/bits";
import { ActionsMenu, type MenuAction, WithContextMenu } from "./ui/menu";

const KIND_LABEL = {
  song: "Song",
  album: "Album",
  artist: "Artist",
  playlist: "Playlist",
} as const;

/** A cover card for a shelf or grid: album, playlist, artist (round) or song. */
export function MediaCard({ item, className }: { item: Item; className?: string }) {
  const open = useOpenItem();
  const round = item.kind === "artist";
  return (
    <button
      type="button"
      onClick={() => open(item)}
      className={cn(
        "group flex w-[148px] shrink-0 snap-start flex-col gap-2.5 rounded-[14px] p-0 text-left outline-offset-4 md:w-[176px]",
        className,
      )}
      title={item.subtitle ? `${item.title} · ${item.subtitle}` : item.title}
    >
      <div className="relative w-full">
        {item.id === "LM" ? (
          <LikedArt className="aspect-square w-full shadow-[0_8px_24px_-12px_rgb(0_0_0/0.45)]" />
        ) : (
          <Artwork
            src={itemArt(item, 352)}
            size={176}
            kind={item.kind}
            round={round}
            className="aspect-square w-full shadow-[0_8px_24px_-12px_rgb(0_0_0/0.45)] transition-transform duration-200 ease-out group-hover:scale-[1.02]"
          />
        )}
        {!round && (
          <span className="absolute right-2 bottom-2 grid size-11 translate-y-1 place-items-center rounded-full bg-accent text-accent-fg opacity-0 shadow-lg transition-all duration-200 ease-out group-hover:translate-y-0 group-hover:opacity-100 group-focus-visible:translate-y-0 group-focus-visible:opacity-100">
            <Play className="size-5 fill-current" aria-hidden />
          </span>
        )}
      </div>
      <div className={cn("min-w-0 px-0.5", round && "text-center")}>
        <div className="truncate text-[14px] font-semibold">{item.title}</div>
        <div className="truncate text-[13px] text-fg-muted">
          {item.subtitle || KIND_LABEL[item.kind]}
        </div>
      </div>
    </button>
  );
}

export function Shelf({
  title,
  items,
  action,
}: {
  title: string;
  items: Item[];
  action?: React.ReactNode;
}) {
  if (!items.length) return null;
  return (
    <section className="mb-8" aria-label={title}>
      <SectionTitle action={action}>{title}</SectionTitle>
      <div className="scroll-x flex gap-4 px-4 pb-1 scroll-px-4 md:gap-5 md:px-8 md:scroll-px-8">
        {items.map((it) => (
          <MediaCard key={`${it.kind}:${it.id}`} item={it} />
        ))}
      </div>
    </section>
  );
}

export function ShelfSkeleton({ round }: { round?: boolean }) {
  return (
    <div className="mb-8">
      <Skeleton className="mx-4 mb-4 h-6 w-40 md:mx-8" />
      <div className="flex gap-4 overflow-hidden px-4 md:gap-5 md:px-8">
        {Array.from({ length: 7 }, (_, i) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: placeholders
          <div key={i} className="w-[148px] shrink-0 md:w-[176px]">
            <Skeleton
              className={cn("aspect-square w-full", round ? "rounded-full" : "rounded-lg")}
            />
            <Skeleton className="mt-3 h-3.5 w-3/4" />
            <Skeleton className="mt-2 h-3 w-1/2" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function CardGrid({ items }: { items: Item[] }) {
  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-6 px-4 sm:grid-cols-3 md:px-8 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6">
      {items.map((it) => (
        <MediaCard key={`${it.kind}:${it.id}`} item={it} className="w-auto" />
      ))}
    </div>
  );
}

// ---------- songs ----------

/** The actions every song row offers (⋯ menu and right-click). */
export function useTrackActions() {
  const { onEcho, name, actions } = useTarget();
  const play = usePlayer((s) => s.play);
  const enqueue = usePlayer((s) => s.enqueue);
  return (tracks: Track[], i: number, source: string, extra: MenuAction[] = []): MenuAction[] => {
    const t = tracks[i];
    if (!t) return [];
    const off = !actions;
    return [
      {
        label: onEcho ? `Play next on ${name}` : "Play now",
        icon: Play,
        disabled: off,
        onSelect: () => void play(onEcho ? [t] : tracks.slice(i), source),
      },
      ...(onEcho
        ? []
        : [
            {
              label: "Play next",
              icon: ListStart,
              disabled: off,
              onSelect: () => void enqueue([t], "next", source),
            },
          ]),
      {
        label: onEcho ? `Add to ${name}'s queue` : "Add to queue",
        icon: ListEnd,
        disabled: off,
        onSelect: () => void enqueue([t], "queue", source),
      },
      {
        label: "Start radio",
        icon: Radio,
        disabled: off,
        onSelect: () => void play([t], `Radio after ${t.title}`, { radio: true }),
      },
      ...extra,
    ];
  };
}

interface TrackListProps {
  tracks: Track[];
  source: string;
  numbered?: boolean;
  showArt?: boolean;
  goArtist?: (artist: string) => void;
}

/** Dense song rows (56 px on phones, 52 on desktop) with a ⋯ menu and right-click menu. */
export function TrackList({ tracks, source, numbered, showArt = true, goArtist }: TrackListProps) {
  const actionsFor = useTrackActions();
  const play = usePlayer((s) => s.play);
  const current = usePlayer((s) => (s.target === BROWSER ? s.queue[s.index]?.video_id : undefined));
  const playing = usePlayer((s) => s.playing);
  const { actions, onEcho } = useTarget();
  return (
    <ol className="px-2 md:px-6" aria-label="Songs">
      {tracks.map((t, i) => {
        const extra: MenuAction[] =
          goArtist && t.artist
            ? [{ label: "Go to artist", icon: UserRound, onSelect: () => goArtist(t.artist) }]
            : [];
        const items = actionsFor(tracks, i, source, extra);
        const isCurrent = current === t.video_id;
        return (
          // biome-ignore lint/suspicious/noArrayIndexKey: a queue can hold the same song twice
          <li key={`${t.video_id}-${i}`}>
            <WithContextMenu actions={items} className="block">
              <div
                className={cn(
                  "group flex h-14 items-center gap-3 rounded-[10px] pr-1 pl-2 transition-colors duration-120 hover:bg-surface-2 md:h-[52px]",
                  isCurrent && "bg-accent-soft",
                )}
              >
                <button
                  type="button"
                  disabled={!actions}
                  onClick={() => void play(onEcho ? [t] : tracks.slice(i), source)}
                  className="flex min-w-0 flex-1 items-center gap-3 self-stretch text-left disabled:cursor-default"
                  aria-label={`${onEcho ? "Play next" : "Play"} ${t.title} by ${t.artist}`}
                >
                  {numbered && (
                    <span className="tabular hidden w-6 shrink-0 text-right text-[13px] text-fg-subtle md:block">
                      {isCurrent ? <Equalizer playing={playing} className="text-accent" /> : i + 1}
                    </span>
                  )}
                  {showArt && <Artwork src={trackArt(t, 96)} size={44} className="size-11" />}
                  <span className="min-w-0 flex-1">
                    <span
                      className={cn(
                        "block truncate text-[15px] font-medium md:text-[14px]",
                        isCurrent && "text-accent",
                      )}
                    >
                      {t.title}
                    </span>
                    <span className="block truncate text-[13px] text-fg-muted">{t.artist}</span>
                  </span>
                </button>
                <span className="tabular hidden w-12 shrink-0 text-right text-[13px] text-fg-subtle sm:block">
                  {t.duration ? mmss(t.duration * 1000) : ""}
                </span>
                <ActionsMenu actions={items} label={`More for ${t.title}`} />
              </div>
            </WithContextMenu>
          </li>
        );
      })}
    </ol>
  );
}

export function TrackListSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div className="px-4 md:px-8" aria-hidden>
      {Array.from({ length: rows }, (_, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: placeholders
        <div key={i} className="flex h-14 items-center gap-3">
          <Skeleton className="size-11 rounded-[4px]" />
          <div className="flex-1">
            <Skeleton className="h-3.5 w-1/2" />
            <Skeleton className="mt-2 h-3 w-1/3" />
          </div>
        </div>
      ))}
    </div>
  );
}

/** YouTube Music's "Quick picks": songs in columns of four that scroll sideways. */
export function QuickPicks({ title, items }: { title: string; items: Item[] }) {
  const tracks = items.map(itemToTrack);
  const actionsFor = useTrackActions();
  const open = useOpenItem();
  const { actions } = useTarget();
  return (
    <section className="mb-8" aria-label={title}>
      <SectionTitle>{title}</SectionTitle>
      <div className="scroll-x grid auto-cols-[82%] grid-flow-col grid-rows-4 gap-x-6 px-2 scroll-px-2 sm:auto-cols-[46%] md:px-6 lg:auto-cols-[340px]">
        {items.map((it, i) => (
          <div
            key={it.id}
            className="group flex h-14 snap-start items-center gap-3 rounded-[10px] pl-2 hover:bg-surface-2"
          >
            <button
              type="button"
              disabled={!actions}
              onClick={() => open(it)}
              className="flex min-w-0 flex-1 items-center gap-3 self-stretch text-left disabled:cursor-default"
              aria-label={`Play ${it.title} by ${it.subtitle}`}
            >
              <Artwork src={itemArt(it, 96)} size={44} className="size-11" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[15px] font-medium md:text-[14px]">
                  {it.title}
                </span>
                <span className="block truncate text-[13px] text-fg-muted">{it.subtitle}</span>
              </span>
            </button>
            <ActionsMenu actions={actionsFor(tracks, i, title)} label={`More for ${it.title}`} />
          </div>
        ))}
      </div>
    </section>
  );
}
