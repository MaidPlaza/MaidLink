import React, { useEffect, useState } from 'react'
import { useUIStructure, chipSvg } from '@/lib/uiStructure'



export default function ChipContainer({ locked = false, chip = null, hint = false }) {
  const svgStructure = useUIStructure()
  const [wiggling, setWiggling] = useState(hint)
  useEffect(() => { if (hint) setWiggling(true) }, [hint])
  return (
    <div
      className={`chip-container no-select${wiggling ? ' chip-container--hint' : ''}`}
      onAnimationIteration={(e) => {
        if (!hint && e.target === e.currentTarget && e.animationName === 'chip-hint-wiggle') setWiggling(false)
      }}
    >
      <div
        className={`chip-item${locked ? ' chip-item--locked' : ''}`}
        dangerouslySetInnerHTML={{ __html: chip || chipSvg(svgStructure) }}
      />
    </div>
  )
}
