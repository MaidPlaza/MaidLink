import React, { useRef } from 'react'

const HANDLES = [
  { id: 'n' },
  { id: 's' },
]

const MIN_HEIGHT = 906

function computeBounds(id, start, dx, dy) {
  let { x, y, width, height } = start

  if (id.includes('e')) width  = start.width  + dx
  if (id.includes('s')) height = Math.max(start.height + dy, MIN_HEIGHT)
  if (id.includes('w')) { x = start.x + dx; width  = start.width  - dx }
  if (id.includes('n')) {
    height = Math.max(start.height - dy, MIN_HEIGHT)
    y = start.y + start.height - height
  }

  return {
    x:      Math.round(x),
    y:      Math.round(y),
    width:  Math.round(width),
    height: Math.round(height),
  }
}

export default function ResizeEdges({ expanded = false }) {
  const startRef = useRef(null)

  const onMouseDown = (id) => (e) => {
    e.preventDefault()
    const bounds = window.maidlink?.getBounds()
    if (!bounds) return

    startRef.current = { ...bounds, mouseX: e.screenX, mouseY: e.screenY }

    const onMove = (e) => {
      const { mouseX, mouseY, ...startBounds } = startRef.current
      const dx = e.screenX - mouseX
      const dy = e.screenY - mouseY
      window.maidlink.resize(computeBounds(id, startBounds, dx, dy))
    }

    const onUp = () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      startRef.current = null
    }

    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  return (
    <>
      {HANDLES.map(({ id }) => (
        <div
          key={id}
          className={`resize-handle rh-${id}${expanded ? ' resize-handle--full' : ''}`}
          onMouseDown={onMouseDown(id)}
        />
      ))}
    </>
  )
}
