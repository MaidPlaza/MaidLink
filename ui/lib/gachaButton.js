const FRAME_STANDALONE = 'M5 1.5H43.5V43.5H5C3.067 43.5 1.5 41.933 1.5 40V5C1.5 3.067 3.067 1.5 5 1.5Z'
const FRAME_BLOCK_TOP = 'M5 1.5H43.5V43.5H1.5V5C1.5 3.067 3.067 1.5 5 1.5Z'
const FRAME_BLOCK_MIDDLE = 'M43.5 1.5V43.5H1.5V1.5H43.5Z'
const FRAME_BLOCK_BOTTOM = 'M43.5 1.5V43.5H5C3.067 43.5 1.5 41.933 1.5 40V1.5H43.5Z'

const TICKET_ICON =
  '<path d="M10.5 16.5h24v4a2.5 2.5 0 0 0 0 5v4h-24v-4a2.5 2.5 0 0 0 0-5z" stroke="{icon}" stroke-width="2" stroke-linejoin="round" fill="none"/>' +
  '<path d="M27.5 16.5v13" stroke="{icon}" stroke-width="2" stroke-dasharray="2 2"/>'

const HEX = '(#[0-9A-Fa-f]{3,8})'

function variants(svg) {
  return String(svg || '').split(/(?=<svg\b)/).filter((s) => s.startsWith('<svg'))
}

function colorsOf(variant) {
  const frame = new RegExp(`<path[^>]*fill="${HEX}"[^>]*stroke="${HEX}"`).exec(variant)
  const fills = [...variant.matchAll(new RegExp(`fill="${HEX}"`, 'g'))].map((m) => m[1])
  return {
    fill: (frame && frame[1]) || fills[0] || '#E9E1F8',
    stroke: (frame && frame[2]) || fills[fills.length - 1] || '#7B79AB',
    icon: fills[fills.length - 1] || '#7B79AB',
  }
}

export function profileBlockTopSvg(profileSvg) {
  return String(profileSvg || '').split(FRAME_STANDALONE).join(FRAME_BLOCK_TOP)
}

export function frameAsBlockMiddle(svg) {
  return String(svg || '').split(FRAME_BLOCK_BOTTOM).join(FRAME_BLOCK_MIDDLE)
}

export function frameAsBlockBottom(svg) {
  return String(svg || '').split(FRAME_BLOCK_MIDDLE).join(FRAME_BLOCK_BOTTOM)
}

export function gachaButtonSvg(profileSvg) {
  const vs = variants(profileSvg)
  if (!vs.length) return ''
  const one = (variant, cls) => {
    const c = colorsOf(variant)
    return `<svg class="chat-controls-toggle-icon chat-controls-toggle-icon--${cls}" width="45" height="45" viewBox="0 0 45 45" fill="none" xmlns="http://www.w3.org/2000/svg">`
      + `<path d="${FRAME_BLOCK_BOTTOM}" fill="${c.fill}" stroke="${c.stroke}" stroke-width="3"/>`
      + `<rect x="42" y="3" width="3" height="39" fill="${c.fill}"/>`
      + TICKET_ICON.replace(/\{icon\}/g, c.icon)
      + '</svg>'
  }
  return one(vs[0], 'default') + (vs[1] ? one(vs[1], 'hover') : '')
}

export function gachaBadgeColors(profileSvg) {
  const vs = variants(profileSvg)
  const base = colorsOf(vs[0] || '')
  const hover = colorsOf(vs[1] || vs[0] || '')
  return { background: base.stroke, color: hover.icon }
}
