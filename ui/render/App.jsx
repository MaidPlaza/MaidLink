import React, { useState, useEffect, useRef } from 'react'
import { flushSync } from 'react-dom'
import Dashboard from './components/Dashboard'
import Chat from './components/Chat'
import ResizeEdges from './components/ResizeEdges'

import DiagonalPattern from './components/DiagonalPattern'
import PixelWave from './components/PixelWave'
import ChipContainer from './components/ChipContainer'
import StartupChipInsertion from './components/StartupChipInsertion'
import StartupPattern from './components/StartupPattern'
import logoLoop from '../assets/logo/logo_loading_loop.svg'
import logoSequence from '../assets/logo/logo_sequence.svg'
import SetupWizard from './components/SetupWizard'
import CharacterSelect from './components/CharacterSelect'
import { useCharacter } from '@/hooks/useCharacter'
import { useChat } from '@/hooks/useChat'
import { resolveUrl } from '@/lib/url'
import { useSetting, getSettingValue, setSettingValue } from '@/lib/settings'
import { api } from '@/lib/api'
import { sounds } from '@/lib/sounds'
import { applyCharacterTheme, chipSvg, darkCharacterStructure, standardThemeStructure } from '@/lib/uiStructure'
import { setThemeWaveActive } from '@/lib/themeWave'
import { ensureCharacterUi, refreshCharacterUi } from '@/lib/characterUi'
import { dropCharacterInfo, warmCharacterInfo } from '@/lib/characterInfo'

const CHIP_RETURN_DELAY_MS = 300
const WAVE_DELAY_MS = 600
const WAVE_WIPE_MS = 1200
const LOGO_SEQUENCE_MS = 4060
const LOGO_HOLD_MS = 2000
const DASHBOARD_CLOSE_MS = 300

export default function App() {
  const [chatOpen, setChatOpen] = useState(false)
  const [charSelectOpen, setCharSelectOpen] = useState(false)
  const [selectionLock, setSelectionLock] = useState(false)
  const [chipHidden, setChipHidden] = useState(false)
  const [panelBare, setPanelBare] = useState(false)
  const [pendingChip, setPendingChip] = useState(null)
  const [linesVisible, setLinesVisible] = useState(true)
  const [patternPlaying, setPatternPlaying] = useState(false)
  const [waveActive, setWaveActive] = useState(false)
  const [waveDirection, setWaveDirection] = useState('tl-br')
  const [loading, setLoading] = useState(true)
  const [loadingExiting, setLoadingExiting] = useState(false)
  const [logoPlaying, setLogoPlaying] = useState(false)
  const [contentVisible, setContentVisible] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [expandMode, setExpandMode] = useState('default')
  const [dashboardVisible, setDashboardVisible] = useState(false)
  const [needsSetup, setNeedsSetup] = useState(null)
  const [minElapsed, setMinElapsed] = useState(false)
  const [slowStart, setSlowStart] = useState(false)
  const [migration, setMigration] = useState(null)
  const [chipVisible, setChipVisible] = useState(false)
  const [launchDone, setLaunchDone] = useState(false)
  const startupCoverUp = linesVisible
  const dragStart = useRef(null)
  const patternDoneCallback = useRef(null)
  const { characters, character, identity, select, refresh, refreshActive } = useCharacter()
  const chat = useChat()
  const activeChar = characters.find((c) => c.active)
  const chipHint = character !== null && characters.length === 0 && !charSelectOpen && launchDone
  const [moodPortraits] = useSetting('drawing.mood_portraits_enabled')
  const liveMood = identity?.reaction_state || identity?.mood_live || identity?.mood_state || ''
  const moodQ = moodPortraits && liveMood && liveMood !== 'ровное' ? `&mood=${encodeURIComponent(liveMood)}` : ''
  const portraitUrl = activeChar
    ? resolveUrl(`/api/avatar/portrait?c=${activeChar.id}&v=${chat.portraitVersion}${moodQ}`)
    : ''
  const chatAvatarUrl = activeChar
    ? resolveUrl(`${activeChar.avatar_chat}?c=${activeChar.id}&v=${chat.portraitVersion}`)
    : ''

  function handleSelectionLock(v) {
    setSelectionLock(v)
    setChipHidden(v)
  }

  function closeCharSelect() {
    setPanelBare(false)
    setPendingChip(null)
    handleSelectionLock(false)
    setCharSelectOpen(false)
  }
  const chipClosesSelect = charSelectOpen && !chipHidden && !panelBare
  function onChipClick() {
    if (!charSelectOpen) {
      if (expanded) {
        handleToggleExpand()
        setTimeout(() => setCharSelectOpen(true), DASHBOARD_CLOSE_MS)
        return
      }
      setCharSelectOpen(true)
      return
    }
    if (chipClosesSelect && !pickInFlightRef.current) closeCharSelect()
  }

  function playPatternThen(cb, direction = 'tl-br') {
    patternDoneCallback.current = cb
    setWaveDirection(direction)
    setWaveActive(true)
  }

  async function playThemeWipe(applyChanges, onDone) {
    const mainWindow = document.querySelector(
      '.main-window, .main-window-expanded, .main-window-expanded-avatar',
    )
    let dataUrl = null
    try {
      dataUrl = await window.maidlink?.captureScreenshot()
    } catch (e) {
      console.error('[App] снимок для перехода не получился', e)
    }
    if (!dataUrl || !mainWindow) {
      await applyChanges()
      playPatternThen(() => onDone?.(), 'br-tl')
      return
    }

    const overlay = document.createElement('div')
    overlay.style.cssText = [
      'position:absolute', 'inset:0', 'z-index:9996', 'pointer-events:none',
      `background:url(${dataUrl}) no-repeat 0 0 / ${window.innerWidth}px 100%`,
    ].join(';')
    mainWindow.appendChild(overlay)

    await applyChanges()

    requestAnimationFrame(() => {
      overlay.style.animation = `curtain-wipe-reverse ${WAVE_WIPE_MS}ms linear forwards`
      playPatternThen(() => { overlay.remove(); onDone?.() }, 'br-tl')
    })
  }

  const [darkThemeOn] = useSetting('appearance.dark_theme')
  const [standardThemeOn] = useSetting('appearance.standard_theme')

  const devThemeRef = useRef(null)
  const pickedCharRef = useRef(null)
  const pickInFlightRef = useRef(false)

  async function fetchAndApplyTheme(force = false) {
    if (!force && pickInFlightRef.current) return
    const standardOn = getSettingValue('appearance.standard_theme')
    const noCharacter = !activeChar && !devThemeRef.current
    if (standardOn || noCharacter) {
      const who = standardOn ? (pickedCharRef.current || activeChar) : null
      applyCharacterTheme(standardThemeStructure(who, { dark: darkThemeOn }), { dark: darkThemeOn })
      return
    }
    if (darkThemeOn) {
      const dark = darkCharacterStructure(pickedCharRef.current || activeChar)
      if (dark) { applyCharacterTheme(dark, { dark: true }); return }
    }
    if (devThemeRef.current) { applyCharacterTheme(devThemeRef.current); return }
    try {
      const r = await api.characterTheme()
      applyCharacterTheme(r && r.theme)
    } catch {
      applyCharacterTheme(null)
    }
  }

  useEffect(() => {
    ensureCharacterUi(activeChar ? [activeChar] : []).finally(() => fetchAndApplyTheme())
  }, [activeChar?.id])

  useEffect(() => { ensureCharacterUi(characters) }, [characters])
  useEffect(() => {
    if (chat.portraitVersion > 0 && activeChar) refreshCharacterUi([activeChar])
  }, [chat.portraitVersion])

  useEffect(() => {
    dropCharacterInfo()
    if (activeChar) warmCharacterInfo()
  }, [activeChar?.id])
  useEffect(() => {
    if (!chat.appStatus && activeChar) warmCharacterInfo()
  }, [chat.appStatus])

  useEffect(() => { setThemeWaveActive(waveActive) }, [waveActive])
  useEffect(() => () => setThemeWaveActive(false), [])

  const darkWipeSkipRef = useRef(true)
  useEffect(() => {
    if (darkWipeSkipRef.current) { darkWipeSkipRef.current = false; return }
    if (pickInFlightRef.current) return
    playThemeWipe(async () => { await fetchAndApplyTheme(true) })
  }, [darkThemeOn, standardThemeOn])

  function animateWindowWidth(fromWidth, toWidth, durationMs) {
    const bounds = window.maidlink?.getBounds()
    if (!bounds) return
    const start = performance.now()
    function frame(now) {
      const t = Math.min((now - start) / durationMs, 1)
      const ease = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t
      const w = Math.round(fromWidth + (toWidth - fromWidth) * ease)
      window.maidlink.resize({ x: bounds.x, y: bounds.y, width: w, height: bounds.height })
      if (t < 1) requestAnimationFrame(frame)
    }
    requestAnimationFrame(frame)
  }

  const avatarOpen = expandMode === 'avatar'

  function growWindow() {
    const current = window.maidlink?.getBounds()?.width ?? 780
    animateWindowWidth(current, current + 290, 300)
  }
  function shrinkWindow() {
    const current = window.maidlink?.getBounds()?.width ?? 780
    if (current > 780) animateWindowWidth(current, 780, 300)
  }

  function growWindowInstant() {
    const b = window.maidlink?.getBounds()
    if (!b) return
    window.maidlink.resize({ x: b.x, y: b.y, width: b.width + 290, height: b.height })
  }
  function shrinkWindowInstant() {
    const b = window.maidlink?.getBounds()
    if (!b || b.width <= 780) return
    window.maidlink.resize({ x: b.x, y: b.y, width: 780, height: b.height })
  }

  function handleToggleExpand() {
    if (!expanded) {
      if (!avatarOpen) {
        growWindow()
        setTimeout(() => setDashboardVisible(true), 300)
      } else {
        setDashboardVisible(true)
      }
      setExpanded(true)
    } else {
      setExpanded(false)
      setDashboardVisible(false)
      if (!avatarOpen) setTimeout(shrinkWindow, 300)
    }
  }

  function handleToggleExpandAvatar() {
    if (!avatarOpen) {
      if (!expanded) growWindowInstant()
      setExpandMode('avatar')
    } else {
      setExpandMode('default')
      if (!expanded) shrinkWindowInstant()
    }
  }

  function onResizeMouseDown(e) {
    e.preventDefault()
    const bounds = window.maidlink?.getBounds()
    if (!bounds) return
    dragStart.current = { mouseX: e.screenX, ...bounds }

    function onMove(e) {
      const dx = e.screenX - dragStart.current.mouseX
      window.maidlink.resize({
        x:      dragStart.current.x,
        y:      dragStart.current.y,
        width:  Math.max(1070, Math.round(dragStart.current.width + dx)),
        height: dragStart.current.height,
      })
    }
    function onUp() {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      dragStart.current = null
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }



  useEffect(() => {
    const t = setTimeout(() => setMinElapsed(true), 3000)
    return () => clearTimeout(t)
  }, [])
  useEffect(() => {
    if (minElapsed && needsSetup !== null) setLogoPlaying(true)
  }, [minElapsed, needsSetup])

  useEffect(() => {
    if (!logoPlaying) return
    const t = setTimeout(() => setLoadingExiting(true), LOGO_SEQUENCE_MS + LOGO_HOLD_MS)
    return () => clearTimeout(t)
  }, [logoPlaying])

  useEffect(() => sounds.installGlobal(), [])

  useEffect(() => {
    let alive = true
    let attempt = 0
    async function check() {
      if (!alive) return
      try {
        const s = await api.setupStatus()
        if (alive) setNeedsSetup(!!s.needs_setup || s.agreement_ok === false)
      } catch {
        if (!alive) return
        const mig = await api.migrationStatus().catch(() => null)
        if (!alive) return
        if (mig?.migrating) {
          setMigration(mig)
          setTimeout(check, 2000)
          return
        }
        setMigration(null)
        attempt += 1
        if (attempt >= 4) setSlowStart(true)
        if (attempt < 120) setTimeout(check, 2000)
        else setNeedsSetup(false)
      }
    }
    check()
    return () => { alive = false }
  }, [])

  useEffect(() => {
    if (!loadingExiting) return
    const tContent = setTimeout(() => setContentVisible(true), 600)
    const tDone = setTimeout(() => setLoading(false), 900)
    return () => { clearTimeout(tContent); clearTimeout(tDone) }
  }, [loadingExiting])

  const prevGenRef = useRef(false)
  useEffect(() => {
    if (prevGenRef.current && !chat.isGenerating) {
      refreshActive()
      warmCharacterInfo()
    }
    prevGenRef.current = chat.isGenerating
  }, [chat.isGenerating, refreshActive])

  return (
    <div className={`${expanded ? 'main-window-expanded' : (avatarOpen ? 'main-window-expanded-avatar' : 'main-window')}${contentVisible ? '' : ' main-window--boot'}`}>

      {needsSetup === true && contentVisible && <SetupWizard onDone={() => setNeedsSetup(false)} />}

      {loading && (
        <div className={`loading-screen${loadingExiting ? ' loading-screen--exit' : ''}`}>
          {!loadingExiting && (
            <img
              key={logoPlaying ? 'sequence' : 'loop'}
              className="loading-logo"
              src={logoPlaying ? logoSequence : logoLoop}
              alt=""
            />
          )}
        </div>
      )}
      {loading && !loadingExiting && migration && (
        <div className="loading-slow-hint">
          Переносим данные в папку установки: {migration.total ? Math.floor(migration.done * 100 / migration.total) : 0}%
          {' '}({(migration.done / 2 ** 30).toFixed(1)} из {(migration.total / 2 ** 30).toFixed(1)} ГБ). Это однократно — не закрывайте приложение.
        </div>
      )}
      {loading && !loadingExiting && slowStart && !migration && (
        <div className="loading-slow-hint">Первый запуск дольше обычного — идёт проверка и подготовка файлов…</div>
      )}
      <div style={{ visibility: contentVisible ? 'visible' : 'hidden', pointerEvents: contentVisible ? 'auto' : 'none' }}>

            <Dashboard  character={character} activeChar={activeChar} identity={identity} portraitUrl={portraitUrl} onPlayPattern={() => setPatternPlaying(true)}  onPlayWave={() => setWaveActive(true)} dashboardVisible={dashboardVisible} expandMode={expandMode} />

            <div className="chat" style={{ visibility: (charSelectOpen && !panelBare) || startupCoverUp ? 'hidden' : 'visible', pointerEvents: charSelectOpen || startupCoverUp ? 'none' : 'auto' }}>
              <Chat onToggleExpand={handleToggleExpand} onToggleExpandAvatar={handleToggleExpandAvatar} expanded={expanded} expandMode={expandMode} character={character} characters={characters} onSelectCharacter={select} chatAvatarUrl={chatAvatarUrl} portraitUrl={portraitUrl} chat={chat} contextWindow={chat.contextWindow} />
            </div>

            <div style={{ visibility: (charSelectOpen && !panelBare) || startupCoverUp ? 'hidden' : 'visible' }}>
              <div className="chat-top-shadow"/>
              <div className="chat-middle-shadow"/>
              <div className="chat-bottom-shadow"/>
            </div>

          <div className={`chip-reveal${chipVisible ? ' chip-reveal--on' : ''}`}>
            <div
              className={`chip-activation-region${chipClosesSelect ? ' chip-activation-region--over-select' : ''}`}
              onClick={onChipClick}
            >

            </div>

            <ChipContainer locked={chipHidden} chip={pendingChip} hint={chipHint} />
          </div>

          <div className="drag-region" />
      </div>

      {charSelectOpen && (
        <CharacterSelect
          characters={characters}
          onSelect={async (id, secret, theme) => {
            devThemeRef.current = theme || null
            pickedCharRef.current = characters.find((c) => c.id === id) || null
            pickInFlightRef.current = true
            const res = await select(id, secret)
            if (res !== 'ok') { pickInFlightRef.current = false; pickedCharRef.current = null }
            if (res === 'ok') {
              setSettingValue('appearance.standard_theme', false)
              setPendingChip(chipSvg(theme) || null)
              setTimeout(() => setChipHidden(false), CHIP_RETURN_DELAY_MS)
              setTimeout(() => {
                playThemeWipe(
                  async () => {
                    await fetchAndApplyTheme(true)
                    pickInFlightRef.current = false
                    pickedCharRef.current = null
                    flushSync(() => {
                      chat.clearMessages()
                      setPanelBare(true)
                    })
                  },
                  () => { setPanelBare(false); setPendingChip(null); handleSelectionLock(false); setCharSelectOpen(false) },
                )
              }, WAVE_DELAY_MS)
            }
            return res
          }}
          selectionLock={selectionLock}
          bare={panelBare}
          onSelectionLock={handleSelectionLock}
          onRefresh={refresh}
        />
      )}

      <div className={expanded ? 'resize-handle-right' : 'resize-handle-right-blocked'} onMouseDown={onResizeMouseDown} />

      <ResizeEdges expanded={expanded} />

      <DiagonalPattern play={patternPlaying} onComplete={() => setPatternPlaying(false)}/>

        {linesVisible && contentVisible &&
        <div  className="startup-chip-insertion-lines">
          <StartupPattern />
          <svg className="startup-chip-insertion-lines-stripes" width="658" height="906" viewBox="0 0 658 906" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M564.505 886L55 885.91V884H556.5L581.021 860H590.93L564.505 886Z" fill="#7B79AB"/>
            <path d="M587.627 886H577.718L604.143 860H614.052L587.627 886Z" fill="#7B79AB"/>
            <path d="M611.575 886H601.666L628.091 860H638L611.575 886Z" fill="#7B79AB"/>
            <path d="M94.4946 21L604 21.09V23H102.5L77.9789 47H68.0696L94.4946 21Z" fill="#7B79AB"/>
            <path d="M71.3727 21H81.2821L54.8571 47H44.9477L71.3727 21Z" fill="#7B79AB"/>
            <path d="M47.425 21H57.3344L30.9094 47H21L47.425 21Z" fill="#7B79AB"/>
            </svg>


        </div>
      }

      <div className="pixel-wave-startup">
        <PixelWave active={waveActive} direction={waveDirection} onComplete={() => { setWaveActive(false); patternDoneCallback.current?.(); patternDoneCallback.current = null }}/>
      </div>
    
      {contentVisible && (
        <StartupChipInsertion
          onPlayPattern={(cb) => playPatternThen(() => { cb?.(); setLaunchDone(true) })}
          onOverlayReady={() => setLinesVisible(false)}
          onEnterStart={() => setChipVisible(true)}
          modelState={chat.modelState}
          onWarmup={chat.notifyKeystroke}
        />
      )}
    </div>
  )
}
