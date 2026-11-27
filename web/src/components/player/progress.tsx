import { useState } from "react";
import { cn } from "@/lib/cn";
import { mmss } from "@/lib/format";

/** Seek bar with times: a native range input (keyboard and screen readers for free), or a plain
 *  bar for an Echo, which the page can't seek. */
export function Progress({
  position,
  duration,
  onSeek,
  className,
}: {
  position: number;
  duration: number;
  onSeek?: ((seconds: number) => void) | undefined;
  className?: string;
  tone?: "default" | "onArt";
}) {
  const [drag, setDrag] = useState<number | null>(null);
  const max = Math.max(1, Math.round(duration));
  const value = Math.min(max, drag ?? position);
  const pct = duration ? (100 * value) / max : 0;
  const style = { "--pct": `${pct}%` } as React.CSSProperties;
  return (
    <div className={cn("w-full", className)}>
      {onSeek && duration ? (
        <input
          type="range"
          className="seek"
          min={0}
          max={max}
          step={1}
          value={Math.round(value)}
          style={style}
          aria-label="Song position"
          aria-valuetext={`${mmss(value * 1000)} of ${mmss(duration * 1000)}`}
          onChange={(e) => setDrag(Number(e.target.value))}
          onPointerUp={(e) => {
            onSeek(Number((e.target as HTMLInputElement).value));
            setDrag(null);
          }}
          onKeyUp={(e) => {
            onSeek(Number((e.target as HTMLInputElement).value));
            setDrag(null);
          }}
        />
      ) : (
        <div
          className="flex h-6 items-center"
          role="progressbar"
          aria-label="Song position"
          aria-valuemin={0}
          aria-valuemax={max}
          aria-valuenow={Math.round(value)}
          aria-valuetext={`${mmss(value * 1000)} of ${duration ? mmss(duration * 1000) : "unknown"}`}
        >
          <div className="h-1 w-full overflow-hidden rounded-full bg-fg/15">
            <div className="h-full rounded-full bg-fg" style={{ width: `${pct}%` }} />
          </div>
        </div>
      )}
      <div className="tabular -mt-0.5 flex justify-between text-[12px] text-fg-muted">
        <span>{mmss(value * 1000)}</span>
        <span>{duration ? mmss(duration * 1000) : "–"}</span>
      </div>
    </div>
  );
}

/** The 2 px line along the top of the mini-player. */
export function ProgressLine({ position, duration }: { position: number; duration: number }) {
  const pct = duration ? Math.min(100, (100 * position) / duration) : 0;
  return (
    <div
      className="absolute inset-x-3 top-0 h-[2px] overflow-hidden rounded-full bg-fg/10"
      aria-hidden
    >
      <div className="h-full rounded-full bg-fg/80" style={{ width: `${pct}%` }} />
    </div>
  );
}
