import { useSyncExternalStore } from "react";
import { api } from "./api";

export interface AddonInfo {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  capabilities: string[];
}

let _addons: AddonInfo[] = [];
let _listSnapshot: AddonInfo[] = [];
let _enabledIds: Set<string> = new Set();
const _listeners = new Set<() => void>();

function _emit(): void {
  _listSnapshot = _addons.slice();
  _enabledIds = new Set(_addons.filter((a) => a.enabled).map((a) => a.id));
  _listeners.forEach((l) => l());
}

export async function refreshAddons(retries = 10, delayMs = 1500): Promise<void> {
  for (let attempt = 0; attempt < retries; attempt++) {
    try {
      const data = await api.addons();
      _addons = Array.isArray(data?.addons) ? data.addons : [];
      _emit();
      return;
    } catch {
      await new Promise((r) => setTimeout(r, delayMs));
    }
  }
}

export async function setAddonEnabled(id: string, enabled: boolean): Promise<void> {
  _addons = _addons.map((a) => (a.id === id ? { ...a, enabled } : a));
  _emit();
  try {
    await api.setAddon(id, enabled);
  } catch (e) {
    console.warn(`[addons] не удалось переключить «${id}»:`, e);
    _addons = _addons.map((a) => (a.id === id ? { ...a, enabled: !enabled } : a));
    _emit();
  }
}

function _subscribe(cb: () => void): () => void {
  _listeners.add(cb);
  return () => _listeners.delete(cb);
}

export function useAddons(): AddonInfo[] {
  return useSyncExternalStore(_subscribe, () => _listSnapshot, () => _listSnapshot);
}

export function useEnabledAddonIds(): Set<string> {
  return useSyncExternalStore(_subscribe, () => _enabledIds, () => _enabledIds);
}
