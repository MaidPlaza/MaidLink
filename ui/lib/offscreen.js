const callbacks = new Map()
let io = null

function observer() {
  if (!io) {
    io = new IntersectionObserver((entries) => {
      for (const e of entries) callbacks.get(e.target)?.(e.isIntersecting)
    }, { rootMargin: '64px 0px' })
  }
  return io
}

export function watchVisibility(el, cb) {
  if (!el || typeof IntersectionObserver === 'undefined') return () => {}
  callbacks.set(el, cb)
  observer().observe(el)
  return () => {
    callbacks.delete(el)
    io?.unobserve(el)
  }
}

export function markOffscreen(el) {
  return watchVisibility(el, (visible) => {
    if (visible) el.removeAttribute('data-offscreen')
    else el.setAttribute('data-offscreen', '')
  })
}
