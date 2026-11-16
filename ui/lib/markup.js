export function parseMarkup(text, rules) {
  if (!text || !rules || rules.length === 0) return [{ text: text || '' }]

  const markers = rules.filter((r) => r.marker).sort((a, b) => b.marker.length - a.marker.length)

  const out = []
  let buf = ''
  let i = 0
  const flush = () => { if (buf) { out.push({ text: buf }); buf = '' } }

  const closeAt = (rule, at, lineEnd) => {
    if (!text.startsWith(rule.marker, at)) return -1
    const openEnd = at + rule.marker.length
    const close = text.indexOf(rule.close || rule.marker, openEnd)
    if (close === -1 || close >= lineEnd) return -1
    return text.slice(openEnd, close).trim() ? close : -1
  }

  while (i < text.length) {
    let lineEnd = text.indexOf('\n', i)
    if (lineEnd === -1) lineEnd = text.length
    let close = -1
    const rule = markers.find((r) => (close = closeAt(r, i, lineEnd)) !== -1)
    if (rule) {
      flush()
      out.push({ text: text.slice(i + rule.marker.length, close), rule })
      i = close + (rule.close || rule.marker).length
      continue
    }
    buf += text[i]
    i += 1
  }
  flush()
  return out.length ? out : [{ text: '' }]
}
