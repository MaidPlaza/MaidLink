import React, { useState, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'

export default function Dropdown({ value, options, onChange, style, className }) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState(null)
  const btnRef = useRef(null)
  const menuRef = useRef(null)

  function toggle() {
    if (open) { setOpen(false); return }
    const r = btnRef.current?.getBoundingClientRect()
    if (r) setPos({ top: Math.round(r.bottom + 2), left: Math.round(r.left), width: Math.round(r.width) })
    setOpen(true)
  }

  useEffect(() => {
    if (!open) return
    function onDoc(e) {
      if (btnRef.current?.contains(e.target) || menuRef.current?.contains(e.target)) return
      setOpen(false)
    }
    function close() { setOpen(false) }
    function closeOnScroll(e) {
      if (menuRef.current && e.target instanceof Node && menuRef.current.contains(e.target)) return
      setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    window.addEventListener('scroll', closeOnScroll, true)
    window.addEventListener('resize', close)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      window.removeEventListener('scroll', closeOnScroll, true)
      window.removeEventListener('resize', close)
    }
  }, [open])

  const list = options || []
  const current = list.find((o) => o.value === value)

  return (
    <div className={`settings-dropdown${className ? ' ' + className : ''}`} style={style}>
      <button
        ref={btnRef}
        type="button"
        onClick={toggle}
        className="settings-dropdown-face settings-dropdown-button"
      >
        <span className="settings-dropdown-value">{current?.label ?? '—'}</span>
        <span className="settings-dropdown-caret">{open ? '▲' : '▼'}</span>
      </button>
      {open && pos && createPortal(
        <div
          ref={menuRef}
          className="settings-dropdown-face settings-dropdown-menu"
          style={{ top: pos.top, left: pos.left, minWidth: pos.width }}
        >
          {list.length === 0 ? (
            <div className="settings-dropdown-empty">нет вариантов</div>
          ) : (
            list.map((o) => (
              <div
                key={o.value}
                onClick={() => { onChange(o.value); setOpen(false) }}
                className={`settings-dropdown-option${o.value === value ? ' is-selected' : ''}`}
              >
                {o.label}
              </div>
            ))
          )}
        </div>,
        document.body,
      )}
    </div>
  )
}
