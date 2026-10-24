import React, { useEffect, useState } from 'react'
import { EntriesLock } from './CharacterEntries'
import { api } from '../../lib/api'

const KIND_RU = { strength: 'сильная сторона', vulnerability: 'уязвимость', quirk: 'причуда' }

function kindLabel(t) {
  if (t.kind === 'quirk' && t.special) return 'особая причуда'
  return KIND_RU[t.kind] || t.kind
}

function fmtDate(sec) {
  const n = Number(sec)
  if (!n) return ''
  return new Date(n * 1000).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
}

export default function CharacterTraits({ section }) {
  const rateNote = (() => {
    const r = section && typeof section.goal_rate === 'number' ? section.goal_rate : null
    if (r == null) return 'тянет медленно'
    const pct = Math.round(r * 1000) / 10
    const stage = section.goal_stage_label ? ` при уважении ${section.goal_stage_label}` : ''
    return r <= 0
      ? `сейчас не действует${stage}`
      : `${pct}% за сессию${stage}${section.goal_override ? ', перекрывает встречный сигнал' : ''}`
  })()
  const poleTitle = (hint, wish) => (hint
    ? `Что тянет сюда: ${hint}\nКлик — пожелание (одно на все оси; ${rateNote}): ${wish}`
    : `пожелание: ${wish}`)
  const [goals, setGoals] = useState({})
  useEffect(() => {
    const next = {}
    for (const ax of (section && section.axes) || []) next[ax.key] = Number(ax.goal) || 0
    setGoals(next)
  }, [section])
  if (!section) return <div className="character-entries-empty">…</div>
  if (!section.unlocked) return <EntriesLock section={section} />
  const axes = section.axes || []
  const traits = section.traits || []
  const toggleGoal = async (ax, dir) => {
    const cur = goals[ax.key] || 0
    const want = cur === dir ? 0 : dir
    const prev = goals
    setGoals(() => (want ? { [ax.key]: want } : {}))
    try {
      const r = await api.setAxisGoal(ax.key, want)
      if (r && r.goals && typeof r.goals === 'object') setGoals({ ...r.goals })
      else if (r && typeof r.goal === 'number') setGoals((g) => ({ ...g, [ax.key]: r.goal }))
    } catch (e) {
      setGoals(prev)
    }
  }
  return (
    <div className="character-traits">
      {axes.length === 0 ? (
        <div className="character-entries-empty">Оси характера ещё не заданы.</div>
      ) : (
        <div className="character-axes">
          {axes.map((ax) => {
            const pct = Math.round(Math.max(0, Math.min(1, Number(ax.value) || 0)) * 100)
            const norm = ax.norm == null ? null : Math.round(Math.max(0, Math.min(1, Number(ax.norm))) * 100)
            const goal = goals[ax.key] || 0
            return (
              <div className="character-axis" key={ax.key}>
                <div className="character-axis-head">
                  <span className="character-axis-label">{ax.label}</span>
                  <span className="character-axis-percent">
                    {pct}%{norm != null && norm !== pct ? ` · норма ${norm}%` : ''}
                  </span>
                </div>
                <div className="character-axis-track" role="img"
                  aria-label={`${ax.label}: ${pct}% (${ax.left} → ${ax.right})`}>
                  <div className="character-axis-fill" style={{ width: `${pct}%` }} />
                  <div className="character-axis-dot" style={{ left: `${pct}%` }} />
                </div>
                <div className="character-axis-poles">
                  <span role="button" tabIndex={0}
                    title={goal === -1 ? 'снять пожелание' : poleTitle(ax.hint_down, ax.wish_down || ax.left)}
                    onClick={() => toggleGoal(ax, -1)}
                    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') toggleGoal(ax, -1) }}>
                    {goal === -1 ? '◀ ' : ''}{ax.left}
                  </span>
                  <span role="button" tabIndex={0}
                    title={goal === 1 ? 'снять пожелание' : poleTitle(ax.hint_up, ax.wish_up || ax.right)}
                    onClick={() => toggleGoal(ax, 1)}
                    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') toggleGoal(ax, 1) }}>
                    {ax.right}{goal === 1 ? ' ▶' : ''}
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      )}
      <div className="character-traits-title">Свойства</div>
      {traits.length === 0 ? (
        <div className="character-entries-empty">Сейчас активных свойств нет — они проявляются по событиям сессий.</div>
      ) : (
        <div className="character-trait-list">
          {traits.map((t) => (
            <div className={`character-trait is-${t.kind || 'vulnerability'}${t.special ? ' is-special' : ''}`} key={t.id}>
              <div className="character-entry-meta">
                <span className="character-trait-kind">{kindLabel(t)}</span>
                {t.innate
                  ? <span className="character-entry-date character-trait-innate">врождённая</span>
                  : (t.activated_at ? <span className="character-entry-date">{fmtDate(t.activated_at)}</span> : null)}
              </div>
              <div className="character-entry-text">{t.text || t.id}</div>
              {t.description ? <div className="character-trait-source">{t.description}</div> : null}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
