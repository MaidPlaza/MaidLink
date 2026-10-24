import React from 'react'
import { Group, Record } from './CharacterStats'

const fmtDate = (iso) => {
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? ''
    : d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
}

export function versionLabel(version) {
  const m = /^\s*(\d+)\s*\.\s*(\d+)\s*$/.exec(String(version || ''))
  if (!m) return String(version || '')
  let n = Number(m[1])
  let letters = ''
  while (n > 0) {
    const rem = (n - 1) % 26
    letters = String.fromCharCode(65 + rem) + letters
    n = Math.floor((n - 1) / 26)
  }
  return `${letters || '?'}${m[2]}`
}

const STATUS_TEXT = {
  ok: 'соответствует приложению',
  step_behind: 'доступна новая ступень',
  level_behind: 'нужно обучение',
  newer: 'новее приложения',
}

export default function CharacterTraining({ training, name }) {
  const t = training || null
  const who = (name || '').trim() || 'персонаж'
  if (!t) {
    return (
      <div className="character-stats">
        <div className="character-stats-note">данные о подготовке недоступны</div>
      </div>
    )
  }
  const status = STATUS_TEXT[t.status] || ''
  const history = Array.isArray(t.history) ? t.history.filter((h) => h && h.to) : []
  const ok = t.status === 'ok'

  return (
    <div className="character-stats">
      <Group title="Уровень" />
      <div className="character-stats-records">
        <Record label="Подготовка файла" value={t.label || versionLabel(t.version)} />
        <Record label="Требует приложение"
          value={t.required_label || (t.required ? versionLabel(t.required) : '—')}
          sub={status}
          muted={ok} />
      </div>
      {!ok && t.message ? (
        <div className="character-stats-note">{t.message}</div>
      ) : null}

      <Group title="Аттестат" />
      {history.length === 0 ? (
        <div className="character-stats-note">
          дополнительного обучения ещё не было — базовая подготовка {t.label || versionLabel(t.version)}
        </div>
      ) : (
        <div className="character-stats-records">
          {history.slice().reverse().map((h, i) => (
            <Record key={`${h.at || ''}-${h.to}-${i}`}
              label={fmtDate(h.at) || '—'}
              value={`${versionLabel(h.from)} → ${versionLabel(h.to)}`}
              sub={h.notes || ''} />
          ))}
        </div>
      )}
      <div className="character-stats-note">
        {who} проходит обучение в тренере персонажа; каждая запись — пройденная ступень
      </div>
    </div>
  )
}
