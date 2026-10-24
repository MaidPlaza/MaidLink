import React, { useState, useRef, useEffect } from 'react'
import { api } from '@/lib/api'
import maidLinkLogo from '../../assets/logo/MaidLink.svg'
import loadingBars from '../../assets/logo/LoadingBars.svg'

const WAVE_WIPE_MS = 1200

const startupImages = [maidLinkLogo, loadingBars].map(src => {
  const img = new Image()
  img.src = src
  return img
})
const startupAssetsReady = Promise.all([
  ...startupImages.map(img => img.decode().catch(() => {})),
  document.fonts.load('300 32px "Kantumruy Pro"').catch(() => {}),
])

const LOADING_STATUSES = [
  { threshold: 0,   status: 'Установка связи' },
  { threshold: 0.5, status: 'Модель разогревается' },
  { threshold: 1,   status: 'Готово к запуску' },
]

const DEBUG_PROGRESS_STEP_MS = 0

const LOADING_TIPS = [
  'Попросите персонажа прислать фото.',
  'Понравившийся снимок можно сохранить сердечком — он попадёт в галерею.',
  'Персонажа можно погладить по голове.',
  'Билеты удачи приходят каждый день — в них новые причёски, украшения и цвета.',
  'В гардеробе — костюмы, стайлинг и стиль рисования.',
  'Персонаж помнит ваши прошлые разговоры.',
  'Насколько вы сблизились, видно в карточке персонажа.',
  'Нового персонажа можно добавить, перетащив его файл в окно выбора.',
  'Персонажа можно защитить паролем — в карточке, раздел «Настройки».',
]
const TIP_INTERVAL_MS = 10_000

const BETA_BADGE = 'Бета-версия'
const BETA_DISCLAIMER =
  'Некоторые функции могут работать с ошибками, а персонаж иногда что-то путать ' +
  'или отвечать невпопад. Мы продолжаем всё улучшать — спасибо, что тестируете вместе с нами!'

function shuffledTips(avoidFirst) {
  const deck = LOADING_TIPS.map((_, i) => i)
  for (let i = deck.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [deck[i], deck[j]] = [deck[j], deck[i]]
  }
  if (deck.length > 1 && deck[0] === avoidFirst) {
    const j = 1 + Math.floor(Math.random() * (deck.length - 1));
    [deck[0], deck[j]] = [deck[j], deck[0]]
  }
  return deck
}

export default function StartupChipInsertion({ onPlayPattern, onOverlayReady,
                                               onEnterStart, modelState, onWarmup }) {
  const [visible, setVisible] = useState(true)
  const [settingsReady, setSettingsReady] = useState(false)
  const [debugPct, setDebugPct] = useState(0)
  const [tipIndex, setTipIndex] = useState(null)
  const [assetsReady, setAssetsReady] = useState(false)
  const [exiting, setExiting] = useState(false)
  const containerRef = useRef(null)
  const busy = useRef(false)

  useEffect(() => {
    let cancelled = false
    async function tick() {
      if (cancelled) return
      try {
        await api.getSettings()
        if (!cancelled) setSettingsReady(true)
        return
      } catch {}
      setTimeout(tick, 1000)
    }
    tick()
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!visible || modelState !== 'UNLOADED') return
    onWarmup?.()
    const t = setInterval(() => onWarmup?.(), 31_000)
    return () => clearInterval(t)
  }, [visible, modelState, onWarmup])

  useEffect(() => {
    if (!DEBUG_PROGRESS_STEP_MS) return
    const t = setInterval(() => setDebugPct(p => Math.min(p + 1, 100)), DEBUG_PROGRESS_STEP_MS)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    let deck = []
    let last = null
    function next() {
      if (!deck.length) deck = shuffledTips(last)
      last = deck.shift()
      setTipIndex(last)
    }
    next()
    const t = setInterval(next, TIP_INTERVAL_MS)
    return () => clearInterval(t)
  }, [])

  const linkReady = modelState !== null
  const modelReady = modelState === 'LOADED'
  const ready = settingsReady && modelReady

  const progress =
    (linkReady ? 1 : 0) +
    (settingsReady ? 1 : 0) +
    (modelReady ? 1 : modelState === 'LOADING' ? 0.5 : 0)
  const realPct = Math.round((progress / 3) * 100)
  const pct = DEBUG_PROGRESS_STEP_MS ? Math.min(realPct, debugPct) : realPct
  const loadingStatus =
    LOADING_STATUSES.findLast(s => pct / 100 >= s.threshold) ?? LOADING_STATUSES[0]

  useEffect(() => {
    let alive = true
    startupAssetsReady.then(() => { if (alive) setAssetsReady(true) })
    return () => { alive = false }
  }, [])

  async function handleClick() {
    if (!ready) return
    if (busy.current) return
    busy.current = true
    try {
      const el = containerRef.current

      const FADE_MS = 300
      setExiting(true)

      await new Promise(r => setTimeout(r, FADE_MS))
      el.style.visibility = 'hidden'

      const dataUrl = await window.maidlink?.captureScreenshot()

      onEnterStart?.()

      const mainWindow = document.querySelector('.main-window, .main-window-expanded')
      const overlay = document.createElement('div')
      const captureW = window.innerWidth
      overlay.style.cssText = [
        'position:absolute', 'inset:0', 'z-index:9996',
        `background:url(${dataUrl}) no-repeat 0 0 / ${captureW}px 100%`,
      ].join(';')
      mainWindow.appendChild(overlay)
      onOverlayReady?.()

      const theme = (await window.maidlink?.readThemeConfig('mira')) || {}
      const root = document.documentElement
      for (const [name, value] of Object.entries(theme)) {
        root.style.setProperty(`--${name}`, value)
      }

      requestAnimationFrame(() => {
        overlay.style.animation = `curtain-wipe ${WAVE_WIPE_MS}ms linear forwards`
        onPlayPattern(() => {
          overlay.remove()
          setVisible(false)
        })
      })
    } catch (e) {
      console.error('applyTheme failed:', e)
      busy.current = false
    }
  }

  if (!visible) return null

  const row = (label, ok, waitText) => (
    <div className="startup-status-row">
      <span className="startup-status-label">{label}</span>
      <span className="startup-status-dots" />
      <span className={`startup-status-value${ok ? '' : ' startup-status-value--wait'}${waitText === 'WARMING' && !ok ? ' startup-status-value--warming' : ''}`}>
        {ok ? 'OK' : waitText}
      </span>
    </div>
  )

  return (
    <div ref={containerRef} className="startup-chip-insertion no-select"  onClick={handleClick}>


      <div className={`loading-screen-progress-container${assetsReady ? ' loading-screen-progress-container--in' : ''}${exiting ? ' loading-screen-progress-container--exit' : ''}`}>
        <div>
            <img src={maidLinkLogo} alt="MaidLink" width={383} height={95} draggable={false} />
        </div>
        <div className="loading-screen-progress-status-switcher">
              <span key={loadingStatus.status} className="loading-screen-progress-status">
                {loadingStatus.status}
              </span>
        </div>
        <div className="loading-screen-progress-bar-container">
          <img src={loadingBars} alt="" width={452} height={95} draggable={false} />
        </div>
        <div className="loading-screen-progress-bar">
          <div className="loading-screen-progress-bar-track">
            <div className="loading-screen-progress-bar-fill" style={{ width: `${pct}%` }} />
          </div>
          <div className="loading-screen-progress-bar-pct">{pct}%</div>
        </div>

        <div>
        <div className="loading-screen-progress-tips-container">
          <svg width="337" height="98" viewBox="0 0 337 98" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M21 8H10C5.02944 8 1 12.0294 1 17V81C1 85.9706 5.02944 90 10 90H296V91H10L9.48535 90.9873C4.37212 90.7281 0.271902 86.6279 0.0126953 81.5146L0 81V17C1.03084e-06 11.4772 4.47715 7 10 7H21V8Z" fill="#7B79AB" fillOpacity="0.7"/>
          <path d="M327 7C332.523 7 337 11.4772 337 17V81L336.987 81.5146C336.728 86.6279 332.628 90.7281 327.515 90.9873L327 91H317V90H327C331.971 90 336 85.9706 336 81V17C336 12.0294 331.971 8 327 8H42V7H327Z" fill="#7B79AB" fillOpacity="0.7"/>
          <path d="M301.3 87C300.955 87 300.625 87.1288 300.381 87.358C300.137 87.5872 300 87.8981 300 88.2222V91.2069C300 91.531 300.137 91.8419 300.381 92.0711C300.625 92.3003 300.955 92.4291 301.3 92.4291H303.104C303.104 92.8585 303.077 93.2879 303.024 93.7173C302.943 94.172 302.809 94.5761 302.621 94.9298C302.433 95.2834 302.19 95.5617 301.894 95.7646C301.599 95.9919 301.223 96.1056 300.766 96.1056V98C301.518 98 302.177 97.8484 302.742 97.5453C303.303 97.246 303.785 96.8316 304.152 96.3329C304.522 95.7839 304.794 95.1821 304.958 94.5509C305.124 93.8545 305.205 93.1427 305.2 92.4291V88.2222C305.2 87.8981 305.063 87.5872 304.819 87.358C304.575 87.1288 304.245 87 303.9 87H301.3ZM309.1 87C308.755 87 308.424 87.1288 308.181 87.358C307.937 87.5872 307.8 87.8981 307.8 88.2222V91.2069C307.8 91.531 307.937 91.8419 308.181 92.0711C308.424 92.3003 308.755 92.4291 309.1 92.4291H310.904C310.904 92.8585 310.877 93.2879 310.824 93.7173C310.742 94.172 310.608 94.5761 310.421 94.9298C310.233 95.2834 309.99 95.5617 309.694 95.7646C309.399 95.9919 309.023 96.1056 308.566 96.1056V98C309.318 98 309.976 97.8484 310.542 97.5453C311.103 97.246 311.585 96.8316 311.952 96.3329C312.322 95.7839 312.594 95.1821 312.758 94.5509C312.924 93.8545 313.005 93.1427 313 92.4291V88.2222C313 87.8981 312.863 87.5872 312.619 87.358C312.375 87.1288 312.045 87 311.7 87H309.1Z" fill="#7B79AB" fillOpacity="0.7"/>
          <path d="M36.7 11C37.0448 11 37.3755 10.8712 37.6192 10.642C37.863 10.4128 38 10.1019 38 9.77778V6.79311C38 6.46896 37.863 6.15808 37.6192 5.92887C37.3755 5.69966 37.0448 5.57089 36.7 5.57089H34.8957C34.8957 5.14148 34.9225 4.71207 34.9763 4.28267C35.0569 3.828 35.1912 3.42385 35.3792 3.07022C35.5673 2.71659 35.8095 2.43833 36.1059 2.23544C36.4006 2.00811 36.7767 1.89444 37.2343 1.89444V0C36.4821 0 35.8234 0.151556 35.2583 0.454667C34.6972 0.753958 34.2151 1.16839 33.8479 1.66711C33.4782 2.21607 33.206 2.81794 33.0419 3.44911C32.876 4.14546 32.7949 4.8573 32.8001 5.57089V9.77778C32.8001 10.1019 32.9371 10.4128 33.1808 10.642C33.4246 10.8712 33.7553 11 34.1001 11H36.7ZM28.9002 11C29.2449 11 29.5756 10.8712 29.8194 10.642C30.0632 10.4128 30.2001 10.1019 30.2001 9.77778V6.79311C30.2001 6.46896 30.0632 6.15808 29.8194 5.92887C29.5756 5.69966 29.2449 5.57089 28.9002 5.57089H27.0958C27.0958 5.14148 27.1227 4.71207 27.1764 4.28267C27.2579 3.828 27.3922 3.42385 27.5794 3.07022C27.7675 2.71659 28.0097 2.43833 28.3061 2.23544C28.6007 2.00811 28.9769 1.89444 29.4345 1.89444V0C28.6822 0 28.0235 0.151556 27.4585 0.454667C26.8973 0.753958 26.4152 1.16839 26.048 1.66711C25.6783 2.21607 25.4061 2.81794 25.242 3.44911C25.0761 4.14546 24.995 4.8573 25.0002 5.57089V9.77778C25.0002 10.1019 25.1372 10.4128 25.381 10.642C25.6248 10.8712 25.9554 11 26.3002 11H28.9002Z" fill="#7B79AB" fillOpacity="0.7"/>
          </svg>

        </div>
        <div className="loading-screen-progress-tips">
          {tipIndex !== null && (
            <span key={tipIndex} className="loading-screen-progress-tip">
              {LOADING_TIPS[tipIndex]}
            </span>
          )}
        </div>
      </div>
        <div className="loading-screen-disclaimer">
          <span className="loading-screen-disclaimer-badge">{BETA_BADGE}</span>
          <p className="loading-screen-disclaimer-text">{BETA_DISCLAIMER}</p>
        </div>
      </div>
    
     

    </div>
  )
}
