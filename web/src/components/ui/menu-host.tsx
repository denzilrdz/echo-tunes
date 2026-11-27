import { Menu } from "@base-ui/react/menu";
import { useMenu } from "./menu";

const popup =
  "pop z-[60] min-w-[220px] overflow-hidden rounded-[14px] border border-border bg-elevated p-1.5 text-fg shadow-pop outline-none";
const item =
  "flex min-h-11 cursor-default select-none items-center gap-3 rounded-[10px] px-3 text-[14px] outline-none data-[highlighted]:bg-surface-2 data-[disabled]:opacity-45 [&_svg]:size-[18px] [&_svg]:text-fg-muted";

/** The one Base UI menu, anchored to whichever ⋯ button (or right-click point) asked. */
export default function MenuHost() {
  const request = useMenu((m) => m.request);
  const hide = useMenu((m) => m.hide);
  const anchor = request?.anchor;
  const virtual =
    anchor && !(anchor instanceof HTMLElement)
      ? {
          getBoundingClientRect: () =>
            DOMRect.fromRect({ x: anchor.x, y: anchor.y, width: 0, height: 0 }),
        }
      : anchor;
  return (
    <Menu.Root
      open={!!request}
      onOpenChange={(open) => {
        if (!open) hide();
      }}
    >
      <Menu.Portal>
        <Menu.Positioner
          anchor={virtual ?? null}
          sideOffset={6}
          align={anchor instanceof HTMLElement ? "end" : "start"}
          collisionPadding={12}
          className="z-[60]"
        >
          <Menu.Popup
            className={popup}
            aria-label={request?.label}
            finalFocus={anchor instanceof HTMLElement ? { current: anchor } : true}
          >
            {request?.actions.map((a) => (
              <Menu.Item
                key={a.label}
                className={item}
                disabled={a.disabled ?? false}
                title={a.hint}
                onClick={() => {
                  hide();
                  a.onSelect();
                }}
              >
                {a.icon && <a.icon />}
                <span className="flex-1">{a.label}</span>
              </Menu.Item>
            ))}
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}
