import { useRef, useEffect } from 'react'

const CELL      = 14
const SQUARE    = 12
const CROSS_ARM = 4
const CROSS_W   = 2
const DOT       = 2
const DURATION  = 1500
const BUFFER    = 6
const FADE      = 0.8

function c01(v) { return Math.max(0, Math.min(1, v)) }

export default function DiagonalPattern({ style, play = false, onComplete }) {
  const svgRef   = useRef(null)
  const frameRef = useRef(null)
  const startRef = useRef(null)

  useEffect(() => {
    if (!play) return
    const svg = svgRef.current
    if (!svg) return

    startRef.current = null

    function render(ts) {
      if (!startRef.current) startRef.current = ts

      const parent = svg.parentElement
      const W = parent.offsetWidth
      const H = parent.offsetHeight

      const cols      = Math.ceil(W / CELL) + 6
      const rows      = Math.ceil(H / CELL) + 6
      const totalDiag = cols + rows

      const elapsed = ts - startRef.current
      if (elapsed >= DURATION) {
        svg.innerHTML = ''
        onComplete && onComplete()
        return
      }
      const t = elapsed / DURATION
      const D = t * (totalDiag + 2 * BUFFER) - BUFFER

      const F       = FADE
      const SQ_CORE = 3.0
      const SQ_EDGE = SQ_CORE + F
      const CR_CORE = SQ_EDGE + 3
      const CR_EDGE = CR_CORE + F
      const DT_CORE = CR_EDGE + 4
      const DT_EDGE = DT_CORE + F

      let html = ''

      for (let row = -2; row < rows - 2; row++) {
        for (let col = -2; col < cols - 2; col++) {
          const dist = Math.abs(col + row - D)
          if (dist > DT_EDGE) continue

          const cx = col * CELL + CELL / 2
          const cy = row * CELL + CELL / 2

          const sqOp = dist <= SQ_CORE ? 1 : c01((SQ_EDGE - dist) / F)

          const crOp = dist <= SQ_CORE || dist > CR_EDGE ? 0
            : dist <= SQ_EDGE ? c01((dist - SQ_CORE) / F)
            : dist <= CR_CORE ? 1
            : c01((CR_EDGE - dist) / F)

          const dtOp = dist <= CR_CORE || dist > DT_EDGE ? 0
            : dist <= CR_EDGE ? c01((dist - CR_CORE) / F)
            : dist <= DT_CORE ? 1
            : c01((DT_EDGE - dist) / F)

          if (sqOp > 0.01) {
            const h = SQUARE / 2
            html += `<rect x="${cx-h}" y="${cy-h}" width="${SQUARE}" height="${SQUARE}" opacity="${sqOp.toFixed(2)}"/>`
          }
          if (crOp > 0.01) {
            const hw = CROSS_W / 2
            html += `<rect x="${cx-hw}" y="${cy-CROSS_ARM}" width="${CROSS_W}" height="${CROSS_ARM*2}" opacity="${crOp.toFixed(2)}"/>`
            html += `<rect x="${cx-CROSS_ARM}" y="${cy-hw}" width="${CROSS_ARM*2}" height="${CROSS_W}" opacity="${crOp.toFixed(2)}"/>`
          }
          if (dtOp > 0.01) {
            const h = DOT / 2
            html += `<rect x="${cx-h}" y="${cy-h}" width="${DOT}" height="${DOT}" opacity="${dtOp.toFixed(2)}"/>`
          }
        }
      }

      svg.innerHTML = html
      frameRef.current = requestAnimationFrame(render)
    }

    frameRef.current = requestAnimationFrame(render)
    return () => {
      cancelAnimationFrame(frameRef.current)
      if (svg) svg.innerHTML = ''
    }
  }, [play])

  return (
    <svg
      ref={svgRef}
      className="diagonal-pattern"
      style={style}
    />
  )
}
