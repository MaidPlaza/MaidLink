import { useSyncExternalStore } from "react";
import type { ComponentType } from "react";
import { api } from "./api";

export type SettingType = "toggle" | "select" | "range" | "custom";

export interface SettingOption {
  value: string;
  label: string;
}

export interface SettingDescriptor {
  id: string;
  section: string;
  label: string;
  type: SettingType;
  default?: boolean | string;
  options?: SettingOption[];
  min?: number;
  max?: number;
  step?: number;
  component?: ComponentType;
  order?: number;
  sectionOrder?: number;
  persist?: "local" | "backend";
  addon?: string;
  lockDuringWave?: boolean;
  home?: "settings" | "context-model";
  hidden?: boolean;
}

const _list: SettingDescriptor[] = [];
const _ids = new Set<string>();
const _descListeners = new Set<() => void>();
let _descSnapshot: SettingDescriptor[] = [];

export function registerSetting(d: SettingDescriptor): void {
  if (_ids.has(d.id)) {
    console.warn(`[settings] дубликат id «${d.id}» — пропущен`);
    return;
  }
  _ids.add(d.id);
  _list.push(d);
  if (d.type !== "custom" && d.default !== undefined && !_values.has(d.id)) {
    if (d.persist === "backend") {
      _values.set(d.id, d.default);
    } else {
      const stored = _readStored(d.id);
      _values.set(d.id, stored !== undefined ? stored : d.default);
    }
  }
  _descSnapshot = _list.slice();
  _descListeners.forEach((l) => l());
  _valueListeners.forEach((l) => l());
}

export function registerSettings(ds: SettingDescriptor[]): void {
  ds.forEach(registerSetting);
}

function _subscribeDesc(cb: () => void): () => void {
  _descListeners.add(cb);
  return () => _descListeners.delete(cb);
}
function _getDescSnapshot(): SettingDescriptor[] {
  return _descSnapshot;
}

export function useSettingsSnapshot(): SettingDescriptor[] {
  return useSyncExternalStore(_subscribeDesc, _getDescSnapshot, _getDescSnapshot);
}

export function groupBySections(
  list: SettingDescriptor[],
): { section: string; items: SettingDescriptor[] }[] {
  const order: string[] = [];
  const map = new Map<string, SettingDescriptor[]>();
  const secOrder = new Map<string, number>();
  for (const d of list) {
    if (!map.has(d.section)) {
      map.set(d.section, []);
      order.push(d.section);
    }
    map.get(d.section)!.push(d);
    if (d.sectionOrder != null && !secOrder.has(d.section)) {
      secOrder.set(d.section, d.sectionOrder);
    }
  }
  order.sort((a, b) => (secOrder.get(a) ?? 0) - (secOrder.get(b) ?? 0));
  return order.map((section) => ({
    section,
    items: map
      .get(section)!
      .slice()
      .sort((a, b) => (a.order ?? 0) - (b.order ?? 0)),
  }));
}

const VALUE_PREFIX = "maidlink.setting.";
const _values = new Map<string, boolean | string>();
const _valueListeners = new Set<() => void>();

function _readStored(id: string): boolean | string | undefined {
  try {
    const raw = localStorage.getItem(VALUE_PREFIX + id);
    return raw == null ? undefined : (JSON.parse(raw) as boolean | string);
  } catch {
    return undefined;
  }
}

function _descById(id: string): SettingDescriptor | undefined {
  return _list.find((d) => d.id === id);
}

export function getSettingValue(id: string): boolean | string | undefined {
  if (_values.has(id)) return _values.get(id);
  return _descById(id)?.default;
}

async function _persistBackendSetting(
  id: string,
  value: boolean | string,
  prev: boolean | string | undefined,
  retries = 8,
  delayMs = 1500,
): Promise<void> {
  for (let attempt = 0; attempt < retries; attempt++) {
    try {
      await api.updateSettings({ [id]: value });
      return;
    } catch {
      await new Promise((r) => setTimeout(r, delayMs));
    }
    if (_values.get(id) !== value) return;
  }
  console.warn(`[settings] «${id}»: бэкенд не ответил — откатываю значение в UI`);
  if (_values.get(id) === value) {
    if (prev === undefined) _values.delete(id);
    else _values.set(id, prev);
    _valueListeners.forEach((l) => l());
  }
}

export function setSettingValue(id: string, value: boolean | string): void {
  const prev = _values.get(id);
  _values.set(id, value);
  const d = _descById(id);
  if (d?.persist === "backend") {
    void _persistBackendSetting(id, value, prev);
  } else {
    try {
      localStorage.setItem(VALUE_PREFIX + id, JSON.stringify(value));
    } catch {
    }
  }
  _valueListeners.forEach((l) => l());
}

function _subscribeValues(cb: () => void): () => void {
  _valueListeners.add(cb);
  return () => _valueListeners.delete(cb);
}

export function useSetting<T extends boolean | string>(
  id: string,
): [T, (v: T) => void] {
  const get = () => getSettingValue(id) as T;
  const value = useSyncExternalStore(_subscribeValues, get, get);
  return [value, (v: T) => setSettingValue(id, v)];
}

function _coerceForDescriptor(d: SettingDescriptor, raw: unknown): boolean | string {
  if (d.type === "toggle") {
    return typeof raw === "string" ? raw === "true" || raw === "1" : Boolean(raw);
  }
  return String(raw);
}

export async function hydrateBackendSettings(
  retries = 10,
  delayMs = 1500,
): Promise<void> {
  for (let attempt = 0; attempt < retries; attempt++) {
    try {
      const data = await api.getSettings();
      let changed = false;
      for (const [key, raw] of Object.entries(data || {})) {
        const d = _descById(key);
        if (!d || d.persist !== "backend") continue;
        _values.set(key, _coerceForDescriptor(d, raw));
        changed = true;
      }
      if (changed) _valueListeners.forEach((l) => l());
      return;
    } catch {
      await new Promise((r) => setTimeout(r, delayMs));
    }
  }
}
