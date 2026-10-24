import React, { useEffect, useRef, useState } from 'react'

const R = 53
const VIEW = 122
const MID = VIEW / 2
const CIRC = 2 * Math.PI * R
const ARC = CIRC

const GROW = 2000
const HOLD = 2000
const SETTLE = 2000
const TOTAL = GROW + HOLD + SETTLE
const clamp01 = (v) => Math.max(0, Math.min(1, Number(v) || 0))
const lerp = (a, b, t) => a + (b - a) * t
const easeOut = (t) => 1 - Math.pow(1 - t, 3)
const asPercent = (v) => Math.round(v * 100)
const deltaSign = (v) => (v > 0 ? '+' : v < 0 ? '−' : '')
const asDelta = (v) => Math.abs(v * 100).toFixed(1).replace('.', ',')

export default function CharacterInformationTier({
  title = '',
  lastProgress = 0,
  newProgress = 0,
  startDelay = 0,
  tier = '',
  label = '',
}) {
  const last = clamp01(lastProgress)
  const next = clamp01(newProgress)
  const delta = next - last

  const [t, setT] = useState(0)
  const frame = useRef(0)
  useEffect(() => {
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (reduced) { setT(TOTAL); return }
    const started = performance.now() + startDelay
    const tick = (now) => {
      const elapsed = Math.max(0, now - started)
      setT(elapsed)
      if (elapsed < TOTAL) frame.current = requestAnimationFrame(tick)
    }
    setT(0)
    frame.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame.current)
  }, [last, next, startDelay])

  const p1 = easeOut(clamp01(t / GROW))
  const p2 = easeOut(clamp01((t - GROW - HOLD) / SETTLE))
  const gainNow = lerp(last, next, p1)
  const valueNow = lerp(last, next, p2)
  const percentNow = valueNow
  const deltaNow = delta * p1
  const deltaLeaving = t >= GROW + HOLD

  const spin = `rotate(-90 ${MID} ${MID})`

  return (
    <div className="character-information-tier-information-container">
      <div className="character-information-tier-title">{title}</div>
      <div className="character-information-tier-badge">{tier}</div>

      <div className="character-information-tier-gauge">
        <svg
          viewBox={`0 0 ${VIEW} ${VIEW}`}
          width={VIEW}
          height={VIEW}
          shapeRendering="geometricPrecision"
        >
         
          <circle
            className="character-information-tier-outline"
            cx={MID} cy={MID} r={R}
          />
          <circle
            className="character-information-tier-track"
            cx={MID} cy={MID} r={R}
          
          />
          <circle
            className="character-information-tier-gain"
            cx={MID} cy={MID} r={R}
            strokeDasharray={`${ARC * gainNow} ${CIRC}`}
            transform={spin}
          />
          <circle
            className="character-information-tier-value"
            cx={MID} cy={MID} r={R}
            strokeDasharray={`${ARC * valueNow} ${CIRC}`}
            transform={spin}
          />
        </svg>

        <div className="character-information-tier-readout">
          <div className="character-information-tier-percent">{asPercent(percentNow)}%</div>
          {delta !== 0 && (
            <div className={`character-information-tier-delta${deltaLeaving ? ' is-leaving' : ''}`}>
              <span className="character-information-tier-delta-sign">{deltaSign(deltaNow)}</span>{asDelta(deltaNow)}
            </div>
          )}
        </div>
      </div>

      <div className="character-information-tier-footer">
        <div className="character-information-tier-label">{label}</div>
      </div>
    </div>
  )
}
