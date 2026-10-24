const isBlock = (v) => v !== null && typeof v === 'object' && !Array.isArray(v)
const nonEmpty = (v) => typeof v === 'string' && v.trim() !== ''
const escapeRx = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
export const IS_COLOR = /^\s*(#[0-9a-f]{3,8}|(rgb|hsl)a?\()/i

export const LEGACY_FROM_PALETTE = [
  ['COLOR_BASE', 'MainColor'],
  ['COLOR_COMPLIMENTARY', 'ComplimentaryColor'],
  ['COLOR_ACCENT', 'AccentColor'],
  ['COLOR_ADDITION_1', 'AdditionColor_1'],
]
const PALETTE_FALLBACK = {
  COLOR_COMPLIMENTARY: ['Chat', 'Chat.Settings.Background'],
}

export const SETTINGS_FROM_BLOCK = [
  ['COLOR_SETTINGS_FONT_1', 'Chat.Settings.Dropdown.FontColor'],
  ['COLOR_SETTINGS_FONT_2', 'Chat.Settings.Dropdown.FontColor'],
  ['COLOR_SETTINGS_CARD_BACKGROUND', 'Chat.Settings.Dropdown.Option.BackgroundSelected'],
  ['COLOR_SETTINGS_CARD_BORDER', 'Chat.Settings.Dropdown.Border'],
  ['COLOR_SETTINGS_DROPDOWN_BUTTON', 'Chat.Settings.Toggle.Background'],
]

export const SETTINGS_BLOCK_FROM_THEME = [
  ["Chat.CharacterInformation.Gallery", "Chat.CharacterInformation.Gallery.Cell.Background", "Chat.Settings", "Chat.Settings.Dropdown.Option.BackgroundSelected"],
  ["Chat.CharacterInformation.Gallery.Viewer", "Chat.CharacterInformation.Gallery.Viewer.Bar.Background", "CharacterColorThemeDescription", "MainColor"],
  ["Chat.CharacterInformation.Gallery.Viewer", "Chat.CharacterInformation.Gallery.Viewer.FontColor", "Chat.Header", "Chat.Header.FontColor"],
  ["Chat.CharacterInformation.Gallery.Viewer", "Chat.CharacterInformation.Gallery.Viewer.Stage.Background", "Chat", "Chat.Background"],
  ["Chat.Settings.Addons", "Chat.Settings.Addons.Background", "Chat.Settings", "Chat.Settings.Dropdown.Option.BackgroundSelected"],
  ["Chat.Settings.Drawing", "Chat.Settings.Drawing.Background", "Chat.Settings", "Chat.Settings.Dropdown.Option.BackgroundSelected"],
  ["Chat.Settings.Drawing", "Chat.Settings.Drawing.Status.FontColor", "Chat.Settings", "Chat.Settings.Dropdown.FontColor"],
  ["Chat.Settings.ImageGenSetup", "Chat.Settings.ImageGenSetup.FontColor", "Chat.Settings", "Chat.Settings.Dropdown.FontColor"],
  ["Chat.Settings.ModelPresets", "Chat.Settings.ModelPresets.Background", "Chat.Settings", "Chat.Settings.Dropdown.Option.BackgroundSelected"],
  ["Chat.Settings.ModelPresets", "Chat.Settings.ModelPresets.Card.BorderColorActive", "Chat.Settings", "Chat.Settings.Toggle.BackgroundActive"],
  ["Chat.Settings.ModelPresets", "Chat.Settings.ModelPresets.Card.BorderColorHover", "Chat.Settings", "Chat.Settings.Toggle.Background"],
  ["Chat.Settings.ModelPresets", "Chat.Settings.ModelPresets.Card.FontColor", "Chat.Settings", "Chat.Settings.Dropdown.FontColor"],
  ["Chat.Settings.ModelPresets", "Chat.Settings.ModelPresets.Details.Label.FontColor", "Chat.Settings", "Chat.Settings.Dropdown.FontColor"],
  ["Chat.Settings.ModelPresets", "Chat.Settings.ModelPresets.Details.Range.AccentColor", "Chat.Settings", "Chat.Settings.Toggle.BackgroundActive"],
  ["Chat.Settings.ModelPresets", "Chat.Settings.ModelPresets.Dot.BackgroundActive", "Chat.Settings", "Chat.Settings.Toggle.BackgroundActive"],
  ["Chat.Settings.ModelPresets", "Chat.Settings.ModelPresets.Dot.BorderColor", "Chat.Settings", "Chat.Settings.Toggle.Background"],
  ["Chat.Settings.ModelPresets", "Chat.Settings.ModelPresets.Download.Bar.Fill.Background", "Chat.Settings", "Chat.Settings.Toggle.BackgroundActive"],
  ["Chat.Settings.ModelPresets", "Chat.Settings.ModelPresets.Download.Button.Background", "Chat.Settings", "Chat.Settings.Toggle.Background"],
  ["Chat.Settings.ModelPresets", "Chat.Settings.ModelPresets.Download.Button.FontColor", "Chat.Settings", "Chat.Settings.Toggle.KnobBackground"],
  ["Chat.Settings.ModelPresets", "Chat.Settings.ModelPresets.Fit.Full.FontColor", "Chat.Settings", "Chat.Settings.Toggle.BackgroundActive"],
  ["Chat.Settings.ModelPresets", "Chat.Settings.ModelPresets.Machine.FontColor", "Chat.Settings", "Chat.Settings.Dropdown.FontColor"],
  ["Chat.Settings.ModelPresets", "Chat.Settings.ModelPresets.Note.FontColor", "Chat.Settings", "Chat.Settings.Dropdown.FontColor"],
  ["Chat.Settings.ModelPresets", "Chat.Settings.ModelPresets.SpeedDot.BackgroundOn", "Chat.Settings", "Chat.Settings.Toggle.BackgroundActive"],
  ["Chat.Settings.ModelPresets", "Chat.Settings.ModelPresets.SpeedDot.BorderColor", "Chat.Settings", "Chat.Settings.Toggle.Background"],
  ["Chat.Settings.ModelPresets", "Chat.Settings.ModelPresets.Title.FontColor", "Chat.Settings", "Chat.Settings.Dropdown.FontColor"],
  ["Chat.Settings.Panel", "Chat.Settings.Panel.Card.Border", "Chat.Settings", "Chat.Settings.Dropdown.Border"],
  ["Chat.Settings.Panel", "Chat.Settings.Panel.Empty.FontColor", "Chat.Settings", "Chat.Settings.Dropdown.FontColor"],
  ["Chat.Settings.Panel", "Chat.Settings.Panel.Header.FontColor", "Chat.Settings", "Chat.Settings.Dropdown.FontColor"],
  ["Chat.Settings.Panel", "Chat.Settings.Panel.Range.AccentColor", "Chat.Settings", "Chat.Settings.Toggle.BackgroundActive"],
  ["Chat.Settings.Panel", "Chat.Settings.Panel.Range.Value.FontColor", "Chat.Settings", "Chat.Settings.Dropdown.FontColor"],
  ["Chat.Settings.Panel", "Chat.Settings.Panel.Row.Background", "Chat.Settings", "Chat.Settings.Dropdown.Option.BackgroundSelected"],
  ["Chat.Settings.Panel", "Chat.Settings.Panel.Row.Label.FontColor", "Chat.Settings", "Chat.Settings.Dropdown.FontColor"],
  ["Chat.Settings.Panel", "Chat.Settings.Panel.Section.Title.FontColor", "Chat.Settings", "Chat.Settings.Dropdown.FontColor"],
  ["Chat.Settings.Protection", "Chat.Settings.Protection.Button.Cancel.Background", "Chat.Settings", "Chat.Settings.Toggle.Background"],
  ["Chat.Settings.Protection", "Chat.Settings.Protection.Button.Cancel.FontColor", "Chat.Settings", "Chat.Settings.Dropdown.FontColor"],
  ["Chat.Settings.Protection", "Chat.Settings.Protection.Button.Secondary.FontColor", "Chat.Settings", "Chat.Settings.Dropdown.FontColor"],
  ["Chat.Settings.Protection", "Chat.Settings.Protection.Code.FontColor", "Chat.Settings", "Chat.Settings.Dropdown.FontColor"],
  ["Chat.Settings.Protection", "Chat.Settings.Protection.Code.Value.FontColor", "Chat.Settings", "Chat.Settings.Dropdown.FontColor"],
  ["Chat.Settings.Protection", "Chat.Settings.Protection.Row.Background", "Chat.Settings", "Chat.Settings.Dropdown.Option.BackgroundSelected"],
  ["Chat.Settings.Sound", "Chat.Settings.Sound.Value.FontColor", "Chat.Settings", "Chat.Settings.Dropdown.FontColor"],
]

export const COMPUTED_BLOCK_TOKENS = [
  ['Chat.CharacterInformation.Entries', 'Chat.CharacterInformation.Entries.Tag.New.FontColor',
    'Chat.CharacterInformation', 'Chat.CharacterInformation.Tier.Gauge.Value.Color', 'contrast'],
  ['Chat.CharacterWardrobe', 'Chat.CharacterWardrobe.Tag.Current.FontColor',
    'Chat.CharacterInformation', 'Chat.CharacterInformation.Tier.Gauge.Value.Color', 'contrast'],
  ['Chat.CharacterWardrobe', 'Chat.CharacterWardrobe.Button.FontColorArmed',
    'Chat.CharacterInformation', 'Chat.CharacterInformation.Tier.Gauge.Value.Color', 'contrast'],
  ['Chat.CharacterWardrobe', 'Chat.CharacterWardrobe.Hero.Background',
    'Chat.CharacterInformation', 'Chat.CharacterInformation.Tier.Gauge.Value.Color', 'alpha07'],
]

export const READABLE_ON_BUBBLE_TOKENS = [
  ['Chat.RichText.Emphasis', 'Chat.RichText.Emphasis.FontColor',
    'Chat.Messages.AIMessage', 'Chat.Messages.AIMessage.Background', 'Chat.Messages.AIMessage.FontColor'],
  ['Chat.RichText.Emphasis', 'Chat.RichText.Emphasis.OnUser.FontColor',
    'Chat.Messages.UserMessage', 'Chat.Messages.UserMessage.Background', 'Chat.Messages.UserMessage.FontColor'],
]
export const MIN_TEXT_CONTRAST = 4.5

export function parseColor(s) {
  const t = String(s || '').trim()
  let m = /^#([0-9a-f]{3,4})$/i.exec(t)
  if (m) return [...m[1].slice(0, 3)].map((c) => parseInt(c + c, 16))
  m = /^#([0-9a-f]{6})(?:[0-9a-f]{2})?$/i.exec(t)
  if (m) return [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16))
  m = /^rgba?\(\s*(\d+)\s*[, ]\s*(\d+)\s*[, ]\s*(\d+)/i.exec(t)
  if (m) return [m[1], m[2], m[3]].map(Number)
  return null
}

export function labLightness(rgb) {
  const lin = rgb.map((v) => { const c = v / 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4 })
  const y = 0.2126729 * lin[0] + 0.7151522 * lin[1] + 0.0721750 * lin[2]
  const f = y > 0.008856 ? Math.cbrt(y) : (7.787 * y + 16 / 116)
  return 116 * f - 16
}

export function contrastRatio(a, b) {
  const lum = (rgb) => {
    const [r, g, bl] = rgb.map((v) => { const c = v / 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4 })
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl
  }
  const [x, y] = [lum(a), lum(b)]
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05)
}

const FORMULAS = {
  contrast: (rgb) => (labLightness(rgb) < 49.44 ? '#FFFFFF' : '#000000'),
  alpha07: (rgb) => `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, 0.07)`,
}

export function applyComputedTokens(theme, merged, base = null) {
  for (const [block, key, srcBlock, srcKey, formula] of COMPUTED_BLOCK_TOKENS) {
    const own = isBlock(theme) && isBlock(theme[block]) ? theme[block][key] : undefined
    if (nonEmpty(own)) continue
    const src = isBlock(merged[srcBlock]) ? merged[srcBlock][srcKey] : undefined
    if (base && isBlock(base[srcBlock]) && base[srcBlock][srcKey] === src) continue
    const rgb = parseColor(src)
    if (!rgb) continue
    merged[block] = { ...(isBlock(merged[block]) ? merged[block] : {}), [key]: FORMULAS[formula](rgb) }
  }
  return merged
}

export function applyReadableTokens(theme, merged) {
  for (const [block, key, bubble, bgKey, fontKey] of READABLE_ON_BUBBLE_TOKENS) {
    const own = isBlock(theme) && isBlock(theme[block]) ? theme[block][key] : undefined
    if (nonEmpty(own) || !isBlock(merged[block]) || !isBlock(merged[bubble])) continue
    const font = merged[bubble][fontKey]
    const [fg, bg, text] = [merged[block][key], merged[bubble][bgKey], font].map(parseColor)
    if (!fg || !bg || !text) continue
    const ratio = contrastRatio(fg, bg)
    if (ratio >= MIN_TEXT_CONTRAST || contrastRatio(text, bg) <= ratio) continue
    merged[block] = { ...merged[block], [key]: font }
  }
  return merged
}

export function deriveBlockTokens(theme) {
  if (!isBlock(theme)) return theme
  let out = theme
  for (const [block, key, srcBlock, srcKey] of SETTINGS_BLOCK_FROM_THEME) {
    const own = isBlock(theme[block]) ? theme[block][key] : undefined
    if (nonEmpty(own)) continue
    const v = isBlock(theme[srcBlock]) ? theme[srcBlock][srcKey] : undefined
    if (!nonEmpty(v)) continue
    if (out === theme) out = { ...theme }
    out[block] = { ...(isBlock(out[block]) ? out[block] : {}), [key]: v }
  }
  return out
}

export function deriveFlatTokens(theme) {
  if (!isBlock(theme)) return theme
  let out = theme
  const set = (k, v) => {
    if (out === theme) out = { ...theme }
    out[k] = v
  }
  const palette = theme['CharacterColorThemeDescription']
  for (const [flat, src] of LEGACY_FROM_PALETTE) {
    if (nonEmpty(theme[flat])) continue
    let v = isBlock(palette) ? palette[src] : undefined
    if (!nonEmpty(v)) {
      const fb = PALETTE_FALLBACK[flat]
      const blk = fb ? theme[fb[0]] : undefined
      v = isBlock(blk) ? blk[fb[1]] : undefined
    }
    if (nonEmpty(v)) set(flat, v)
  }
  const settings = theme['Chat.Settings']
  if (isBlock(settings)) {
    for (const [flat, src] of SETTINGS_FROM_BLOCK) {
      if (nonEmpty(theme[flat])) continue
      const v = settings[src]
      if (nonEmpty(v)) set(flat, v)
    }
  }
  return out
}

export function mergeStructures(defaultStructure, theme) {
  const next = { ...defaultStructure, ...theme }
  for (const [key, value] of Object.entries(theme)) {
    if (isBlock(value) && isBlock(defaultStructure[key])) {
      next[key] = { ...defaultStructure[key], ...value }
    }
  }
  return next
}

export const PALETTE_KEYS = LEGACY_FROM_PALETTE.map(([flat]) => flat)

export function buildColorMap(defaultStructure, theme, keys) {
  return (keys || Object.keys(defaultStructure))
    .filter((k) => /^COLOR_[A-Z0-9_]*$/.test(k))
    .filter((k) => defaultStructure[k] && theme[k]
      && String(theme[k]).toLowerCase() !== String(defaultStructure[k]).toLowerCase()
      && IS_COLOR.test(defaultStructure[k]) && IS_COLOR.test(theme[k]))
    .map((k) => [new RegExp(escapeRx(defaultStructure[k]), 'gi'), theme[k]])
}

export const PALETTE_BLOCK = 'CharacterColorThemeDescription'

export function buildPaletteBlockMap(baseStructure, theme) {
  const base = isBlock(baseStructure) ? baseStructure[PALETTE_BLOCK] : null
  const own = isBlock(theme) ? theme[PALETTE_BLOCK] : null
  if (!isBlock(base) || !isBlock(own)) return []
  const seen = new Set()
  const out = []
  for (const [slot, from] of Object.entries(base)) {
    const to = own[slot]
    if (!IS_COLOR.test(from || '') || !IS_COLOR.test(to || '')) continue
    const key = String(from).toLowerCase()
    if (key === String(to).toLowerCase() || seen.has(key)) continue
    seen.add(key)
    out.push([new RegExp(escapeRx(from), 'gi'), to])
  }
  return out
}

export function composeTheme(lightDefault, darkDefault, rawTheme, { dark = false } = {}) {
  const base = dark && isBlock(darkDefault) ? darkDefault : lightDefault
  const isDark = base !== lightDefault
  const theme = isDark ? rawTheme : deriveBlockTokens(deriveFlatTokens(rawTheme))
  if (!isBlock(theme) || !Object.keys(theme).length) return { theme: null, merged: lightDefault }
  const merged = mergeStructures(base, theme)
  if (isDark) {
    const map = [...buildPaletteBlockMap(base, theme), ...buildColorMap(base, theme)]
    recolorMissing(base, theme, merged, map, map)
  } else {
    recolorMissing(base, theme, merged,
      buildColorMap(base, theme),
      buildColorMap(base, theme, PALETTE_KEYS))
  }
  applyComputedTokens(theme, merged, isDark ? base : null)
  applyReadableTokens(theme, merged)
  return { theme, merged }
}

export function recolorMissing(defaultStructure, theme, merged, colorMap, blockColorMap = colorMap) {
  const painter = (map) => (s) => map.reduce((acc, [rx, to]) => acc.replace(rx, to), s)
  const paint = painter(colorMap)
  const paintBlock = painter(blockColorMap)
  for (const [key, base] of Object.entries(defaultStructure)) {
    if (typeof base === 'string') {
      if (theme[key] !== undefined || !colorMap.length) continue
      merged[key] = paint(base)
    } else if (isBlock(base)) {
      if (!blockColorMap.length) continue
      const over = isBlock(theme[key]) ? theme[key] : {}
      const blk = { ...merged[key] }
      for (const [path, v] of Object.entries(base)) {
        if (over[path] !== undefined || typeof v !== 'string') continue
        blk[path] = paintBlock(v)
      }
      merged[key] = blk
    }
  }
  return merged
}
