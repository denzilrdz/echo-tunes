import { create } from "zustand";

export type Sheet = "now" | "queue" | "devices" | "welcome" | "echoTip" | null;

interface UiStore {
  sheet: Sheet;
  used: boolean; // a sheet was opened: the sheet code (loaded on demand) stays mounted
  open: (sheet: Sheet) => void;
  close: () => void;
}

/** One sheet at a time: Now Playing, Up next, the device picker, first-run, Echo explainer. */
export const useUi = create<UiStore>((set) => ({
  sheet: null,
  used: false,
  open: (sheet) => set({ sheet, used: true }),
  close: () => set({ sheet: null }),
}));
