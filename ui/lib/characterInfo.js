import { api } from '@/lib/api'

let cached = null
let inflight = null

export function peekCharacterInfo() {
  return cached
}

export function dropCharacterInfo() {
  cached = null
}

export function warmCharacterInfo() {
  if (inflight) return inflight
  inflight = api.characterInfo()
    .then((r) => { if (r && !r.error) cached = r; return cached })
    .catch(() => cached)
    .finally(() => { inflight = null })
  return inflight
}
