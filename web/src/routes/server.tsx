// The "Server" pages: Status, Stats, History, Setup, Settings. Loaded on demand (their own
// chunk): listening comes first, administration second.

import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import {
  Activity,
  BarChart3,
  Check,
  ChevronDown,
  ChevronRight,
  CircleCheck,
  CircleX,
  Copy,
  Download,
  History as HistoryIcon,
  Info,
  ListChecks,
  LogOut,
  Monitor,
  Moon,
  Play,
  RefreshCw,
  Search,
  Settings,
  Star,
  Sun,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { PageHeader } from "@/components/page";
import { Artwork } from "@/components/ui/artwork";
import { Card, EmptyState, Skeleton, StatusDot } from "@/components/ui/bits";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import { ApiError, get, goToSignIn, isDemo, post, qs } from "@/lib/api";
import { thumb } from "@/lib/art";
import { cn } from "@/lib/cn";
import { ago, clock, duration, mmss, plural } from "@/lib/format";
import { useDevices, useHealth, useSetup, useStats } from "@/lib/queries";
import { savedTheme, setTheme, type ThemeChoice } from "@/lib/theme";
import type { HistoryResponse, HistoryRow, SetupCheck, TestPlay } from "@/lib/types";
import { BROWSER, browserLabel, echoName, usePlayer } from "@/store/player";
import { toast } from "@/store/toast";
import { useUi } from "@/store/ui";

// ---------- hub (phones) ----------

const PAGES = [
  { to: "/server/status", label: "Status", icon: Activity, note: "Health and monitoring" },
  {
    to: "/server/stats",
    label: "Stats",
    icon: BarChart3,
    note: "Plays, listening time, favourites",
  },
  { to: "/server/history", label: "History", icon: HistoryIcon, note: "Every song played" },
  { to: "/server/setup", label: "Setup", icon: ListChecks, note: "Checklist and test play" },
  {
    to: "/server/settings",
    label: "Settings",
    icon: Settings,
    note: "Theme, favourite device, sign out",
  },
] as const;

export function ServerPage() {
  const health = useHealth();
  const h = health.data;
  return (
    <div>
      <PageHeader
        back="mobile"
        title="Server"
        subtitle={h ? `echo-tunes ${h.version} · up ${duration(h.uptime_seconds)}` : " "}
      />
      {h && (
        <div className="mx-4 mb-4 flex items-center gap-3 rounded-[16px] border border-border bg-surface p-4 md:mx-8">
          <StatusDot tone={h.status === "ok" ? "ok" : "warn"} pulse={h.status === "ok"} />
          <span className="text-[15px] font-semibold">
            {h.status === "ok" ? "Everything's healthy" : "Something needs attention"}
          </span>
        </div>
      )}
      <ul className="mx-4 overflow-hidden rounded-[16px] border border-border bg-surface md:mx-8">
        {PAGES.map(({ to, label, icon: Icon, note }) => (
          <li key={to} className="border-b border-border last:border-0">
            <Link to={to} className="flex min-h-16 items-center gap-4 px-4 hover:bg-surface-2">
              <span className="grid size-10 place-items-center rounded-[12px] bg-accent-soft text-accent">
                <Icon className="size-5" aria-hidden />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-[15px] font-semibold">{label}</span>
                <span className="block truncate text-[13px] text-fg-muted">{note}</span>
              </span>
              <ChevronRight className="size-5 text-fg-subtle" aria-hidden />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------- status & monitoring ----------

function Tile({
  label,
  value,
  note,
  tone,
}: {
  label: string;
  value: string;
  note?: string;
  tone?: "ok" | "warn" | "bad";
}) {
  return (
    <div className="rounded-[16px] border border-border bg-surface p-4 shadow-elevated">
      <div className="flex items-center gap-2 text-[12.5px] font-semibold text-fg-muted">
        {tone && <StatusDot tone={tone} />}
        {label}
      </div>
      <div className="tabular mt-1.5 truncate text-[24px] font-bold tracking-tight">{value}</div>
      {note && <div className="mt-0.5 truncate text-[12.5px] text-fg-muted">{note}</div>}
    </div>
  );
}

function CopyBlock({ title, note, code }: { title: string; note: string; code: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="min-w-0 rounded-[14px] border border-border bg-surface-2/50">
      <div className="flex items-start gap-3 p-4 pb-2">
        <div className="min-w-0 flex-1">
          <h3 className="text-[15px] font-semibold">{title}</h3>
          <p className="text-[13px] text-fg-muted">{note}</p>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(code);
              setCopied(true);
              setTimeout(() => setCopied(false), 2000);
            } catch {
              toast("Couldn't copy: select the text and copy it.", { tone: "error" });
            }
          }}
        >
          {copied ? <Check /> : <Copy />}
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <pre className="thin-scroll overflow-x-auto px-4 pb-4 font-mono text-[12.5px] leading-relaxed text-fg">
        {code}
      </pre>
    </div>
  );
}

export function StatusPage() {
  const health = useHealth(true);
  const h = health.data;
  const base = isDemo() ? "http://your-server:8081" : location.origin;
  const host = isDemo() ? "your-server:8081" : location.host;
  const https = !isDemo() && location.protocol === "https:";
  const recipes = [
    {
      title: "Uptime Kuma: is it up and healthy?",
      note: "Monitor type: HTTP(s) - Json Query. Headers: the API token (see below).",
      code: `URL:            ${base}/api/health\nJSON query:     status\nExpected value: ok\nInterval:       60 s\nHeaders:        {"Authorization": "Bearer <your API token>"}`,
    },
    {
      title: "Uptime Kuma: is the public side reachable?",
      note: "Monitor type: HTTP(s) (from outside your network if you can)",
      code: "URL: https://<your public address>/healthz",
    },
    {
      title: "Prometheus scrape config",
      note: "Then graph it in Grafana; metric names start with echo_tunes_.",
      code: `- job_name: echo-tunes\n  scrape_interval: 30s\n  metrics_path: /metrics${https ? "\n  scheme: https" : ""}\n  authorization:\n    type: Bearer\n    credentials: <your API token>\n  static_configs:\n    - targets: ["${host}"]`,
    },
    {
      title: "Home Assistant: now-playing sensor",
      note: "configuration.yaml (REST sensor)",
      code: `rest:\n  - resource: ${base}/api/now\n    scan_interval: 15\n    headers:\n      Authorization: "Bearer <your API token>"\n    sensor:\n      - name: "echo-tunes now playing"\n        value_template: "{{ value_json.devices[0].current.title if value_json.devices else 'Nothing' }}"`,
    },
  ];
  return (
    <div>
      <PageHeader
        back="mobile"
        title="Status"
        subtitle={h ? `echo-tunes ${h.version}` : "Checking…"}
      />
      <div className="grid grid-cols-2 gap-3 px-4 md:px-8 xl:grid-cols-4">
        {h ? (
          <>
            <Tile
              label="Status"
              tone={h.status === "ok" ? "ok" : "warn"}
              value={h.status === "ok" ? "Healthy" : "Degraded"}
              note={h.last_error || "All checks passing"}
            />
            <Tile
              label="YouTube audio"
              tone={h.youtube === "ok" ? "ok" : h.youtube === "failing" ? "bad" : undefined}
              value={
                h.youtube === "ok" ? "Working" : h.youtube === "failing" ? "Failing" : "Unknown"
              }
              note={h.last_audio_ok ? `Last OK ${ago(h.last_audio_ok)}` : "No songs yet"}
            />
            <Tile
              label="Uptime"
              value={duration(h.uptime_seconds)}
              note={`Memory ${h.memory_mb} MB`}
            />
            <Tile
              label="History"
              value={h.history_plays.toLocaleString()}
              note={`Plays kept · ${h.history_days} days`}
            />
          </>
        ) : (
          [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[104px] rounded-[16px]" />)
        )}
      </div>
      <div className="px-4 pt-8 md:px-8">
        <h2 className="text-[20px] font-bold tracking-tight">Add echo-tunes to your monitoring</h2>
        <p className="mt-1 mb-4 max-w-2xl text-[14px] text-fg-muted">
          Copy-paste settings for the tools you already run. These addresses are on this private
          dashboard. With a dashboard password set, give monitors their own token: set{" "}
          <code className="rounded bg-surface-2 px-1 text-fg">ECHO_TUNES_DASHBOARD_API_TOKEN</code>{" "}
          on the server and use it where the snippets say {"<your API token>"} (without a password,
          leave the header out). See{" "}
          <a
            className="font-semibold text-accent hover:underline"
            href="https://github.com/denzilrdz/echo-tunes/blob/main/docs/MONITORING.md"
            rel="noreferrer"
            target="_blank"
          >
            MONITORING.md
          </a>
          .
        </p>
        <div className="grid min-w-0 gap-3 xl:grid-cols-2">
          {recipes.map((r) => (
            <CopyBlock key={r.title} {...r} />
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------- filters shared by stats and history ----------

function PeriodSelect({
  value,
  onChange,
  keep,
}: {
  value: number;
  onChange: (d: number) => void;
  keep: number;
}) {
  const ranges: [number, string][] = (
    [
      [1, "Last 24 hours"],
      [7, "Last 7 days"],
      [15, "Last 15 days"],
      [30, "Last 30 days"],
      [90, "Last 90 days"],
    ] as [number, string][]
  ).filter(([d]) => d <= keep);
  if (!ranges.some(([d]) => d === keep)) ranges.push([keep, `All (${keep} days)`]);
  return (
    <Select
      label="Period"
      value={String(value)}
      onChange={(v) => onChange(Number(v))}
      options={ranges.map(([d, t]) => [String(d), t])}
    />
  );
}

function DeviceSelect({ value, onChange }: { value: string; onChange: (d: string) => void }) {
  const devices = useDevices();
  const options: [string, string][] = [
    ["", "All devices"],
    ...(devices.data ?? []).map((d): [string, string] => [
      d.id,
      d.id === "browser" ? d.name || "Web player" : echoName(d),
    ]),
  ];
  return <Select label="Device" value={value} onChange={onChange} options={options} />;
}

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: [string, string][];
}) {
  return (
    <label className="flex min-w-0 flex-col gap-1 text-[12px] font-semibold text-fg-muted">
      {label}
      <span className="relative">
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="h-11 w-full min-w-[150px] appearance-none rounded-[12px] border border-border bg-surface pr-10 pl-3 text-[14px] font-medium text-fg focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
        >
          {options.map(([v, t]) => (
            <option key={v} value={v}>
              {t}
            </option>
          ))}
        </select>
        <ChevronDown
          aria-hidden
          className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-fg-muted"
        />
      </span>
    </label>
  );
}

const keepDays = (d: number | undefined) => Math.max(1, d || 1);

// ---------- stats ----------

export function StatsPage() {
  const health = useHealth();
  const keep = keepDays(health.data?.history_days);
  const [days, setDays] = useState(7);
  const [device, setDevice] = useState("");
  const d = Math.min(days, keep);
  const stats = useStats(d, device);
  const s = stats.data;
  const hours = s ? s.listened_minutes / 60 : 0;
  return (
    <div>
      <PageHeader back="mobile" title="Stats" subtitle="What you've been listening to" />
      <div className="flex flex-wrap gap-3 px-4 pb-5 md:px-8">
        <PeriodSelect value={d} onChange={setDays} keep={keep} />
        <DeviceSelect value={device} onChange={setDevice} />
      </div>
      <div className="grid grid-cols-2 gap-3 px-4 md:px-8 xl:grid-cols-4">
        {s ? (
          <>
            <Tile
              label="Plays"
              value={s.plays.toLocaleString()}
              note={`in ${plural(s.days, "day")}`}
            />
            <Tile
              label="Listening time"
              value={hours >= 1 ? `${hours.toFixed(1)} h` : `${s.listened_minutes} min`}
              note={`≈ ${Math.round(s.listened_minutes / Math.max(1, s.days))} min a day`}
            />
            <Tile label="Different songs" value={s.songs.toLocaleString()} />
            <Tile label="Different artists" value={s.artists.toLocaleString()} />
          </>
        ) : (
          [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[104px] rounded-[16px]" />)
        )}
      </div>
      <div className="px-4 pt-4 md:px-8">
        <Card>
          <h2 className="mb-3 text-[16px] font-bold">Plays per day</h2>
          {s ? <DayChart rows={s.per_day} days={s.days} /> : <Skeleton className="h-[200px]" />}
        </Card>
      </div>
      <div className="grid gap-4 px-4 pt-4 md:px-8 xl:grid-cols-2">
        <Card>
          <h2 className="mb-2 text-[16px] font-bold">Top songs</h2>
          <Ranked
            items={(s?.top_songs ?? []).map((t) => ({
              a: t.title,
              b: t.artist,
              n: t.plays,
              art: thumb(t.video_id),
            }))}
          />
        </Card>
        <Card>
          <h2 className="mb-2 text-[16px] font-bold">Top artists</h2>
          <Ranked items={(s?.top_artists ?? []).map((t) => ({ a: t.artist, b: "", n: t.plays }))} />
        </Card>
      </div>
    </div>
  );
}

function Ranked({ items }: { items: { a: string; b: string; n: number; art?: string }[] }) {
  if (!items.length) return <p className="py-4 text-[14px] text-fg-muted">Nothing yet.</p>;
  const max = Math.max(...items.map((i) => i.n));
  return (
    <ol className="space-y-1">
      {items.map((i, k) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: a ranking; names can repeat
        <li key={`${i.a}-${k}`} className="flex items-center gap-3 py-1.5">
          <span className="tabular w-5 text-right text-[13px] font-semibold text-fg-subtle">
            {k + 1}
          </span>
          {i.art !== undefined && <Artwork src={i.art} size={40} className="size-10" />}
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline justify-between gap-3">
              <span className="truncate text-[14px] font-medium">
                {i.a}
                {i.b && <span className="text-fg-muted"> · {i.b}</span>}
              </span>
              <span className="tabular shrink-0 text-[13px] text-fg-muted">{i.n}×</span>
            </div>
            <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-fg/8">
              <div
                className="h-full rounded-full bg-accent"
                style={{ width: `${(100 * i.n) / max}%` }}
              />
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}

function DayChart({ rows, days }: { rows: { day: string; plays: number }[]; days: number }) {
  const box = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(640);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(
      ([e]) => e && setW(Math.max(280, Math.round(e.contentRect.width))),
    );
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const byDay = new Map(rows.map((r) => [r.day, r.plays]));
  const list: { key: string; n: number; d: Date }[] = [];
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(Date.now() - i * 86400000);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    list.push({ key, n: byDay.get(key) ?? 0, d });
  }
  const H = 200;
  const pad = 24;
  const max = Math.max(1, ...list.map((x) => x.n));
  const bw = (w - pad) / list.length;
  const every = list.length <= 15 ? 1 : Math.ceil(list.length / 10);
  return (
    <div ref={box} className="w-full">
      <svg
        width={w}
        height={H}
        viewBox={`0 0 ${w} ${H}`}
        role="img"
        aria-label={`Plays per day over ${plural(days, "day")}, at most ${max}`}
        className="block"
      >
        {[0.5, 1].map((f) => (
          <line
            key={f}
            x1={pad}
            x2={w}
            y1={H - pad - (H - pad - 10) * f}
            y2={H - pad - (H - pad - 10) * f}
            className="stroke-border"
            strokeDasharray="3 4"
          />
        ))}
        <text x={0} y={14} className="fill-fg-subtle text-[11px]">
          {max}
        </text>
        {list.map(({ key, n, d }, i) => {
          const h = ((H - pad - 10) * n) / max;
          return (
            <g key={key}>
              <rect
                x={pad + i * bw + bw * 0.18}
                y={H - pad - h}
                width={Math.max(2, bw * 0.64)}
                height={Math.max(h, n ? 3 : 0)}
                rx={Math.min(6, bw * 0.25)}
                className="fill-accent"
              >
                <title>{`${d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" })}: ${plural(n, "play")}`}</title>
              </rect>
              {i % every === 0 && (
                <text
                  x={pad + i * bw + bw / 2}
                  y={H - 6}
                  textAnchor="middle"
                  className="fill-fg-subtle text-[11px]"
                >
                  {list.length <= 7 ? d.toLocaleDateString([], { weekday: "short" }) : d.getDate()}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ---------- history ----------

const STATUS: Record<string, [string, string]> = {
  finished: ["text-fg-muted bg-fg/6", "Played"],
  playing: ["text-success bg-success/12", "Playing"],
  stopped: ["text-fg-muted bg-fg/6", "Paused"],
  skipped: ["text-warning bg-warning/12", "Skipped"],
  failed: ["text-danger bg-danger/12", "Failed"],
};

export function HistoryPage() {
  const search = useSearch({ from: "/server/history" });
  const navigate = useNavigate({ from: "/server/history" });
  const health = useHealth();
  const keep = keepDays(health.data?.history_days);
  const days = Math.min(search.days ?? Math.min(7, keep), keep);
  const device = search.device ?? "";
  const q = search.q ?? "";
  const [text, setText] = useState(q);
  const actions = usePlayer((s) => s.info.actions);
  const [confirm, setConfirm] = useState(false);
  const client = useQueryClient();
  useEffect(() => {
    const id = setTimeout(() => {
      if (text.trim() !== q)
        void navigate({ search: (s) => ({ ...s, q: text.trim() || undefined }), replace: true });
    }, 250);
    return () => clearTimeout(id);
  }, [text, q, navigate]);
  const hist = useInfiniteQuery({
    queryKey: ["history", days, device, q],
    queryFn: ({ pageParam }) =>
      get<HistoryResponse>(`/api/history${qs({ limit: 50, offset: pageParam, days, device, q })}`),
    initialPageParam: 0,
    getNextPageParam: (last, all) =>
      last.plays.length < 50 ? undefined : all.reduce((n, p) => n + p.plays.length, 0),
    refetchInterval: 30_000,
  });
  const rows = hist.data?.pages.flatMap((p) => p.plays) ?? [];
  const enabled = hist.data?.pages[0]?.enabled ?? true;
  return (
    <div>
      <PageHeader
        back="mobile"
        title="History"
        subtitle={`Every song played in the last ${plural(keep, "day")}`}
      />
      <div className="flex flex-wrap items-end gap-3 px-4 pb-4 md:px-8">
        <DeviceSelect
          value={device}
          onChange={(v) =>
            void navigate({ search: (s) => ({ ...s, device: v || undefined }), replace: true })
          }
        />
        <PeriodSelect
          value={days}
          keep={keep}
          onChange={(v) => void navigate({ search: (s) => ({ ...s, days: v }), replace: true })}
        />
        <label className="flex min-w-[200px] flex-1 flex-col gap-1 text-[12px] font-semibold text-fg-muted">
          Search
          <span className="relative">
            <Search
              className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
              aria-hidden
            />
            <input
              type="search"
              value={text}
              maxLength={100}
              onChange={(e) => setText(e.target.value)}
              placeholder="Song or artist"
              className="h-11 w-full rounded-[12px] border border-border bg-surface pr-3 pl-9 text-[14px] font-medium text-fg placeholder:text-fg-subtle focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
            />
          </span>
        </label>
        {actions && (
          <Button
            variant="ghost"
            size="md"
            className="text-danger hover:text-danger"
            onClick={() => setConfirm(true)}
          >
            <Trash2 /> Clear history
          </Button>
        )}
      </div>
      <div className="px-2 md:px-6">
        {hist.isLoading ? (
          Array.from({ length: 8 }, (_, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: placeholders
            <Skeleton key={i} className="mx-2 my-2 h-14 rounded-[10px]" />
          ))
        ) : !rows.length ? (
          <EmptyState
            icon={HistoryIcon}
            title={enabled ? "No songs in this period" : "History is turned off"}
          >
            {enabled
              ? "Play something, or pick a longer period."
              : "Set ECHO_TUNES_HISTORY_DAYS to keep a history."}
          </EmptyState>
        ) : (
          <ol aria-label="Plays">
            {rows.map((r) => (
              <HistoryItem key={r.id} r={r} />
            ))}
          </ol>
        )}
        {hist.hasNextPage && (
          <div className="flex justify-center py-4">
            <Button
              variant="secondary"
              onClick={() => void hist.fetchNextPage()}
              disabled={hist.isFetchingNextPage}
            >
              {hist.isFetchingNextPage ? "Loading…" : "Show more"}
            </Button>
          </div>
        )}
      </div>
      <Sheet
        open={confirm}
        onOpenChange={setConfirm}
        title="Clear all history?"
        description="This deletes every play from the server's history, for every device. Stats start again from zero."
      >
        <div className="flex justify-end gap-2 px-5 pt-2 pb-6">
          <Button variant="ghost" onClick={() => setConfirm(false)}>
            Cancel
          </Button>
          <Button
            variant="danger"
            onClick={async () => {
              setConfirm(false);
              try {
                const r = await post<{ removed: number }>("/api/history/clear", {});
                toast(`Deleted ${plural(r.removed, "play")} from the history.`, {
                  tone: "success",
                });
                void client.invalidateQueries({ queryKey: ["history"] });
                void client.invalidateQueries({ queryKey: ["stats"] });
              } catch (err) {
                toast(err instanceof Error ? err.message : String(err), { tone: "error" });
              }
            }}
          >
            <Trash2 /> Delete everything
          </Button>
        </div>
      </Sheet>
    </div>
  );
}

function HistoryItem({ r }: { r: HistoryRow }) {
  const [cls, label] = STATUS[r.status] ?? ["text-fg-muted bg-fg/6", r.status];
  const listened =
    r.played_ms != null
      ? `${mmss(r.played_ms)}${r.duration ? ` / ${mmss(r.duration * 1000)}` : ""}`
      : "–";
  const where =
    r.device === "browser"
      ? r.device_name || "Web player"
      : r.device_name || `Echo …${r.device.slice(-6)}`;
  return (
    <li className="grid grid-cols-[44px_1fr_auto] items-center gap-x-3 gap-y-0.5 rounded-[10px] px-2 py-2.5 hover:bg-surface-2 md:grid-cols-[44px_minmax(0,2fr)_minmax(0,1fr)_minmax(0,1.2fr)_90px_96px]">
      <Artwork src={thumb(r.video_id)} size={44} className="row-span-2 size-11 md:row-span-1" />
      <div className="min-w-0">
        <div className="truncate text-[15px] font-medium md:text-[14px]">{r.title}</div>
        <div className="truncate text-[13px] text-fg-muted">{r.artist}</div>
      </div>
      <span
        className={cn(
          "justify-self-end rounded-full px-2.5 py-0.5 text-[12px] font-semibold md:order-last",
          cls,
        )}
      >
        {label}
      </span>
      <div className="col-start-2 col-end-4 truncate text-[12.5px] text-fg-muted md:col-auto md:text-[13px]">
        <span className="md:hidden">
          {clock(r.started)} · {where}
          {r.source ? ` · ${r.source}` : ""}
        </span>
        <span className="hidden md:inline">{where}</span>
      </div>
      <div className="hidden truncate text-[13px] text-fg-muted md:block" title={r.source}>
        {r.source}
      </div>
      <div
        className="tabular hidden text-[13px] text-fg-muted md:block"
        title={`Listened ${listened}`}
      >
        <div>{clock(r.started)}</div>
        <div className="text-[12px] text-fg-subtle">{ago(r.started)}</div>
      </div>
    </li>
  );
}

// ---------- setup ----------

const CHECK_ICON = {
  ok: [CircleCheck, "text-success"],
  warn: [TriangleAlert, "text-warning"],
  fail: [CircleX, "text-danger"],
  info: [Info, "text-accent"],
} as const;

export function SetupPage() {
  const setup = useSetup();
  const client = useQueryClient();
  const [rerunning, setRerunning] = useState(false);
  const r = setup.data;
  const counts = (r?.checks ?? []).reduce<Record<string, number>>((a, c) => {
    a[c.status] = (a[c.status] ?? 0) + 1;
    return a;
  }, {});
  const rerun = async () => {
    setRerunning(true);
    try {
      const fresh = await get<NonNullable<typeof r>>("/api/setup?refresh=1");
      client.setQueryData(["setup"], fresh);
    } catch (err) {
      toast(err instanceof Error ? err.message : String(err), { tone: "error" });
    } finally {
      setRerunning(false);
    }
  };
  return (
    <div>
      <PageHeader back="mobile" title="Setup" subtitle="The same checks as echo-tunes doctor" />
      <div className="grid gap-4 px-4 md:px-8 xl:grid-cols-[1.4fr_1fr]">
        <Card>
          <div className="flex items-start gap-3">
            <div className="min-w-0 flex-1">
              <h2 className="text-[17px] font-bold">Checklist</h2>
              <p className="mt-0.5 text-[13px] text-fg-muted" aria-live="polite">
                {setup.isLoading || rerunning
                  ? "Running checks… (YouTube can take a few seconds)"
                  : setup.error
                    ? "Couldn't run the checks."
                    : r?.status === "ok"
                      ? `Everything works (${plural(counts.ok ?? 0, "check")} passed). Checked ${ago(r.time)}.`
                      : r
                        ? `${plural(counts.fail ?? 0, "problem")}, ${plural(counts.warn ?? 0, "warning")}. Checked ${ago(r.time)}.`
                        : ""}
              </p>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={rerun}
              disabled={rerunning || setup.isLoading}
            >
              <RefreshCw className={rerunning ? "animate-spin" : ""} /> Run again
            </Button>
          </div>
          <ul className="mt-4 divide-y divide-border">
            {setup.isLoading
              ? Array.from({ length: 6 }, (_, i) => (
                  // biome-ignore lint/suspicious/noArrayIndexKey: placeholders
                  <li key={i} className="py-3">
                    <Skeleton className="h-10" />
                  </li>
                ))
              : (r?.checks ?? []).map((c) => <CheckRow key={c.name} c={c} />)}
          </ul>
        </Card>
        <TestPlayCard />
      </div>
    </div>
  );
}

function CheckRow({ c }: { c: SetupCheck }) {
  const [Icon, color] = CHECK_ICON[c.status] ?? CHECK_ICON.info;
  return (
    <li className="flex gap-3 py-3">
      <Icon className={cn("mt-0.5 size-5 shrink-0", color)} aria-label={c.status} />
      <div className="min-w-0 flex-1">
        <div className="text-[14.5px] font-semibold">{c.name}</div>
        <div className="text-[13px] break-words text-fg-muted">{c.detail}</div>
        {c.hint && c.status !== "ok" && (
          <div className="mt-1.5 rounded-[10px] bg-surface-2 px-3 py-2 text-[13px]">
            {c.hint}{" "}
            {c.link && (
              <a
                href={c.link}
                rel="noreferrer"
                target="_blank"
                className="font-semibold text-accent hover:underline"
              >
                {c.status === "info" ? "Learn more" : "How to fix"}
              </a>
            )}
          </div>
        )}
      </div>
    </li>
  );
}

/** POST /api/test-play (newer servers); older ones only have GET (they answer POST with 405). */
export async function testPlay(): Promise<TestPlay> {
  try {
    return await post<TestPlay>("/api/test-play", {});
  } catch (err) {
    if (err instanceof ApiError && err.status === 405) return get<TestPlay>("/api/test-play");
    throw err;
  }
}

function TestPlayCard() {
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const audio = useRef<HTMLAudioElement>(null);
  return (
    <Card className="self-start">
      <h2 className="text-[17px] font-bold">Test play</h2>
      <p className="mt-1 text-[14px] text-fg-muted">
        Plays a song in this browser through YouTube, this server and your public address, the same
        way an Echo does. If you hear it, everything but the Alexa skill works.
      </p>
      <Button
        variant="primary"
        className="mt-4"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setStatus("Getting the song (a few seconds the first time)…");
          try {
            const t = await testPlay();
            if (t.demo) {
              setStatus(
                "This is the demo: on your own server, a song plays here through your public address.",
              );
              return;
            }
            const el = audio.current;
            if (!t.url || !el) throw new Error(t.error || "not available");
            el.hidden = false;
            el.src = t.url;
            el.onplaying = () =>
              setStatus(
                `Playing “${t.title}” by ${t.artist} via ${new URL(t.url ?? "").host}. It works.`,
              );
            el.onerror = () =>
              setStatus(
                "The browser couldn't load the audio through the public address. Check the checklist.",
              );
            await el.play();
          } catch (err) {
            setStatus(
              `Couldn't start the test song: ${err instanceof Error ? err.message : String(err)}`,
            );
          } finally {
            setBusy(false);
          }
        }}
      >
        <Play className="fill-current" /> Play a test song
      </Button>
      <p className="mt-3 min-h-5 text-[13.5px] text-fg-muted" aria-live="polite">
        {status}
      </p>
      {/* biome-ignore lint/a11y/useMediaCaption: a test tone of a song; nothing to caption */}
      <audio ref={audio} controls preload="none" hidden className="mt-2 w-full" />
      <h3 className="mt-5 text-[15px] font-semibold">Then on your Echo</h3>
      <ol className="mt-2 list-decimal space-y-1.5 pl-5 text-[14px] text-fg-muted">
        <li>Alexa developer console → your skill → Test → set testing to Development.</li>
        <li>Say “Alexa, ask my tunes to play Tum Hi Ho”.</li>
        <li>It appears under Devices here within a few seconds.</li>
      </ol>
    </Card>
  );
}

// ---------- settings ----------

interface InstallPrompt extends Event {
  prompt: () => Promise<void>;
}
let deferredInstall: InstallPrompt | null = null;
if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredInstall = e as InstallPrompt;
  });
}

export function SettingsPage() {
  const [theme, setChoice] = useState<ThemeChoice>(savedTheme());
  const favourite = usePlayer((s) => s.favourite);
  const echos = usePlayer((s) => s.info.echos);
  const health = useHealth();
  const open = useUi((u) => u.open);
  const favName =
    favourite === BROWSER
      ? browserLabel()
      : favourite
        ? echoName(echos.find((e) => e.id === favourite) ?? { id: favourite, name: "" })
        : "Not chosen yet";
  const signOut = async (all: boolean) => {
    if (isDemo()) {
      toast("This is the demo: there's nothing to sign out of.");
      return;
    }
    try {
      await post(all ? "/api/logout/all" : "/api/logout", {});
      goToSignIn();
    } catch (err) {
      if (err instanceof ApiError && (err.status === 404 || err.status === 405) && all)
        toast("This server can't sign everyone out yet; update echo-tunes.", { tone: "error" });
      else toast(err instanceof Error ? err.message : String(err), { tone: "error" });
    }
  };
  const themes: [ThemeChoice, string, typeof Sun][] = [
    ["system", "System", Monitor],
    ["light", "Light", Sun],
    ["dark", "Dark", Moon],
  ];
  return (
    <div>
      <PageHeader back="mobile" title="Settings" />
      <div className="max-w-2xl space-y-4 px-4 md:px-8">
        <Card>
          <h2 className="text-[16px] font-bold">Appearance</h2>
          <div
            role="radiogroup"
            aria-label="Theme"
            className="mt-3 grid grid-cols-3 gap-1 rounded-[14px] bg-surface-2 p-1"
          >
            {themes.map(([v, label, Icon]) => (
              // biome-ignore lint/a11y/useSemanticElements: a segmented control
              <button
                key={v}
                type="button"
                role="radio"
                aria-checked={theme === v}
                onClick={() => {
                  setChoice(v);
                  setTheme(v);
                }}
                className={cn(
                  "flex h-11 items-center justify-center gap-2 rounded-[11px] text-[14px] font-semibold transition-colors",
                  theme === v
                    ? "bg-surface text-fg shadow-elevated"
                    : "text-fg-muted hover:text-fg",
                )}
              >
                <Icon className="size-4" aria-hidden />
                {label}
              </button>
            ))}
          </div>
        </Card>
        <Card>
          <h2 className="text-[16px] font-bold">Favourite device</h2>
          <p className="mt-1 text-[14px] text-fg-muted">
            Chosen every time you open echo-tunes on this device.
          </p>
          <div className="mt-3 flex items-center gap-3">
            <Star className="size-5 fill-warning text-warning" aria-hidden />
            <span className="flex-1 text-[15px] font-semibold">{favName}</span>
            <Button size="sm" variant="outline" onClick={() => open("devices")}>
              Change
            </Button>
          </div>
        </Card>
        <InstallCard />
        {!isDemo() && (
          <Card>
            <h2 className="text-[16px] font-bold">Signing in</h2>
            <p className="mt-1 text-[14px] text-fg-muted">
              This device stays signed in until you sign out.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => void signOut(false)}>
                <LogOut /> Sign out
              </Button>
              <Button
                variant="ghost"
                className="text-danger hover:text-danger"
                onClick={() => void signOut(true)}
              >
                Sign out everywhere
              </Button>
            </div>
          </Card>
        )}
        <p className="px-1 pb-4 text-[13px] text-fg-muted">
          echo-tunes {health.data?.version ?? ""} ·{" "}
          <a
            className="font-semibold text-accent hover:underline"
            href="https://github.com/denzilrdz/echo-tunes"
            rel="noreferrer"
            target="_blank"
          >
            Source and docs
          </a>
        </p>
      </div>
    </div>
  );
}

function InstallCard() {
  const [can, setCan] = useState(!!deferredInstall);
  const standalone =
    typeof window !== "undefined" && window.matchMedia("(display-mode: standalone)").matches;
  useEffect(() => {
    const on = () => setCan(true);
    window.addEventListener("beforeinstallprompt", on);
    return () => window.removeEventListener("beforeinstallprompt", on);
  }, []);
  if (standalone) return null;
  return (
    <Card>
      <h2 className="text-[16px] font-bold">Install the app</h2>
      <p className="mt-1 text-[14px] text-fg-muted">
        Its own icon, full screen, lock-screen controls. Needs HTTPS (or localhost). On iPhone:
        Share → Add to Home Screen. On Android: menu → Install app.
      </p>
      {can && (
        <Button
          className="mt-3"
          variant="primary"
          onClick={async () => {
            await deferredInstall?.prompt();
            deferredInstall = null;
            setCan(false);
          }}
        >
          <Download /> Install echo-tunes
        </Button>
      )}
    </Card>
  );
}
