// Row menus (⋯ and right-click). One menu host for the whole app, loaded the first time a menu
// opens, so the menu library isn't part of the first download.

import { MoreHorizontal } from "lucide-react";
import type * as React from "react";
import { lazy, Suspense } from "react";
import { create } from "zustand";
import { cn } from "@/lib/cn";

export interface MenuAction {
  label: string;
  icon?: React.ComponentType<{ className?: string }>;
  onSelect: () => void;
  disabled?: boolean;
  hint?: string;
}

export interface MenuRequest {
  actions: MenuAction[];
  /** The ⋯ button (focus returns to it), or a point for right-click. */
  anchor: HTMLElement | { x: number; y: number };
  label: string;
}

interface MenuStore {
  request: MenuRequest | null;
  used: boolean;
  show: (r: MenuRequest) => void;
  hide: () => void;
}

export const useMenu = create<MenuStore>((set) => ({
  request: null,
  used: false,
  show: (request) => set({ request, used: true }),
  hide: () => set({ request: null }),
}));

const MenuHost = lazy(() => import("./menu-host"));

/** Mount once (in the app shell). */
export function MenuOutlet() {
  const used = useMenu((m) => m.used);
  if (!used) return null;
  return (
    <Suspense fallback={null}>
      <MenuHost />
    </Suspense>
  );
}

/** Warm the menu code in the background once the page is idle. */
export const preloadMenu = (): void => {
  void import("./menu-host");
};

/** The ⋯ button on a row: Play now, Play next, Add to queue, Start radio, Go to artist… */
export function ActionsMenu({
  actions,
  label,
  className,
}: {
  actions: MenuAction[];
  label: string;
  className?: string;
}) {
  const open = useMenu((m) => m.request?.anchor);
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-haspopup="menu"
      aria-expanded={false}
      className={cn(
        "inline-flex size-11 shrink-0 items-center justify-center rounded-full text-fg-muted transition-colors hover:bg-surface-2 hover:text-fg",
        className,
      )}
      onClick={(e) => {
        e.stopPropagation();
        const el = e.currentTarget;
        if (open === el) useMenu.getState().hide();
        else useMenu.getState().show({ actions, anchor: el, label });
      }}
    >
      <MoreHorizontal className="size-5" />
    </button>
  );
}

/** Right-click on a row opens the same actions at the pointer. */
export function WithContextMenu({
  actions,
  children,
  className,
  label = "Actions",
}: {
  actions: MenuAction[];
  children: React.ReactNode;
  className?: string;
  label?: string;
}) {
  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: a pointer shortcut; the ⋯ button is the keyboard way
    <div
      className={className}
      onContextMenu={(e) => {
        e.preventDefault();
        useMenu.getState().show({ actions, anchor: { x: e.clientX, y: e.clientY }, label });
      }}
    >
      {children}
    </div>
  );
}
