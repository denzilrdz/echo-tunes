import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import {
  Activity,
  BarChart3,
  History,
  Home,
  Library,
  ListChecks,
  Search,
  Settings,
  Speaker,
} from "lucide-react";
import { lazy, Suspense, useEffect } from "react";
import { isDemo } from "@/lib/api";
import { cn } from "@/lib/cn";
import { shotsMode } from "@/lib/params";
import { usePlayerInfo } from "@/lib/queries";
import { KEYS, load } from "@/lib/storage";
import { usePlayer } from "@/store/player";
import { useUi } from "@/store/ui";
import { DevicePill, MiniPlayer, PlayerBar } from "./player/bars";
import { NowPanel, usePanel } from "./player/now-panel";
import { MenuOutlet, preloadMenu } from "./ui/menu";
import { Toaster } from "./ui/toaster";

const MAIN = [
  { to: "/", label: "Home", icon: Home },
  { to: "/search", label: "Search", icon: Search },
  { to: "/library", label: "Library", icon: Library },
  { to: "/devices", label: "Devices", icon: Speaker },
] as const;

const SERVER = [
  { to: "/server/status", label: "Status", icon: Activity },
  { to: "/server/stats", label: "Stats", icon: BarChart3 },
  { to: "/server/history", label: "History", icon: History },
  { to: "/server/setup", label: "Setup", icon: ListChecks },
  { to: "/server/settings", label: "Settings", icon: Settings },
] as const;

export const appName = (): string =>
  document.querySelector<HTMLMetaElement>('meta[name="application-name"]')?.content || "echo-tunes";

function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-3">
      <img src="static/icon.svg" alt="" width={32} height={32} className="size-8 rounded-[9px]" />
      <span className="truncate text-[17px] font-bold tracking-tight">{appName()}</span>
    </div>
  );
}

function SideLink({ to, label, icon: Icon }: { to: string; label: string; icon: typeof Home }) {
  return (
    <Link
      to={to}
      activeOptions={{ exact: to === "/" }}
      className="group flex h-11 items-center gap-3.5 rounded-[10px] px-3 text-[14.5px] font-semibold text-fg-muted transition-colors hover:bg-surface-2 hover:text-fg data-[status=active]:bg-surface-2 data-[status=active]:text-fg"
    >
      <Icon className="size-[20px] group-data-[status=active]:text-accent" aria-hidden />
      {label}
    </Link>
  );
}

function Sidebar() {
  return (
    <nav
      aria-label="Main"
      className="fixed top-0 bottom-20 left-0 z-30 hidden w-[248px] flex-col gap-6 border-r border-border bg-surface px-3 pt-6 pb-4 lg:flex"
    >
      <Brand />
      <div className="flex flex-col gap-0.5">
        {MAIN.map((l) => (
          <SideLink key={l.to} {...l} />
        ))}
      </div>
      <div className="flex flex-col gap-0.5">
        <div className="px-3 pb-1.5 text-[11px] font-semibold tracking-[0.12em] text-fg-subtle uppercase">
          Server
        </div>
        {SERVER.map((l) => (
          <SideLink key={l.to} {...l} />
        ))}
      </div>
      <div className="mt-auto px-1">
        <DevicePill className="w-full justify-start" />
      </div>
    </nav>
  );
}

function TabBar() {
  const path = useRouterState({ select: (s) => s.location.pathname });
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-border/70 bg-bg/88 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl lg:hidden"
    >
      <div className="mx-auto grid h-16 max-w-xl grid-cols-4">
        {MAIN.map(({ to, label, icon: Icon }) => {
          const active = to === "/" ? path === "/" : path.startsWith(to);
          return (
            <Link
              key={to}
              to={to}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex flex-col items-center justify-center gap-1 text-[11px] font-semibold transition-colors",
                active ? "text-fg" : "text-fg-subtle",
              )}
            >
              <Icon
                className={cn("size-6", active && "text-accent")}
                strokeWidth={active ? 2.3 : 1.9}
                aria-hidden
              />
              {label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

/** Keeps the player store in step with /api/player and opens the first-run sheet once. */
function PlayerSync() {
  const info = usePlayerInfo();
  const setInfo = usePlayer((s) => s.setInfo);
  useEffect(() => {
    if (info.data) setInfo(info.data);
  }, [info.data, setInfo]);
  useEffect(() => {
    if (!info.data) return;
    const shots = shotsMode();
    if (
      !shots &&
      !load(KEYS.welcomed, false) &&
      !load(KEYS.favourite, null) &&
      !useUi.getState().sheet
    ) {
      useUi.getState().open("welcome");
    }
  }, [info.data]);
  return null;
}

// Sheets and menus load after the first screen (they aren't needed to see it), then stay.
const AllSheets = lazy(() => import("./player/sheets"));
const preloadSheets = () => void import("./player/sheets");

function SheetsOutlet() {
  const used = useUi((u) => u.used);
  useEffect(() => {
    const idle = window.requestIdleCallback ?? ((cb: () => void) => setTimeout(cb, 1200));
    idle(() => {
      preloadSheets();
      preloadMenu();
    });
  }, []);
  if (!used) return null;
  return (
    <Suspense fallback={null}>
      <AllSheets />
    </Suspense>
  );
}

export function AppShell() {
  const path = useRouterState({ select: (s) => s.location.pathname });
  const panel = usePanel((p) => p.open);
  // biome-ignore lint/correctness/useExhaustiveDependencies: scroll to the top on every new page
  useEffect(() => {
    window.scrollTo({ top: 0 });
    // A new page closes Now Playing and the pickers (not the first-run questions).
    const { sheet, close } = useUi.getState();
    if (sheet && sheet !== "welcome" && sheet !== "echoTip") close();
  }, [path]);
  return (
    <>
      <a
        href="#main"
        className="sr-only z-[80] rounded-md bg-accent px-3 py-2 text-accent-fg focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Skip to content
      </a>
      {isDemo() && <DemoBanner />}
      <Sidebar />
      <main
        id="main"
        className={cn(
          "min-h-[100dvh] pb-[calc(176px+env(safe-area-inset-bottom))] lg:pb-28 lg:pl-[248px]",
          panel && "xl:pr-[340px]",
        )}
      >
        <Outlet />
      </main>
      <NowPanel />
      <MiniPlayer />
      <TabBar />
      <PlayerBar />
      <SheetsOutlet />
      <MenuOutlet />
      <Toaster />
      <PlayerSync />
    </>
  );
}

function DemoBanner() {
  if (shotsMode()) return null;
  return (
    <div className="relative z-30 bg-accent-soft px-4 pt-[env(safe-area-inset-top)] text-center text-[13px] text-fg lg:pl-[264px]">
      <p className="py-2">
        Demo with sample data: nothing plays and nothing is sent anywhere.{" "}
        <a
          className="font-semibold text-accent underline-offset-2 hover:underline"
          href="https://github.com/denzilrdz/echo-tunes"
        >
          Run your own echo-tunes
        </a>
      </p>
    </div>
  );
}
