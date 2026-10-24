import React, { useState } from 'react'

const KIND_RU = { interest: 'интерес', idea: 'идея', diary: 'запись', diary_consolidation: 'итог' }
const TIER_RU = { 1: 'важное', 2: 'очень важное', 3: 'ключевое' }
const DAY = 86400
const NEW_DAYS = 3
const FADING_BELOW = 0.3
const CLAMP_CHARS = 220

function LockIcon() {
  return (
    <svg className="character-entries-lock-icon" width="12" height="14" viewBox="0 0 12 14" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path d="M3 6V4a3 3 0 0 1 6 0v2h1.5A1.5 1.5 0 0 1 12 7.5v5A1.5 1.5 0 0 1 10.5 14h-9A1.5 1.5 0 0 1 0 12.5v-5A1.5 1.5 0 0 1 1.5 6H3zm1.5 0h3V4a1.5 1.5 0 0 0-3 0v2z" fill="currentColor" />
    </svg>
  )
}

export function EntriesLock({ section }) {
  return (
    <div className="character-entries-lock">
      <LockIcon />
      <span>
        Откроется на уровне доверия {section.tier_required}
        {section.label_required ? ` · ${section.label_required}` : ''}
      </span>
    </div>
  )
}

const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime() / 1000
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s)

function groupOf(sec, nowSec) {
  if (!sec) return 'Без даты'
  const today = startOfDay(new Date(nowSec * 1000))
  const day = startOfDay(new Date(sec * 1000))
  const diff = Math.round((today - day) / DAY)
  if (diff <= 0) return 'Сегодня'
  if (diff === 1) return 'Вчера'
  if (diff < 7) return 'На этой неделе'
  if (diff < 30) return 'В этом месяце'
  return cap(new Date(sec * 1000).toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' }).replace(/\s*г\.$/, ''))
}

function fmtWhen(sec, group) {
  if (!sec) return ''
  const d = new Date(sec * 1000)
  if (group === 'Сегодня' || group === 'Вчера') {
    return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })
}

function Entry({ it, group, nowSec, collapsible, expanded, onToggle }) {
  const ageDays = it.created_at ? (nowSec - it.created_at) / DAY : Infinity
  const isNew = ageDays <= NEW_DAYS
  const tier = Math.max(0, Math.min(3, Number(it.tier) || 0))
  const fading = typeof it.relevance === 'number' && it.relevance < FADING_BELOW
  const long = collapsible && String(it.text || '').length > CLAMP_CHARS
  const clamped = long && !expanded
  const cls = ['character-entry', isNew ? 'is-new' : '', tier ? `is-tier-${tier}` : '', fading ? 'is-fading' : '',
    long ? 'is-collapsible' : ''].filter(Boolean).join(' ')
  return (
    <div className={cls} onClick={long ? onToggle : undefined}>
      <div className="character-entry-meta">
        <span className="character-entry-date">{fmtWhen(it.created_at, group)}</span>
        {it.kind ? <span className="character-entry-kind">{KIND_RU[it.kind] || it.kind}</span> : null}
        {isNew ? <span className="character-entry-tag is-new">новое</span> : null}
        {tier ? <span className={`character-entry-tag is-tier-${tier}`}>{TIER_RU[tier]}</span> : null}
        {fading ? <span className="character-entry-tag is-fading">угасает</span> : null}
      </div>
      <div className={`character-entry-text${clamped ? ' is-clamped' : ''}`}>{it.text}</div>
      {long ? <span className="character-entry-more">{expanded ? 'свернуть' : 'развернуть'}</span> : null}
    </div>
  )
}

export default function CharacterEntries({ section, emptyText, collapsible = false, pageSize = 0 }) {
  const [visible, setVisible] = useState(pageSize || Infinity)
  const [expanded, setExpanded] = useState(() => new Set())
  if (!section) return <div className="character-entries-empty">…</div>
  if (!section.unlocked) return <EntriesLock section={section} />
  const items = section.items || []
  if (!items.length) return <div className="character-entries-empty">{emptyText}</div>

  const nowSec = Date.now() / 1000
  const keyOf = (it, i) => it.id || `${it.created_at || 0}-${i}`
  const shown = items.slice(0, visible)
  const groups = []
  shown.forEach((it, i) => {
    const g = groupOf(it.created_at, nowSec)
    const last = groups[groups.length - 1]
    if (last && last.title === g) last.items.push([it, i])
    else groups.push({ title: g, items: [[it, i]] })
  })
  const toggle = (key) => setExpanded((prev) => {
    const next = new Set(prev)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    return next
  })
  const rest = items.length - shown.length

  return (
    <div className="character-entries">
      {groups.map((g) => (
        <div className="character-entries-group" key={g.title}>
          <div className="character-stats-group">
            <span>{g.title}</span>
            <i aria-hidden="true" />
          </div>
          {g.items.map(([it, i]) => {
            const key = keyOf(it, i)
            const isExpanded = expanded.has(key) ? !(i === 0) : i === 0
            return (
              <Entry key={key} it={it} group={g.title} nowSec={nowSec} collapsible={collapsible}
                expanded={isExpanded} onToggle={() => toggle(key)} />
            )
          })}
        </div>
      ))}
      {rest > 0 && (
        <button className="character-entries-more" onClick={() => setVisible((v) => v + (pageSize || rest))}>
          показать ещё {Math.min(rest, pageSize || rest)} из {rest}
        </button>
      )}
    </div>
  )
}
