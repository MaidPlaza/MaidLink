import React, { useState, useEffect, useCallback } from 'react'
import { api } from '@/lib/api'
import { useSetting, hydrateBackendSettings } from '@/lib/settings'
import Dropdown from './Dropdown'
import { REASONING_MODE_OPTIONS, REASONING_MODE_SHORT } from './modelOptions'

const fmtK = (n) => `${Math.round((n || 0) / 1024)}k`
const fmtTok = (n) => `${Math.round((n || 0) / 1000)}k`
const fmtGB = (n) => `${((n || 0) / 1024 ** 3).toFixed(1)} ГБ`
const fmtGiB = (mib) => `${((mib || 0) / 1024).toFixed(1)} ГБ`
const shortModel = (label) => String(label || '').replace(/\s*\(.*\)\s*$/, '')
const FIT_ICON = { full: '✓', partial: '◐', poor: '▽', none: '✕' }


function SpeedDots({ value }) {
  const v = Math.max(0, Math.min(4, Number(value) || 0))
  return (
    <span className="model-preset-speed-dots" title={`${v} из 4`}>
      {[1, 2, 3, 4].map((i) => <i key={i} className={i <= v ? 'on' : ''} />)}
    </span>
  )
}

function PresetDownload({ p, onDownload }) {
  const dl = p.download
  const active = dl && dl.status === 'downloading'
  const failed = dl && dl.status === 'error'
  const pct = active && dl.total > 0 ? Math.min(100, Math.floor((dl.downloaded / dl.total) * 100)) : 0
  if (!p.downloadable) {
    return <div className="model-preset-fit fit-missing">Файл модели не найден</div>
  }
  return (
    <div className="model-preset-download" onClick={(e) => e.stopPropagation()}>
      {active ? (
        <>
          <div className="model-preset-line">{pct}% · {fmtGB(dl.downloaded)} / {fmtGB(dl.total)}</div>
          <div className="model-download-bar"><div style={{ width: `${pct}%` }} /></div>
        </>
      ) : (
        <>
          <div className="model-preset-fit fit-missing">Не скачана · {fmtGB(p.download_size)}</div>
          <button type="button" className="model-download-button" onClick={() => onDownload(p.model)}>
            {failed ? 'Повторить' : 'Скачать'}
          </button>
          {failed && (
            <div className="model-download-error">
              {dl.error || 'Загрузка не удалась.'} Докачка продолжится с места обрыва.
            </div>
          )}
        </>
      )}
    </div>
  )
}

function PresetCard({ p, active, busy, onChoose, onDownload }) {
  const [mode] = useSetting('llm.reasoning_mode')
  const hasModel = !!p.model
  const info = hasModel ? p : p.current
  const unavailable = hasModel && !p.available
  const cls = ['model-preset', active ? 'is-active' : '', unavailable ? 'is-unavailable' : '', busy ? 'is-busy' : '']
    .filter(Boolean).join(' ')
  const curMode = hasModel ? p.reasoning_mode : String(mode || info?.reasoning_mode || '')
  return (
    <div className={cls} role="button" tabIndex={0}
      onClick={() => onChoose(p)}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onChoose(p) } }}
    >
      <div className="model-preset-title">
        <span className="model-preset-dot" />
        <span>{p.label}</span>
        {info && info.experimental && <span className="model-preset-badge">эксперимент</span>}
      </div>
      <div className="model-preset-summary">{p.summary}</div>
      {info && (
        <>
          <div className="model-preset-line" title={info.model_label}>
            {hasModel ? '' : 'Сейчас: '}<b>{shortModel(info.model_label)}</b>
            {hasModel ? '' : ` · ${fmtK(info.ctx)}`}
            {curMode ? ` · ${REASONING_MODE_SHORT[curMode] || curMode}` : ''}
            {info.vision ? ' · vision' : ''}
          </div>
          <div className="model-preset-line">
            Видеопамять ~{fmtGiB(info.need_mib)}{hasModel ? ` · окно ${fmtK(info.ctx)}` : ''}
          </div>
          {hasModel && (
            <div className="model-preset-line model-preset-speed">
              Скорость <SpeedDots value={p.speed} />
            </div>
          )}
          {unavailable
            ? <PresetDownload p={p} onDownload={onDownload} />
            : (
              <div className={`model-preset-fit fit-${info.fit}`} title={`~${fmtGiB(info.need_mib)} нужно`}>
                {FIT_ICON[info.fit] || ''} {info.note}
              </div>
            )}
        </>
      )}
    </div>
  )
}

export default function ModelSettings() {
  const [data, setData] = useState(null)
  const [current, setCurrent] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)

  const loadPresets = useCallback(async () => {
    try {
      const r = await api.modelPresets()
      if (r && Array.isArray(r.presets) && r.presets.length) {
        setData(r)
        setCurrent(r.current || 'custom')
        return true
      }
    } catch {
    }
    return false
  }, [])

  useEffect(() => {
    let cancelled = false
    let attempt = 0
    async function tick() {
      if (cancelled) return
      const ok = await loadPresets()
      if (cancelled) return
      if (ok) { setLoaded(true); return }
      if (++attempt >= 30) { setLoaded(true); return }
      setTimeout(tick, 2000)
    }
    tick()
    return () => { cancelled = true }
  }, [loadPresets])

  const downloadingNow = !!(data && data.presets.some(
    (p) => p.download && p.download.status === 'downloading'))
  useEffect(() => {
    if (!downloadingNow) return
    const t = setInterval(() => { loadPresets() }, 1500)
    return () => clearInterval(t)
  }, [downloadingNow, loadPresets])

  async function choosePreset(p) {
    if (!p || busy) return
    if (p.model && !p.available) {
      setNote(p.downloadable
        ? 'Модель пресета не скачана — нажми «Скачать» на панельке.'
        : 'Файл модели этого пресета не найден.')
      return
    }
    if (p.key === current) return
    setBusy(true)
    const prev = current
    setCurrent(p.key)
    setNote(p.model ? 'Применяю пресет — модель загрузится на следующем сообщении…' : '')
    try {
      const r = await api.applyModelPreset(p.key)
      if (r && r.error) {
        setNote(`Не удалось: ${r.error}`)
        setCurrent(prev)
      } else {
        setCurrent((r && r.current) || p.key)
        setNote(p.model
          ? `${(r && r.label) || p.label}: ${(r && r.model_label) || ''}. `
            + (r && r.restart ? 'Загрузится на следующем сообщении.' : 'Уже активна.')
          : 'Пользовательский режим — настрой модель ниже.')
        hydrateBackendSettings(1, 0)
      }
      await loadPresets()
    } catch {
      setNote('Не удалось применить пресет.')
      setCurrent(prev)
    } finally {
      setBusy(false)
    }
  }

  async function startDownload(modelKey) {
    setNote('')
    try {
      const r = await api.downloadModel(modelKey)
      if (r && r.error) { setNote(`Не удалось: ${r.error}`); return }
      await loadPresets()
    } catch {
      setNote('Не удалось начать загрузку.')
    }
  }

  const machine = data && data.machine
  return (
    <div className="model-settings">
      {data && (
        <div className="model-presets">
          {data.presets.map((p) => (
            <PresetCard key={p.key} p={p} active={p.key === current} busy={busy}
              onChoose={choosePreset} onDownload={startDownload} />
          ))}
        </div>
      )}
      {machine && (
        <div className="model-presets-machine">
          {machine.gpu_available
            ? `${machine.gpu} · ${fmtGiB(machine.vram_mib)} видеопамяти`
            : 'Видеокарта NVIDIA не найдена'}
          {machine.ram_mib > 0 ? ` · ${fmtGiB(machine.ram_mib)} оперативной` : ''}
          {' · оценка ±1 ГБ'}
        </div>
      )}
      {!loaded && !data && (
        <div className="model-settings-note">Загрузка пресетов…</div>
      )}
      {loaded && !data && (
        <div className="model-settings-error">
          Список пресетов не получен.{' '}
          <span onClick={() => { setLoaded(false); loadPresets().then(() => setLoaded(true)) }}
            className="model-settings-retry">
            Повторить
          </span>
          {' '}— или перезапусти бэкенд (нужен эндпоинт /api/models/presets).
        </div>
      )}
      {note && <div className="model-settings-note">{note}</div>}
      {current === 'custom' && <ModelDetails onChanged={loadPresets} />}
    </div>
  )
}

function ModelDetails({ onChanged }) {
  const [models, setModels] = useState([])
  const [current, setCurrent] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [ctxIdx, setCtxIdx] = useState(-1)
  const [mode, setMode] = useSetting('llm.reasoning_mode')

  async function load(light = false) {
    try {
      const r = await api.models()
      if (r && Array.isArray(r.models) && r.models.length) {
        setModels(r.models)
        setCurrent(r.current || '')
        if (!light) syncCtxIdx(r.models, r.current || '')
        return true
      }
    } catch {
    }
    return false
  }

  const downloadingNow = models.some(
    (m) => m.download && m.download.status === 'downloading')
  useEffect(() => {
    if (!downloadingNow) return
    const t = setInterval(() => { load(true) }, 1500)
    return () => clearInterval(t)
  }, [downloadingNow])

  async function startDownload(key) {
    setNote('')
    try {
      const r = await api.downloadModel(key)
      if (r && r.error) { setNote(`Не удалось: ${r.error}`); return }
      await load(true)
    } catch {
      setNote('Не удалось начать загрузку.')
    }
  }

  function stepsOf(list, key) {
    const m = (list || []).find((x) => x.key === key)
    return (m && Array.isArray(m.ctx_steps)) ? m.ctx_steps : []
  }
  function syncCtxIdx(list, key) {
    const m = (list || []).find((x) => x.key === key)
    const steps = stepsOf(list, key)
    const i = steps.findIndex((s) => s.ctx === (m && m.ctx_current))
    setCtxIdx(i)
  }

  useEffect(() => {
    let cancelled = false
    let attempt = 0
    async function tick() {
      if (cancelled) return
      const ok = await load()
      if (cancelled) return
      if (ok) { setLoaded(true); return }
      if (++attempt >= 30) { setLoaded(true); return }
      setTimeout(tick, 2000)
    }
    tick()
    return () => { cancelled = true }
  }, [])

  async function manualRetry() {
    setNote('')
    setLoaded(false)
    await load()
    setLoaded(true)
  }

  async function switchTo(choice) {
    if (!choice || choice === current || busy) return
    const m = models.find((x) => x.key === choice)
    if (m && !m.available) {
      setNote(m.downloadable
        ? 'Модель не скачана — нажми «Скачать» ниже.'
        : 'Файл этой модели не скачан.')
      return
    }
    setBusy(true)
    setCurrent(choice)
    syncCtxIdx(models, choice)
    setNote('Переключаю модель — загрузится на следующем сообщении…')
    try {
      const r = await api.switchModel(choice)
      if (r && r.error) {
        setNote(`Не удалось: ${r.error}`)
        await load()
      } else {
        setNote(`Активна: ${(r && r.label) || choice}. Загрузится на следующем сообщении.`)
        if (onChanged) onChanged()
      }
    } catch {
      setNote('Не удалось переключить модель.')
      await load()
    } finally {
      setBusy(false)
    }
  }

  async function commitCtx(idx) {
    const steps = stepsOf(models, current)
    const step = steps[idx]
    const m = models.find((x) => x.key === current)
    if (!step || busy || !m || step.ctx === m.ctx_current) return
    setBusy(true)
    setNote(`Окно ${fmtK(step.ctx)} — применится на следующем сообщении…`)
    try {
      const r = await api.setModelCtx(step.ctx)
      if (r && r.ok) {
        setModels((prev) => prev.map((x) =>
          x.key === current ? { ...x, ctx_current: r.ctx } : x))
        setNote(`Окно ${fmtK(r.ctx)} · память диалога ≈${fmtTok(r.hist)} ток. `
          + 'Применится на следующем сообщении.')
        if (onChanged) onChanged()
      } else {
        setNote(`Не удалось: ${(r && r.error) || 'ошибка'}`)
        await load()
      }
    } catch {
      setNote('Не удалось поменять окно контекста.')
      await load()
    } finally {
      setBusy(false)
    }
  }

  const options = models.map((m) => ({
    value: m.key,
    label: m.available ? m.label
      : `${m.label} — ${m.downloadable ? 'не скачана' : 'нет файла'}`,
  }))
  const ctxSteps = stepsOf(models, current)
  const ctxStep = ctxIdx >= 0 ? ctxSteps[ctxIdx] : null
  const toDownload = models.filter((m) => !m.available && m.downloadable)

  return (
    <div className="model-details">
      <div className="model-details-row">
        <span className="model-details-label">Модель</span>
        <Dropdown
          value={current}
          options={options}
          onChange={switchTo}
          className="model-details-dropdown"
        />
      </div>
      {ctxSteps.length > 1 && ctxStep && (
        <div className="model-details-group">
          <div className="model-details-row">
            <span className="model-details-label">Окно контекста</span>
            <span className="model-details-label model-details-value">
              {fmtK(ctxStep.ctx)} · диалог ≈{fmtTok(ctxStep.hist)}
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={ctxSteps.length - 1}
            step={1}
            value={ctxIdx}
            disabled={busy}
            onChange={(e) => setCtxIdx(Number(e.target.value))}
            onPointerUp={(e) => commitCtx(Number(e.target.value))}
            onKeyUp={(e) => {
              if (e.key.startsWith('Arrow') || e.key === 'Home' || e.key === 'End') {
                commitCtx(Number(e.target.value))
              }
            }}
            className="model-details-range"
          />
          <div className="model-details-ticks">
            {ctxSteps.map((s) => (
              <span
                key={s.ctx}
                className={`model-details-label model-details-tick${s.ctx === ctxStep.ctx ? ' is-current' : ''}`}
              >
                {fmtK(s.ctx)}
              </span>
            ))}
          </div>
        </div>
      )}
      <div className="model-details-row model-details-group">
        <span className="model-details-label">Режим рассуждений</span>
        <Dropdown
          value={mode}
          options={REASONING_MODE_OPTIONS}
          onChange={setMode}
          className="model-details-dropdown"
        />
      </div>
      {toDownload.length > 0 && (
        <div className="model-details-downloads">
          {toDownload.map((m) => {
            const dl = m.download
            const active = dl && dl.status === 'downloading'
            const failed = dl && dl.status === 'error'
            const pct = active && dl.total > 0
              ? Math.min(100, Math.floor((dl.downloaded / dl.total) * 100)) : 0
            return (
              <div key={m.key}>
                <div className="model-details-row">
                  <span className="model-details-label model-details-download-label">{m.label}</span>
                  {active ? (
                    <span className="model-details-label model-details-download-progress">
                      {pct}% · {fmtGB(dl.downloaded)} / {fmtGB(dl.total)}
                    </span>
                  ) : (
                    <button onClick={() => startDownload(m.key)} className="model-download-button">
                      {failed ? 'Повторить' : 'Скачать'} {fmtGB(m.download_size)}
                    </button>
                  )}
                </div>
                {active && (
                  <div className="model-download-bar model-details-download-bar">
                    <div style={{ width: `${pct}%` }} />
                  </div>
                )}
                {failed && (
                  <div className="model-download-error model-details-download-error">
                    {dl.error || 'Загрузка не удалась.'} Докачка продолжится с места обрыва.
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
      {!loaded && models.length === 0 && (
        <div className="model-settings-note">Загрузка списка моделей…</div>
      )}
      {loaded && models.length === 0 && (
        <div className="model-settings-error">
          Список моделей не получен.{' '}
          <span onClick={manualRetry} className="model-settings-retry">
            Повторить
          </span>
          {' '}— или перезапусти бэкенд (нужен эндпоинт /api/models).
        </div>
      )}
      {note && <div className="model-settings-note">{note}</div>}
    </div>
  )
}
