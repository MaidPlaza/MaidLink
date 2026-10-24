import { useSyncExternalStore } from 'react'
import { api } from '@/lib/api'
import { resolveUrl } from '@/lib/url'

const REG = new Map()
const inflight = new Map()
let version = 0
const listeners = new Set()

function bump() {
  version++
  for (const fn of listeners) fn()
}

function subscribe(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

export function useCharacterUiVersion() {
  return useSyncExternalStore(subscribe, () => version)
}

export function getCharacterUi(c) {
  if (!c) return null
  return REG.get(c.baseline_id) || REG.get(c.id) || null
}

export function characterListAvatarUrl(c) {
  if (!c || !c.id) return ''
  return resolveUrl(`/api/characters/${encodeURIComponent(c.id)}/ui/list-avatar`)
}

export function getCharacterListAvatar(c) {
  const reg = getCharacterUi(c)
  return (reg && reg.avatarUrl) || null
}

async function fetchAvatarBlobUrl(c) {
  try {
    const res = await fetch(characterListAvatarUrl(c))
    if (!res.ok) return null
    return URL.createObjectURL(await res.blob())
  } catch {
    return null
  }
}

async function fetchBundle(c) {
  const key = c.baseline_id || c.id
  try {
    const [light, dark, avatarUrl] = await Promise.all([
      api.characterUiStructure(c.id, false).catch(() => null),
      api.characterUiStructure(c.id, true).catch(() => null),
      fetchAvatarBlobUrl(c),
    ])
    const entry = {
      structure: light && light.structure ? light.structure : null,
      dark: dark && dark.structure ? dark.structure : null,
      avatarUrl,
    }
    REG.set(key, entry)
    if (c.id && c.id !== key) REG.set(c.id, entry)
    bump()
  } finally {
    inflight.delete(key)
  }
}

export function ensureCharacterUi(rows) {
  const jobs = []
  for (const c of rows || []) {
    if (!c || !c.id) continue
    const key = c.baseline_id || c.id
    if (REG.has(key)) continue
    if (!inflight.has(key)) inflight.set(key, fetchBundle(c))
    jobs.push(inflight.get(key))
  }
  return Promise.allSettled(jobs)
}

export function refreshCharacterUi(rows) {
  for (const c of rows || []) {
    if (!c || !c.id) continue
    const key = c.baseline_id || c.id
    if (inflight.has(key)) continue
    const old = REG.get(key)
    REG.delete(key)
    if (c.id !== key) REG.delete(c.id)
    if (old && old.avatarUrl) { try { URL.revokeObjectURL(old.avatarUrl) } catch {} }
  }
  return ensureCharacterUi(rows)
}
