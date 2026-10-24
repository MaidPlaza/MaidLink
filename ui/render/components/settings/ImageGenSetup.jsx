import React, { useState, useEffect, useRef } from 'react'
import { api } from '@/lib/api'

export default function ImageGenSetup() {
  const [st, setSt] = useState(null)
  const [consent, setConsent] = useState(false)
  const [note, setNote] = useState('')
  const [noteOk, setNoteOk] = useState(false)
  const [dropOver, setDropOver] = useState(false)
  const [cpPath, setCpPath] = useState('')
  const timer = useRef(null)

  async function refresh() {
    try { setSt(await api.imagegenStatus()) } catch {}
  }
  useEffect(() => {
    let alive = true
    let t = null
    let attempt = 0
    async function tick() {
      if (!alive) return
      try {
        const s = await api.imagegenStatus()
        if (alive) setSt(s)
      } catch {
        if (++attempt < 40 && alive) t = setTimeout(tick, 2000)
      }
    }
    tick()
    return () => { alive = false; if (t) clearTimeout(t); if (timer.current) clearTimeout(timer.current) }
  }, [])
  useEffect(() => {
    if (st && (st.installing)) timer.current = setTimeout(refresh, 1500)
    return () => { if (timer.current) clearTimeout(timer.current) }
  }, [st])

  async function install() {
    const r = await api.imagegenInstall(consent)
    if (!r.started && r.error === 'agpl_consent_required') {
      setNote('Отметьте согласие на AGPL, чтобы продолжить.')
      return
    }
    setNote('')
    refresh()
  }

  async function sendCheckpoint(path) {
    if (!path) return
    setNote(''); setNoteOk(false)
    const r = await api.imagegenCheckpoint(path)
    if (!r.ok) { setNote(r.error || 'не удалось принять файл'); return }
    setCpPath('')
    if (r.pipeline?.name) { setNoteOk(true); setNote(`Распознан: ${r.pipeline.name} — копирую…`) }
    setTimeout(refresh, 600)
  }
  function onDropCheckpoint(e) {
    e.preventDefault()
    setDropOver(false)
    setNoteOk(false)
    const f = e.dataTransfer?.files?.[0]
    if (!f) return
    if (!f.name.toLowerCase().endsWith('.safetensors')) { setNote('Нужен файл .safetensors'); return }
    const path = window.maidlink?.getPathForFile?.(f)
    if (path) sendCheckpoint(path)
    else setNote('Перетаскивание доступно в приложении; в браузере укажите путь вручную ниже.')
  }

  if (!st) return <div className="settings-imagegen is-loading">Проверяю модуль рисования…</div>

  const progByKey = {}
  for (const p of st.progress || []) progByKey[p.key] = p
  const agplMissing = (st.agpl_components || []).filter((k) => (st.missing || []).includes(k))
  const needConsent = agplMissing.length > 0
  const lockBtn = needConsent && !consent
  const autoMissing = (st.components || []).filter((c) => !c.present && !c.user_provided)

  function rightLabel(c, p) {
    if (!p) return c.present ? 'есть' : (c.user_provided ? 'ваш файл' : c.license)
    return p.status === 'done' ? 'готово'
      : p.status === 'error' ? 'ошибка'
      : p.status === 'copying' ? 'копирование…'
      : p.status === 'pip' ? 'зависимости…'
      : p.status === 'extracting' ? 'распаковка…'
      : `${p.total ? Math.round((p.downloaded / p.total) * 100) : 0}%`
  }

  return (
    <div className="settings-imagegen">
      {st.installed && !st.drawing_available && (
        <div className="settings-imagegen-ready">
          ✅ Всё на месте. <b>Перезапустите приложение</b>, чтобы включить рисование.
        </div>
      )}
      {!st.installed && (
        <div className="settings-imagegen-intro">
          Модуль рисования не установлен. Движок и вспомогательные модели качаются
          автоматически; <b>чекпойнт вы добавляете сами</b> — перетащите свой .safetensors.
        </div>
      )}

      {(st.components || []).map((c) => {
        const p = progByKey[c.key]
        return (
          <div key={c.key} className="settings-imagegen-component">
            <div className="settings-imagegen-component-row">
              <span>{c.present ? '✓ ' : '• '}{c.title}{c.agpl ? '  ⚠ AGPL' : ''}</span>
              <span className="settings-imagegen-component-state">{rightLabel(c, p)}</span>
            </div>
            {p && p.status === 'error' && <div className="settings-imagegen-component-error">{p.error}</div>}

            {c.user_provided && !c.present && !p && (
              <div className="settings-imagegen-checkpoint">
                <div
                  onDragOver={(e) => { e.preventDefault(); setDropOver(true) }}
                  onDragLeave={() => setDropOver(false)}
                  onDrop={onDropCheckpoint}
                  className={`settings-imagegen-drop${dropOver ? ' is-over' : ''}`}
                >Перетащите сюда свой <b>.safetensors</b></div>
                <div className="settings-imagegen-path">
                  <input value={cpPath} onChange={(e) => setCpPath(e.target.value)}
                    placeholder="…или путь к файлу" className="settings-imagegen-input" />
                  <button onClick={() => sendCheckpoint(cpPath.trim())} className="settings-imagegen-button">Указать</button>
                </div>
              </div>
            )}
          </div>
        )
      })}

      {needConsent && !st.installing && (
        <label className="settings-imagegen-consent">
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
          <span>Согласен(на) установить AGPL-компоненты ({agplMissing.join(', ')}) — детейлер лица под AGPL-3.0.</span>
        </label>
      )}
      {autoMissing.length > 0 && !st.installing && (
        <button onClick={install} disabled={lockBtn} className="settings-imagegen-install">
          Скачать и установить движок
        </button>
      )}
      {st.installing && <div className="settings-imagegen-installing">Установка идёт… (можно закрыть настройки)</div>}
      {note && <div className={`settings-imagegen-note${noteOk ? ' is-ok' : ''}`}>{note}</div>}
    </div>
  )
}
