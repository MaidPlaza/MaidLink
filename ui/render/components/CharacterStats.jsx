import React from 'react'

const fmtN = (n) => (typeof n === 'number' && Number.isFinite(n) ? n.toLocaleString('ru-RU') : '—')

export function plural(n, one, few, many) {
  const a = Math.abs(n) % 100
  const b = a % 10
  if (a > 10 && a < 20) return many
  if (b > 1 && b < 5) return few
  if (b === 1) return one
  return many
}

function fmtMinutes(min) {
  const m = Math.max(0, Math.round(Number(min) || 0))
  if (m < 60) return `${m} мин`
  const h = Math.floor(m / 60)
  const rest = m % 60
  return rest ? `${fmtN(h)} ч ${rest} мин` : `${fmtN(h)} ч`
}

function Tile({ value, label, sub }) {
  return (
    <div className="character-stats-tile">
      <div className="character-stats-tile-value">{value}</div>
      <div className="character-stats-tile-label">{label}</div>
      {sub ? <div className="character-stats-tile-sub">{sub}</div> : null}
    </div>
  )
}

export function Group({ title }) {
  return (
    <div className="character-stats-group">
      <span>{title}</span>
      <i aria-hidden="true" />
    </div>
  )
}

export function Record({ label, value, sub, muted }) {
  return (
    <>
      <div className="character-stats-record-label">{label}</div>
      <div className={`character-stats-record-value${muted ? ' is-muted' : ''}`}>
        {value}
        {sub ? <span className="character-stats-record-sub"> · {sub}</span> : null}
      </div>
    </>
  )
}

export default function CharacterStats({ stats, name }) {
  const s = stats || {}
  const hasCounts = typeof s.sessions === 'number'
  const who = (name || '').trim() || 'персонаж'
  const since = s.since
    ? new Date(s.since * 1000).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
    : ''
  const days = Number(s.days) || 0
  const longestMsgs = Number(s.longest_messages) || 0
  const longestMin = Number(s.longest_minutes) || 0
  const talkMin = Number(s.talk_minutes) || 0
  const streak = Number(s.streak_days) || 0
  const best = Number(s.best_streak_days) || 0
  const sent = Number(s.proactive_sent) || 0
  const answered = Number(s.proactive_answered) || 0
  const moods = Array.isArray(s.moods_top) ? s.moods_top.filter((m) => Array.isArray(m) && m[0]) : []

  return (
    <div className="character-stats">
      <div className="character-stats-tiles">
        <Tile value={days > 0 ? fmtN(days) : '—'}
          label={days > 0 ? `${plural(days, 'день', 'дня', 'дней')} знакомы` : 'знакомы'} />
        <Tile value={hasCounts ? fmtN(s.sessions) : '—'} label="сессий" />
        <Tile value={hasCounts ? fmtN(s.messages) : '—'} label="сообщений"
          sub={hasCounts ? `вы ${fmtN(s.messages_user)} · ${who} ${fmtN(s.messages_assistant)}` : ''} />
        <Tile value={hasCounts ? fmtN(s.images) : '—'} label="снимков" />
      </div>

      <Group title="Рекорды" />
      <div className="character-stats-records">
        <Record label="Самый долгий разговор"
          value={longestMsgs > 0 ? `${fmtN(longestMsgs)} ${plural(longestMsgs, 'сообщение', 'сообщения', 'сообщений')}` : 'ещё не было'}
          sub={longestMsgs > 0 ? fmtMinutes(longestMin) : ''}
          muted={longestMsgs === 0} />
        <Record label="Всего разговоров"
          value={talkMin > 0 ? fmtMinutes(talkMin) : 'ещё не было'}
          muted={talkMin === 0} />
        <Record label="Серия дней подряд"
          value={best > 0 ? `${fmtN(streak)} ${plural(streak, 'день', 'дня', 'дней')}` : 'ещё не было'}
          sub={best > 0 ? (best > streak ? `рекорд ${fmtN(best)}` : 'это рекорд') : ''}
          muted={best === 0} />
        <Record label="Инициатива"
          value={sent > 0 ? `${fmtN(sent)} ${plural(sent, 'весточка', 'весточки', 'весточек')}` : 'весточек ещё не было'}
          sub={sent > 0 ? `ответ на ${fmtN(answered)}` : ''}
          muted={sent === 0} />
      </div>

      <Group title="Настроения в конце сессий" />
      {moods.length === 0 ? (
        <div className="character-stats-note">пока нет завершённых сессий</div>
      ) : (
        <div className="character-stats-moods">
          {moods.map(([mood, n]) => (
            <span className="character-stats-mood" key={mood}>
              {mood} <b>×{fmtN(Number(n) || 0)}</b>
            </span>
          ))}
        </div>
      )}

      {since && (
        <div className="character-stats-note">сообщения, снимки и рекорды считаем с {since}</div>
      )}
    </div>
  )
}
