import { useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { KeyRound, ListMusic, Play, Shuffle } from "lucide-react";
import type * as React from "react";
import { CardGrid, ShelfSkeleton, TrackList, TrackListSkeleton } from "@/components/music";
import { ErrorNote, PageHeader, ServerLink } from "@/components/page";
import { Artwork, LikedArt } from "@/components/ui/artwork";
import { EmptyState, Skeleton } from "@/components/ui/bits";
import { IconButton } from "@/components/ui/button";
import { ActionsMenu } from "@/components/ui/menu";
import { itemArt, trackArt } from "@/lib/art";
import { plural } from "@/lib/format";
import { useArtColour } from "@/lib/hooks";
import { openedItem, shuffled, useTarget } from "@/lib/play";
import { useLibrary, useMood, useTracks } from "@/lib/queries";
import type { Kind } from "@/lib/types";
import { usePlayer } from "@/store/player";

export function LibraryPage() {
  const signedIn = usePlayer((s) => s.info.signed_in);
  const loaded = usePlayer((s) => s.loaded);
  const lib = useLibrary(signedIn);
  return (
    <div>
      <PageHeader
        title="Library"
        subtitle={signedIn ? "Your YouTube Music playlists" : undefined}
        actions={<ServerLink />}
      />
      {!loaded || (signedIn && lib.isLoading) ? (
        <ShelfSkeleton />
      ) : !signedIn ? (
        <EmptyState icon={KeyRound} title="Your library lives on your server">
          Sign the server in to YouTube Music once and your playlists, liked songs and mixes show up
          here. On the server, run{" "}
          <code className="rounded bg-surface-2 px-1.5 py-0.5 text-fg">echo-tunes login</code>.
        </EmptyState>
      ) : lib.error ? (
        <ErrorNote error={lib.error} retry={() => lib.refetch()} />
      ) : (lib.data?.items.length ?? 0) === 0 ? (
        <EmptyState icon={ListMusic} title="No playlists yet">
          Playlists you make or save in YouTube Music appear here.
        </EmptyState>
      ) : (
        <CardGrid items={lib.data?.items ?? []} />
      )}
    </div>
  );
}

const KIND_NAME: Record<string, string> = {
  playlist: "Playlist",
  album: "Album",
  artist: "Artist",
};

/** A playlist, album or artist: artwork-tinted hero, big play button, songs. */
export function CollectionPage() {
  const { kind, id } = useParams({ from: "/collection/$kind/$id" });
  const known = openedItem(kind, id);
  const tracks = useTracks(kind, id);
  const navigate = useNavigate();
  const { playLabel, playHint, actions, disabledReason, onEcho, name } = useTarget();
  const play = usePlayer((s) => s.play);
  const enqueue = usePlayer((s) => s.enqueue);
  const list = tracks.data?.tracks ?? [];
  const title = known?.title || tracks.data?.title || "";
  const liked = id === "LM";
  const cover = known ? itemArt(known, 464) : list[0] ? trackArt(list[0], 464) : null;
  const colour = useArtColour(
    known ? itemArt(known, 120) : list[0] ? trackArt(list[0], 120) : null,
  );
  const source = `${KIND_NAME[kind] ?? "Playlist"}: ${title}`;
  const round = kind === "artist";
  const goArtist = (artist: string) =>
    void navigate({ to: "/search", search: { q: artist, type: "artist" } });
  return (
    <div
      className="hero-art"
      style={colour ? ({ "--art": colour } as React.CSSProperties) : undefined}
    >
      <PageHeader back title="" className="pb-0 md:pb-0" />
      <div className="flex flex-col items-center gap-5 px-4 pb-6 text-center md:flex-row md:items-end md:gap-7 md:px-8 md:pb-8 md:text-left">
        {liked ? (
          <LikedArt className="size-[200px] shadow-2xl md:size-[232px]" />
        ) : (
          <Artwork
            src={cover}
            size={232}
            kind={kind as Kind}
            round={round}
            eager
            className="size-[200px] shadow-[0_24px_60px_-20px_rgb(0_0_0/0.65)] md:size-[232px]"
          />
        )}
        <div className="min-w-0 max-w-full">
          <div className="text-[12px] font-semibold tracking-[0.12em] text-fg-muted uppercase">
            {KIND_NAME[kind] ?? "Playlist"}
          </div>
          {title ? (
            <h1 className="mt-1 line-clamp-2 text-[30px] leading-[1.08] font-extrabold tracking-[-0.02em] md:text-[48px]">
              {title}
            </h1>
          ) : (
            <Skeleton className="mx-auto mt-2 h-9 w-56 md:mx-0" />
          )}
          <p className="mt-2 text-[14px] text-fg-muted">
            {[known?.subtitle, tracks.data ? plural(list.length, "song") : null]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>
      </div>
      <div className="flex items-center justify-center gap-3 px-4 pb-4 md:justify-start md:px-8">
        <button
          type="button"
          disabled={!actions || !list.length}
          title={disabledReason ?? playHint}
          aria-label={`${playHint}: ${title}`}
          onClick={() => void play(list, source)}
          className="inline-flex h-14 items-center gap-2 rounded-full bg-accent pr-6 pl-5 text-[16px] font-bold text-accent-fg shadow-xl transition-transform duration-120 hover:scale-[1.03] active:scale-[0.97] disabled:opacity-50"
        >
          <Play className="size-6 fill-current" aria-hidden />
          {playLabel}
        </button>
        <IconButton
          label={onEcho ? `Shuffle and play next on ${name}` : "Shuffle"}
          size="lg"
          variant="ghost"
          disabled={!actions || !list.length}
          onClick={() => void play(shuffled(list), `${source} (shuffled)`)}
          className="bg-fg/6 text-fg"
        >
          <Shuffle />
        </IconButton>
        <ActionsMenu
          label="More"
          className="size-14 bg-fg/6 text-fg"
          actions={[
            ...(onEcho
              ? []
              : [
                  {
                    label: "Play next",
                    disabled: !actions,
                    onSelect: () => void enqueue(list, "next", source),
                  },
                ]),
            {
              label: onEcho ? `Add to ${name}'s queue` : "Add to queue",
              disabled: !actions,
              onSelect: () => void enqueue(list, "queue", source),
            },
          ]}
        />
      </div>
      {!actions && (
        <p className="mx-4 mb-3 rounded-[12px] bg-surface-2 px-4 py-3 text-[13px] text-fg-muted md:mx-8">
          {disabledReason}
        </p>
      )}
      <div className="pb-6">
        {tracks.isLoading ? (
          <TrackListSkeleton />
        ) : tracks.error ? (
          <ErrorNote error={tracks.error} retry={() => tracks.refetch()} />
        ) : list.length ? (
          <TrackList tracks={list} source={source} numbered goArtist={goArtist} />
        ) : (
          <EmptyState icon={ListMusic} title="No playable songs here" />
        )}
      </div>
    </div>
  );
}

export function MoodPage() {
  const { params } = useParams({ from: "/mood/$params" });
  const { title } = useSearch({ from: "/mood/$params" });
  const mood = useMood(params);
  return (
    <div className="glow-art">
      <PageHeader back title={title || "Playlists"} subtitle="Playlists for this mood" />
      {mood.isLoading ? (
        <ShelfSkeleton />
      ) : mood.error ? (
        <ErrorNote error={mood.error} retry={() => mood.refetch()} />
      ) : (
        <CardGrid items={mood.data?.items ?? []} />
      )}
    </div>
  );
}
