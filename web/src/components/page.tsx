import { Link, useRouter } from "@tanstack/react-router";
import { ChevronLeft, Settings } from "lucide-react";
import type * as React from "react";
import { cn } from "@/lib/cn";
import { IconButton } from "./ui/button";

/** A page's title row. Phones get the safe-area inset (the status bar overlays the app). */
export function PageHeader({
  title,
  subtitle,
  back,
  actions,
  className,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  back?: boolean | "mobile";
  actions?: React.ReactNode;
  className?: string;
}) {
  const router = useRouter();
  return (
    <header
      className={cn(
        "flex items-center gap-2 px-4 pt-[calc(env(safe-area-inset-top)+14px)] pb-4 md:px-8 md:pt-8",
        className,
      )}
    >
      {back && (
        <IconButton
          label="Back"
          onClick={() => router.history.back()}
          className={cn("-ml-2 text-fg", back === "mobile" && "lg:hidden")}
        >
          <ChevronLeft className="size-6" />
        </IconButton>
      )}
      <div className="min-w-0 flex-1">
        {title && (
          <h1 className="truncate text-[28px] leading-tight font-extrabold tracking-[-0.02em] md:text-[32px]">
            {title}
          </h1>
        )}
        {subtitle && <p className="mt-0.5 truncate text-[14px] text-fg-muted">{subtitle}</p>}
      </div>
      {actions}
    </header>
  );
}

/** The gear that leads to the Server pages (phones; desktop has them in the sidebar). */
export function ServerLink() {
  return (
    <Link
      to="/server"
      aria-label="Server: status, stats, history, setup and settings"
      title="Server"
      className="grid size-11 place-items-center rounded-full text-fg-muted hover:bg-surface-2 hover:text-fg lg:hidden"
    >
      <Settings className="size-[22px]" />
    </Link>
  );
}

export function Container({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={cn("px-4 md:px-8", className)}>{children}</div>;
}

export function ErrorNote({ error, retry }: { error: unknown; retry?: () => void }) {
  return (
    <div className="mx-4 my-6 rounded-[14px] border border-border bg-surface p-5 text-[14px] md:mx-8">
      <p className="font-semibold">That didn't load.</p>
      <p className="mt-1 text-fg-muted">{error instanceof Error ? error.message : String(error)}</p>
      {retry && (
        <button
          type="button"
          onClick={retry}
          className="mt-3 h-10 rounded-full bg-surface-2 px-4 text-[13px] font-semibold hover:bg-surface-3"
        >
          Try again
        </button>
      )}
    </div>
  );
}
