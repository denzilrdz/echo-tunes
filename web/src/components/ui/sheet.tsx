import { Drawer } from "@base-ui/react/drawer";
import { X } from "lucide-react";
import type * as React from "react";
import { cn } from "@/lib/cn";
import { IconButton } from "./button";

interface SheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  /** Visually hide the title (it still names the dialog for screen readers). */
  hideTitle?: boolean;
  description?: React.ReactNode;
  children: React.ReactNode;
  /** "auto": a bottom sheet on phones, a centred card from 768 px. "full": the whole screen. */
  layout?: "auto" | "full";
  className?: string;
  /** Extra styles on the popup (CSS variables such as --np-art; set through the CSSOM). */
  style?: React.CSSProperties;
  bare?: boolean; // no header/close button: the content draws its own
}

/** A swipe-to-dismiss bottom sheet (Base UI Drawer), the app's one modal surface. */
export function Sheet({
  open,
  onOpenChange,
  title,
  hideTitle,
  description,
  children,
  layout = "auto",
  className,
  style,
  bare,
}: SheetProps) {
  const full = layout === "full";
  return (
    <Drawer.Root open={open} onOpenChange={(o) => onOpenChange(o)} swipeDirection="down">
      <Drawer.Portal>
        <Drawer.Backdrop className="sheet-backdrop fixed inset-0 z-50 bg-[var(--scrim)] backdrop-blur-[2px]" />
        <Drawer.Viewport
          className={cn(
            "fixed inset-0 z-50 flex justify-center",
            full ? "items-stretch" : "items-end md:items-center md:p-6",
          )}
        >
          <Drawer.Popup
            style={style}
            className={cn(
              "sheet-popup relative flex w-full flex-col bg-elevated text-fg shadow-pop outline-none",
              full
                ? "h-[100dvh] max-w-none"
                : "sheet-center max-h-[88dvh] rounded-t-[22px] pb-[env(safe-area-inset-bottom)] md:max-h-[80dvh] md:max-w-[440px] md:rounded-[22px] md:pb-0",
              className,
            )}
          >
            {!full && (
              <div className="flex justify-center pt-2.5 pb-1 md:hidden" aria-hidden>
                <div className="h-1.5 w-10 rounded-full bg-fg/20" />
              </div>
            )}
            {bare ? (
              <Drawer.Title className="sr-only">{title}</Drawer.Title>
            ) : (
              <div className="flex items-start gap-3 px-5 pt-3 pb-2 md:pt-5">
                <div className="min-w-0 flex-1">
                  <Drawer.Title
                    className={cn("text-xl font-bold tracking-tight", hideTitle && "sr-only")}
                  >
                    {title}
                  </Drawer.Title>
                  {description && (
                    <Drawer.Description className="mt-1 text-sm text-fg-muted">
                      {description}
                    </Drawer.Description>
                  )}
                </div>
                <Drawer.Close
                  render={<IconButton label="Close" size="sm" className="-mr-1.5 -mt-1" />}
                >
                  <X />
                </Drawer.Close>
              </div>
            )}
            <Drawer.Content className="thin-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain">
              {children}
            </Drawer.Content>
          </Drawer.Popup>
        </Drawer.Viewport>
      </Drawer.Portal>
    </Drawer.Root>
  );
}
