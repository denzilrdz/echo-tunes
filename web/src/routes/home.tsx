import { Link, useNavigate } from "@tanstack/react-router";
import { ArrowRight, Wrench } from "lucide-react";
import { CardGrid, QuickPicks, Shelf, ShelfSkeleton, TrackListSkeleton } from "@/components/music";
import { ErrorNote, PageHeader, ServerLink } from "@/components/page";
import { DevicePill } from "@/components/player/bars";
import { Chip, SectionTitle } from "@/components/ui/bits";
import { greeting } from "@/lib/format";
import { useExplore, useHome, useLibrary, useSetup } from "@/lib/queries";
import type { Item, MoodGroup } from "@/lib/types";
import { usePlayer } from "@/store/player";

export function HomePage() {
  const signedIn = usePlayer((s) => s.info.signed_in);
  const home = useHome();
  const explore = useExplore();
  const library = useLibrary(signedIn);
  const sections = home.data?.sections ?? [];
  const songRow = sections.find(
    (s) => s.items.length >= 4 && s.items.every((i) => i.kind === "song"),
  );
  const others = sections.filter((s) => s !== songRow);
  const moods = explore.data?.moods ?? [];
  return (
    <div>
      <div className="glow-art">
        <PageHeader
          title={greeting()}
          actions={
            <>
              <DevicePill className="hidden max-w-[180px] sm:inline-flex lg:hidden" />
              <ServerLink />
            </>
          }
        />
        <SetupBanner />
        {moods[0] && <MoodChips group={moods[0]} />}
      </div>

      {home.isLoading && (
        <>
          <div className="mb-8">
            <SectionTitle>Quick picks</SectionTitle>
            <TrackListSkeleton rows={4} />
          </div>
          <ShelfSkeleton />
        </>
      )}
      {home.error && !sections.length && (
        <ErrorNote error={home.error} retry={() => home.refetch()} />
      )}

      {songRow && <QuickPicks title={songRow.title} items={songRow.items} />}
      {signedIn && (
        <Shelf
          title="Your library"
          items={library.data?.items ?? []}
          action={<SeeAll to="/library" />}
        />
      )}
      {others.map((s) => (
        <Shelf key={s.title} title={s.title} items={s.items} />
      ))}
      {explore.isLoading && <ShelfSkeleton />}
      <Shelf title="Charts" items={explore.data?.charts ?? []} />
      <Shelf title="Top artists" items={explore.data?.artists ?? []} />
      {moods.map((g) => (
        <MoodGrid key={g.title} group={g} />
      ))}
    </div>
  );
}

function SeeAll({ to }: { to: string }) {
  return (
    <Link
      to={to}
      className="inline-flex h-9 items-center gap-1 rounded-full px-3 text-[13px] font-semibold text-fg-muted hover:bg-surface-2 hover:text-fg"
    >
      See all <ArrowRight className="size-4" aria-hidden />
    </Link>
  );
}

function SetupBanner() {
  const setup = useSetup();
  const failing = setup.data?.checks.filter((c) => c.status === "fail") ?? [];
  if (!failing.length) return null;
  return (
    <Link
      to="/server/setup"
      className="mx-4 mb-4 flex items-center gap-3 rounded-[14px] border border-warning/40 bg-warning/10 p-3.5 text-[14px] md:mx-8"
    >
      <Wrench className="size-5 shrink-0 text-warning" aria-hidden />
      <span className="min-w-0 flex-1">
        <b>Finish setup.</b>{" "}
        <span className="text-fg-muted">
          {failing.length === 1
            ? `${failing[0]?.name} needs attention.`
            : `${failing.length} checks need attention.`}
        </span>
      </span>
      <ArrowRight className="size-4 shrink-0" aria-hidden />
    </Link>
  );
}

function MoodChips({ group }: { group: MoodGroup }) {
  const navigate = useNavigate();
  return (
    <nav className="scroll-x mb-6 flex gap-2 px-4 md:px-8" aria-label={group.title}>
      {group.categories.slice(0, 14).map((c) => (
        <Chip
          key={c.params}
          onClick={() =>
            void navigate({
              to: "/mood/$params",
              params: { params: c.params },
              search: { title: c.title },
            })
          }
          className="bg-fg/8 backdrop-blur hover:bg-fg/14"
        >
          {c.title}
        </Chip>
      ))}
    </nav>
  );
}

const TILE = [
  "from-[#7c3aed] to-[#4c1d95]",
  "from-[#0ea5e9] to-[#1e3a8a]",
  "from-[#f43f5e] to-[#7f1d1d]",
  "from-[#10b981] to-[#064e3b]",
  "from-[#f59e0b] to-[#7c2d12]",
  "from-[#ec4899] to-[#581c87]",
  "from-[#14b8a6] to-[#134e4a]",
  "from-[#6366f1] to-[#1e1b4b]",
];

/** Moods & genres as colourful tiles. */
export function MoodGrid({ group, limit = 12 }: { group: MoodGroup; limit?: number }) {
  const navigate = useNavigate();
  return (
    <section className="mb-8" aria-label={group.title}>
      <SectionTitle>{group.title}</SectionTitle>
      <div className="grid grid-cols-2 gap-3 px-4 sm:grid-cols-3 md:px-8 lg:grid-cols-4 xl:grid-cols-6">
        {group.categories.slice(0, limit).map((c, i) => (
          <button
            key={c.params}
            type="button"
            onClick={() =>
              void navigate({
                to: "/mood/$params",
                params: { params: c.params },
                search: { title: c.title },
              })
            }
            className={`relative h-[72px] overflow-hidden rounded-[12px] bg-gradient-to-br px-3.5 text-left text-[15px] font-bold text-white shadow-sm transition-transform duration-120 hover:scale-[1.02] active:scale-[0.98] ${TILE[i % TILE.length]}`}
          >
            <span className="relative z-10 line-clamp-2">{c.title}</span>
            <span
              aria-hidden
              className="absolute -right-4 -bottom-6 size-20 rounded-full bg-white/12"
            />
          </button>
        ))}
      </div>
    </section>
  );
}

export function ItemsPage({ items }: { items: Item[] }) {
  return <CardGrid items={items} />;
}
