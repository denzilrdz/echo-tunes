import { useQueryClient } from "@tanstack/react-query";
import { ChevronDown, LoaderCircle, RefreshCw, WifiOff } from "lucide-react";
import { useEffect, useRef } from "react";
import { useTick } from "@/lib/hooks";
import { useConnection } from "@/store/connection";
import { Button } from "./ui/button";

/** Shown while the server can't be reached at all. It can't be dismissed: it goes away by
 *  itself once the server answers. What's already on screen stays visible underneath. */
export function ConnectionScreen() {
  const offline = useConnection((c) => c.offline);
  const checking = useConnection((c) => c.checking);
  const nextRetryAt = useConnection((c) => c.nextRetryAt);
  const retryNow = useConnection((c) => c.retryNow);
  const client = useQueryClient();
  const was = useRef(offline);
  useTick(offline, 1000);
  useEffect(() => {
    // Back online: refresh everything that may have failed meanwhile.
    if (was.current && !offline) void client.invalidateQueries();
    was.current = offline;
  }, [offline, client]);
  if (!offline) return null;
  const secs = Math.max(0, Math.ceil((nextRetryAt - Date.now()) / 1000));
  return (
    <div className="pointer-events-none fixed inset-x-0 top-0 z-[75] flex justify-center px-3 pt-[calc(env(safe-area-inset-top)+12px)] lg:pl-[260px]">
      <section
        role="alert"
        aria-labelledby="conn-title"
        className="toast-enter thin-scroll pointer-events-auto max-h-[78dvh] w-full max-w-[560px] overflow-y-auto rounded-[20px] border border-danger/40 bg-elevated p-5 shadow-pop"
      >
        <div className="flex items-start gap-3.5">
          <span className="grid size-11 shrink-0 place-items-center rounded-full bg-danger/14 text-danger">
            <WifiOff className="size-5" aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id="conn-title" className="text-[18px] leading-snug font-bold tracking-tight">
              Can't reach your echo-tunes server
            </h2>
            <p className="mt-1 text-[14px] text-fg-muted">
              Tried <span className="font-mono text-[13px] break-all text-fg">{location.host}</span>
              . What you see below may be out of date, and playing is off until it's back.
            </p>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button variant="primary" onClick={() => void retryNow()} disabled={checking}>
            {checking ? <LoaderCircle className="animate-spin" /> : <RefreshCw />}
            {checking ? "Trying…" : "Try again"}
          </Button>
          <span className="text-[13px] text-fg-muted" aria-live="off">
            {checking ? "" : `Trying again by itself in ${secs} s`}
          </span>
        </div>
        <details className="group mt-4 rounded-[14px] bg-surface-2 px-4 py-3 text-[14px]">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-2 font-semibold [&::-webkit-details-marker]:hidden">
            Why might this happen?
            <ChevronDown
              className="size-4 transition-transform group-open:rotate-180"
              aria-hidden
            />
          </summary>
          <ul className="mt-3 list-disc space-y-2.5 pl-5 text-fg-muted">
            <li>
              <b className="text-fg">Away from home:</b> connect to the network or VPN your server
              is on.
            </li>
            <li>
              <b className="text-fg">At home but still failing:</b> your browser or phone may be
              using its own “secure DNS” or “Private DNS” provider, which skips your network's DNS.
              In Chrome: Settings › Privacy and security › Security › Use secure DNS → “With your
              current service provider” (or off). On Android: Settings › Network › Private DNS →
              Automatic or Off. On iPhone: turn off iCloud Private Relay, or any DNS profile, for
              your home Wi-Fi.
            </li>
            <li>
              <b className="text-fg">The server may be restarting or down:</b> check its status page
              or your monitoring.
            </li>
          </ul>
        </details>
      </section>
    </div>
  );
}
