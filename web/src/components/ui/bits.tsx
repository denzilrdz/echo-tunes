import type * as React from "react";
import { cn } from "@/lib/cn";

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("skeleton rounded-md", className)} />;
}

export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
  className,
}: {
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  title: string;
  children?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "mx-auto flex max-w-sm flex-col items-center px-6 py-14 text-center",
        className,
      )}
    >
      <div className="mb-4 grid size-16 place-items-center rounded-full bg-accent-soft text-accent">
        <Icon className="size-7" strokeWidth={1.8} />
      </div>
      <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
      {children && <div className="mt-1.5 text-sm text-fg-muted">{children}</div>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

/** A filter chip / segmented choice. */
export function Chip({
  active,
  children,
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { active?: boolean }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      className={cn(
        "inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full px-4 text-[13px] font-semibold transition-colors duration-120",
        active ? "bg-fg text-bg" : "bg-surface-2 text-fg hover:bg-surface-3",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export function SectionTitle({
  children,
  action,
  className,
}: {
  children: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mb-3 flex items-end justify-between gap-3 px-4 md:px-8", className)}>
      <h2 className="text-[20px] font-bold tracking-tight md:text-[22px]">{children}</h2>
      {action}
    </div>
  );
}

export function Card({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div
      className={cn(
        "rounded-[16px] border border-border bg-surface p-5 shadow-elevated",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function StatusDot({
  tone,
  pulse,
}: {
  tone: "ok" | "warn" | "bad" | "idle";
  pulse?: boolean;
}) {
  const color = {
    ok: "bg-success",
    warn: "bg-warning",
    bad: "bg-danger",
    idle: "bg-fg-subtle",
  }[tone];
  return (
    <span className="relative inline-flex size-2.5 shrink-0" aria-hidden>
      {pulse && (
        <span className={cn("absolute inset-0 animate-ping rounded-full opacity-60", color)} />
      )}
      <span className={cn("relative size-2.5 rounded-full", color)} />
    </span>
  );
}

/** Three bars that bounce while something plays. */
export function Equalizer({ playing, className }: { playing: boolean; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "equalizer inline-flex h-3.5 items-end gap-[2px]",
        !playing && "paused",
        className,
      )}
    >
      <span className="h-full w-[3px] rounded-full bg-current" />
      <span className="h-full w-[3px] rounded-full bg-current" />
      <span className="h-full w-[3px] rounded-full bg-current" />
    </span>
  );
}
