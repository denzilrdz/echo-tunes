import { useNavigate, useSearch as useRouteSearch } from "@tanstack/react-router";
import { Clock, Play, Search as SearchIcon, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { CardGrid, Shelf, ShelfSkeleton, TrackList, TrackListSkeleton } from "@/components/music";
import { ErrorNote } from "@/components/page";
import { Artwork } from "@/components/ui/artwork";
import { Chip, EmptyState, SectionTitle } from "@/components/ui/bits";
import { IconButton } from "@/components/ui/button";
import { itemArt } from "@/lib/art";
import { useDebounced } from "@/lib/hooks";
import { itemToTrack, useOpenItem, useTarget } from "@/lib/play";
import { useExplore, useSearch } from "@/lib/queries";
import { KEYS, load, save } from "@/lib/storage";
import type { Item, Kind } from "@/lib/types";
import { MoodGrid } from "./home";

export type SearchType = "all" | Kind;
const TYPES: [SearchType, string][] = [
  ["all", "All"],
  ["song", "Songs"],
  ["album", "Albums"],
  ["artist", "Artists"],
  ["playlist", "Playlists"],
];

export function SearchPage() {
  const { q = "", type = "all" } = useRouteSearch({ from: "/search" });
  const navigate = useNavigate({ from: "/search" });
  const [text, setText] = useState(q);
  const term = useDebounced(text.trim(), 250);
  const input = useRef<HTMLInputElement>(null);

  // The box and the address stay in step both ways: typing updates ?q= (debounced), and a
  // new ?q= from elsewhere ("Go to artist", back/forward, a link) fills the box.
  const synced = useRef(q);
  useEffect(() => {
    if (term === synced.current) return;
    synced.current = term;
    void navigate({ search: (s) => ({ ...s, q: term || undefined }), replace: true });
  }, [term, navigate]);
  useEffect(() => {
    if (q === synced.current) return;
    synced.current = q;
    setText(q);
  }, [q]);
  useEffect(() => {
    if (!q && window.matchMedia("(pointer: fine)").matches) input.current?.focus();
  }, [q]);

  const remember = (value: string) => {
    if (!value) return;
    const list = [value, ...load<string[]>(KEYS.recent, []).filter((x) => x !== value)].slice(0, 8);
    save(KEYS.recent, list);
  };

  return (
    <div>
      <div className="sticky top-0 z-20 bg-bg/92 px-4 pt-[calc(env(safe-area-inset-top)+12px)] pb-3 backdrop-blur-xl md:px-8 md:pt-6">
        <h1 className="mb-3 text-[28px] font-extrabold tracking-[-0.02em] lg:sr-only">Search</h1>
        {/* biome-ignore lint/a11y/useSemanticElements: <search> isn't in every browser this supports */}
        <form
          role="search"
          onSubmit={(e) => {
            e.preventDefault();
            remember(text.trim());
            input.current?.blur();
          }}
          className="relative"
        >
          <SearchIcon
            className="pointer-events-none absolute top-1/2 left-4 size-5 -translate-y-1/2 text-fg-muted"
            aria-hidden
          />
          <input
            ref={input}
            type="search"
            enterKeyHint="search"
            value={text}
            maxLength={100}
            onChange={(e) => setText(e.target.value)}
            placeholder="Songs, albums, artists, playlists"
            aria-label="Search YouTube Music"
            className="h-12 w-full rounded-full border border-transparent bg-surface-2 pr-12 pl-12 text-[16px] text-fg placeholder:text-fg-subtle focus:border-border focus:bg-surface focus:outline-none focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)] md:max-w-[560px]"
          />
          {text && (
            <IconButton
              label="Clear search"
              size="sm"
              className="absolute top-1/2 right-1.5 -translate-y-1/2 md:right-auto md:left-[514px]"
              onClick={() => {
                setText("");
                input.current?.focus();
              }}
            >
              <X />
            </IconButton>
          )}
        </form>
        {q && (
          // biome-ignore lint/a11y/useSemanticElements: a row of filter chips, not a form fieldset
          <div
            className="scroll-x -mx-4 mt-3 flex gap-2 px-4 md:mx-0 md:px-0"
            role="group"
            aria-label="Result type"
          >
            {TYPES.map(([k, label]) => (
              <Chip
                key={k}
                active={type === k}
                onClick={() =>
                  void navigate({
                    search: (s) => ({ ...s, type: k === "all" ? undefined : k }),
                    replace: true,
                  })
                }
              >
                {label}
              </Chip>
            ))}
          </div>
        )}
      </div>
      {q ? (
        <Results q={q} type={type} onUse={() => remember(q)} />
      ) : (
        <Idle onPick={(v) => setText(v)} />
      )}
    </div>
  );
}

function Idle({ onPick }: { onPick: (v: string) => void }) {
  const [recent, setRecent] = useState(() => load<string[]>(KEYS.recent, []));
  const explore = useExplore();
  return (
    <div className="pt-2">
      {recent.length > 0 && (
        <section className="mb-8 px-4 md:px-8" aria-label="Recent searches">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-[17px] font-bold">Recent searches</h2>
            <button
              type="button"
              className="h-9 rounded-full px-3 text-[13px] font-semibold text-fg-muted hover:bg-surface-2"
              onClick={() => {
                save(KEYS.recent, null);
                setRecent([]);
              }}
            >
              Clear
            </button>
          </div>
          <ul>
            {recent.map((r) => (
              <li key={r}>
                <button
                  type="button"
                  onClick={() => onPick(r)}
                  className="flex h-12 w-full items-center gap-3 rounded-[10px] px-2 text-left text-[15px] hover:bg-surface-2"
                >
                  <Clock className="size-5 text-fg-subtle" aria-hidden />
                  {r}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      {explore.isLoading && <ShelfSkeleton />}
      {(explore.data?.moods ?? []).map((g) => (
        <MoodGrid key={g.title} group={g} limit={24} />
      ))}
    </div>
  );
}

function Results({ q, type, onUse }: { q: string; type: SearchType; onUse: () => void }) {
  if (type !== "all") return <Single q={q} kind={type} />;
  return <All q={q} onUse={onUse} />;
}

function Single({ q, kind }: { q: string; kind: Kind }) {
  const r = useSearch(q, kind);
  if (r.isLoading) return kind === "song" ? <TrackListSkeleton /> : <ShelfSkeleton />;
  if (r.error) return <ErrorNote error={r.error} retry={() => r.refetch()} />;
  const items = r.data?.items ?? [];
  if (!items.length) return <NoResults q={q} />;
  if (kind === "song") return <TrackList tracks={items.map(itemToTrack)} source={`Search: ${q}`} />;
  return (
    <div className="pt-2">
      <CardGrid items={items} />
    </div>
  );
}

function NoResults({ q }: { q: string }) {
  return (
    <EmptyState icon={SearchIcon} title={`Nothing found for “${q}”`}>
      Check the spelling, or try fewer words.
    </EmptyState>
  );
}

function All({ q, onUse }: { q: string; onUse: () => void }) {
  const songs = useSearch(q, "song");
  const artists = useSearch(q, "artist");
  const albums = useSearch(q, "album");
  const playlists = useSearch(q, "playlist");
  const navigate = useNavigate();
  if (songs.isLoading && artists.isLoading)
    return (
      <div className="pt-2">
        <TrackListSkeleton rows={5} />
        <ShelfSkeleton round />
      </div>
    );
  if (songs.error && artists.error)
    return <ErrorNote error={songs.error} retry={() => songs.refetch()} />;
  const s = songs.data?.items ?? [];
  const a = artists.data?.items ?? [];
  if (!s.length && !a.length && !(albums.data?.items.length || playlists.data?.items.length))
    return <NoResults q={q} />;
  const norm = (x: string) => x.toLowerCase().replace(/\s+/g, " ").trim();
  const artistFirst = a[0] && norm(a[0].title) === norm(q);
  const top = artistFirst ? a[0] : (s[0] ?? a[0]);
  const goArtist = (name: string) =>
    void navigate({ to: "/search", search: { q: name, type: "artist" } });
  return (
    <div className="pt-2" onClickCapture={onUse}>
      <div className="mb-8 grid gap-6 px-0 lg:grid-cols-[minmax(280px,380px)_1fr] lg:px-8">
        {top && (
          <section aria-label="Top result" className="px-4 lg:px-0">
            <h2 className="mb-3 text-[20px] font-bold tracking-tight">Top result</h2>
            <TopResult item={top} />
          </section>
        )}
        {s.length > 0 && (
          <section aria-label="Songs" className="min-w-0">
            <SectionTitle className="lg:px-0">Songs</SectionTitle>
            <div className="lg:-mx-6">
              <TrackList
                tracks={s.slice(0, 4).map(itemToTrack)}
                source={`Search: ${q}`}
                goArtist={goArtist}
              />
            </div>
          </section>
        )}
      </div>
      <Shelf title="Artists" items={a} />
      <Shelf title="Albums" items={albums.data?.items ?? []} />
      <Shelf title="Playlists" items={playlists.data?.items ?? []} />
    </div>
  );
}

function TopResult({ item }: { item: Item }) {
  const open = useOpenItem();
  const { playLabel, actions } = useTarget();
  const round = item.kind === "artist";
  return (
    <div className="group relative flex flex-col gap-4 rounded-[18px] bg-surface-2 p-5 transition-colors hover:bg-surface-3">
      <Artwork
        src={itemArt(item, 240)}
        size={112}
        kind={item.kind}
        round={round}
        className="size-28 shadow-lg"
        eager
      />
      <div className="min-w-0">
        <div className="truncate text-[26px] font-extrabold tracking-tight">{item.title}</div>
        <div className="mt-1 flex items-center gap-2 text-[14px] text-fg-muted">
          <span className="rounded-full bg-bg/60 px-2 py-0.5 text-[12px] font-semibold text-fg capitalize">
            {item.kind}
          </span>
          <span className="truncate">{item.subtitle}</span>
        </div>
      </div>
      <button
        type="button"
        onClick={() => open(item)}
        disabled={item.kind === "song" && !actions}
        aria-label={item.kind === "song" ? `${playLabel} ${item.title}` : `Open ${item.title}`}
        className="absolute right-5 bottom-5 grid size-14 place-items-center rounded-full bg-accent text-accent-fg shadow-xl transition-transform duration-120 hover:scale-105 active:scale-95 disabled:opacity-50"
      >
        <Play className="size-6 translate-x-[1px] fill-current" aria-hidden />
      </button>
    </div>
  );
}
