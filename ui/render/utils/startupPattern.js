const W = 658
const H = 906
const STEP = 6
const ZONE = 380
const ZONE_BOTTOM = ZONE - 100
const R_MAX = 4
const WARP_Y = 10
const WARP_X = 6
const CORNER_WIDTH = 0.4
const CORNER_ZONE = 1.15
const CORNER_SIZE = 1.5
const SPEED_X = 0.25
const SPEED_Y = 0.35
const SPEED_SWELL = 0.175

export const PATTERN_WIDTH = W
export const PATTERN_HEIGHT = H

const ROW_FIRST = -1
const ROW_LAST = Math.ceil((Math.max(ZONE, ZONE_BOTTOM) * CORNER_ZONE + STEP) / STEP)
const COL_FIRST = -2
const COL_LAST = Math.ceil((W + STEP * 2) / STEP)
export const DOT_CAPACITY = (ROW_LAST - ROW_FIRST + 1) * (COL_LAST - COL_FIRST + 1) * 2
export const DOT_STRIDE = 4

function cornerness(x) {
  const c = Math.max(0, 1 - Math.min(x, W - x) / (W * CORNER_WIDTH))
  return c * c * (3 - 2 * c)
}

function radius(depth, c, swell, zoneBase) {
  const zone = zoneBase * (1 + (CORNER_ZONE - 1) * c)
  if (depth > zone) return 0
  const k = 1 - Math.max(0, depth) / zone
  return R_MAX * (1 + (CORNER_SIZE - 1) * c) * k * Math.sqrt(k) * swell
}

export function computeDots(t, out) {
  let n = 0
  const maxZone = Math.max(ZONE, ZONE_BOTTOM) * CORNER_ZONE
  for (let gy = ROW_FIRST; gy <= ROW_LAST; gy++) {
    const by = gy * STEP
    const rowY = 1.3 * Math.sin(by / 89) - t * SPEED_Y
    const rowX = by / 31 + t * SPEED_X
    const shift = gy % 2 ? STEP / 2 : 0
    for (let gx = COL_FIRST; gx <= COL_LAST; gx++) {
      const bx = gx * STEP + shift
      const depth = by + WARP_Y * Math.sin(bx / 47 + rowY)
      if (depth > maxZone) continue
      const x = bx + WARP_X * Math.sin(rowX + 1.7 * Math.sin(bx / 173))
      const c = cornerness(x)
      const swell = 0.8 + 0.2 * Math.sin(x / 61 + 2.4 * Math.sin(depth / 71 + x / 233) + t * SPEED_SWELL)
      const rTop = radius(depth, c, swell, ZONE)
      if (rTop >= 0.35) {
        const o = n++ * DOT_STRIDE
        out[o] = x; out[o + 1] = depth; out[o + 2] = rTop; out[o + 3] = 0
      }
      const rBottom = radius(depth, c, swell, ZONE_BOTTOM)
      if (rBottom >= 0.35) {
        const o = n++ * DOT_STRIDE
        out[o] = x; out[o + 1] = H - depth; out[o + 2] = rBottom; out[o + 3] = 1
      }
    }
  }
  return n
}

const TAU = Math.PI * 2
let fallbackDots = null

export function drawStartupPattern(ctx, t, topColor, bottomColor) {
  fallbackDots = fallbackDots || new Float32Array(DOT_CAPACITY * DOT_STRIDE)
  const n = computeDots(t, fallbackDots)
  ctx.clearRect(0, 0, W, H)
  for (const [edge, color] of [[0, topColor], [1, bottomColor]]) {
    ctx.beginPath()
    for (let i = 0; i < n; i++) {
      const o = i * DOT_STRIDE
      if (fallbackDots[o + 3] !== edge) continue
      const x = fallbackDots[o], y = fallbackDots[o + 1], r = fallbackDots[o + 2]
      ctx.moveTo(x + r, y)
      ctx.arc(x, y, r, 0, TAU)
    }
    ctx.fillStyle = color
    ctx.fill()
  }
}
