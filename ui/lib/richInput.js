import { gestureChipText } from './gestures'

const TOKEN_RX = /⟦[^⟧]*⟧/g

const HAND_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
  + 'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
  + '<path d="M18 11V6a2 2 0 0 0-2-2a2 2 0 0 0-2 2"/>'
  + '<path d="M14 10V4a2 2 0 0 0-2-2a2 2 0 0 0-2 2v2"/>'
  + '<path d="M10 10.5V6a2 2 0 0 0-2-2a2 2 0 0 0-2 2v8"/>'
  + '<path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"/>'
  + '</svg>'

export function makeChip(token) {
  const span = document.createElement('span')
  span.className = 'gesture-fx'
  span.contentEditable = 'false'
  span.dataset.token = token
  span.innerHTML = HAND_SVG
  span.appendChild(document.createTextNode(gestureChipText(token.slice(1, -1))))
  return span
}

function isChip(node) {
  return node.nodeType === 1 && !!(node.dataset && node.dataset.token)
}

export function renderValue(el, value) {
  const v = String(value || '')
  el.textContent = ''
  if (!v) return
  const frag = document.createDocumentFragment()
  const pushText = (s) => {
    s.split('\n').forEach((line, i) => {
      if (i > 0) frag.appendChild(document.createElement('br'))
      if (line) frag.appendChild(document.createTextNode(line))
    })
  }
  let last = 0
  TOKEN_RX.lastIndex = 0
  let m
  while ((m = TOKEN_RX.exec(v)) !== null) {
    pushText(v.slice(last, m.index))
    frag.appendChild(makeChip(m[0]))
    last = m.index + m[0].length
  }
  pushText(v.slice(last))
  if (v.endsWith('\n')) frag.appendChild(document.createElement('br'))
  el.appendChild(frag)
}

export function serializeNode(node) {
  let out = ''
  const walk = (n) => {
    for (const c of n.childNodes) {
      if (c.nodeType === 3) { out += c.nodeValue; continue }
      if (c.nodeType !== 1) continue
      if (c.tagName === 'BR') { out += '\n'; continue }
      if (isChip(c)) { out += c.dataset.token; continue }
      if (/^(DIV|P)$/.test(c.tagName) && out && !out.endsWith('\n')) out += '\n'
      walk(c)
    }
  }
  walk(node)
  return out
}

export function serialize(el) {
  const kids = [...el.childNodes]
  if (kids.length && kids[kids.length - 1].nodeType === 1 && kids[kids.length - 1].tagName === 'BR') {
    const clone = el.cloneNode(true)
    clone.removeChild(clone.lastChild)
    return serializeNode(clone)
  }
  return serializeNode(el)
}

export function hasRawToken(el) {
  const it = document.createNodeIterator(el, NodeFilter.SHOW_TEXT)
  let n
  while ((n = it.nextNode())) {
    if (n.parentNode && isChip(n.parentNode)) continue
    TOKEN_RX.lastIndex = 0
    if (TOKEN_RX.test(n.nodeValue)) return true
  }
  return false
}

export function selectionOffsets(el) {
  const sel = window.getSelection()
  if (!sel || sel.rangeCount === 0) return null
  const r = sel.getRangeAt(0)
  if (!el.contains(r.startContainer) || !el.contains(r.endContainer)) return null
  const measure = (container, offset) => {
    const pre = document.createRange()
    pre.setStart(el, 0)
    pre.setEnd(container, offset)
    return serializeNode(pre.cloneContents()).length
  }
  return { start: measure(r.startContainer, r.startOffset), end: measure(r.endContainer, r.endOffset) }
}

export function setCaretOffset(el, offset) {
  const sel = window.getSelection()
  if (!sel) return
  const range = document.createRange()
  let remaining = Math.max(0, offset | 0)
  let placed = false
  const kids = [...el.childNodes]
  for (let i = 0; i < kids.length; i++) {
    const c = kids[i]
    if (c.nodeType === 3) {
      const len = c.nodeValue.length
      if (remaining <= len) { range.setStart(c, remaining); placed = true; break }
      remaining -= len
    } else if (c.nodeType === 1 && c.tagName === 'BR') {
      if (remaining === 0) { range.setStart(el, i); placed = true; break }
      remaining -= 1
      if (remaining === 0) { range.setStart(el, i + 1); placed = true; break }
    } else if (isChip(c)) {
      const len = c.dataset.token.length
      if (remaining === 0) { range.setStart(el, i); placed = true; break }
      if (remaining <= len) { range.setStart(el, i + 1); placed = true; break }
      remaining -= len
    } else if (c.nodeType === 1) {
      const len = serializeNode(c).length
      if (remaining <= len) { range.setStart(el, i + 1); placed = true; break }
      remaining -= len
    }
  }
  if (!placed) range.setStart(el, el.childNodes.length)
  range.collapse(true)
  sel.removeAllRanges()
  sel.addRange(range)
}

export function insertPlainText(text) {
  const parts = String(text || '').replace(/\r\n?/g, '\n').split('\n')
  parts.forEach((p, i) => {
    if (i > 0) document.execCommand('insertLineBreak')
    if (p) document.execCommand('insertText', false, p)
  })
}

export function renderedWidth(el) {
  if (!el.childNodes.length) return 0
  const r = document.createRange()
  r.selectNodeContents(el)
  return r.getBoundingClientRect().width
}

export function editorFacade(el) {
  let last = { start: 0, end: 0 }
  const onSelectionChange = () => {
    const off = selectionOffsets(el)
    if (off) last = off
  }
  document.addEventListener('selectionchange', onSelectionChange)
  const current = () => selectionOffsets(el) || last
  return {
    el,
    get value() { return serialize(el) },
    set value(v) { renderValue(el, v) },
    get selectionStart() { return current().start },
    get selectionEnd() { return current().end },
    set selectionStart(n) { setCaretOffset(el, n); last = { start: n, end: n } },
    set selectionEnd(n) { setCaretOffset(el, n); last = { start: n, end: n } },
    setSelectionRange(a, b) { setCaretOffset(el, b); last = { start: b, end: b } },
    focus() { el.focus() },
    blur() { el.blur() },
    get scrollHeight() { return el.scrollHeight },
    get clientHeight() { return el.clientHeight },
    get style() { return el.style },
    getBoundingClientRect() { return el.getBoundingClientRect() },
    dispose() { document.removeEventListener('selectionchange', onSelectionChange) },
  }
}
