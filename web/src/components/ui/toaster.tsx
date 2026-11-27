import { CircleAlert, CircleCheck, Info, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { useToasts } from "@/store/toast";

/** Toasts sit above the mini-player / player bar; screen readers hear them (aria-live). */
export function Toaster() {
  const { toasts, dismiss } = useToasts();
  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 bottom-[calc(168px+env(safe-area-inset-bottom))] z-[70] flex flex-col items-center gap-2 px-3 lg:bottom-[104px]"
    >
      {toasts.map((t) => {
        const Icon = t.tone === "error" ? CircleAlert : t.tone === "success" ? CircleCheck : Info;
        return (
          <div
            key={t.id}
            className="toast-enter pointer-events-auto flex w-full max-w-[460px] items-center gap-3 rounded-[14px] border border-border bg-elevated py-2.5 pr-2 pl-3.5 text-[14px] text-fg shadow-pop"
          >
            <Icon
              aria-hidden
              className={cn(
                "size-5 shrink-0",
                t.tone === "error"
                  ? "text-danger"
                  : t.tone === "success"
                    ? "text-success"
                    : "text-accent",
              )}
            />
            <span className="min-w-0 flex-1 py-1">{t.text}</span>
            {t.action && (
              <button
                type="button"
                className="h-9 shrink-0 rounded-full px-3 text-[13px] font-semibold text-accent hover:bg-accent-soft"
                onClick={() => {
                  t.action?.run();
                  dismiss(t.id);
                }}
              >
                {t.action.label}
              </button>
            )}
            <button
              type="button"
              aria-label="Dismiss"
              className="grid size-9 shrink-0 place-items-center rounded-full text-fg-muted hover:bg-surface-2"
              onClick={() => dismiss(t.id)}
            >
              <X className="size-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
