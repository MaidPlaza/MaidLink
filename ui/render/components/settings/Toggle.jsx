import React from 'react'

export default function Toggle({ value, onChange }) {
  return (
    <div
      className={`settings-toggle${value ? ' is-on' : ''}`}
      onClick={() => onChange(!value)}
    >
      <div className="settings-toggle-knob" />
    </div>
  )
}
