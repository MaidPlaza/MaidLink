import React, { useEffect, useRef, useState } from 'react'

export default function TypedText({ text = '', speed = 45, startDelay = 0, className, scrollRef }) {
  const [shown, setShown] = useState(0)
  const frame = useRef(0)
  const spanRef = useRef(null)

  useEffect(() => {
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (reduced || !text) { setShown(text.length); return }

    setShown(0)
    const started = performance.now() + startDelay
    function tick(now) {
      const elapsed = now - started
      const n = elapsed <= 0 ? 0 : Math.floor((elapsed / 1000) * speed)
      setShown(Math.min(n, text.length))
      if (n < text.length) frame.current = requestAnimationFrame(tick)
    }
    frame.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame.current)
  }, [text])

  useEffect(() => {
    const box = scrollRef?.current || spanRef.current?.parentElement
    if (box) box.scrollTop = box.scrollHeight
  }, [shown, scrollRef])

  return (
    <span ref={spanRef} className={className} data-typing={shown < text.length ? '1' : undefined}>
      {text.slice(0, shown)}
    </span>
  )
}
