(() => {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)')
  const narrow = matchMedia('(max-width: 720px)')

  function liveness(root, onChange) {
    let hovered = false
    let focused = false
    let onScreen = true
    const schedule = () => onChange(!reduce.matches && !hovered && !focused && onScreen && !document.hidden)
    root.addEventListener('mouseenter', () => { hovered = true; schedule() })
    root.addEventListener('mouseleave', () => { hovered = false; schedule() })
    root.addEventListener('focusin', () => { focused = true; schedule() })
    root.addEventListener('focusout', () => { focused = false; schedule() })
    document.addEventListener('visibilitychange', schedule)
    reduce.addEventListener?.('change', schedule)
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(([entry]) => {
        if (entry.isIntersecting === onScreen) return
        onScreen = entry.isIntersecting
        schedule()
      }, { threshold: 0.35 }).observe(root)
    }
    return schedule
  }

  function pulse(root, { interval, delay = 0, onTick, onState }) {
    let timer = null
    let lead = null
    return liveness(root, (on) => {
      clearInterval(timer)
      clearTimeout(lead)
      timer = lead = null
      onState?.(on)
      if (!on) return
      const start = () => { timer = setInterval(onTick, interval) }
      if (delay) { lead = setTimeout(() => { delay = 0; onTick(); start() }, delay) } else start()
    })
  }

  for (const root of document.querySelectorAll('[data-vcar]')) {
    const items = [...root.querySelectorAll('.vcar-item')]
    const scale = root.querySelector('[data-vcar-scale]')
    const n = items.length
    if (n < 2 || !scale) continue
    const INTERVAL = 6000
    const wanted = Math.max(1, Math.min(n - 1, Number(root.dataset.visible) || 1))
    let visible = narrow.matches ? 1 : wanted
    let active = 0

    scale.setAttribute('role', 'slider')
    scale.setAttribute('aria-valuemin', '1')
    scale.setAttribute('aria-valuemax', String(n))
    scale.tabIndex = 0
    scale.style.setProperty('--n', n)
    const rail = document.createElement('div')
    rail.className = 'vcar-rail'
    const timer = document.createElement('i')
    timer.className = 'vcar-timer'
    const ticks = items.map((item, i) => {
      const tick = document.createElement('i')
      tick.className = 'vcar-tick'
      tick.style.setProperty('--x', i / (n - 1))
      tick.style.setProperty('--c', getComputedStyle(item).getPropertyValue('--c').trim())
      return tick
    })
    const thumb = document.createElement('i')
    thumb.className = 'vcar-thumb'
    rail.append(timer, ...ticks, thumb)
    scale.append(rail)

    const measure = () => {
      root.classList.add('is-measuring')
      const h = Math.max(...items.map((el) => el.offsetHeight))
      root.classList.remove('is-measuring')
      root.style.setProperty('--item-h', `${h}px`)
    }

    const place = () => {
      items.forEach((el, i) => {
        let slot = (i - active + n) % n
        if (slot === n - 1) slot = -1
        el.style.setProperty('--slot', Math.min(slot, visible))
        el.classList.toggle('is-shown', slot >= 0 && slot < visible)
      })
      ticks.forEach((t, i) => t.classList.toggle('is-active', i === active))
      scale.style.setProperty('--at', active / (n - 1))
      scale.style.setProperty('--c', ticks[active].style.getPropertyValue('--c'))
      scale.classList.toggle('is-last', active === n - 1)
      scale.setAttribute('aria-valuenow', String(active + 1))
      scale.setAttribute('aria-valuetext', `Пример ${active + 1} из ${n}`)
    }

    const restartFill = () => {
      timer.classList.remove('is-run')
      void timer.offsetWidth
      timer.classList.add('is-run')
    }

    const go = (i) => { active = (i + n) % n; place(); restartFill() }

    const schedule = pulse(root, {
      interval: INTERVAL,
      delay: Number(root.dataset.delay) || 0,
      onTick: () => go(active + 1),
      onState: (on) => {
        root.classList.toggle('is-static', reduce.matches)
        root.classList.toggle('is-paused', !on)
        if (on) restartFill()
      },
    })

    const nearest = (x) => {
      const r = rail.getBoundingClientRect()
      return Math.round(Math.min(1, Math.max(0, (x - r.left) / r.width)) * (n - 1))
    }
    const scrub = (e) => { const i = nearest(e.clientX); if (i !== active) go(i) }
    scale.addEventListener('pointermove', (e) => {
      if (e.pointerType === 'mouse' || scale.hasPointerCapture(e.pointerId)) scrub(e)
    })
    scale.addEventListener('pointerdown', (e) => {
      if (e.pointerType !== 'mouse') scale.setPointerCapture(e.pointerId)
      scrub(e)
    })
    scale.addEventListener('pointerup', () => schedule())
    scale.addEventListener('pointercancel', () => schedule())
    scale.addEventListener('mousedown', (e) => e.preventDefault())
    scale.addEventListener('keydown', (e) => {
      const to = { ArrowRight: active + 1, ArrowUp: active + 1, ArrowLeft: active - 1, ArrowDown: active - 1, Home: 0, End: n - 1 }[e.key]
      if (to === undefined) return
      e.preventDefault()
      go(Math.min(n - 1, Math.max(0, to)))
      schedule()
    })

    let resizeTimer = null
    addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(measure, 150) })
    root.style.setProperty('--vcar-interval', `${INTERVAL}ms`)
    root.style.setProperty('--visible', visible)
    narrow.addEventListener?.('change', () => {
      visible = narrow.matches ? 1 : wanted
      root.style.setProperty('--visible', visible)
      place()
    })
    root.classList.add('is-live')
    measure()
    place()
    schedule()
    document.fonts?.ready.then(measure)
  }

  for (const root of document.querySelectorAll('[data-adapt]')) {
    const buttons = [...root.querySelectorAll('[data-adapt-preset]')]
    if (!buttons.length) continue
    let current = 0
    const show = (i) => {
      current = (i + buttons.length) % buttons.length
      buttons.forEach((b, k) => {
        root.classList.toggle(`is-p${k}`, k === current)
        b.setAttribute('aria-pressed', String(k === current))
      })
    }
    const schedule = pulse(root, { interval: 3800, onTick: () => show(current + 1) })
    buttons.forEach((b, k) => b.addEventListener('click', () => { show(k); schedule() }))
    schedule()
  }

  for (const root of document.querySelectorAll('[data-mood]')) {
    const says = [...root.querySelectorAll('[data-mood-say]')]
    const imgs = [...root.querySelectorAll('[data-mood-img]')]
    const label = root.querySelector('[data-mood-label]')
    if (!says.length || says.length !== imgs.length) continue
    let current = 0
    const show = (i) => {
      current = (i + says.length) % says.length
      says.forEach((b, k) => b.setAttribute('aria-pressed', String(k === current)))
      imgs.forEach((img, k) => img.classList.toggle('is-on', k === current))
      label.textContent = says[current].dataset.label
      label.classList.remove('is-pop')
      void label.offsetWidth
      label.classList.add('is-pop')
    }
    const schedule = pulse(root, { interval: 3500, onTick: () => show(current + 1) })
    says.forEach((b, k) => b.addEventListener('click', () => { show(k); schedule() }))
    schedule()
  }

  for (const root of document.querySelectorAll('[data-photo]')) {
    const tile = root.closest('.feature') || root
    const asks = [...tile.querySelectorAll('[data-photo-ask]')]
    const imgs = [...root.querySelectorAll('[data-photo-img]')]
    const askText = root.querySelector('[data-photo-ask-text]')
    const msg = root.querySelector('.photo-msg')
    if (!asks.length || asks.length !== imgs.length) continue
    let current = 0
    let wait = null
    const show = (i) => {
      current = (i + asks.length) % asks.length
      asks.forEach((b, k) => b.setAttribute('aria-pressed', String(k === current)))
      clearTimeout(wait)
      askText.classList.add('is-fade')
      wait = setTimeout(() => {
        askText.textContent = asks[current].textContent.replace(/^«|»$/g, '')
        askText.classList.remove('is-fade')
        msg.classList.add('is-typing')
        wait = setTimeout(() => {
          imgs.forEach((img, k) => img.classList.toggle('is-on', k === current))
          msg.classList.remove('is-typing')
        }, reduce.matches ? 0 : 900)
      }, reduce.matches ? 0 : 300)
    }
    const schedule = pulse(tile, { interval: 5500, onTick: () => show(current + 1) })
    asks.forEach((b, k) => b.addEventListener('click', () => { show(k); schedule() }))
    schedule()
  }

  for (const root of document.querySelectorAll('[data-gacha]')) {
    const tile = root.closest('.feature') || root
    const card = root.querySelector('[data-gacha-card]')
    const btn = tile.querySelector('[data-gacha-pull]')
    const count = tile.querySelector('[data-gacha-count]')
    const log = root.querySelector('[data-gacha-log]')
    const nameEl = card.querySelector('[data-gacha-name]')
    const rarityEl = card.querySelector('[data-gacha-rarity]')
    const catEl = card.querySelector('[data-gacha-cat]')
    if (!btn) continue
    const ITEMS = [
      ...[['Высокий хвост', 'укладка'], ['Две косы', 'укладка'], ['Пучок на макушке', 'укладка'],
        ['Волнистые волосы', 'текстура волос'], ['Чёлка набок', 'чёлка'], ['Ахоге', 'элемент причёски'],
        ['Помада', 'макияж'], ['Тени', 'макияж'], ['Лак для ногтей', 'макияж'],
        ['Бант в волосах', 'украшение'], ['Лента в волосах', 'украшение']].map((x) => [...x, 'common']),
      ...[['Канзаши', 'украшение'], ['Цветок в волосах', 'украшение'], ['Колокольчик в волосах', 'украшение'],
        ['Жемчужное ожерелье', 'украшение'], ['Серьги-полумесяцы', 'украшение'], ['Брошь', 'украшение'],
        ['Локоны-колечки', 'укладка'], ['Блёстки', 'макияж'], ['Монокль', 'украшение'],
        ['Чокер-лента', 'украшение']].map((x) => [...x, 'rare']),
      ...[['Маска лисы', 'украшение'], ['Тиара', 'украшение'], ['Нимб', 'украшение'], ['Венок', 'украшение'],
        ['Мини-корона', 'украшение'], ['Вуаль', 'украшение'], ['Ахоге-сердечко', 'элемент причёски']].map((x) => [...x, 'legendary']),
    ]
    const RU = { common: 'Обычная', rare: 'Редкая', legendary: 'Легендарная' }
    let left = [...ITEMS]
    let opened = 0
    let busy = false

    const fit = () => {
      nameEl.classList.remove('is-two')
      let size = 30
      nameEl.style.fontSize = `${size}px`
      while (nameEl.scrollWidth > nameEl.clientWidth && size > 22) nameEl.style.fontSize = `${--size}px`
      if (nameEl.scrollWidth > nameEl.clientWidth) {
        nameEl.classList.add('is-two')
        size = 30
        nameEl.style.fontSize = `${size}px`
        const over = () => nameEl.scrollWidth > nameEl.clientWidth || nameEl.offsetHeight > size * 1.08 * 2 + 2
        while (over() && size > 16) nameEl.style.fontSize = `${--size}px`
      }
    }

    const renderCount = () => {
      count.textContent = opened ? `открыто ${opened} из ${ITEMS.length}` : `${ITEMS.length} предметов в демо`
    }

    const pull = () => {
      if (busy) return
      if (!left.length) { left = [...ITEMS]; opened = 0; log.innerHTML = '' }
      const [name, cat, rarity] = left.splice(Math.floor(Math.random() * left.length), 1)[0]
      opened += 1
      busy = true
      btn.disabled = true
      card.classList.remove('is-shine')
      card.classList.add('is-flip')
      setTimeout(() => {
        card.classList.remove('is-back', 'is-rare', 'is-legendary')
        if (rarity !== 'common') card.classList.add(`is-${rarity}`)
        rarityEl.textContent = RU[rarity]
        nameEl.textContent = name
        catEl.textContent = cat
        fit()
        card.classList.remove('is-flip')
        if (rarity === 'legendary' && !reduce.matches) {
          void card.offsetWidth
          card.classList.add('is-shine')
        }
        const li = document.createElement('li')
        li.className = `is-${rarity}`
        li.textContent = name
        log.prepend(li)
        while (log.children.length > 6) log.lastChild.remove()
        renderCount()
        busy = false
        btn.disabled = false
      }, reduce.matches ? 0 : 300)
    }

    card.classList.remove('is-rare', 'is-legendary')
    card.classList.add('is-back')
    rarityEl.textContent = 'Билет удачи'
    nameEl.textContent = '?'
    catEl.textContent = 'что выпадет?'
    btn.addEventListener('click', pull)
    renderCount()
  }

  for (const root of document.querySelectorAll('[data-shots]')) {
    const track = root.querySelector('.shots-track')
    const shots = [...track.children]
    if (shots.length < 4) continue
    for (const shot of shots) {
      const copy = shot.cloneNode(true)
      copy.setAttribute('aria-hidden', 'true')
      for (const a of copy.querySelectorAll('a')) a.tabIndex = -1
      track.append(copy)
    }
    root.style.setProperty('--shots-loop', `${shots.length * 10}s`)
    root.classList.add('is-drifting')
    liveness(root, (on) => root.classList.toggle('is-paused', !on))()
  }
})()
