export const GESTURE_EVENT = 'maid:gesture'
export const GESTURE_PREFIX = 'жест:'
export const FALLBACK_GESTURES = [
  { id: 'headpat', label: 'гладит тебя по голове', title: 'Погладить по голове',
    zone: 'head', token: '⟦жест: гладит тебя по голове⟧' },
]

export function dispatchGesture(gesture) {
  window.dispatchEvent(new CustomEvent(GESTURE_EVENT, { detail: gesture }))
}

export function gestureChipText(inner) {
  const t = String(inner || '').trim()
  return t.startsWith(GESTURE_PREFIX) ? t.slice(GESTURE_PREFIX.length).trim() : t
}

export function insertAtCaret(value, start, end, token) {
  const v = String(value || '')
  const s = Math.max(0, Math.min(start ?? v.length, v.length))
  const e = Math.max(s, Math.min(end ?? s, v.length))
  const before = v.slice(0, s)
  const after = v.slice(e)
  const lead = before && !/\s$/.test(before) ? ' ' : ''
  const trail = after && !/^\s/.test(after) ? ' ' : ''
  const ins = lead + token + trail
  return { value: before + ins + after, caret: before.length + ins.length }
}

const TOKEN_RX = /⟦[^⟧]*⟧/g

export function tokenSpans(value) {
  const v = String(value || '')
  const out = []
  TOKEN_RX.lastIndex = 0
  let m
  while ((m = TOKEN_RX.exec(v)) !== null) out.push({ start: m.index, end: m.index + m[0].length })
  return out
}

function spanInside(spans, pos) {
  return spans.find((s) => s.start < pos && pos < s.end) || null
}

export function deleteTokenAt(value, pos, dir) {
  const v = String(value || '')
  const spans = tokenSpans(v)
  const s = spanInside(spans, pos)
    || spans.find((t) => (dir === 'back' ? t.end === pos : t.start === pos))
  if (!s) return null
  return { value: v.slice(0, s.start) + v.slice(s.end), caret: s.start }
}

export function jumpOverToken(value, pos, dir) {
  const spans = tokenSpans(value)
  const s = dir === 'left' ? spans.find((t) => t.end === pos) : spans.find((t) => t.start === pos)
  if (!s) return null
  return dir === 'left' ? s.start : s.end
}
