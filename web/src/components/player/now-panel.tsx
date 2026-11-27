import { X } from "lucide-react";
import { create } from "zustand";
import { trackArt } from "@/lib/art";
import { useArtColour } from "@/lib/hooks";
import { load, save } from "@/lib/storage";
import { useUi } from "@/store/ui";
import { Artwork } from "../ui/artwork";
import { IconButton } from "../ui/button";
import { useShowing } from "./controls";
import { UpNext } from "./up-next";

interface PanelStore {
  open: boolean;
  toggle: () => void;
}

/** Wide screens: the Now Playing panel on the right (remembered per browser). */
export const usePanel = create<PanelStore>((set, get) => ({
  open: load("et.panel", true),
  toggle: () => {
    save("et.panel", !get().open);
    set({ open: !get().open });
  },
}));

export function NowPanel() {
  const open = usePanel((p) => p.open);
  const toggle = usePanel((p) => p.toggle);
  const s = useShowing();
  const openSheet = useUi((u) => u.open);
  const art = s.track ? trackArt(s.track, 640) : null;
  const colour = useArtColour(s.track ? trackArt(s.track, 120) : null);
  if (!open) return null;
  return (
    <aside
      aria-label="Now playing"
      className="fixed top-0 right-0 bottom-20 z-30 hidden w-[340px] flex-col border-l border-border bg-surface xl:flex"
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-[420px] opacity-80 transition-[background] duration-500"
        style={
          colour
            ? { background: `linear-gradient(180deg, ${colour} 0%, transparent 100%)` }
            : undefined
        }
      />
      <div className="relative flex items-center gap-2 px-5 pt-5">
        <h2 className="min-w-0 flex-1 truncate text-[13px] font-semibold tracking-[0.12em] text-fg-muted uppercase">
          Now playing · {s.where}
        </h2>
        <IconButton label="Hide the Now Playing panel" size="sm" onClick={toggle}>
          <X />
        </IconButton>
      </div>
      <div className="thin-scroll relative min-h-0 flex-1 overflow-y-auto pb-4">
        <button
          type="button"
          className="mx-5 mt-4 block w-[calc(100%-40px)] text-left"
          onClick={() => openSheet("now")}
          aria-label="Open Now Playing"
        >
          <Artwork
            key={art ?? "none"}
            src={art}
            size={300}
            className="art-fade aspect-square w-full rounded-[14px] shadow-[0_24px_48px_-20px_rgb(0_0_0/0.6)]"
          />
          <div className="mt-4 truncate text-[20px] font-bold tracking-tight">
            {s.track?.title ?? "Nothing playing"}
          </div>
          <div className="truncate text-[14px] text-fg-muted">
            {s.track?.artist ?? `Pick something to play on ${s.where}`}
          </div>
        </button>
        <div className="mt-5 -mx-1">
          <UpNext showCurrent={false} />
        </div>
      </div>
    </aside>
  );
}
