import React, { useState, useEffect, useRef } from 'react'
import { api } from '@/lib/api'
import { refreshCapabilities } from '@/lib/capabilities'

const STATE_TONE = {
  installing: 'info', starting: 'info',
  missing: 'warn', need_checkpoint: 'warn', disabled: 'warn',
  broken: 'error', engine_failed: 'error', nodes_missing: 'error',
}
const WAITING_STATES = new Set(['installing', 'starting'])
const RESTART_STATES = new Set(['engine_failed', 'nodes_missing'])

export default function ImageGenSetup() {
  const [st, setSt] = useState(null)
  const [consent, setConsent] = useState(false)
  const [note, setNote] = useState('')
  const [noteOk, setNoteOk] = useState(false)
  const [dropOver, setDropOver] = useState(false)
  const [cpPath, setCpPath] = useState('')
  const timer = useRef(null)
  const wasReady = useRef(null)

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
    if (!st) return undefined
    const waiting = st.installing || WAITING_STATES.has(st.drawing_state)
    timer.current = setTimeout(refresh, waiting ? 1500 : 10000)
    return () => { if (timer.current) clearTimeout(timer.current) }
  }, [st])
  useEffect(() => {
    if (!st) return
    const ready = st.drawing_state === 'ready'
    if (wasReady.current !== null && ready !== wasReady.current) refreshCapabilities(3)
    wasReady.current = ready
  }, [st])

  async function install() {
    const r = await api.imagegenInstall(consent)
    if (!r.started && r.error === 'agpl_consent_required') {
      setNote('Отметьте согласие на AGPL, чтобы продолжить.')
      return
    }
    if (!r.started && r.error === 'busy') {
      setNote(`Сейчас идёт ${r.busy_with || 'другая работа'} — повторите, когда закончится.`)
      return
    }
    setNote('')
    refresh()
  }

  async function restart() {
    const r = await api.imagegenRestart()
    if (!r.ok) {
      setNote(r.error === 'busy'
        ? `Сейчас идёт ${r.busy_with || 'другая работа'} — повторите, когда закончится.`
        : 'Не удалось перезапустить движок — попробуйте ещё раз.')
      return
    }
    setNote('')
    refresh()
  }

  async function pickCheckpoint() {
    setNoteOk(false)
    if (cpPath.trim()) { sendCheckpoint(cpPath.trim()); return }
    if (!window.maidlink?.pickFile) { setNote('Впишите путь к файлу .safetensors в поле слева.'); return }
    const path = await window.maidlink.pickFile('checkpoint')
    if (path) sendCheckpoint(path)
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

  const state = st.drawing_state || (st.drawing_available ? 'ready' : 'missing')
  if (state === 'ready') {
    return (
      <div className="settings-drawing">
        <div className="settings-drawing-status">
          Рисование работает. Стиль рисования (выбор и импорт по коду) — в окне гардероба.
        </div>
      </div>
    )
  }

  const progByKey = {}
  for (const p of st.progress || []) progByKey[p.key] = p
  const agplMissing = (st.agpl_components || []).filter((k) => (st.missing || []).includes(k))
  const needConsent = agplMissing.length > 0
  const lockBtn = needConsent && !consent
  const autoMissing = (st.components || []).filter((c) => !c.present && !c.user_provided)
  const broken = st.broken || []
  const canInstall = (autoMissing.length > 0 || broken.length > 0) && !st.installing
  const canRestart = RESTART_STATES.has(state) && !st.installing

  function rightLabel(c, p) {
    if (!p) {
      if (c.broken) return 'не работает'
      return c.present ? 'есть' : (c.user_provided ? 'ваш файл' : c.license)
    }
    return p.status === 'done' ? 'готово'
      : p.status === 'error' ? 'ошибка'
      : p.status === 'copying' ? 'копирование…'
      : p.status === 'pip' ? 'зависимости…'
      : p.status === 'verifying' ? 'проверка…'
      : p.status === 'extracting' ? 'распаковка…'
      : `${p.total ? Math.round((p.downloaded / p.total) * 100) : 0}%`
  }

  return (
    <div className="settings-imagegen">
      <div className={`settings-imagegen-status is-${STATE_TONE[state] || 'warn'}`}>
        {st.drawing_message}
        {st.drawing_detail && <div className="settings-imagegen-status-detail">{st.drawing_detail}</div>}
      </div>
      {(state === 'missing' || state === 'need_checkpoint') && (
        <div className="settings-imagegen-intro">
          Движок и вспомогательные модели качаются автоматически; <b>чекпойнт вы
          добавляете сами</b> — перетащите свой .safetensors.
        </div>
      )}

      {(st.components || []).map((c) => {
        const p = progByKey[c.key]
        const error = p?.status === 'error' ? p.error : (!p && c.broken ? c.error : '')
        return (
          <div key={c.key} className="settings-imagegen-component">
            <div className="settings-imagegen-component-row">
              <span>{c.broken && !p ? '✕ ' : c.present ? '✓ ' : '• '}{c.title}{c.agpl ? '  ⚠ AGPL' : ''}</span>
              <span className="settings-imagegen-component-state">{rightLabel(c, p)}</span>
            </div>
            {error && <div className="settings-imagegen-component-error">{error}</div>}

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
                  <button onClick={pickCheckpoint} className="settings-imagegen-button">Указать</button>
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
      {canInstall && (
        <button onClick={install} disabled={lockBtn} className="settings-imagegen-install">
          {autoMissing.length === 0 ? 'Починить' : 'Скачать и установить'}
        </button>
      )}
      {canRestart && (
        <button onClick={restart} className="settings-imagegen-install">Перезапустить движок</button>
      )}
      {note && <div className={`settings-imagegen-note${noteOk ? ' is-ok' : ''}`}>{note}</div>}
    </div>
  )
}
