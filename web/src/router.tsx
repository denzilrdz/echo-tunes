// Hash routes (#/search, #/server/stats …): the GitHub Pages demo has no server to fall back
// to index.html, and the dashboard only serves "/".

import {
  createHashHistory,
  createRootRoute,
  createRoute,
  createRouter,
  lazyRouteComponent,
} from "@tanstack/react-router";
import { AppShell } from "./components/shell";
import { DevicesPage } from "./routes/devices";
import { HomePage } from "./routes/home";
import { CollectionPage, LibraryPage, MoodPage } from "./routes/library";
import { SearchPage, type SearchType } from "./routes/search";

const str = (v: unknown): string | undefined => (typeof v === "string" && v ? v : undefined);
const TYPES = new Set(["all", "song", "album", "artist", "playlist", "video"]);

const root = createRootRoute({ component: AppShell });

const home = createRoute({ getParentRoute: () => root, path: "/", component: HomePage });
const search = createRoute({
  getParentRoute: () => root,
  path: "/search",
  component: SearchPage,
  validateSearch: (s: Record<string, unknown>): { q?: string; type?: SearchType } => {
    const q = str(s.q)?.slice(0, 100);
    const type = str(s.type);
    return {
      ...(q ? { q } : {}),
      ...(type && TYPES.has(type) ? { type: type as SearchType } : {}),
    };
  },
});
const library = createRoute({
  getParentRoute: () => root,
  path: "/library",
  component: LibraryPage,
});
const devices = createRoute({
  getParentRoute: () => root,
  path: "/devices",
  component: DevicesPage,
});
const collection = createRoute({
  getParentRoute: () => root,
  path: "/collection/$kind/$id",
  component: CollectionPage,
});
const mood = createRoute({
  getParentRoute: () => root,
  path: "/mood/$params",
  component: MoodPage,
  validateSearch: (s: Record<string, unknown>): { title?: string } => {
    const title = str(s.title)?.slice(0, 80);
    return title ? { title } : {};
  },
});

const page = (
  name: "ServerPage" | "StatusPage" | "StatsPage" | "HistoryPage" | "SetupPage" | "SettingsPage",
) => lazyRouteComponent(() => import("./routes/server"), name);

const server = createRoute({
  getParentRoute: () => root,
  path: "/server",
  component: page("ServerPage"),
});
const status = createRoute({
  getParentRoute: () => root,
  path: "/server/status",
  component: page("StatusPage"),
});
const stats = createRoute({
  getParentRoute: () => root,
  path: "/server/stats",
  component: page("StatsPage"),
});
const history = createRoute({
  getParentRoute: () => root,
  path: "/server/history",
  component: page("HistoryPage"),
  validateSearch: (s: Record<string, unknown>): { device?: string; days?: number; q?: string } => {
    const device = str(s.device)?.slice(0, 64);
    const q = str(s.q)?.slice(0, 100);
    const days = Number(s.days);
    return {
      ...(device ? { device } : {}),
      ...(q ? { q } : {}),
      ...(Number.isInteger(days) && days >= 1 && days <= 3650 ? { days } : {}),
    };
  },
});
const setup = createRoute({
  getParentRoute: () => root,
  path: "/server/setup",
  component: page("SetupPage"),
});
const settings = createRoute({
  getParentRoute: () => root,
  path: "/server/settings",
  component: page("SettingsPage"),
});

const routeTree = root.addChildren([
  home,
  search,
  library,
  devices,
  collection,
  mood,
  server,
  status,
  stats,
  history,
  setup,
  settings,
]);

export const router = createRouter({
  routeTree,
  history: createHashHistory(),
  defaultPreload: "intent",
  scrollRestoration: true,
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
