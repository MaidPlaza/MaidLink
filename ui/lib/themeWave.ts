import { useSyncExternalStore } from "react";

let active = false;
const listeners = new Set<() => void>();

export function setThemeWaveActive(v: boolean): void {
  const next = !!v;
  if (next === active) return;
  active = next;
  for (const fn of listeners) fn();
}

export function getThemeWaveActive(): boolean {
  return active;
}

function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function useThemeWaveActive(): boolean {
  return useSyncExternalStore(subscribe, getThemeWaveActive);
}
