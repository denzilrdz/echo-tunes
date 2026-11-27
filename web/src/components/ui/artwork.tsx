import { Disc3, Heart, ListMusic, Music2, UserRound } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/cn";
import type { Kind } from "@/lib/types";

interface ArtworkProps {
  src: string | null | undefined;
  size: number; // CSS pixels of the drawn square (also width/height, so nothing shifts)
  kind?: Kind | undefined;
  round?: boolean;
  className?: string;
  eager?: boolean;
}

const FALLBACK = { song: Music2, album: Disc3, playlist: ListMusic, artist: UserRound } as const;

/** Square cover art with a fixed size, lazy loading and a calm placeholder. */
export function Artwork({ src, size, kind = "song", round, className, eager }: ArtworkProps) {
  const [failed, setFailed] = useState<string | null>(null);
  const radius = round
    ? "rounded-full"
    : size <= 48
      ? "rounded-[4px]"
      : size <= 72
        ? "rounded-md"
        : "rounded-lg";
  const Icon = FALLBACK[kind];
  const show = src && failed !== src;
  // hqdefault thumbnails are letterboxed 4:3: zoom so only the cover shows.
  const zoom = src?.includes("/hqdefault.jpg") ? "scale-[1.34]" : "";
  return (
    <div className={cn("relative shrink-0 overflow-hidden bg-surface-2", radius, className)}>
      {show ? (
        <img
          src={src}
          alt=""
          width={size}
          height={size}
          loading={eager ? "eager" : "lazy"}
          decoding="async"
          draggable={false}
          referrerPolicy="no-referrer"
          onError={() => setFailed(src)}
          className={cn("size-full object-cover", zoom)}
        />
      ) : (
        <div className="grid size-full place-items-center bg-gradient-to-br from-surface-2 to-surface-3 text-fg-subtle">
          <Icon className="size-[38%]" strokeWidth={1.6} aria-hidden />
        </div>
      )}
    </div>
  );
}

/** "Liked songs" (playlist LM) gets its own cover, like in the YouTube Music app. */
export function LikedArt({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "grid shrink-0 place-items-center rounded-lg bg-gradient-to-br from-[#a78bfa] via-[#6d28d9] to-[#1e1b4b]",
        className,
      )}
    >
      <Heart className="size-[34%] fill-white text-white drop-shadow" aria-hidden />
    </div>
  );
}
