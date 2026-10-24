const FENCE = '```'

const CODE_LINE_SCORE = 2
const SINGLE_LINE_SCORE = 3

const STRONG = [
  /^\s*(def|class)\s+[A-Za-z_]\w*\s*[(:]/,
  /^\s*for\s+\w+(\s*,\s*\w+)*\s+in\s+.+:\s*$/,
  /^\s*(elif|except)\b.*:\s*$|^\s*(else|try|finally)\s*:\s*$/,
  /^\s*(async\s+)?function\b\s*[\w$]*\s*\(/,
  /^\s*(const|let|var)\s+[\w${}[\],\s]+=/,
  /^\s*(import\s+[\w{*"']|from\s+[\w.]+\s+import\s|export\s+(default|const|let|function|class|async)\b)/,
  /^\s*#include\s*[<"]|^\s*#define\s+\w/,
  /^\s*(using\s+[\w.]+\s*;|package\s+[\w.]+\s*;?\s*$|namespace\s+[\w.]+)/,
  /^\s*(public|private|protected|internal)\s+(static\s+)?[\w<>[\],]+\s+\w+/,
  /^\s*(if|for|while|switch|catch|foreach)\s*\(.*\)\s*\{?\s*$/,
  /^\s*(fn|pub\s+fn|impl|struct|enum|trait|interface)\s+\w+.*[{(<]\s*$/,
  /^\s*(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|CREATE\s+(TABLE|INDEX|VIEW)|ALTER\s+TABLE|DROP\s+TABLE)\b/,
  /^\s*<\/?[a-zA-Z][\w:-]*(\s[^<>]*)?\/?>/,
  /^\s*"[^"]+"\s*:\s*/,
  /^\s*[}\]][}\])]*[;,]?\s*$/,
  /^\s*(return|yield)\b.*;\s*$/,
  /^\s*(\/\/|\/\*|\*\/)/,
  /^\s*[\w$.[\]]+\s*(=|\+=|-=|\*=|\/=)\s*[^=\s].*;\s*$/,
  /^\s*[.#:@*[a-zA-Z][\w\s.#:>+~,()[\]="'*@%-]*\{\s*$/,
  /^\s*-{0,2}[a-z][a-z0-9-]*\s*:\s*[^;{}]+;\s*$/,
]

const WEAK = [
  /([;{}]|\):|=>\s*\{?)\s*$/,
  /(=>|->|::|===|!==|==|!=|&&|\|\||\+\+|\+=|-=|<=|>=)/,
  /[A-Za-z_$][\w$]*(\.[A-Za-z_$][\w$]*)*\([^()]*\)/,
  /^(\t| {2,})\S/,
  /^\s*[A-Za-z_][\w.[\]]*\s*=\s*\S/,
  /\b[a-z]+_[a-z0-9_]+\b|\b[a-z]+[A-Z][a-zA-Z]+\b/,
  /^\s*(if|while|with)\s+.+:\s*$/,
  /^\s*(return|yield|raise|pass|break|continue)\b/,
]

const BLOCK_DELIMS = [['/*', '*/'], ['<!--', '-->'], ['"""', '"""'], ["'''", "'''"]]

function blockContinuation(lines) {
  const cont = new Array(lines.length).fill(false)
  let close = null
  for (let i = 0; i < lines.length; i++) {
    let line = lines[i]
    if (close) {
      cont[i] = true
      const at = line.indexOf(close)
      if (at === -1) continue
      line = line.slice(at + close.length)
      close = null
    }
    let pos = 0
    for (;;) {
      let best = null
      for (const [o, c] of BLOCK_DELIMS) {
        const at = line.indexOf(o, pos)
        if (at !== -1 && (!best || at < best.at)) best = { at, o, c }
      }
      if (!best) break
      const end = line.indexOf(best.c, best.at + best.o.length)
      if (end === -1) { close = best.c; cont[i] = true; break }
      pos = end + best.c.length
    }
  }
  return cont
}

const ACTION_LINE = /^\s*\*[^*]+\*\s*$/
const CYRILLIC = /[А-Яа-яЁё]/

function stripLiteralsAndComments(line) {
  return line
    .replace(/"(\\.|[^"\\])*"|'(\\.|[^'\\])*'|`(\\.|[^`\\])*`/g, '""')
    .replace(/(\/\/|#\s).*$/, '')
}

export function codeLineScore(line) {
  if (!line.trim()) return null
  if (ACTION_LINE.test(line)) return -3
  let score = STRONG.some((re) => re.test(line)) ? 2 : 0
  const strong = score > 0
  for (const re of WEAK) if (re.test(line)) score += 1
  const sym = (line.match(/[{}[\]();<>=]/g) || []).length
  if (sym >= 3 && sym / line.trim().length >= 0.08) score += 1
  if (!strong && CYRILLIC.test(stripLiteralsAndComments(line))) score -= 2
  return score
}

export function detectCodeBlocks(text) {
  if (!text || text.includes(FENCE)) return []
  const lines = text.split('\n')
  const scores = lines.map(codeLineScore)
  const isCode = (i) => scores[i] !== null && scores[i] >= CODE_LINE_SCORE
  const nonBlank = scores.filter((s) => s !== null).length

  if (nonBlank === 1) {
    const i = scores.findIndex((s) => s !== null)
    return scores[i] >= SINGLE_LINE_SCORE ? [{ start: i, end: i }] : []
  }

  const cont = blockContinuation(lines)
  const blocks = []
  let i = 0
  while (i < lines.length) {
    if (!isCode(i)) { i += 1; continue }
    let end = i
    let codeLines = 0
    for (let j = i; j < lines.length; j++) {
      const s = scores[j]
      const indented = /^(\t| {2,})\S/.test(lines[j])
      if (s === null) continue
      if (cont[j]) { end = j; continue }
      if (s >= CODE_LINE_SCORE) codeLines += 1
      else if (!(s >= 1 || (indented && s >= 0))) break
      end = j
    }
    if (codeLines >= 2) blocks.push({ start: i, end })
    i = end + 1
  }
  return blocks
}

function dedent(lines) {
  const indents = lines.filter((l) => l.trim()).map((l) => l.match(/^[ \t]*/)[0].length)
  const cut = indents.length ? Math.min(...indents) : 0
  return lines.map((l) => l.slice(Math.min(cut, l.match(/^[ \t]*/)[0].length)))
}

export function wrapCodeBlocks(text) {
  const norm = (text || '').replace(/\u00A0/g, ' ')
  const blocks = detectCodeBlocks(norm)
  if (!blocks.length) return (text || '').trim()
  const lines = text.split('\n')
  const codeLines = norm.split('\n')
  const out = []
  let cursor = 0
  for (const { start, end } of blocks) {
    out.push(...lines.slice(cursor, start))
    out.push(FENCE, ...dedent(codeLines.slice(start, end + 1)), FENCE)
    cursor = end + 1
  }
  out.push(...lines.slice(cursor))
  return out.join('\n').trim()
}

export function splitCodeBlocks(text) {
  if (!text || !text.includes(FENCE)) return [{ text: text || '' }]
  const parts = []
  let i = 0
  while (i < text.length) {
    const open = text.indexOf(FENCE, i)
    if (open === -1) { parts.push({ text: text.slice(i) }); break }
    if (open > i) parts.push({ text: text.slice(i, open) })
    const close = text.indexOf(FENCE, open + FENCE.length)
    const body = text.slice(open + FENCE.length, close === -1 ? text.length : close)
    let lang = ''
    let code = body
    const nl = body.indexOf('\n')
    if (nl !== -1) {
      const head = body.slice(0, nl).trim()
      if (/^[\w+#.-]*$/.test(head)) { lang = head; code = body.slice(nl + 1) }
    }
    code = code.replace(/\n$/, '')
    if (code.trim()) parts.push({ code, lang })
    else parts.push({ text: text.slice(open, close === -1 ? text.length : close + FENCE.length) })
    i = close === -1 ? text.length : close + FENCE.length
  }
  for (let k = 0; k < parts.length; k++) {
    if (parts[k].code === undefined) continue
    if (parts[k - 1]?.text !== undefined) parts[k - 1].text = parts[k - 1].text.replace(/[ \t]*(\n[ \t]*)+$/, '')
    if (parts[k + 1]?.text !== undefined) parts[k + 1].text = parts[k + 1].text.replace(/^([ \t]*\n)+/, '')
  }
  return parts.filter((p) => p.code !== undefined || p.text)
}
