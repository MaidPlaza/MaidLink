import { useSyncExternalStore } from 'react'
import defaultStructure from '@/electron/configs/UIStructure.json'
import darkDefaultStructure from '@/electron/configs/UIStructure_dark.json'
import { getCharacterUi } from '@/lib/characterUi'
import { composeTheme } from '@/lib/themeDerive'

const FLAT_TOKEN = /^[A-Z0-9_]+$/
const isBlock = (v) => v !== null && typeof v === 'object' && !Array.isArray(v)
const IS_MARKUP = /^\s*</
const HAS_WS = /\s/

const cssVarOf = (key) => '--' + key
  .split('.')
  .map((seg) => seg
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .replace(/_/g, '-')
    .toLowerCase())
  .join('-')

export function tokenEntries(structure) {
  const out = []
  for (const [key, value] of Object.entries(structure)) {
    if (isBlock(value)) {
      for (const [path, v] of Object.entries(value)) {
        if (typeof v === 'string' && !IS_MARKUP.test(v) && !HAS_WS.test(path)) out.push([cssVarOf(path), v])
      }
    } else if (typeof value === 'string' && FLAT_TOKEN.test(key)) {
      out.push([cssVarOf(key), value])
    }
  }
  return out
}

let current = defaultStructure
const listeners = new Set()

export function getUIStructure() {
  return current
}

export function subscribeUIStructure(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

export function useUIStructure() {
  return useSyncExternalStore(subscribeUIStructure, getUIStructure)
}

const THEME_STYLE_ID = 'character-theme'
let themeStyleEl = null
const ALL_THEME_VARS = tokenEntries(defaultStructure).map(([cssVar]) => cssVar)

function writeThemeSheet(decls) {
  const rootStyle = document.documentElement.style
  if (rootStyle.length) for (const cssVar of ALL_THEME_VARS) rootStyle.removeProperty(cssVar)

  if (!themeStyleEl || !themeStyleEl.isConnected) {
    themeStyleEl = document.getElementById(THEME_STYLE_ID)
    if (!themeStyleEl) {
      themeStyleEl = document.createElement('style')
      themeStyleEl.id = THEME_STYLE_ID
    }
  }
  if (themeStyleEl.parentNode !== document.head || themeStyleEl.nextSibling) {
    document.head.appendChild(themeStyleEl)
  }
  themeStyleEl.textContent = decls.length ? `:root {\n${decls.join('\n')}\n}\n` : ''
}

const CHAT_WINDOW_SVG = [
  ['ChatWindowChipSlot',       'chat-svg-area-chip-slot'],
  ['ChatWindowArea_0',         'chat-svg-area-0'],
  ['ChatWindowArea_1',         'chat-svg-area-1'],
  ['ChatWindowArea_2',         'chat-svg-area-2'],
  ['ChatWindowArea_3',         'chat-svg-area-3'],
  ['ChatWindowArea_4',         'chat-svg-area-4'],
  ['ChatWindowArea_5',         'chat-svg-area-5'],
  ['ChatWindowHeader',         'chat-svg-area-header'],
  ['ChatWindowWindowControls', 'chat-svg-area-window-controls'],
]

function chatWindowSvg(structure, blockKey, cssClass) {
  const block = structure?.['Chat.SVGStructure']?.['ChatWindow.SVG']
  return block?.[blockKey] || structure?.[cssClass] || ''
}

export function chatWindowSvgs(structure) {
  return CHAT_WINDOW_SVG
    .map(([blockKey, cssClass]) => [cssClass, chatWindowSvg(structure, blockKey, cssClass)])
    .filter(([, markup]) => markup)
}

export function windowControlsSvg(structure) {
  return chatWindowSvg(structure, 'ChatWindowWindowControls', 'chat-svg-area-window-controls')
}

const SIDE_PANEL_SVG = {
  corner: ['SidePanelCorner', 'chat-controls-svg-corner'],
  border: ['SidePanelBorder', 'chat-controls-svg-border'],
}

export function sidePanelSvg(structure, part) {
  const [blockKey, flatKey] = SIDE_PANEL_SVG[part] || []
  const block = structure?.['Chat.SVGStructure']?.['SidePanelBorder.SVG']
  return block?.[blockKey] || structure?.[flatKey] || ''
}

const SIDE_PANEL_BUTTON = {
  toggle:       ['SidePanelButtonToggle',       'chat-controls-button-toggle'],
  wardrobe:     ['SidePanelButtonWardrobe',     'chat-controls-button-wardrobe'],
  avatarToggle: ['SidePanelButtonAvatarToggle', 'chat-controls-button-avatar-toggle'],
  expand:       ['SidePanelButtonExpand',       'chat-controls-button-expand'],
  contextModel: ['SidePanelButtonContextModel', null],
  characterInformation: ['SidePanelButtonCharacterInformation', null],
  gacha:        ['SidePanelButtonGacha',        null],
}

export function sidePanelButtonSvg(structure, name) {
  const [blockKey, flatKey] = SIDE_PANEL_BUTTON[name] || []
  const block = structure?.['Chat.SVGStructure']?.['SidePanelButtons.SVG']
  return block?.[blockKey] || structure?.[flatKey] || ''
}

const MESSAGES_CONTAINER_SVG = {
  bottom: [['MessagesContainerAreaBottom'], 'chat-messages-container-svg-decorations-area-bottom'],
  top:    [['MessagesContainerAreaTop'],    'chat-messages-container-svg-decorations-area-top'],
  left:   [['MessagesContainerAreaLeft', 'MessagesContainerAreaReft'],
                                            'chat-messages-container-svg-decorations-area-left'],
  right:  [['MessagesContainerAreaRight'],  'chat-messages-container-svg-decorations-area-right'],
}

export function messagesContainerSvg(structure, side) {
  const [blockKeys = [], flatKey] = MESSAGES_CONTAINER_SVG[side] || []
  const block = structure?.['Chat.SVGStructure']?.['MessagesContainer.SVG']
  for (const k of blockKeys) if (block?.[k]) return block[k]
  return structure?.[flatKey] || ''
}

export function chatBackgroundSvg(structure) {
  return structure?.['Chat']?.['Chat.Messages.Background.SVG']
    || structure?.['chat-background-svg-decoration']
    || ''
}

export function chipSvg(structure) {
  return structure?.['Chat.SVGStructure']?.['Chip.SVG']
    || structure?.['chip-item']
    || ''
}

export function userMessageTailSvg(structure) {
  const fromBlock = structure?.['Chat.Messages.UserMessage']?.['Chat.Messages.UserMessage.Tail.SVG']
  if (IS_MARKUP.test(fromBlock || '')) return fromBlock
  return structure?.['user-message-tail'] || ''
}

const DARK_STRUCTURES = Object.fromEntries(
  Object.entries(
    import.meta.glob('@/electron/configs/dev/character_list_UIStructure/*_UIStructure_dark.json', {
      eager: true,
      import: 'default',
    }),
  ).map(([path, json]) => [path.split('/').pop().replace('_UIStructure_dark.json', ''), json]),
)

export function darkCharacterStructure(character) {
  if (!character) return null
  const reg = getRuntimeDark(character)
  if (reg) return reg
  return DARK_STRUCTURES[character.baseline_id] || DARK_STRUCTURES[character.id] || null
}

function getRuntimeDark(character) {
  const entry = getCharacterUi(character)
  return (entry && entry.dark) || null
}

export function defaultDarkStructure() {
  return darkDefaultStructure
}

const LIGHT_STRUCTURES = Object.fromEntries(
  Object.entries(
    import.meta.glob('@/electron/configs/dev/character_list_UIStructure/*_UIStructure.json', {
      eager: true,
      import: 'default',
    }),
  ).map(([path, json]) => [path.split('/').pop().replace('_UIStructure.json', ''), json]),
)

function lightCharacterStructure(character) {
  const entry = getCharacterUi(character)
  if (entry && entry.structure) return entry.structure
  return LIGHT_STRUCTURES[character.baseline_id] || LIGHT_STRUCTURES[character.id] || null
}

export function standardThemeChipSvg(character, { dark = false } = {}) {
  if (!character) return ''
  const raw = dark ? darkCharacterStructure(character) : lightCharacterStructure(character)
  return raw?.['Chat.StandardThemeChip']?.['Chat.StandardThemeChip.SVG'] || ''
}

export function standardThemeStructure(character, { dark = false } = {}) {
  const base = dark ? darkDefaultStructure : null
  const chip = standardThemeChipSvg(character, { dark })
  if (!chip) return base
  const src = base || defaultStructure
  return { ...src, 'Chat.SVGStructure': { ...src['Chat.SVGStructure'], 'Chip.SVG': chip } }
}

export function avatarFrameSvg(structure) {
  return structure?.['Chat.CharacterInformation']?.['Chat.CharacterInformation.AvatarFrame.SVG'] || ''
}

export function loreFrameSvg(structure) {
  return structure?.['Chat.CharacterInformation']?.['Chat.CharacterInformation.LoreFrame.SVG'] || ''
}

export function loreFrameStroke(structure) {
  const m = /stroke="(#[0-9a-fA-F]{6,8})"/.exec(loreFrameSvg(structure))
  return m ? m[1] : ''
}

const NOTIFICATION_SVG = {
  panel: ['Chat.Messages.Notification.SVG',      'chat-notification-svg-decoration'],
  icon:  ['Chat.Messages.Notification.Icon.SVG', 'chat-reminder-head-icon'],
}

export function notificationSvg(structure, part) {
  const [blockKey, flatKey] = NOTIFICATION_SVG[part] || []
  const block = structure?.['Chat.Messages.Notification']
  return block?.[blockKey] || structure?.[flatKey] || ''
}

export function emoteSvg(structure, id) {
  const block = structure?.['Chat.SVGStructure']?.['AIMessageEmotions.SVG']
  return block?.[`Emote_${id}`] || structure?.[`mood-${id}`] || ''
}

export function themeTokenVars(rawTheme, prefix, { dark = false } = {}) {
  if (!rawTheme) return undefined
  const { merged } = composeTheme(defaultStructure, darkDefaultStructure, rawTheme, { dark })
  const head = cssVarOf(prefix) + '-'
  const out = {}
  for (const [cssVar, v] of tokenEntries(merged)) {
    if (cssVar.startsWith(head)) out[cssVar] = v
  }
  return out
}

export function applyCharacterTheme(rawTheme, { dark = false } = {}) {
  const { theme, merged } = composeTheme(defaultStructure, darkDefaultStructure, rawTheme, { dark })
  const hasTheme = !!theme
  current = hasTheme ? merged : defaultStructure
  const themed = new Map(tokenEntries(current))
  const decls = []
  for (const [cssVar, base] of tokenEntries(defaultStructure)) {
    const v = hasTheme ? themed.get(cssVar) : ''
    if (v && v !== base) decls.push(`  ${cssVar}: ${v};`)
  }
  writeThemeSheet(decls)
  listeners.forEach((fn) => {
    try { fn() } catch {}
  })
}
