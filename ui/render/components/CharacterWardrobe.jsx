import React, { useCallback, useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { sendCommand } from '@/lib/commandBus'
import { useCapability } from '@/lib/capabilities'
import CharacterInformationSectionItem from './CharacterInformationSectionItem'
import CharacterStyling from './CharacterStyling'

const POLL_MS = 4000
const fmtN = (n) => (typeof n === 'number' && Number.isFinite(n) ? n.toLocaleString('ru-RU') : '—')

const STYLE_SOURCE_RU = { builtin: 'встроенный', user_imported: 'импортированный' }

function statusOf(o) {
  if (o.preparing) return { cls: 'is-preparing', text: `готовится ${o.done}/${o.total}` }
  if (o.prepared) return o.current ? { cls: 'is-current', text: 'надет' } : { cls: 'is-ready', text: 'готов' }
  if (o.queued) return { cls: 'is-queued', text: 'в очереди' }
  return { cls: 'is-idle', text: 'не подготовлен' }
}

function StatusTag({ o }) {
  const st = statusOf(o)
  return <span className={`character-wardrobe-tag ${st.cls}`}>{st.text}</span>
}

function PrepareButton({ o, busy, onPrepare }) {
  if (o.prepared) return null
  const label = o.preparing ? `${o.done}/${o.total}…` : o.queued ? 'Начать сейчас' : 'Подготовить'
  const disabled = o.preparing || busy
  return (
    <button
      type="button"
      className="character-wardrobe-btn"
      disabled={disabled}
      onClick={() => !disabled && onPrepare(o.id)}
      title={o.queued && !o.preparing
        ? 'Готовить прямо сейчас (~10 минут, чат будет недоступен)'
        : 'Добавить в очередь подготовки (в свободное время между сессиями)'}
    >
      {label}
    </button>
  )
}

function RegenerateButton({ o, busy, onRegenerate }) {
  const [armed, setArmed] = useState(false)
  useEffect(() => {
    if (!armed) return
    const t = setTimeout(() => setArmed(false), 3500)
    return () => clearTimeout(t)
  }, [armed])
  if (!o.prepared || o.protected) return null
  const disabled = o.preparing || busy
  const click = () => {
    if (disabled) return
    if (!armed) { setArmed(true); return }
    setArmed(false)
    onRegenerate(o.id)
  }
  return (
    <button
      type="button"
      className={`character-wardrobe-btn${armed ? ' is-armed' : ''}`}
      disabled={disabled}
      onClick={click}
      onBlur={() => setArmed(false)}
      title={o.current
        ? 'Удалить набор и сгенерировать заново. Костюм сейчас надет — персонаж вернётся в обычный наряд.'
        : 'Удалить набор и сгенерировать заново (в очередь фоновой подготовки).'}
    >
      {armed ? 'Удалить?' : '↻ Заново'}
    </button>
  )
}

function DeleteStyleButton({ s, onDelete }) {
  const [armed, setArmed] = useState(false)
  useEffect(() => {
    if (!armed) return
    const t = setTimeout(() => setArmed(false), 3500)
    return () => clearTimeout(t)
  }, [armed])
  const click = () => {
    if (!armed) { setArmed(true); return }
    setArmed(false)
    onDelete(s)
  }
  return (
    <button
      type="button"
      className={`character-wardrobe-btn${armed ? ' is-armed' : ''}`}
      onClick={click}
      onBlur={() => setArmed(false)}
      title="Удалить импортированный стиль из списка"
    >
      {armed ? 'Удалить?' : 'Удалить'}
    </button>
  )
}

function wornByCategory(styling) {
  const out = []
  for (const c of (styling && styling.categories) || []) {
    const items = (c.items || []).filter((it) => it.worn)
    if (items.length) out.push({ key: c.key, label: c.label, items })
  }
  return out
}

function wornDetail(it) {
  return it.worn_as && it.worn_as !== it.tag ? it.worn_as : ''
}

export default function CharacterWardrobe() {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [styles, setStyles] = useState([])
  const [styleActive, setStyleActive] = useState('')
  const [styleCode, setStyleCode] = useState('')
  const [styleNote, setStyleNote] = useState('')
  const drawingAvailable = useCapability('drawing')

  const refresh = useCallback(() => {
    api.wardrobe()
      .then((d) => { setData(d); setError('') })
      .catch((e) => setError(String(e)))
    api.drawingStyles()
      .then((r) => {
        if (r && Array.isArray(r.styles)) { setStyles(r.styles); setStyleActive(r.active || '') }
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, POLL_MS)
    return () => clearInterval(t)
  }, [refresh])

  const onPrepare = useCallback((outfitId) => {
    setBusy(true)
    setNotice('')
    api.prepareOutfit(outfitId)
      .then((d) => {
        if (d && d.status === 'busy' && d.busy_with) {
          setNotice(`Сейчас идёт ${d.busy_with} — начать подготовку можно после завершения.`)
        }
        refresh()
      })
      .catch((e) => setError(String(e)))
      .finally(() => setBusy(false))
  }, [refresh])

  const onRegenerate = useCallback((outfitId) => {
    setBusy(true)
    setNotice('')
    api.regenerateOutfit(outfitId)
      .then((d) => {
        if (d && d.status === 'busy') {
          setNotice('Этот набор сейчас рендерится — перегенерировать можно после завершения.')
        }
        refresh()
      })
      .catch((e) => setError(String(e)))
      .finally(() => setBusy(false))
  }, [refresh])

  const applyStyle = useCallback((id) => {
    if (!id || id === styleActive) return
    setStyleActive(id)
    sendCommand(`/style ${id}`)
    setStyleNote(id === 'default'
      ? 'Возвращаю обычный стиль — из архива, быстро.'
      : 'Меняю стиль: гардероб сбрасывается, два базовых наряда рисуются заново (~20 мин, чат недоступен).')
    setTimeout(refresh, 1500)
  }, [styleActive, refresh])

  const deleteStyle = useCallback((s) => {
    const name = s.name || s.id
    api.deleteDrawingStyle(s.id)
      .then((d) => {
        setStyleNote(d && d.ok ? `Стиль «${name}» удалён.`
          : `Стиль «${name}» не удалён: ${(d && d.error) || 'неизвестная ошибка'}.`)
        refresh()
      })
      .catch((e) => setStyleNote(`Стиль «${name}» не удалён: ${e}`))
  }, [refresh])

  const applyCode = useCallback(() => {
    const c = styleCode.trim()
    if (!c) return
    if (!c.startsWith('artstyle:')) {
      setStyleNote('Код стиля должен начинаться с «artstyle:».')
      return
    }
    sendCommand(`/style ${c}`)
    setStyleNote('Импортирую код стиля — он станет активным: гардероб сбрасывается, базовые наряды рисуются заново.')
    setStyleCode('')
    setTimeout(refresh, 2000)
  }, [styleCode, refresh])

  const outfits = (data && data.outfits) || []
  const styling = (data && data.styling) || null
  const current = (data && data.current_outfit) || null
  const worn = wornByCategory(styling)
  const wornCount = worn.reduce((n, c) => n + c.items.length, 0)
  const ready = outfits.filter((o) => o.prepared).length
  const queued = outfits.filter((o) => o.queued && !o.prepared && !o.preparing).length
  const preparingNow = outfits.find((o) => o.preparing) || null

  return (
    <div className='character-information-main-container character-wardrobe'>
        <div className='character-information-list'>
            <div className="character-wardrobe-hero">
              <div className="character-wardrobe-hero-kicker"><span>Текущий облик</span><i aria-hidden="true" /></div>
              <div className="character-wardrobe-hero-title">
                {current ? current.name : (data ? 'Наряд не определён' : '…')}
              </div>
              <div className="character-wardrobe-hero-meta">
                {current ? <span className="character-wardrobe-tag is-current">надет</span> : null}
                {current && current.default ? <span>обычный наряд</span> : null}
                {current ? <span className="character-wardrobe-id">{current.id}</span> : null}
                {!current && data ? <span>рисование выключено или у персонажа нет костюма</span> : null}
              </div>
              <div className="character-wardrobe-hero-kicker is-sub">
                <span>Образ{wornCount ? ` · ${fmtN(wornCount)}` : ''}</span><i aria-hidden="true" />
              </div>
              {worn.length ? (
                <div className="character-wardrobe-hero-look">
                  {worn.map((c) => (
                    <React.Fragment key={c.key}>
                      <span className="character-wardrobe-hero-look-label">{c.label}</span>
                      <span className="character-wardrobe-hero-look-chips">
                        {c.items.map((it) => (
                          <span key={it.tag} className={`character-styling-chip is-${it.rarity || 'common'} is-worn`} title={it.tag}>
                            {it.label || it.tag}
                            {wornDetail(it) ? <em className="character-wardrobe-worn-as">({wornDetail(it)})</em> : null}
                          </span>
                        ))}
                      </span>
                    </React.Fragment>
                  ))}
                </div>
              ) : (
                <div className="character-wardrobe-hero-muted">{data ? 'Ничего сверх костюма — образ базовый.' : '…'}</div>
              )}
              <div className="character-stats-note">
                Переодевание и смена образа — только через персонажа: попроси в чате. Для переодевания костюм должен быть подготовлен.
              </div>
            </div>

            <CharacterInformationSectionItem title="КОСТЮМЫ" defaultOpen>
                <div className="character-wardrobe-outfits">
                  <div className="character-wardrobe-head">
                    <span>
                      Готово <b>{fmtN(ready)}</b> из {fmtN(outfits.length)}
                      {queued ? ` · в очереди ${fmtN(queued)}` : ''}
                    </span>
                    {preparingNow ? (
                      <span className="character-wardrobe-head-note">готовится: {preparingNow.name}</span>
                    ) : null}
                  </div>
                  {error ? <div className="character-wardrobe-error">Гардероб недоступен: {error}</div> : null}
                  {notice ? <div className="character-wardrobe-notice">{notice}</div> : null}
                  {outfits.length === 0 && !error ? (
                    <div className="character-entries-empty">{data ? 'Доступных костюмов пока нет.' : '…'}</div>
                  ) : null}
                  {outfits.map((o) => (
                    <div className={`character-wardrobe-row${o.current ? ' is-current' : ''}`} key={o.id}>
                      <div className="character-wardrobe-row-main">
                        <span className="character-wardrobe-name">{o.name}</span>
                        <span className="character-wardrobe-id">{o.id}</span>
                      </div>
                      <div className="character-wardrobe-row-side">
                        <StatusTag o={o} />
                        <PrepareButton o={o} busy={busy} onPrepare={onPrepare} />
                        <RegenerateButton o={o} busy={busy} onRegenerate={onRegenerate} />
                      </div>
                    </div>
                  ))}
                  <div className="character-stats-note">
                    Подготовленный костюм — полный набор портретов, переодевание в него мгновенно. «Подготовить» ставит в очередь на свободное время между сессиями; повторное нажатие — начать сейчас (~10 минут, чат будет занят).
                  </div>
                </div>
            </CharacterInformationSectionItem>
            <CharacterInformationSectionItem title="СТАЙЛИНГ" defaultOpen>
                {styling
                  ? <CharacterStyling
                      section={styling}
                      onSectionChange={(st) => setData((d) => (d ? { ...d, styling: st } : d))}
                    />
                  : <div className="character-entries-empty">{data ? 'Стайлинг для этого персонажа недоступен.' : '…'}</div>}
            </CharacterInformationSectionItem>
            <CharacterInformationSectionItem title="СТИЛЬ РИСОВАНИЯ" defaultOpen>
                <div className="character-wardrobe-styles">
                  {!drawingAvailable ? (
                    <div className="character-entries-empty">
                      Модуль рисования не подключён — подключить можно в настройках (Drawing).
                    </div>
                  ) : (
                    <>
                      {styles.length === 0 ? <div className="character-entries-empty">…</div> : null}
                      {styles.map((s) => (
                        <div className={`character-wardrobe-row${s.id === styleActive ? ' is-current' : ''}`} key={s.id}>
                          <div className="character-wardrobe-row-main">
                            <span className="character-wardrobe-name">{s.name || s.id}</span>
                            <span className="character-wardrobe-id">{s.id}</span>
                            {s.source ? (
                              <span className="character-wardrobe-hint">{STYLE_SOURCE_RU[s.source] || s.source}</span>
                            ) : null}
                          </div>
                          <div className="character-wardrobe-row-side">
                            {s.id === styleActive ? (
                              <span className="character-wardrobe-tag is-current">активен</span>
                            ) : (
                              <>
                                <button
                                  type="button"
                                  className="character-wardrobe-btn"
                                  onClick={() => applyStyle(s.id)}
                                  title={s.id === 'default'
                                    ? 'Вернуть обычный стиль (из архива, быстро)'
                                    : 'Сменить стиль: гардероб сбросится, два базовых наряда нарисуются заново (~20 минут, чат недоступен)'}
                                >
                                  Выбрать
                                </button>
                                {s.source === 'user_imported' ? (
                                  <DeleteStyleButton s={s} onDelete={deleteStyle} />
                                ) : null}
                              </>
                            )}
                          </div>
                        </div>
                      ))}
                      <div className="character-wardrobe-import">
                        <input
                          className="character-wardrobe-input"
                          value={styleCode}
                          onChange={(e) => setStyleCode(e.target.value)}
                          onKeyDown={(e) => { if (e.key === 'Enter') applyCode() }}
                          placeholder="artstyle:v1:… — код стиля для импорта"
                        />
                        <button type="button" className="character-wardrobe-btn" onClick={applyCode}>Импорт</button>
                      </div>
                      {styleNote ? <div className="character-wardrobe-notice">{styleNote}</div> : null}
                      <div className="character-stats-note">
                        Стиль привязан к костюмам: при смене подготовленные наборы сбрасываются, два базовых наряда рисуются заново (~20 минут, чат недоступен); возврат к обычному стилю — из архива, быстро. Импорт кода добавляет стиль и сразу делает его активным. Импортированный стиль можно удалить, если он не выбран ни у одного персонажа.
                      </div>
                    </>
                  )}
                </div>
            </CharacterInformationSectionItem>
        </div>
    </div>
  )
}
