import { create } from "zustand";

export interface Toast {
  id: number;
  text: string;
  tone: "info" | "error" | "success";
  action?: { label: string; run: () => void };
}

interface ToastStore {
  toasts: Toast[];
  show: (text: string, opts?: Partial<Omit<Toast, "id" | "text">>) => void;
  dismiss: (id: number) => void;
}

let next = 1;
const timers = new Map<number, ReturnType<typeof setTimeout>>();

export const useToasts = create<ToastStore>((set, get) => ({
  toasts: [],
  show: (text, opts = {}) => {
    const id = next++;
    const toast: Toast = {
      id,
      text,
      tone: opts.tone ?? "info",
      ...(opts.action ? { action: opts.action } : {}),
    };
    set({ toasts: [...get().toasts.slice(-2), toast] });
    timers.set(
      id,
      setTimeout(() => get().dismiss(id), opts.action ? 7000 : 4500),
    );
  },
  dismiss: (id) => {
    clearTimeout(timers.get(id));
    timers.delete(id);
    set({ toasts: get().toasts.filter((t) => t.id !== id) });
  },
}));

export const toast = (text: string, opts?: Partial<Omit<Toast, "id" | "text">>): void =>
  useToasts.getState().show(text, opts);
