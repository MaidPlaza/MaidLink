import { useEffect, useMemo, useRef, useState } from 'react'
import '../styles/components/pixel-wave-effect.css'

const PALETTE = [
  'var(--color-1)',
  'var(--color-2)',
  'var(--color-1)',
  'var(--color-4)',
  'var(--color-5)',
  'var(--color-1)',
  'var(--color-1)',
  'var(--color-4)',
]

const NOISE_RES = 8

function makeNoiseGrid() {
  const g = []
  for (let r = 0; r < NOISE_RES; r++) {
    g[r] = []
    for (let c = 0; c < NOISE_RES; c++) g[r][c] = Math.random()
  }
  return g
}

function smoothstep(t) {
  return t * t * (3 - 2 * t)
}

function sampleNoise(g, u, v) {
  const wrap = (n) => ((n % NOISE_RES) + NOISE_RES) % NOISE_RES
  const nx = wrap(u * NOISE_RES)
  const ny = wrap(v * NOISE_RES)
  const x0 = Math.floor(nx)
  const y0 = Math.floor(ny)
  const x1 = (x0 + 1) % NOISE_RES
  const y1 = (y0 + 1) % NOISE_RES
  const sx = smoothstep(nx - x0)
  const sy = smoothstep(ny - y0)
  const a = g[y0][x0] * (1 - sx) + g[y0][x1] * sx
  const b = g[y1][x0] * (1 - sx) + g[y1][x1] * sx
  return a * (1 - sy) + b * sy
}

function pickColorFromNoise(value) {
  const idx = Math.min(Math.floor(value * PALETTE.length), PALETTE.length - 1)
  return PALETTE[idx]
}

const GLITCH_CHARS =
  '0123456789ABCDEF' +
  '░▒▓█' +
  '◆◇◈◊▲▼◀▶★☆♦♣' +
  'αβγδλμπφψωΩ∑∂∇∞≠≈≡∈∪∩' +
  '─│┌┐└┘├┤┬┴┼' +
  '+-=*/\\<>!@#$%^&'

function pickGlitchChar() {
  return GLITCH_CHARS[Math.floor(Math.random() * GLITCH_CHARS.length)]
}

function complementColor(hex) {
  const r = 255 - parseInt(hex.slice(1, 3), 16)
  const g = 255 - parseInt(hex.slice(3, 5), 16)
  const b = 255 - parseInt(hex.slice(5, 7), 16)
  const c = (n) => n.toString(16).padStart(2, '0')
  return `#${c(r)}${c(g)}${c(b)}`
}

function caClassName(ca, borderL, borderR, borderT) {
  if (ca <= 0) return ''
  const bits = (borderL ? 1 : 0) | (borderR ? 2 : 0) | (borderT ? 4 : 0)
  return bits === 0 ? '' : `ca-${bits}`
}

function diagonalIndex(c, r, cols, rows, dir) {
  switch (dir) {
    case 'tl-br': return c + r
    case 'tr-bl': return cols - 1 - c + r
    case 'bl-tr': return c + (rows - 1 - r)
    case 'br-tl': return cols - 1 - c + (rows - 1 - r)
  }
}

function generateCells({ gridCols, gridRows, direction, stepMs, sparsity, chaos, turbulence, jitterSteps, invertBursts }) {
  const arr = []
  const noiseA = makeNoiseGrid()
  const noiseB = makeNoiseGrid()
  const turbGrid = makeNoiseGrid()

  const TURB_MAX_STEPS = 8
  const turbAmplitude = turbulence * TURB_MAX_STEPS * stepMs

  const colorMat = []
  const visMat = []
  for (let r = 0; r < gridRows; r++) {
    colorMat[r] = []
    visMat[r] = []
    for (let c = 0; c < gridCols; c++) {
      const u = c / Math.max(1, gridCols - 1)
      const v = r / Math.max(1, gridRows - 1)
      const nValue = sampleNoise(noiseA, u, v) * 0.7
                   + sampleNoise(noiseB, u * 2, v * 2) * 0.3
      const useChaos = Math.random() < chaos
      colorMat[r][c] = useChaos
        ? PALETTE[Math.floor(Math.random() * PALETTE.length)]
        : pickColorFromNoise(nValue)
      visMat[r][c] = Math.random() >= sparsity
    }
  }

  const isDifferent = (rr, cc, myColor) => {
    if (rr < 0 || rr >= gridRows || cc < 0 || cc >= gridCols) return true
    if (!visMat[rr][cc]) return true
    return colorMat[rr][cc] !== myColor
  }

  for (let r = 0; r < gridRows; r++) {
    for (let c = 0; c < gridCols; c++) {
      const diag = diagonalIndex(c, r, gridCols, gridRows, direction)
      const u = c / Math.max(1, gridCols - 1)
      const v = r / Math.max(1, gridRows - 1)
      const visible = visMat[r][c]
      const color = colorMat[r][c]

      const turb = sampleNoise(turbGrid, u * 1.5, v * 1.5) - 0.5
      const turbDelay = turb * 2 * turbAmplitude
      const jitter = (Math.random() - 0.5) * stepMs * jitterSteps
      const delay = Math.max(0, diag * stepMs + turbDelay + jitter)

      const inverted = Math.random() < invertBursts

      const borderL = visible && isDifferent(r, c - 1, color)
      const borderR = visible && isDifferent(r, c + 1, color)
      const borderT = visible && isDifferent(r - 1, c, color)

      arr.push({
        col: c, row: r,
        delay, color,
        visible, inverted,
        borderL, borderR, borderT,
        glitchChar: pickGlitchChar(),
      })
    }
  }
  return arr
}

export default function PixelWave({
  active,
  onComplete,
  direction = 'tl-br',
  gridCols = 40,
  gridRows = 25,
  stepMs = 14,
  visibleMs = 290,
  sparsity = 0.15,
  blendMode = 'multiply',
  chaos = 0.12,
  turbulence = 0.6,
  jitterSteps = 3,
  chromaticAberration = 1.5,
  invertBursts = 0.06,
  showGlitchChars = true,
}) {
  const [running, setRunning] = useState(false)
  const completeTimer = useRef(null)

  const cells = useMemo(() => {
    return generateCells({
      gridCols, gridRows, direction, stepMs, sparsity,
      chaos, turbulence, jitterSteps, invertBursts,
    })
  }, [running, direction, gridCols, gridRows, stepMs, sparsity, chaos, turbulence, jitterSteps, invertBursts])

  const sortedIndices = useMemo(() => {
    return cells
      .map((_, i) => i)
      .sort((a, b) => cells[a].delay - cells[b].delay)
  }, [cells])

  const [activeRange, setActiveRange] = useState([0, 0])
  const startTimeRef = useRef(0)
  const mountTimesRef = useRef(new Map())

  useEffect(() => {
    if (!running) {
      setActiveRange([0, 0])
      mountTimesRef.current.clear()
      return
    }

    startTimeRef.current = performance.now()
    mountTimesRef.current.clear()

    let raf
    let curStart = 0
    let curEnd = 0
    const PREROLL_MS = 30
    const POSTROLL_MS = 50

    function tick() {
      const elapsed = performance.now() - startTimeRef.current

      let changed = false
      while (curEnd < sortedIndices.length) {
        const cell = cells[sortedIndices[curEnd]]
        if (cell.delay > elapsed + PREROLL_MS) break
        curEnd++
        changed = true
      }
      while (curStart < curEnd) {
        const cell = cells[sortedIndices[curStart]]
        if (cell.delay + visibleMs + POSTROLL_MS > elapsed) break
        mountTimesRef.current.delete(sortedIndices[curStart])
        curStart++
        changed = true
      }
      if (changed) setActiveRange([curStart, curEnd])

      if (curStart < sortedIndices.length) {
        raf = requestAnimationFrame(tick)
      }
    }

    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [running, sortedIndices, cells, visibleMs])

  useEffect(() => {
    if (!active) return
    setRunning(true)

    const maxDelay =
      (gridCols + gridRows - 2) * stepMs +
      turbulence * 8 * stepMs +
      (jitterSteps * stepMs) / 2
    const totalMs = maxDelay + visibleMs + 60

    completeTimer.current = setTimeout(() => {
      setRunning(false)
      onComplete?.()
    }, totalMs)

    return () => {
      if (completeTimer.current) clearTimeout(completeTimer.current)
    }
  }, [active, gridCols, gridRows, stepMs, visibleMs, turbulence, jitterSteps, onComplete])

  if (!running) return null

  return (
    <div aria-hidden className="pixel-wave-layer">
      <div
        className="pixel-wave-grid"
        style={{
          gridTemplateColumns: `repeat(${gridCols}, 1fr)`,
          gridTemplateRows: `repeat(${gridRows}, 1fr)`,
          '--gc': gridCols,
          '--gr': gridRows,
          '--ca-px': `${chromaticAberration}px`,
        }}
      >
        {sortedIndices.slice(activeRange[0], activeRange[1]).map((i) => {
          const cell = cells[i]
          if (!cell.visible) return null

          let mountTime = mountTimesRef.current.get(i)
          if (mountTime === undefined) {
            mountTime = performance.now()
            mountTimesRef.current.set(i, mountTime)
          }
          const adjustedDelay = cell.delay - (mountTime - startTimeRef.current)

          const caClass = caClassName(
            chromaticAberration,
            cell.borderL, cell.borderR, cell.borderT,
          )
          const className =
            'pixel-wave-cell' +
            (showGlitchChars ? ' pixel-wave-cell-text' : '') +
            (caClass ? ' ' + caClass : '')

          return (
            <div
              key={i}
              className={className}
              style={{
                gridColumn: cell.col + 1,
                gridRow: cell.row + 1,
                background: cell.color,
                mixBlendMode: cell.inverted ? 'difference' : blendMode,
                animationDelay: `${adjustedDelay}ms`,
                animationDuration: `${visibleMs}ms`,
              }}
            >
              {showGlitchChars ? cell.glitchChar : null}
            </div>
          )
        })}
      </div>
    </div>
  )
}
