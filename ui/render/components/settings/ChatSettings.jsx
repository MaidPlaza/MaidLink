import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useSettingsSnapshot, groupBySections, useSetting } from '@/lib/settings'
import { useEnabledAddonIds } from '@/lib/addons'
import { useThemeWaveActive } from '@/lib/themeWave'
import Dropdown from './Dropdown'
import Toggle from './Toggle'

function Select({ value, options, onChange }) {
  return <Dropdown value={value} options={options} onChange={onChange} className="settings-select" />
}

function Range({ value, min = 0, max = 100, step = 1, onChange }) {
  return (
    <div className="settings-range">
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={Number(value) || min}
        onChange={(e) => onChange(e.target.value)}
        className="settings-range-input"
      />
      <span className="settings-range-value">{Number(value) || min}</span>
    </div>
  )
}

function SettingControl({ descriptor }) {
  const [value, setValue] = useSetting(descriptor.id)
  const waveActive = useThemeWaveActive()
  const locked = !!descriptor.lockDuringWave && waveActive
  if (locked) {
    return (
      <div className="settings-control-locked" aria-disabled="true">
        <SettingControlBody descriptor={descriptor} value={value} setValue={setValue} />
      </div>
    )
  }
  return <SettingControlBody descriptor={descriptor} value={value} setValue={setValue} />
}

function SettingControlBody({ descriptor, value, setValue }) {
  if (descriptor.type === 'select') {
    return <Select value={value} options={descriptor.options} onChange={setValue} />
  }
  if (descriptor.type === 'range') {
    return (
      <Range
        value={value}
        min={descriptor.min}
        max={descriptor.max}
        step={descriptor.step}
        onChange={setValue}
      />
    )
  }
  return <Toggle value={!!value} onChange={setValue} />
}

function Section({ title, children }) {
  return (
    <div className="settings-section">
      <div className="settings-section-title">{title}</div>
      <div className="settings-section-card">{children}</div>
    </div>
  )
}

function Row({ label, children, last }) {
  return (
    <div className={`settings-row${last ? ' is-last' : ''}`}>
      <span className="settings-row-label">{label}</span>
      {children}
    </div>
  )
}

export default function ChatSettings({ open = false, home = 'settings' }) {
  const settings = useSettingsSnapshot()
  const enabledAddons = useEnabledAddonIds()
  const visible = settings.filter((d) => !d.hidden
    && (!d.addon || enabledAddons.has(d.addon))
    && (d.home || 'settings') === home)
  const sections = groupBySections(visible)

  const scrollRef = useRef(null)
  const [fades, setFades] = useState({ top: false, bottom: false })

  const updateFades = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    const top = el.scrollTop > 4
    const bottom = el.scrollHeight - el.scrollTop - el.clientHeight > 4
    setFades((p) => (p.top === top && p.bottom === bottom ? p : { top, bottom }))
  }, [])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    updateFades()
    const ro = new ResizeObserver(updateFades)
    ro.observe(el)
    return () => ro.disconnect()
  }, [updateFades, sections.length])

  return (
    <div className="settings-panel">
      {home === 'settings' && (
        <div className="settings-panel-header">Настройки</div>
      )}

      <div className="settings-panel-body">
        <div
          ref={scrollRef}
          onScroll={updateFades}
          className="chat-settings-scroll settings-panel-scroll"
        >
          {sections.length === 0 && (
            <div className="settings-panel-empty">Нет доступных настроек.</div>
          )}

          {sections.map(({ section, items }) => (
            <Section key={section} title={section}>
              {items.map((d, i) => {
                if (d.type === 'custom' && d.component) {
                  const Comp = d.component
                  return <Comp key={d.id} open={open} />
                }
                return (
                  <Row key={d.id} label={d.label} last={i === items.length - 1}>
                    <SettingControl descriptor={d} />
                  </Row>
                )
              })}
            </Section>
          ))}
        </div>

        <div className={`chat-settings-fade chat-settings-fade--top${fades.top ? ' chat-settings-fade--visible' : ''}`} />
        <div className={`chat-settings-fade chat-settings-fade--bottom${fades.bottom ? ' chat-settings-fade--visible' : ''}`} />
      </div>
    </div>
  )
}
