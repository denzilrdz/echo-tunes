// What a play button does and says, depending on where music goes.

import { useNavigate } from "@tanstack/react-router";
import { BROWSER, browserLabel, echoName, usePlayer } from "@/store/player";
import type { Item, Track } from "./types";

/** Items opened from a shelf, so their page can show the title and cover at once. */
const opened = new Map<string, Item>();
export const rememberItem = (item: Item): void => {
  if (opened.size > 200) opened.clear();
  opened.set(`${item.kind}:${item.id}`, item);
};
export const openedItem = (kind: string, id: string): Item | undefined =>
  opened.get(`${kind}:${id}`);

export const itemToTrack = (item: Item): Track => ({
  video_id: item.id,
  title: item.title,
  artist: item.subtitle,
  duration: item.duration,
  image: item.image,
});

/** The target's name and how play buttons read: "Play" here, "Play next" on an Echo. */
export function useTarget() {
  const target = usePlayer((s) => s.target);
  const info = usePlayer((s) => s.info);
  const onEcho = target !== BROWSER;
  const echo = info.echos.find((e) => e.id === target);
  const name = onEcho ? echoName(echo ?? { id: target, name: "" }) : browserLabel();
  return {
    onEcho,
    name,
    actions: info.actions,
    playLabel: onEcho ? "Play next" : "Play",
    playHint: onEcho ? `Play next on ${name}` : `Play on ${name.toLowerCase()}`,
    disabledReason: info.actions
      ? undefined
      : "Set a dashboard password on the server (ECHO_TUNES_DASHBOARD_PASSWORD) to play from here.",
  };
}

/** Opening an item: a song plays (with radio after it), anything else opens its page. */
export function useOpenItem() {
  const navigate = useNavigate();
  const play = usePlayer((s) => s.play);
  return (item: Item) => {
    if (item.kind === "song") {
      void play([itemToTrack(item)], `Radio after ${item.title}`, { radio: true });
      return;
    }
    rememberItem(item);
    void navigate({ to: "/collection/$kind/$id", params: { kind: item.kind, id: item.id } });
  };
}

export function shuffled<T>(list: T[]): T[] {
  const a = list.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j] as T, a[i] as T];
  }
  return a;
}
