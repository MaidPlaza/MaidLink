import React, { useState } from 'react'
import { sounds } from '@/lib/sounds'
import Toggle from './Toggle'

function Row({ label, children, last }) {
  return (
    <div className={`settings-row${last ? ' is-last' : ''}`}>
      <span className="settings-row-label">{label}</span>
      {children}
    </div>
  )
}

export default function SoundSettings() {
  const [enabled, setEnabled] = useState(sounds.enabled)
  const [volume, setVolume] = useState(Math.round(sounds.volume * 100))

  const toggle = (on) => {
    sounds.setEnabled(on)
    setEnabled(on)
    if (on) sounds.play('click')
  }

  const onVolume = (v) => {
    setVolume(v)
    sounds.setVolume(v / 100)
  }

  return (
    <>
      <Row label="Звуки интерфейса">
        <Toggle value={enabled} onChange={toggle} />
      </Row>
      <Row label="Громкость" last>
        <div className={`settings-sound-volume${enabled ? '' : ' is-disabled'}`}>
          <input
            type="range"
            min={0}
            max={100}
            value={volume}
            onChange={(e) => onVolume(Number(e.target.value))}
            onPointerUp={() => sounds.play('msg_neutral')}
            className="settings-sound-range"
          />
          <span className="settings-sound-value">{volume}%</span>
        </div>
      </Row>
    </>
  )
}
