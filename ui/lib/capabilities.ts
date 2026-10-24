import { useSyncExternalStore } from "react";
import { api } from "./api";

export type Capabilities = { drawing: boolean; vision: boolean };

let _caps: Capabilities = { drawing: false, vision: false };
const _listeners = new Set<() => void>();

const _sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function refreshCapabilities(retries = Infinity, delayMs = 2000): Promise<void> {
  for (let attempt = 0; attempt < retries; attempt++) {
    try {
      const data = await api.capabilities();
      _caps = { drawing: Boolean(data.drawing), vision: Boolean(data.vision) };
      _listeners.forEach((l) => l());
      if (!_caps.drawing) void _watchDrawing();
      return;
    } catch {
      await _sleep(delayMs);
    }
  }
}

let _watchingDrawing = false;

async function _watchDrawing(): Promise<void> {
  if (_watchingDrawing) return;
  _watchingDrawing = true;
  try {
    for (let i = 0; i < 60 && !_caps.drawing; i++) {
      await _sleep(5000);
      try {
        const data = await api.capabilities();
        const next = { drawing: Boolean(data.drawing), vision: Boolean(data.vision) };
        if (next.drawing !== _caps.drawing || next.vision !== _caps.vision) {
          _caps = next;
          _listeners.forEach((l) => l());
        }
      } catch {
      }
    }
  } finally {
    _watchingDrawing = false;
  }
}

function _subscribe(cb: () => void): () => void {
  _listeners.add(cb);
  return () => _listeners.delete(cb);
}
function _getSnapshot(): Capabilities {
  return _caps;
}

export function useCapability(name: keyof Capabilities): boolean {
  const get = () => _getSnapshot()[name];
  return useSyncExternalStore(_subscribe, get, get);
}

export function getCapability(name: keyof Capabilities): boolean {
  return _caps[name];
}
