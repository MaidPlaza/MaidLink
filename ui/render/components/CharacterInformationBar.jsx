import React from 'react'

const W = 12
const STEP = 12
const CAP = 19
const THICK = 8
const GAP = STEP - THICK

const PATH_BOTTOM = 'M0 8L11 0V16C11 17.6569 9.65685 19 8 19H3C1.34315 19 0 17.6569 0 16V8Z'
const PATH_BODY = 'M0 8L11 0V8L0 16V8Z'
const PATH_TOP = 'M11 11L0 19V3C0 1.34315 1.34315 0 3 0H8C9.65685 0 11 1.34315 11 3V11Z'

export default function CharacterInformationBar({ value = 0, segments = 7 }) {
  const total = Math.max(2, Math.round(segments))
  const filled = Math.round(Math.max(0, Math.min(1, Number(value) || 0)) * total)

  const TOP_RISE = 11 + GAP
  const H = CAP + TOP_RISE + (total - 2) * STEP
  const yBottom = H - CAP
  const yBody = (i) => yBottom - i * STEP
  const yTop = yBottom - (total - 2) * STEP - TOP_RISE

  const parts = []
  for (let i = 0; i < filled; i++) {
    const isBottom = i === 0
    const isTop = i === total - 1
    parts.push(
      <path
        key={i}
        d={isBottom ? PATH_BOTTOM : isTop ? PATH_TOP : PATH_BODY}
        transform={`translate(0 ${isBottom ? yBottom : isTop ? yTop : yBody(i)})`}
        className={`character-information-bar-segment${isTop ? ' is-top' : ''}`}
      />,
    )
  }

  return (
    <div className="character-information-bar">
      <svg
        className="character-information-bar-svg"
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="xMidYMax meet"
        shapeRendering="geometricPrecision"
      >
        {parts}
      </svg>
    </div>
  )
}
