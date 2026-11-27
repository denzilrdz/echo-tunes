// Server state through TanStack Query. Live things (Echos, now playing, health) poll every few
// seconds while the page is visible; browsing results are kept for a few minutes.

import { QueryClient, useQuery } from "@tanstack/react-query";
import { get, qs } from "./api";
import type {
  Device,
  Explore,
  Health,
  HomeResponse,
  Item,
  NowResponse,
  PlayerInfo,
  SetupResult,
  Stats,
  TracksResponse,
} from "./types";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (n, err) => n < 2 && (err as { status?: number }).status !== 401,
      refetchOnWindowFocus: true,
      staleTime: 30_000,
    },
  },
});

const LIVE = 4_000;

export const usePlayerInfo = () =>
  useQuery({
    queryKey: ["player"],
    queryFn: () => get<PlayerInfo>("/api/player"),
    refetchInterval: LIVE,
    staleTime: 0,
  });

export const useNow = () =>
  useQuery({
    queryKey: ["now"],
    queryFn: () => get<NowResponse>("/api/now"),
    refetchInterval: 5_000,
    staleTime: 0,
  });

export const useHealth = (live = false) =>
  useQuery({
    queryKey: ["health"],
    queryFn: () => get<Health>("/api/health"),
    refetchInterval: live ? 5_000 : 60_000,
  });

export const useDevices = () =>
  useQuery({ queryKey: ["devices"], queryFn: () => get<Device[]>("/api/devices") });

export const useHome = () =>
  useQuery({
    queryKey: ["home"],
    queryFn: () => get<HomeResponse>("/api/browse/home"),
    staleTime: 10 * 60_000,
  });

export const useExplore = () =>
  useQuery({
    queryKey: ["explore"],
    queryFn: () => get<Explore>("/api/browse/explore"),
    staleTime: 30 * 60_000,
  });

export const useLibrary = (enabled: boolean) =>
  useQuery({
    queryKey: ["library"],
    queryFn: () => get<{ items: Item[] }>("/api/browse/library"),
    staleTime: 5 * 60_000,
    enabled,
  });

export const useMood = (params: string) =>
  useQuery({
    queryKey: ["mood", params],
    queryFn: () => get<{ items: Item[] }>(`/api/browse/mood${qs({ params })}`),
    staleTime: 30 * 60_000,
  });

export const useTracks = (kind: string, id: string) =>
  useQuery({
    queryKey: ["tracks", kind, id],
    queryFn: () => get<TracksResponse>(`/api/browse/tracks${qs({ kind, id })}`),
    staleTime: 10 * 60_000,
  });

export const useSearch = (q: string, kind: string) =>
  useQuery({
    queryKey: ["search", kind, q],
    queryFn: () => get<{ kind: string; items: Item[] }>(`/api/search${qs({ q, kind })}`),
    enabled: q.length > 0,
    staleTime: 5 * 60_000,
    placeholderData: (prev) => prev,
  });

export const useStats = (days: number, device: string) =>
  useQuery({
    queryKey: ["stats", days, device],
    queryFn: () =>
      get<Stats>(`/api/stats${qs({ days, device, tz: -new Date().getTimezoneOffset() })}`),
  });

export const useSetup = () =>
  useQuery({
    queryKey: ["setup"],
    queryFn: () => get<SetupResult>("/api/setup"),
    staleTime: 60_000,
    retry: false,
  });
