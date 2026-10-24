import React from 'react'

const fmtN = (n) => (typeof n === 'number' && Number.isFinite(n) ? n.toLocaleString('ru-RU') : '—')

function Row({ earned, title, hint, tickets }) {
  return (
    <div className={`chat-gacha-how-row${earned ? ' is-earned' : ''}`} title={hint || ''}>
      <span className={`chat-gacha-how-mark${earned ? ' is-on' : ''}`}>{earned ? '✓' : '○'}</span>
      <span className="chat-gacha-how-text">
        {title}
        {hint ? <span className="chat-gacha-how-hint">{hint}</span> : null}
      </span>
      {typeof tickets === 'number' ? <span className="chat-gacha-how-tickets">+{fmtN(tickets)}</span> : null}
    </div>
  )
}

export default function GachaHowTo({ data, onBack }) {
  const tut = (data && data.tutorial) || []
  const rels = (data && data.relations) || []
  const hidden = (data && data.hidden) || []
  const hiddenTotal = (data && data.hidden_total) || 0
  const cap = (data && data.daily && data.daily.cap) || 21
  const perDay = (data && data.daily && data.daily.per_day) || 3
  const sphereEvery = (data && data.daily && data.daily.sphere_every) || 25
  return (
    <div className="chat-gacha-how">
      <div className="chat-gacha-how-head">
        <button className="chat-gacha-popover-back" onClick={onBack}>← Назад</button>
        <span className="chat-gacha-popover-title">Как получить билеты</span>
        {data ? <span className="chat-gacha-how-count">{fmtN(data.earned)} из {fmtN(data.total)}</span> : null}
      </div>
      {!data ? (
        <div className="chat-gacha-popover-note">Загружаем…</div>
      ) : (
        <>
          <div className="chat-gacha-how-group">
            <div className="chat-gacha-how-group-title">Каждый день</div>
            <Row earned title={`Билетов в день: ${fmtN(perDay)}, копятся до ${fmtN(cap)}`} />
            <Row earned title={`Каждый ${fmtN(sphereEvery)}-й открытый билет — ещё и сфера изменения`} />
          </div>
          <div className="chat-gacha-how-group">
            <div className="chat-gacha-how-group-title">Обучение</div>
            {tut.map((a) => <Row key={a.id} earned={a.earned} title={a.title} hint={a.hint} tickets={a.tickets} />)}
          </div>
          <div className="chat-gacha-how-group">
            <div className="chat-gacha-how-group-title">Отношения</div>
            <div className="chat-gacha-how-hint">За каждый новый уровень оси — столько билетов, какой уровень.</div>
            {rels.map((r) => (
              <div key={r.axis} className="chat-gacha-how-row">
                <span className="chat-gacha-how-text">{r.label}</span>
                <span className="chat-gacha-how-levels">
                  {(r.levels || []).map((l) => (
                    <span
                      key={l.id}
                      className={`chat-gacha-how-level${l.earned ? ' is-on' : ''}`}
                      title={l.earned ? `Уровень ${l.roman} — получено` : `Уровень ${l.roman}: +${l.tickets}`}
                    >
                      {l.roman}<small>+{l.tickets}</small>
                    </span>
                  ))}
                </span>
              </div>
            ))}
          </div>
          <div className="chat-gacha-how-group">
            <div className="chat-gacha-how-group-title">Скрытые · {fmtN(hidden.length)} из {fmtN(hiddenTotal)}</div>
            {hidden.map((a) => <Row key={a.id} earned title={a.title} hint={a.hint} tickets={a.tickets} />)}
            {hidden.length < hiddenTotal && (
              <div className="chat-gacha-how-hint">Ещё {fmtN(hiddenTotal - hidden.length)} — откроются, когда выполнишь.</div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
