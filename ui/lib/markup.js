export function parseMarkup(text, rules) {
  if (!text || !rules || rules.length === 0) return [{ text: text || '' }]

  const markers = [...rules].sort((a, b) => b.marker.length - a.marker.length)

  const out = []
  let buf = ''
  let i = 0
  const flush = () => { if (buf) { out.push({ text: buf }); buf = '' } }

  while (i < text.length) {
    const rule = markers.find((r) => r.marker && text.startsWith(r.marker, i))
    if (rule) {
      const closeMarker = rule.close || rule.marker
      const openEnd = i + rule.marker.length
      const close = text.indexOf(closeMarker, openEnd)
      if (close !== -1) {
        const inner = text.slice(openEnd, close)
        if (inner.length > 0) {
          flush()
          out.push({ text: inner, rule })
          i = close + closeMarker.length
          continue
        }
      }
    }
    buf += text[i]
    i += 1
  }
  flush()
  return out.length ? out : [{ text: '' }]
}
