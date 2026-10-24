(() => {
  const root = document.querySelector('[data-catalog]')
  if (!root) return
  const track = root.querySelector('[data-carousel-track]')
  const cards = [...track.querySelectorAll('.carousel-card')]
  if (!cards.length) return
  const panels = new Map([...root.querySelectorAll('.dossier')].map((el) => [el.id, el]))
  const search = root.querySelector('[data-catalog-search]')
  const filterButtons = [...root.querySelectorAll('.tag[data-group]')]
  const count = root.querySelector('[data-catalog-count]')
  const empty = root.querySelector('[data-catalog-empty]')
  const prev = root.querySelector('[data-carousel-prev]')
  const next = root.querySelector('[data-carousel-next]')
  const total = cards.length

  const norm = (s) => s.toLowerCase().replace(/ё/g, 'е').trim()
  const plural = (n, one, few, many) => {
    if (n % 10 === 1 && n % 100 !== 11) return one
    if (n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14)) return few
    return many
  }
  const visible = () => cards.filter((c) => !c.hidden)
  const activeGroups = () => {
    const groups = new Map()
    for (const b of filterButtons) {
      if (b.getAttribute('aria-pressed') !== 'true') continue
      if (!groups.has(b.dataset.group)) groups.set(b.dataset.group, [])
      groups.get(b.dataset.group).push(b.dataset.value)
    }
    return groups
  }
  let current = cards.find((c) => c.getAttribute('aria-selected') === 'true') || cards[0]

  function select(card, { focus = false, scroll = true, hash = true } = {}) {
    current = card
    for (const c of cards) {
      const on = c === card
      c.setAttribute('aria-selected', on ? 'true' : 'false')
      c.tabIndex = on ? 0 : -1
    }
    for (const [id, panel] of panels) panel.classList.toggle('is-active', id === card.dataset.id)
    if (scroll) {
      const left = card.offsetLeft - (track.clientWidth - card.offsetWidth) / 2
      track.scrollTo({ left, behavior: 'smooth' })
    }
    if (focus) card.focus({ preventScroll: true })
    if (hash) history.replaceState(null, '', '#' + card.dataset.id)
  }

  function revealPanel() {
    const panel = panels.get(current.dataset.id)
    if (!panel) return
    const top = panel.getBoundingClientRect().top
    if (top > innerHeight - 80) scrollBy({ top: top - innerHeight * 0.42, behavior: 'smooth' })
  }

  function updateArrows() {
    const max = track.scrollWidth - track.clientWidth
    const atStart = track.scrollLeft <= 2
    const atEnd = track.scrollLeft >= max - 2
    prev.disabled = atStart
    next.disabled = atEnd
    track.style.setProperty('--fade-l', atStart ? '0px' : '28px')
    track.style.setProperty('--fade-r', atEnd ? '0px' : '28px')
    root.classList.toggle('carousel-fits', max <= 2)
  }

  function apply() {
    const q = norm(search.value)
    const groups = activeGroups()
    for (const c of cards) {
      const tags = c.dataset.tags ? c.dataset.tags.split('|') : []
      let ok = !q || c.dataset.name.includes(q)
      for (const [group, values] of groups) {
        const own = group === 'Кто' ? [c.dataset.kind] : tags
        ok = ok && values.some((v) => own.includes(v))
      }
      c.hidden = !ok
    }
    const shown = visible()
    count.textContent = shown.length === total
      ? `${total} ${plural(total, 'карточка', 'карточки', 'карточек')}`
      : `Найдено: ${shown.length} из ${total}`
    empty.hidden = shown.length > 0
    root.classList.toggle('is-empty', shown.length === 0)
    if (shown.length && current.hidden) select(shown[0], { hash: false, scroll: false })
    track.scrollLeft = 0
    updateArrows()
  }

  track.addEventListener('click', (ev) => {
    const card = ev.target.closest('.carousel-card')
    if (!card) return
    select(card)
    revealPanel()
  })
  track.addEventListener('keydown', (ev) => {
    const shown = visible()
    const i = shown.indexOf(current)
    const to = { ArrowRight: shown[i + 1], ArrowLeft: shown[i - 1], Home: shown[0], End: shown[shown.length - 1] }[ev.key]
    if (!to) return
    ev.preventDefault()
    select(to, { focus: true })
  })
  prev.addEventListener('click', () => track.scrollBy({ left: -track.clientWidth * 0.8, behavior: 'smooth' }))
  next.addEventListener('click', () => track.scrollBy({ left: track.clientWidth * 0.8, behavior: 'smooth' }))
  track.addEventListener('scroll', updateArrows, { passive: true })
  addEventListener('resize', updateArrows)

  search.addEventListener('input', apply)
  for (const b of filterButtons) {
    b.addEventListener('click', () => {
      b.setAttribute('aria-pressed', b.getAttribute('aria-pressed') === 'true' ? 'false' : 'true')
      apply()
    })
  }

  function fromHash() {
    const id = decodeURIComponent(location.hash.slice(1))
    const card = cards.find((c) => c.dataset.id === id)
    if (!card) return
    if (card.hidden) {
      search.value = ''
      for (const b of filterButtons) b.setAttribute('aria-pressed', 'false')
      apply()
    }
    select(card, { hash: false })
    document.getElementById('maids').scrollIntoView()
  }
  addEventListener('hashchange', fromHash)

  root.classList.add('is-ready')
  fromHash()
  updateArrows()
})()
