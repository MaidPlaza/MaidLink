import React, { useState, useEffect, useRef, useMemo, useId } from 'react'
import { api } from '@/lib/api'
import { chipSvg, darkCharacterStructure, themeTokenVars } from '@/lib/uiStructure'
import { useSetting } from '@/lib/settings'
import { ensureCharacterUi, getCharacterUi, getCharacterListAvatar,
         useCharacterUiVersion } from '@/lib/characterUi'
import WindowControls from './WindowControls'
import avatarFallback from '../../assets/avatars/avatar_0.png'

const LIST_AVATARS = Object.fromEntries(
  Object.entries(
    import.meta.glob('@/electron/configs/dev/character_list_avatars/*.png', {
      eager: true,
      import: 'default',
    }),
  ).map(([path, url]) => [path.split('/').pop().replace('_default.png', ''), url]),
)

const LIST_UI_DEFAULTS = { chip: '', scale: '1.2', top: '45px', right: '0', base: '', structure: null }

const LIST_UI = Object.fromEntries(
  Object.entries(
    import.meta.glob('@/electron/configs/dev/character_list_UIStructure/*_UIStructure.json', {
      eager: true,
      import: 'default',
    }),
  ).map(([path, json]) => {
    const select = json['CharacterSelect'] || {}
    return [
      path.split('/').pop().replace('_UIStructure.json', ''),
      {
        chip: chipSvg(json) || LIST_UI_DEFAULTS.chip,
        scale: select['CharacterSelect.CharacterCard.Avatar.Scale']
          ?? json['character-list-avatar-scale'] ?? LIST_UI_DEFAULTS.scale,
        top: select['CharacterSelect.CharacterCard.Avatar.TopOffset']
          ?? json['character-list-avatar-top-offset'] ?? LIST_UI_DEFAULTS.top,
        right: select['CharacterSelect.CharacterCard.Avatar.RightOffset']
          ?? json['character-list-avatar-right-offeset'] ?? LIST_UI_DEFAULTS.right,
        base: json['CharacterColorThemeDescription']?.['MainColor']
          || json['COLOR_BASE'] || LIST_UI_DEFAULTS.base,
        structure: json,
      },
    ]
  }),
)

function listAvatar(c) {
  if (!c) return avatarFallback
  return getCharacterListAvatar(c)
    || LIST_AVATARS[c.baseline_id] || LIST_AVATARS[c.id] || avatarFallback
}

function listAvatarFallback(c) {
  if (!c) return avatarFallback
  return LIST_AVATARS[c.baseline_id] || LIST_AVATARS[c.id] || avatarFallback
}

function listUI(c) {
  if (!c) return LIST_UI_DEFAULTS
  const reg = getCharacterUi(c)
  if (reg && reg.structure) {
    const json = reg.structure
    const select = json['CharacterSelect'] || {}
    return {
      chip: chipSvg(json) || LIST_UI_DEFAULTS.chip,
      scale: select['CharacterSelect.CharacterCard.Avatar.Scale']
        ?? json['character-list-avatar-scale'] ?? LIST_UI_DEFAULTS.scale,
      top: select['CharacterSelect.CharacterCard.Avatar.TopOffset']
        ?? json['character-list-avatar-top-offset'] ?? LIST_UI_DEFAULTS.top,
      right: select['CharacterSelect.CharacterCard.Avatar.RightOffset']
        ?? json['character-list-avatar-right-offeset'] ?? LIST_UI_DEFAULTS.right,
      base: json['CharacterColorThemeDescription']?.['MainColor']
        || json['COLOR_BASE'] || LIST_UI_DEFAULTS.base,
      structure: json,
    }
  }
  return LIST_UI[c.baseline_id] || LIST_UI[c.id] || LIST_UI_DEFAULTS
}

function listChip(c) {
  return listUI(c).chip
}

function listStructure(c) {
  return listUI(c).structure
}

function listBase(c) {
  return listUI(c).base || undefined
}

function listDark(c) {
  const d = c ? darkCharacterStructure(c) : null
  if (!d) return null
  return {
    ink: d['CharacterSelect.CharacterCard']?.['CharacterSelect.CharacterCard.Name.FontColor'] || undefined,
    chip: chipSvg(d),
  }
}

function cssLength(v) {
  const s = String(v).trim()
  return /^-?\d*\.?\d+$/.test(s) ? `${s}px` : s
}

function listAvatarTransform(c) {
  const { scale, top, right } = listUI(c)
  return `scale(${scale}) translateY(${cssLength(top)}) translateX(${cssLength(right)})`
}

const HIGHLIGHT_MS = 300
const FINALIZE_MS = 300
const cardHover = new WeakMap()

function cardEnter(el) {
  const prev = cardHover.get(el)
  if (prev?.timer) clearTimeout(prev.timer)
  const enterAt = el.dataset.hover && prev ? prev.enterAt : performance.now()
  cardHover.set(el, { enterAt, timer: null })
  el.dataset.hover = '1'
}

function cardLeave(el) {
  const prev = cardHover.get(el)
  const left = prev ? HIGHLIGHT_MS - (performance.now() - prev.enterAt) : 0
  const drop = () => {
    delete el.dataset.hover
    cardHover.delete(el)
  }
  if (left > 0) cardHover.set(el, { enterAt: prev.enterAt, timer: setTimeout(drop, left) })
  else drop()
}

function CardPlate() {
  return (
    <svg className="character-card-plate" viewBox="0 0 414 95" fill="none" xmlns="http://www.w3.org/2000/svg">
      <g filter="url(#character-card-plate-shadow)">
        <path d="M0 5C0 2.23857 2.23858 0 5 0H414L319 95H5C2.23858 95 0 92.7614 0 90V5Z" fill="white" fillOpacity="0.01"/>
      </g>
    </svg>
  )
}
function CardFacet() {
  return (
    <svg className="character-card-facet" viewBox="0 0 245 95" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M95 0H240C242.761 0 245 2.23858 245 5L245 89.9977C245 92.7591 242.761 94.9977 240 94.9977L0 95L95 0Z"/>
    </svg>
  )
}
function CardShade() {
  return (
    <svg className="character-card-shade" viewBox="0 0 564 95" fill="none" xmlns="http://www.w3.org/2000/svg">
      <g filter="url(#character-card-shade-shadow)">
        <path d="M532.667 0C535.139 0.000164952 537.144 2.00453 537.144 4.47656V25C537.144 27.7614 539.382 30 542.144 30H559.524C561.983 30.0004 563.979 31.9836 564 34.4375V75H473C470.239 75 468 77.2386 468 80V95H5C2.23858 95 2.01336e-08 92.7614 0 90V5C0 2.23858 2.23858 5.63724e-08 5 0H532.667Z" fill="#F4F4F4" fillOpacity="0.01"/>
      </g>
    </svg>
  )
}
function PanelShape({ className = '', onClick }) {
  const patternId = 'cs-panel-' + useId().replace(/[^\w-]/g, '')
  return (
    <div className={`character-select-background-shape${className ? ' ' + className : ''}`} onClick={onClick}>
      <svg className="character-select-shape-top" viewBox="0 0 650 40" preserveAspectRatio="none" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M0.5 40V20C0.5 9.23045 9.23045 0.5 20 0.5H630C640.77 0.5 649.5 9.23045 649.5 20V40" vectorEffect="non-scaling-stroke" />
      </svg>
      <svg className="character-select-shape-middle" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <pattern id={patternId} width="100%" height="10" patternUnits="userSpaceOnUse">
            <rect className="character-select-shape-fill" width="100%" height="10" />
            <line className="character-select-shape-edge" x1="0.5" y1="0" x2="0.5" y2="10" />
            <line className="character-select-shape-edge" x1="100%" y1="0" x2="100%" y2="10" transform="translate(-0.5 0)" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill={`url(#${patternId})`} />
      </svg>
      <svg className="character-select-shape-bottom" viewBox="0 640 650 260" preserveAspectRatio="none" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M649.5 640V679C649.5 684.247 645.247 688.5 640 688.5H617C611.201 688.5 606.5 693.201 606.5 699V880C606.5 890.77 597.77 899.5 587 899.5H20C9.23045 899.5 0.5 890.77 0.5 880V640" vectorEffect="non-scaling-stroke" />
      </svg>
    </div>
  )
}

function CardCaps() {
  return (
    <svg className="character-card-caps" viewBox="0 0 96 95" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M90.9998 0C93.7612 0 95.9998 2.23858 95.9998 5L96.0007 30V34.4766C96.0007 32.0046 93.9961 30.0002 91.5242 30H74.1433C71.3819 30 69.1433 27.7614 69.1433 25V4.47656C69.1433 2.00443 67.1389 0 64.6667 0H90.9998Z"/>
      <path d="M0 80C0 77.2386 2.23858 75 5 75H96V90C96 92.7614 93.7614 95 91 95H0V80Z"/>
    </svg>
  )
}

function roleOf(c) {
  return c.gender === 'male' ? 'дворецкий' : 'горничная'
}
function ruPlural(n, one, few, many) {
  const m10 = n % 10, m100 = n % 100
  if (m10 === 1 && m100 !== 11) return one
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few
  return many
}
function togetherText(c) {
  if (!c.first_meeting_at) return 'не знакомы'
  const days = Math.floor((Date.now() / 1000 - c.first_meeting_at) / 86400)
  if (days < 1) return 'первый день'
  return `${days} ${ruPlural(days, 'день', 'дня', 'дней')}`
}
function accessText(c) {
  if (!c.is_protected) return 'без пароля'
  return c.is_unlocked ? 'пароль введён' : 'под паролем'
}

const LIST_SLOTS = 6

export default function CharacterSelect({
  characters = [],
  onSelect,
  onRefresh,
  selectionLock = false,
  onSelectionLock,
  bare = false,
}) {
  useCharacterUiVersion()
  useEffect(() => { ensureCharacterUi(characters) }, [characters])
  const [darkThemeOn] = useSetting('appearance.dark_theme')
  const cardInk = (c) => (darkThemeOn ? listDark(c)?.ink : listBase(c))
  const cardChip = (c) => (darkThemeOn && listDark(c)?.chip) || listChip(c)

  const [chipSecret, setChipSecret] = useState('')
  const [chipSecretErr, setChipSecretErr] = useState('')
  useEffect(() => { setChipSecret(''); setChipSecretErr('') }, [selectionLock])

  const [dropOver, setDropOver] = useState(false)
  const [note, setNote] = useState('')
  const [noteOk, setNoteOk] = useState(false)
  const [busy, setBusy] = useState(false)
  const [selectedId, setSelectedId] = useState(null)
  const selectedCharacter = characters.find((x) => x.id === selectedId) || null
  const passwordVars = useMemo(() => {
    if (!selectedCharacter) return undefined
    const theme = darkThemeOn ? darkCharacterStructure(selectedCharacter) : listStructure(selectedCharacter)
    return themeTokenVars(theme, 'CharacterSelect.Lockscreen.Password', { dark: !!darkThemeOn })
  }, [selectedCharacter, darkThemeOn])
  const [finalizing, setFinalizing] = useState(false)
  const finalizeTimer = useRef(null)
  const [frozenRows, setFrozenRows] = useState(null)
  const rows = frozenRows || characters.filter((c) => !c.active)
  const activeCharacter = characters.find((c) => c.active) || null

  useEffect(() => () => clearTimeout(finalizeTimer.current), [])

  function selected(c) {
    setSelectedId(c.id)
  }

  function lockSelection(e) {
    e.stopPropagation()
    onSelectionLock?.(true)
  }

  function unlockSelection() {
    onSelectionLock?.(false)
  }

  function finalizePick() {
    if (!selectedCharacter || finalizing) return
    const needSecret = selectedCharacter.is_protected && !selectedCharacter.is_unlocked
    if (needSecret && !chipSecret.trim()) {
      setChipSecretErr('Введите пароль')
      return
    }
    const c = selectedCharacter
    setFrozenRows(rows)
    setFinalizing(true)
    finalizeTimer.current = setTimeout(async () => {
      const res = await onSelect?.(
        c.id,
        (c.is_protected && !c.is_unlocked) ? chipSecret.trim() : undefined,
        listStructure(c))
      if (res && res !== 'ok') {
        setFinalizing(false)
        setFrozenRows(null)
        setNoteOk(false)
        setNote(res === 'locked' ? 'Персонаж защищён паролем'
              : res === 'wrong' ? 'Пароль не подошёл'
              : 'Не удалось переключиться')
        if (res === 'wrong' || res === 'locked') setChipSecretErr('Пароль не подошёл')
      }
    }, FINALIZE_MS)
  }

  async function importPath(p) {
    if (!p || busy) return
    setBusy(true); setNote(''); setNoteOk(false)
    let r
    try {
      r = await api.importCharacter(p)
    } catch {
      setBusy(false); setNote('не удалось связаться с бэкендом'); return
    }
    setBusy(false)
    if (!r.ok) { setNote(r.error || 'не удалось импортировать'); return }
    setNoteOk(true); setNote(`Добавлен(а): ${r.name || r.id}`)
    onRefresh?.()
  }

  async function openFolder() {
    let r = null
    try { r = await api.openCharactersFolder() } catch {}
    if (!r?.ok) { setNoteOk(false); setNote(r?.error || 'не удалось открыть папку') }
  }

  function onDrop(e) {
    e.preventDefault(); setDropOver(false)
    const f = e.dataTransfer?.files?.[0]
    if (!f) return
    const n = f.name.toLowerCase()
    if (!n.endsWith('.maid') && !n.endsWith('.butler')) {
      setNoteOk(false); setNote('Нужен файл .maid или .butler'); return
    }
    const p = window.maidlink?.getPathForFile?.(f)
    if (p) importPath(p)
    else { setNoteOk(false); setNote('Перетаскивание доступно в приложении') }
  }

  return (
    <div
      className={`character-select${bare ? ' is-bare' : ''}`}
      onDragOver={(e) => { e.preventDefault(); setDropOver(true) }}
      onDragLeave={() => setDropOver(false)}
      onDrop={onDrop}
    >
      <div className="character-select-drag-region" />
      <svg
        className="character-select-notch-shadow"
        viewBox="0 0 114 261"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <g filter="url(#filter0_d_1537_355)">
          <path
            d="M4.80005 5.79688L101.8 33.7969C103.47 37.6145 100.736 41.9068 96.5705 42.0072L63.8 42.7969V129.797V230.737C63.8 242.908 53.0203 252.257 40.9716 250.536L35.8 249.797L4.80005 5.79688Z"
            fill="#D9D9D9"
            fillOpacity="0.01"
            shapeRendering="crispEdges"
          />
        </g>
        <defs>
          <filter
            id="filter0_d_1537_355"
            x="4.86374e-05"
            y="-0.00312519"
            width="113.098"
            height="260.545"
            filterUnits="userSpaceOnUse"
            colorInterpolationFilters="sRGB"
          >
            <feFlood floodOpacity="0" result="BackgroundImageFix"/>
            <feColorMatrix in="SourceAlpha" type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 127 0" result="hardAlpha"/>
            <feOffset dx="3" dy="2"/>
            <feGaussianBlur stdDeviation="3.9"/>
            <feComposite in2="hardAlpha" operator="out"/>
            <feColorMatrix type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.31 0"/>
            <feBlend mode="normal" in2="BackgroundImageFix" result="effect1_dropShadow_1537_355"/>
            <feBlend mode="normal" in="SourceGraphic" in2="effect1_dropShadow_1537_355" result="shape"/>
          </filter>
        </defs>
      </svg>

      <div className="character-select-background">
        <PanelShape />
        <div className="character-select-pattern" aria-hidden="true" />
      </div>
      <div className="character-select-frame">
        <WindowControls neutral={selectionLock} />

        <div className="character-select-header">
          {activeCharacter && <div className="character-select-header-decor" aria-hidden="true" />}
          {activeCharacter && (
            <img
              className="character-select-header-avatar"
              src={listAvatar(activeCharacter)}
              onError={(e) => { e.currentTarget.src = listAvatarFallback(activeCharacter) }}
              alt=""
              style={{ transform: listAvatarTransform(activeCharacter) }}
            />
          )}
          <div className={`character-select-header-name${activeCharacter ? '' : ' is-empty'}`}>
            {activeCharacter ? activeCharacter.name.toUpperCase()
              : characters.length ? 'ВЫБЕРИТЕ ПЕРСОНАЖА' : 'НЕТ ДОБАВЛЕННЫХ ПЕРСОНАЖЕЙ'}
          </div>
          {activeCharacter && (
            <div className="character-select-header-tagline">
              {[activeCharacter.subtitle, roleOf(activeCharacter)].filter(Boolean).join(' ')}
            </div>
          )}
          {activeCharacter && (
            <dl className="character-select-header-info">
              <div className="character-select-header-info-row">
                <dt>ID</dt>
                <dd>{activeCharacter.instance_id || activeCharacter.baseline_id || activeCharacter.id}</dd>
              </div>
              <div className="character-select-header-info-row">
                <dt>ВМЕСТЕ</dt>
                <dd>{togetherText(activeCharacter)}</dd>
              </div>
              <div className="character-select-header-info-row">
                <dt>ДОСТУП</dt>
                <dd>{accessText(activeCharacter)}</dd>
              </div>
              {activeCharacter.training?.label && (
                <div className="character-select-header-info-row">
                  <dt>ЗНАНИЯ</dt>
                  <dd>{activeCharacter.training.label}</dd>
                </div>
              )}
            </dl>
          )}
        </div>

        <div className="character-select-list">
          <svg className="character-card-defs" aria-hidden="true" focusable="false">
            <defs>
              <filter id="character-card-plate-shadow" x="-4" y="0" width="418" height="95" filterUnits="userSpaceOnUse" colorInterpolationFilters="sRGB">
                <feFlood floodOpacity="0" result="BackgroundImageFix"/>
                <feBlend mode="normal" in="SourceGraphic" in2="BackgroundImageFix" result="shape"/>
                <feColorMatrix in="SourceAlpha" type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 127 0" result="hardAlpha"/>
                <feOffset dx="-4"/>
                <feGaussianBlur stdDeviation="2"/>
                <feComposite in2="hardAlpha" operator="arithmetic" k2="-1" k3="1"/>
                <feColorMatrix type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.1 0"/>
                <feBlend mode="normal" in2="shape" result="effect1_innerShadow"/>
              </filter>
              <filter id="character-card-shade-shadow" x="0" y="0" width="564" height="97" filterUnits="userSpaceOnUse" colorInterpolationFilters="sRGB">
                <feFlood floodOpacity="0" result="BackgroundImageFix"/>
                <feBlend mode="normal" in="SourceGraphic" in2="BackgroundImageFix" result="shape"/>
                <feColorMatrix in="SourceAlpha" type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 127 0" result="hardAlpha"/>
                <feOffset dy="2"/>
                <feGaussianBlur stdDeviation="3.5"/>
                <feComposite in2="hardAlpha" operator="arithmetic" k2="-1" k3="1"/>
                <feColorMatrix type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.25 0"/>
                <feBlend mode="normal" in2="shape" result="effect1_innerShadow"/>
              </filter>
            </defs>
          </svg>

          {rows.map((c) => (
            <div
              key={c.id}
              className={`character-card${c.id === selectedId ? ' is-selected' : ''}`}
              onClick={() => selected(c)}
              onMouseEnter={(e) => cardEnter(e.currentTarget)}
              onMouseLeave={(e) => cardLeave(e.currentTarget)}
              
            >
              <div className="character-card-hover-highlight">

              </div>
              <div
                className="character-card-select-hightlight"
                style={{ background: listBase(c) }}
              >
              </div>
              <CardPlate />

              

              

              <div className="character-card-content">
                <img
                  className="character-card-avatar"
                  src={listAvatar(c)}
                  onError={(e) => { e.currentTarget.src = listAvatarFallback(c) }}
                  alt=""
                  style={{ transform: listAvatarTransform(c) }}
                />
                <div className="character-card-body">
                  <span
                    className="character-card-name"
                    style={{ '--card-name': cardInk(c) }}
                  >
                    {c.name}
                  </span>
                  <span className="character-card-desc">
                    {c.subtitle && (
                      <span className="character-card-tagline">{c.subtitle}</span>
                    )}
                    <span className="character-card-role">
                      {c.gender === 'male' ? 'дворецкий' : 'горничная'}
                    </span>
                  </span>
                </div>
              </div>

              <CardFacet />

              <div className="character-card-chip-container">
                <div className="character-info-version">
                    {c.version}
                </div>
                <div
                  className="character-card-chip"
                  dangerouslySetInnerHTML={{ __html: cardChip(c) }}
                />
                <div className="character-card-select-charater-button" onClick={lockSelection}>
                  <svg width="142" height="9" viewBox="0 0 142 9" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <g filter="url(#filter0_i_1499_34)">
                    <path d="M-2.22027e-05 8.84375V0.116477H3.4943C4.13634 0.116477 4.67185 0.211648 5.10083 0.401989C5.52981 0.59233 5.85225 0.856534 6.06816 1.1946C6.28407 1.52983 6.39202 1.91619 6.39202 2.35369C6.39202 2.6946 6.32384 2.99432 6.18748 3.25284C6.05111 3.50852 5.86361 3.71875 5.62498 3.88352C5.38918 4.04545 5.1193 4.16051 4.81532 4.22869V4.31392C5.14771 4.32812 5.45878 4.42187 5.74856 4.59517C6.04117 4.76847 6.27839 5.01136 6.46021 5.32386C6.64202 5.63352 6.73293 6.00284 6.73293 6.43182C6.73293 6.89489 6.61788 7.30824 6.38776 7.67188C6.16049 8.03267 5.82384 8.31818 5.37782 8.52841C4.9318 8.73864 4.38208 8.84375 3.72867 8.84375H-2.22027e-05ZM1.84515 7.33523H3.34941C3.86361 7.33523 4.23861 7.23722 4.47441 7.04119C4.71021 6.84233 4.8281 6.57812 4.8281 6.24858C4.8281 6.0071 4.76986 5.79403 4.65339 5.60938C4.53691 5.42472 4.37072 5.27983 4.15481 5.17472C3.94174 5.0696 3.68748 5.01705 3.39202 5.01705H1.84515V7.33523ZM1.84515 3.76847H3.21305C3.46589 3.76847 3.69032 3.72443 3.88634 3.63636C4.08521 3.54545 4.24146 3.41761 4.35509 3.25284C4.47157 3.08807 4.52981 2.89062 4.52981 2.66051C4.52981 2.34517 4.41759 2.09091 4.19316 1.89773C3.97157 1.70455 3.65623 1.60795 3.24714 1.60795H1.84515V3.76847ZM9.14806 3.34233H11.2276C11.9208 3.34233 12.5174 3.45455 13.0174 3.67898C13.5202 3.90057 13.908 4.21449 14.1807 4.62074C14.4535 5.02699 14.5884 5.50568 14.5856 6.05682C14.5884 6.60511 14.4535 7.08949 14.1807 7.50994C13.908 7.92756 13.5202 8.25426 13.0174 8.49006C12.5174 8.72585 11.9208 8.84375 11.2276 8.84375H7.96766V0.116477H9.80857V7.3608H11.2276C11.56 7.3608 11.8398 7.30114 12.0671 7.18182C12.2944 7.05966 12.4662 6.89915 12.5827 6.70028C12.702 6.49858 12.7603 6.27841 12.7574 6.03977C12.7603 5.69318 12.6296 5.40057 12.3654 5.16193C12.104 4.92045 11.7248 4.79972 11.2276 4.79972H9.14806V3.34233ZM17.1381 0.116477V8.84375H15.2972V0.116477H17.1381ZM18.6562 8.84375V0.116477H24.4474V1.63778H20.5014V3.34233H21.9204C22.6108 3.34233 23.2059 3.45455 23.7059 3.67898C24.2088 3.90057 24.5966 4.21449 24.8693 4.62074C25.142 5.02699 25.2784 5.50568 25.2784 6.05682C25.2784 6.60511 25.142 7.08949 24.8693 7.50994C24.5966 7.92756 24.2088 8.25426 23.7059 8.49006C23.2059 8.72585 22.6108 8.84375 21.9204 8.84375H18.6562ZM20.5014 7.3608H21.9204C22.25 7.3608 22.5284 7.30114 22.7557 7.18182C22.9829 7.05966 23.1548 6.89915 23.2713 6.70028C23.3906 6.49858 23.4503 6.27841 23.4503 6.03977C23.4503 5.69318 23.3182 5.40057 23.054 5.16193C22.7926 4.92045 22.4148 4.79972 21.9204 4.79972H20.5014V7.3608ZM26.4726 8.84375V0.116477H29.9158C30.5777 0.116477 31.1417 0.242898 31.6076 0.495739C32.0735 0.745739 32.4286 1.09375 32.6729 1.53977C32.9201 1.98295 33.0437 2.49432 33.0437 3.07386C33.0437 3.65341 32.9187 4.16477 32.6687 4.60795C32.4187 5.05114 32.0564 5.39631 31.582 5.64347C31.1104 5.89062 30.5394 6.0142 29.8689 6.0142H27.6743V4.53551H29.5706C29.9258 4.53551 30.2184 4.47443 30.4485 4.35227C30.6814 4.22727 30.8547 4.0554 30.9684 3.83665C31.0849 3.61506 31.1431 3.3608 31.1431 3.07386C31.1431 2.78409 31.0849 2.53125 30.9684 2.31534C30.8547 2.09659 30.6814 1.92756 30.4485 1.80824C30.2155 1.68608 29.9201 1.625 29.5621 1.625H28.3178V8.84375H26.4726ZM34.7386 8.84375H32.7613L35.7741 0.116477H38.152L41.1605 8.84375H39.1832L36.9971 2.1108H36.929L34.7386 8.84375ZM34.615 5.41335H39.2855V6.85369H34.615V5.41335ZM40.8121 1.63778V0.116477H47.9797V1.63778H45.3079V8.84375H43.484V1.63778H40.8121ZM50.3746 3.34233H52.4542C53.1474 3.34233 53.7439 3.45455 54.2439 3.67898C54.7468 3.90057 55.1346 4.21449 55.4073 4.62074C55.68 5.02699 55.815 5.50568 55.8121 6.05682C55.815 6.60511 55.68 7.08949 55.4073 7.50994C55.1346 7.92756 54.7468 8.25426 54.2439 8.49006C53.7439 8.72585 53.1474 8.84375 52.4542 8.84375H49.1942V0.116477H51.0351V7.3608H52.4542C52.7866 7.3608 53.0664 7.30114 53.2937 7.18182C53.5209 7.05966 53.6928 6.89915 53.8093 6.70028C53.9286 6.49858 53.9868 6.27841 53.984 6.03977C53.9868 5.69318 53.8562 5.40057 53.592 5.16193C53.3306 4.92045 52.9513 4.79972 52.4542 4.79972H50.3746V3.34233ZM67.4776 0.116477V8.84375H65.6537V1.61648H62.1253V8.84375H60.3015V0.116477H67.4776ZM69.2344 8.84375V0.116477H75.115V1.63778H71.0795V3.71733H74.8125V5.23864H71.0795V7.32244H75.1321V8.84375H69.2344ZM76.582 8.84375V0.116477H80.0252C80.6871 0.116477 81.251 0.242898 81.717 0.495739C82.1829 0.745739 82.538 1.09375 82.7823 1.53977C83.0295 1.98295 83.153 2.49432 83.153 3.07386C83.153 3.65341 83.028 4.16477 82.778 4.60795C82.528 5.05114 82.1658 5.39631 81.6914 5.64347C81.2198 5.89062 80.6488 6.0142 79.9783 6.0142H77.7837V4.53551H79.68C80.0351 4.53551 80.3277 4.47443 80.5579 4.35227C80.7908 4.22727 80.9641 4.0554 81.0777 3.83665C81.1942 3.61506 81.2525 3.3608 81.2525 3.07386C81.2525 2.78409 81.1942 2.53125 81.0777 2.31534C80.9641 2.09659 80.7908 1.92756 80.5579 1.80824C80.3249 1.68608 80.0295 1.625 79.6715 1.625H78.4272V8.84375H76.582ZM92.0518 3.17188H90.1853C90.1513 2.9304 90.0817 2.71591 89.9765 2.52841C89.8714 2.33807 89.7365 2.17614 89.5717 2.04261C89.4069 1.90909 89.2166 1.80682 89.0007 1.7358C88.7876 1.66477 88.5561 1.62926 88.3061 1.62926C87.8544 1.62926 87.4609 1.74148 87.1257 1.96591C86.7905 2.1875 86.5305 2.51136 86.3459 2.9375C86.1612 3.3608 86.0689 3.875 86.0689 4.48011C86.0689 5.10227 86.1612 5.625 86.3459 6.0483C86.5334 6.47159 86.7947 6.79119 87.1299 7.0071C87.4652 7.22301 87.853 7.33097 88.2933 7.33097C88.5405 7.33097 88.7692 7.2983 88.9794 7.23295C89.1924 7.16761 89.3814 7.07244 89.5461 6.94744C89.7109 6.8196 89.8473 6.66477 89.9552 6.48295C90.066 6.30114 90.1427 6.09375 90.1853 5.8608L92.0518 5.86932C92.0035 6.26989 91.8828 6.65625 91.6896 7.02841C91.4993 7.39773 91.2422 7.72869 90.9183 8.02131C90.5973 8.31108 90.2138 8.54119 89.7677 8.71165C89.3246 8.87926 88.8231 8.96307 88.2635 8.96307C87.4851 8.96307 86.789 8.78693 86.1754 8.43466C85.5646 8.08239 85.0817 7.57244 84.7265 6.90483C84.3743 6.23722 84.1981 5.42898 84.1981 4.48011C84.1981 3.52841 84.3771 2.71875 84.7351 2.05114C85.093 1.38352 85.5788 0.875 86.1924 0.525568C86.8061 0.173295 87.4964 -0.00284123 88.2635 -0.00284123C88.7692 -0.00284123 89.2379 0.0681815 89.6697 0.210227C90.1044 0.352273 90.4893 0.559659 90.8246 0.832386C91.1598 1.10227 91.4325 1.43324 91.6427 1.82528C91.8558 2.21733 91.9922 2.66619 92.0518 3.17188ZM101.395 4.48011C101.395 5.43182 101.214 6.24148 100.854 6.90909C100.496 7.5767 100.007 8.08665 99.3878 8.43892C98.7713 8.78835 98.0781 8.96307 97.3082 8.96307C96.5326 8.96307 95.8366 8.78693 95.2201 8.43466C94.6037 8.08239 94.1165 7.57244 93.7585 6.90483C93.4005 6.23722 93.2216 5.42898 93.2216 4.48011C93.2216 3.52841 93.4005 2.71875 93.7585 2.05114C94.1165 1.38352 94.6037 0.875 95.2201 0.525568C95.8366 0.173295 96.5326 -0.00284123 97.3082 -0.00284123C98.0781 -0.00284123 98.7713 0.173295 99.3878 0.525568C100.007 0.875 100.496 1.38352 100.854 2.05114C101.214 2.71875 101.395 3.52841 101.395 4.48011ZM99.5241 4.48011C99.5241 3.86364 99.4318 3.34375 99.2471 2.92045C99.0653 2.49716 98.8082 2.17614 98.4758 1.95739C98.1434 1.73864 97.7542 1.62926 97.3082 1.62926C96.8622 1.62926 96.473 1.73864 96.1406 1.95739C95.8082 2.17614 95.5497 2.49716 95.365 2.92045C95.1832 3.34375 95.0923 3.86364 95.0923 4.48011C95.0923 5.09659 95.1832 5.61648 95.365 6.03977C95.5497 6.46307 95.8082 6.78409 96.1406 7.00284C96.473 7.22159 96.8622 7.33097 97.3082 7.33097C97.7542 7.33097 98.1434 7.22159 98.4758 7.00284C98.8082 6.78409 99.0653 6.46307 99.2471 6.03977C99.4318 5.61648 99.5241 5.09659 99.5241 4.48011ZM102.762 8.84375V0.116477H104.607V3.71733H108.353V0.116477H110.194V8.84375H108.353V5.23864H104.607V8.84375H102.762ZM113.219 8.84375H111.242L114.255 0.116477H116.632L119.641 8.84375H117.664L115.478 2.1108H115.409L113.219 8.84375ZM113.096 5.41335H117.766V6.85369H113.096V5.41335ZM127.339 0.116477V8.84375H125.549V0.116477H127.339ZM120.278 8.84375L123.014 4.24148L120.393 0.116477H122.664L124.625 3.70881H128.311L130.22 0.116477H132.483L129.926 4.22869L132.61 8.84375H130.407L128.562 5.41335H124.356L122.464 8.84375H120.278ZM135.215 8.84375H133.238L136.251 0.116477H138.629L141.637 8.84375H139.66L137.474 2.1108H137.406L135.215 8.84375ZM135.092 5.41335H139.762V6.85369H135.092V5.41335Z"/>
                    </g>
                    <defs>
                    <filter id="filter0_i_1499_34" x="0" y="0" width="141.637" height="9.96094" filterUnits="userSpaceOnUse" colorInterpolationFilters="sRGB">
                    <feFlood floodOpacity="0" result="BackgroundImageFix"/>
                    <feBlend mode="normal" in="SourceGraphic" in2="BackgroundImageFix" result="shape"/>
                    <feColorMatrix in="SourceAlpha" type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 127 0" result="hardAlpha"/>
                    <feOffset dy="1"/>
                    <feGaussianBlur stdDeviation="1.05"/>
                    <feComposite in2="hardAlpha" operator="arithmetic" k2="-1" k3="1"/>
                    <feColorMatrix type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.14 0"/>
                    <feBlend mode="normal" in2="shape" result="effect1_innerShadow_1499_34"/>
                    </filter>
                    </defs>
                  </svg>

                </div>
              </div>
              <CardShade />

              <CardCaps />
              <div className="character-info-id" style={{ color: cardInk(c) }}>
                  {c.instance_id || c.baseline_id || c.id}
              </div>
              <div className="character-info-lock-status">
                {!c.is_protected ? (
                <svg width="18" height="18" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <g filter="url(#filter0_i_1754_1762)">
                  <path fillRule="evenodd" clipRule="evenodd" d="M12 0C13.0609 0 14.0783 0.421427 14.8284 1.17157C15.5786 1.92172 16 2.93913 16 4V6.5H15V4C15 3.20435 14.6839 2.44129 14.1213 1.87868C13.5587 1.31607 12.7956 1 12 1C11.2044 1 10.4413 1.31607 9.87868 1.87868C9.31607 2.44129 9 3.20435 9 4V6H9.5C9.8283 6 10.1534 6.06466 10.4567 6.1903C10.76 6.31594 11.0356 6.50009 11.2678 6.73223C11.4999 6.96438 11.6841 7.23998 11.8097 7.54329C11.9353 7.84661 12 8.1717 12 8.5V13.5C12 13.8283 11.9353 14.1534 11.8097 14.4567C11.6841 14.76 11.4999 15.0356 11.2678 15.2678C11.0356 15.4999 10.76 15.6841 10.4567 15.8097C10.1534 15.9353 9.8283 16 9.5 16H2.5C1.83696 16 1.20107 15.7366 0.732233 15.2678C0.263392 14.7989 0 14.163 0 13.5L0 8.5C0 7.83696 0.263392 7.20107 0.732233 6.73223C1.20107 6.26339 1.83696 6 2.5 6H8V4C8 2.93913 8.42143 1.92172 9.17157 1.17157C9.92172 0.421427 10.9391 0 12 0Z"/>
                  </g>
                  <defs>
                  <filter id="filter0_i_1754_1762" x="0" y="0" width="16" height="18" filterUnits="userSpaceOnUse" colorInterpolationFilters="sRGB">
                  <feFlood floodOpacity="0" result="BackgroundImageFix"/>
                  <feBlend mode="normal" in="SourceGraphic" in2="BackgroundImageFix" result="shape"/>
                  <feColorMatrix in="SourceAlpha" type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 127 0" result="hardAlpha"/>
                  <feOffset dy="2"/>
                  <feGaussianBlur stdDeviation="2"/>
                  <feComposite in2="hardAlpha" operator="arithmetic" k2="-1" k3="1"/>
                  <feColorMatrix type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.2 0"/>
                  <feBlend mode="normal" in2="shape" result="effect1_innerShadow_1754_1762"/>
                  </filter>
                  </defs>
                </svg>
                ) : (
                  <svg width="18" height="18" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <g filter="url(#filter0_i_1754_1763)">
                  <path fillRule="evenodd" clipRule="evenodd" d="M6 0C7.06087 0 8.07828 0.421427 8.82843 1.17157C9.57857 1.92172 10 2.93913 10 4V6.05C10.5647 6.16527 11.0722 6.47209 11.4367 6.91855C11.8011 7.36501 12.0001 7.92367 12 8.5V13.5C12 14.163 11.7366 14.7989 11.2678 15.2678C10.7989 15.7366 10.163 16 9.5 16H2.5C1.83696 16 1.20107 15.7366 0.732233 15.2678C0.263392 14.7989 5.21142e-08 14.163 5.21142e-08 13.5V8.5C-0.000117575 7.92367 0.198892 7.36501 0.563347 6.91855C0.927802 6.47209 1.43532 6.16527 2 6.05V4C2 2.93913 2.42143 1.92172 3.17157 1.17157C3.92172 0.421427 4.93913 0 6 0ZM6 1C5.20435 1 4.44129 1.31607 3.87868 1.87868C3.31607 2.44129 3 3.20435 3 4V6H9V4C9 3.20435 8.68393 2.44129 8.12132 1.87868C7.55871 1.31607 6.79565 1 6 1Z"/>
                  </g>
                  <defs>
                  <filter id="filter0_i_1754_1763" x="0" y="0" width="12" height="18" filterUnits="userSpaceOnUse" colorInterpolationFilters="sRGB">
                  <feFlood floodOpacity="0" result="BackgroundImageFix"/>
                  <feBlend mode="normal" in="SourceGraphic" in2="BackgroundImageFix" result="shape"/>
                  <feColorMatrix in="SourceAlpha" type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 127 0" result="hardAlpha"/>
                  <feOffset dy="2"/>
                  <feGaussianBlur stdDeviation="2"/>
                  <feComposite in2="hardAlpha" operator="arithmetic" k2="-1" k3="1"/>
                  <feColorMatrix type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.2 0"/>
                  <feBlend mode="normal" in2="shape" result="effect1_innerShadow_1754_1763"/>
                  </filter>
                  </defs>
                </svg>
                
                )}
              </div>
            </div>
          ))}

          {Array.from({ length: Math.max(0, LIST_SLOTS - rows.length) }, (_, i) => (
            <div key={`empty-slot-${i}`} className="character-card is-placeholder">
              <CardPlate />
              <div className="character-card-content">
                <div className="character-card-placeholder-avatar" aria-hidden="true">?</div>
                <div className="character-card-body">
                  <span className="character-card-name">пустой слот</span>
                </div>
              </div>
              <CardFacet />
              <CardShade />
              <CardCaps />
              <div className="character-info-id">SLOT {String(rows.length + i + 1).padStart(2, '0')}</div>
            </div>
          ))}
        </div>

        <div className={`character-select-drop${dropOver ? ' character-select-drop--over' : ''}`}>
          <div className="character-select-drop-blobs" aria-hidden="true">
            <span className="character-select-drop-blob is-1" />
            <span className="character-select-drop-blob is-2" />
            <span className="character-select-drop-blob is-3" />
            <span className="character-select-drop-blob is-4" />
            <span className="character-select-drop-blob is-5" />
            <span className="character-select-drop-blob is-6" />
          </div>
          <svg className="character-select-drop-frame" aria-hidden="true">
            <rect />
          </svg>
          <div className="character-select-drop-hint">
            <svg className="character-select-drop-icon" viewBox="0 0 32 32" fill="none" aria-hidden="true">
              <rect x="9" y="3" width="14" height="18" rx="2.5" />
              <path d="M16 8.5v7M13 12.5l3 3 3-3" />
              <path d="M5 21.5v4a3 3 0 0 0 3 3h16a3 3 0 0 0 3-3v-4" />
            </svg>
            <span className="character-select-drop-text">
              {busy ? (
                <span className="character-select-drop-title">adding…</span>
              ) : (
                <>
                  <span className="character-select-drop-title">drop .maid .butler</span>
                  <span className="character-select-drop-sub">files here to add a character</span>
                </>
              )}
            </span>
          </div>
          <button
            type="button"
            className="character-select-drop-folder"
            style={{ '--folder-color': cardInk(activeCharacter) }}
            onClick={openFolder}
          >
            <span className="character-select-drop-folder-label">открыть папку</span>
          </button>
        </div>
        {note && (
          <div className={`character-select-note${noteOk ? ' character-select-note--ok' : ''}`}>
            {note}
          </div>
        )}
      </div>
      <div className={`character-select-locksreen-chip-visuals${selectionLock ? ' is-locked' : ''}`}>
        <PanelShape className="svg-locksreen-chip-visuals" onClick={unlockSelection} />
        <div
         className={`character-selected-chip${finalizing ? ' is-leaving' : ''}`}
         onClick={finalizePick}
         dangerouslySetInnerHTML={{ __html: cardChip(selectedCharacter) }}
        />
        {selectionLock && !finalizing && selectedCharacter?.is_protected
          && !selectedCharacter?.is_unlocked && (
          <div className="character-chip-password" style={passwordVars} onClick={(e) => e.stopPropagation()}>
            <div className="character-chip-password-title">персонаж под паролем</div>
            <input
              className="character-chip-password-input"
              type="password"
              placeholder="пароль"
              value={chipSecret}
              autoFocus
              onChange={(e) => { setChipSecret(e.target.value); setChipSecretErr('') }}
              onKeyDown={(e) => { if (e.key === 'Enter') finalizePick() }}
            />
            {chipSecretErr && (
              <div className="character-chip-password-error">{chipSecretErr}</div>
            )}
          </div>
        )}


        
      </div>
      
    </div>
  )
}
