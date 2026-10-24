(() => {
  const box = document.querySelector('.hero-cards')
  if (!box) return
  const cards = [...box.querySelectorAll('.mini-card')]
  const pool = [...document.querySelectorAll('.dossier:not(.is-soon)')]
    .map((el) => ({
      name: el.querySelector('.dossier-name')?.textContent.trim(),
      note: el.querySelector('.dossier-subtitle')?.textContent.trim() ?? '',
      accent: el.style.getPropertyValue('--accent'),
      src: el.querySelector('.dossier-photo img')?.getAttribute('src'),
    }))
    .filter((m) => m.name && m.src)
  if (!cards.length || pool.length < cards.length) {
    for (const card of cards) card.style.opacity = 1
    return
  }

  const HOLD = 3000
  const IN = { duration: 1000, stagger: 120, far: [360, 480], fade: 450, minFade: 220, ease: [0.22, 0.61, 0.36, 1] }
  const OUT = { duration: 800, stagger: 0, far: [360, 480], minFade: 260, ease: [0.4, 0, 0.6, 1] }
  const STEP = 10
  const reduce = matchMedia('(prefers-reduced-motion: reduce)')

  const rand = (a, b) => a + Math.random() * (b - a)
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v))
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
  const shuffle = (list) => {
    for (let i = list.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[list[i], list[j]] = [list[j], list[i]]
    }
    return list
  }

  function bezier([x1, y1, x2, y2]) {
    const at = (a, b, t) => 3 * a * t * (1 - t) ** 2 + 3 * b * t * t * (1 - t) + t ** 3
    return (x) => {
      let lo = 0
      let hi = 1
      for (let k = 0; k < 20; k++) {
        const mid = (lo + hi) / 2
        if (at(x1, x2, mid) < x) lo = mid
        else hi = mid
      }
      return at(y1, y2, (lo + hi) / 2)
    }
  }
  for (const cfg of [IN, OUT]) {
    cfg.easing = `cubic-bezier(${cfg.ease.join(', ')})`
    cfg.progress = bezier(cfg.ease)
  }

  for (const m of pool) new Image().src = m.src

  let shown = []
  function pick() {
    const fresh = shuffle(pool.filter((m) => !shown.includes(m)))
    const rest = shuffle(pool.filter((m) => shown.includes(m)))
    shown = [...fresh, ...rest].slice(0, cards.length)
    return shown
  }

  const css = (p) => `translate(${p.x}px, ${p.y}px) rotate(${p.r}deg) scale(${p.s})`
  const mix = (a, b, k) => ({
    ...a,
    x: a.x + (b.x - a.x) * k,
    y: a.y + (b.y - a.y) * k,
    r: a.r + (b.r - a.r) * k,
    s: a.s + (b.s - a.s) * k,
  })

  function arrange() {
    const dims = cards.map((c) => ({ w: c.offsetWidth, h: c.offsetHeight }))
    const rx = Math.max(0, box.clientWidth - Math.max(...dims.map((d) => d.w))) / 2
    const ry = Math.max(0, box.clientHeight - Math.max(...dims.map((d) => d.h))) / 2
    const turn = rand(0, Math.PI * 2)
    const step = (Math.PI * 2) / cards.length
    const layers = shuffle(cards.map((_, i) => i + 1))
    return cards.map((_, i) => {
      const angle = turn + i * step + rand(-0.25, 0.25)
      const k = rand(0.8, 1)
      return {
        x: box.clientWidth / 2 + Math.cos(angle) * rx * k - dims[i].w / 2,
        y: box.clientHeight / 2 + Math.sin(angle) * ry * k - dims[i].h / 2,
        r: (Math.random() < 0.5 ? -1 : 1) * rand(2, 12),
        s: 1,
        z: layers[i],
        ...dims[i],
      }
    })
  }

  const text = document.querySelector('.hero-text')
  function freeSide() {
    if (!text) return null
    const t = text.getBoundingClientRect()
    const b = box.getBoundingClientRect()
    if (t.right <= b.left + 1) return 0
    if (t.bottom <= b.top + 1) return Math.PI / 2
    return null
  }

  function away(p, [near, far], k, side) {
    const dx = p.x + p.w / 2 - box.clientWidth / 2
    const dy = p.y + p.h / 2 - box.clientHeight / 2
    const base = Math.hypot(dx, dy) > 24 ? Math.atan2(dy, dx) : rand(0, Math.PI * 2)
    let angle = base + rand(-0.5, 0.5)
    if (side != null) {
      const off = Math.atan2(Math.sin(angle - side), Math.cos(angle - side))
      if (Math.abs(off) > Math.PI / 2) angle = side + Math.sign(off) * (Math.PI / 2 - rand(0, 0.45))
    }
    const d = rand(near, far) * k
    return { ...p, x: p.x + Math.cos(angle) * d, y: p.y + Math.sin(angle) * d, r: p.r + rand(-25, 25), s: 0.9 }
  }

  function touch(a, b, pad = 4) {
    const [p, q] = [a, b].map((o) => {
      const t = (o.r * Math.PI) / 180
      return {
        cx: o.x + o.w / 2,
        cy: o.y + o.h / 2,
        hw: (o.w / 2) * o.s + pad,
        hh: (o.h / 2) * o.s + pad,
        axes: [[Math.cos(t), Math.sin(t)], [-Math.sin(t), Math.cos(t)]],
      }
    })
    const reach = (o, [lx, ly]) =>
      o.hw * Math.abs(o.axes[0][0] * lx + o.axes[0][1] * ly) + o.hh * Math.abs(o.axes[1][0] * lx + o.axes[1][1] * ly)
    for (const [lx, ly] of [...p.axes, ...q.axes]) {
      if (Math.abs((q.cx - p.cx) * lx + (q.cy - p.cy) * ly) > reach(p, [lx, ly]) + reach(q, [lx, ly])) return false
    }
    return true
  }

  function contacts(flights, cfg) {
    const first = flights.map(() => Infinity)
    const last = flights.map(() => -Infinity)
    const end = Math.max(...flights.map((f) => f.delay)) + cfg.duration
    for (let t = 0; t <= end + STEP; t += STEP) {
      const at = flights.map((f) => mix(f.from, f.to, cfg.progress(clamp((t - f.delay) / cfg.duration, 0, 1))))
      for (let i = 0; i < flights.length; i++) {
        for (let j = i + 1; j < flights.length; j++) {
          if (t < flights[i].delay || t < flights[j].delay || !touch(at[i], at[j])) continue
          for (const n of [i, j]) {
            first[n] = Math.min(first[n], t)
            last[n] = Math.max(last[n], t)
          }
        }
      }
    }
    return { first, last }
  }

  function plan(spots, cfg) {
    const incoming = cfg === IN
    const side = freeSide()
    let best = null
    for (let k = 0; k < 40 && !(best?.worst >= cfg.minFade); k++) {
      const flights = spots.map((p, i) => {
        const far = away(p, cfg.far, 1 + k * 0.02, side)
        return incoming ? { from: far, to: p, delay: i * cfg.stagger } : { from: p, to: far, delay: 0 }
      })
      const { first, last } = contacts(flights, cfg)
      const fades = flights.map((f, i) => {
        if (incoming) {
          const until = Math.min(cfg.fade, first[i] - STEP - f.delay)
          const at = clamp(until / cfg.duration, 0, 1)
          return { time: until, frames: [{ opacity: 0, offset: 0 }, { opacity: 1, offset: at }, { opacity: 1, offset: 1 }] }
        }
        const from = Math.max(0, last[i] + STEP)
        const at = clamp(from / cfg.duration, 0, 1)
        return { time: cfg.duration - from, frames: [{ opacity: 1, offset: 0 }, { opacity: 1, offset: at }, { opacity: 0, offset: 1 }] }
      })
      const worst = Math.min(...fades.map((f) => f.time))
      if (!best || worst > best.worst) best = { flights, fades, worst }
    }
    return best
  }

  function fly(card, flight, fade, cfg) {
    for (const a of card.getAnimations()) a.cancel()
    const timing = { duration: cfg.duration, delay: flight.delay, fill: 'both' }
    return Promise.all([
      card.animate([{ transform: css(flight.from) }, { transform: css(flight.to) }], { ...timing, easing: cfg.easing }).finished,
      card.animate(fade.frames, timing).finished,
    ])
  }

  function settle(card, from, to, duration) {
    for (const a of card.getAnimations()) a.cancel()
    card.animate([{ transform: css(from), opacity: 1 }, { transform: css(to), opacity: 1 }], { duration, easing: 'ease', fill: 'both' })
  }

  function dress(card, m) {
    card.querySelector('img').src = m.src
    card.querySelector('b').textContent = m.name
    card.querySelector('figcaption span').textContent = m.note
    card.style.setProperty('--accent', m.accent)
  }

  const decoded = () => Promise.all(cards.map((c) => c.querySelector('img').decode().catch(() => {})))

  let onScreen = true
  let wake = null
  const ready = () => onScreen && !document.hidden
  const whenShown = () => (ready() ? Promise.resolve() : new Promise((r) => { wake = r }))
  const poke = () => { if (wake && ready()) { wake(); wake = null } }
  new IntersectionObserver(([e]) => { onScreen = e.isIntersecting; poke() }).observe(box)
  document.addEventListener('visibilitychange', poke)

  let spots = []
  let holding = false

  async function round() {
    pick().forEach((m, i) => dress(cards[i], m))
    spots = arrange()
    cards.forEach((card, i) => { card.style.zIndex = spots[i].z })
    await decoded()
    const come = plan(spots, IN)
    await Promise.all(cards.map((card, i) => fly(card, come.flights[i], come.fades[i], IN)))
    holding = true
    await sleep(HOLD)
    if (!ready()) { await whenShown(); await sleep(1200) }
    holding = false
    const go = plan(spots, OUT)
    await Promise.all(cards.map((card, i) => fly(card, go.flights[i], go.fades[i], OUT)))
  }

  let resizeTimer = null
  addEventListener('resize', () => {
    clearTimeout(resizeTimer)
    resizeTimer = setTimeout(() => {
      if (!spots.length || (!holding && !reduce.matches)) return
      const from = spots
      spots = arrange()
      cards.forEach((card, i) => {
        card.style.zIndex = spots[i].z
        settle(card, from[i], spots[i], reduce.matches ? 0 : 400)
      })
    }, 150)
  })

  box.classList.add('is-live')

  if (reduce.matches) {
    pick().forEach((m, i) => dress(cards[i], m))
    spots = arrange()
    cards.forEach((card, i) => {
      card.style.zIndex = spots[i].z
      settle(card, spots[i], spots[i], 0)
    })
    return
  }

  ;(async () => {
    for (;;) {
      await whenShown()
      await round()
    }
  })()
})()
