import React, { useState, useEffect, useRef } from 'react'
import { api } from '@/lib/api'
import maidLinkLogo from '../../assets/logo/MaidLink.svg'
import loadingBars from '../../assets/logo/LoadingBars.svg'
import termsText from 'virtual:terms'

function fmtGB(bytes) {
  return (bytes / 1024 / 1024 / 1024).toFixed(1)
}

function SectionTitle({ children }) {
  return (
    <div className="setup-wizard-section">
      <span className="setup-wizard-section-dots" />
      <span className="setup-wizard-section-line" />
      <span className="setup-wizard-section-label">{children}</span>
      <span className="setup-wizard-section-line" />
      <span className="setup-wizard-section-dots" />
    </div>
  )
}

function QuoteBox({ children }) {
  return (
    <div className="setup-wizard-quote">
      <svg className="setup-wizard-quote-mark setup-wizard-quote-mark--open"
           width="13" height="11" viewBox="25 0 13 11" xmlns="http://www.w3.org/2000/svg">
        <path d="M36.7 11C37.0448 11 37.3755 10.8712 37.6192 10.642C37.863 10.4128 38 10.1019 38 9.77778V6.79311C38 6.46896 37.863 6.15808 37.6192 5.92887C37.3755 5.69966 37.0448 5.57089 36.7 5.57089H34.8957C34.8957 5.14148 34.9225 4.71207 34.9763 4.28267C35.0569 3.828 35.1912 3.42385 35.3792 3.07022C35.5673 2.71659 35.8095 2.43833 36.1059 2.23544C36.4006 2.00811 36.7767 1.89444 37.2343 1.89444V0C36.4821 0 35.8234 0.151556 35.2583 0.454667C34.6972 0.753958 34.2151 1.16839 33.8479 1.66711C33.4782 2.21607 33.206 2.81794 33.0419 3.44911C32.876 4.14546 32.7949 4.8573 32.8001 5.57089V9.77778C32.8001 10.1019 32.9371 10.4128 33.1808 10.642C33.4246 10.8712 33.7553 11 34.1001 11H36.7ZM28.9002 11C29.2449 11 29.5756 10.8712 29.8194 10.642C30.0632 10.4128 30.2001 10.1019 30.2001 9.77778V6.79311C30.2001 6.46896 30.0632 6.15808 29.8194 5.92887C29.5756 5.69966 29.2449 5.57089 28.9002 5.57089H27.0958C27.0958 5.14148 27.1227 4.71207 27.1764 4.28267C27.2579 3.828 27.3922 3.42385 27.5794 3.07022C27.7675 2.71659 28.0097 2.43833 28.3061 2.23544C28.6007 2.00811 28.9769 1.89444 29.4345 1.89444V0C28.6822 0 28.0235 0.151556 27.4585 0.454667C26.8973 0.753958 26.4152 1.16839 26.048 1.66711C25.6783 2.21607 25.4061 2.81794 25.242 3.44911C25.0761 4.14546 24.995 4.8573 25.0002 5.57089V9.77778C25.0002 10.1019 25.1372 10.4128 25.381 10.642C25.6248 10.8712 25.9554 11 26.3002 11H28.9002Z" />
      </svg>
      <div className="setup-wizard-quote-text">{children}</div>
      <svg className="setup-wizard-quote-mark setup-wizard-quote-mark--close"
           width="13" height="11" viewBox="300 87 13 11" xmlns="http://www.w3.org/2000/svg">
        <path d="M301.3 87C300.955 87 300.625 87.1288 300.381 87.358C300.137 87.5872 300 87.8981 300 88.2222V91.2069C300 91.531 300.137 91.8419 300.381 92.0711C300.625 92.3003 300.955 92.4291 301.3 92.4291H303.104C303.104 92.8585 303.077 93.2879 303.024 93.7173C302.943 94.172 302.809 94.5761 302.621 94.9298C302.433 95.2834 302.19 95.5617 301.894 95.7646C301.599 95.9919 301.223 96.1056 300.766 96.1056V98C301.518 98 302.177 97.8484 302.742 97.5453C303.303 97.246 303.785 96.8316 304.152 96.3329C304.522 95.7839 304.794 95.1821 304.958 94.5509C305.124 93.8545 305.205 93.1427 305.2 92.4291V88.2222C305.2 87.8981 305.063 87.5872 304.819 87.358C304.575 87.1288 304.245 87 303.9 87H301.3ZM309.1 87C308.755 87 308.424 87.1288 308.181 87.358C307.937 87.5872 307.8 87.8981 307.8 88.2222V91.2069C307.8 91.531 307.937 91.8419 308.181 92.0711C308.424 92.3003 308.755 92.4291 309.1 92.4291H310.904C310.904 92.8585 310.877 93.2879 310.824 93.7173C310.742 94.172 310.608 94.5761 310.421 94.9298C310.233 95.2834 309.99 95.5617 309.694 95.7646C309.399 95.9919 309.023 96.1056 308.566 96.1056V98C309.318 98 309.976 97.8484 310.542 97.5453C311.103 97.246 311.585 96.8316 311.952 96.3329C312.322 95.7839 312.594 95.1821 312.758 94.5509C312.924 93.8545 313.005 93.1427 313 92.4291V88.2222C313 87.8981 312.863 87.5872 312.619 87.358C312.375 87.1288 312.045 87 311.7 87H309.1Z" />
      </svg>
    </div>
  )
}

function ProgressRow({ label, right, pct, error }) {
  return (
    <div className="setup-wizard-progress">
      <div className="setup-wizard-progress-head">
        <span className="setup-wizard-progress-label">{label}</span>
        <span className="setup-wizard-progress-status">{right}</span>
      </div>
      <div className="setup-wizard-progress-track">
        <div
          className={`setup-wizard-progress-fill${error ? ' is-error' : ''}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {error && <div className="setup-wizard-progress-error">{error}</div>}
    </div>
  )
}

const EXIT_MS = 300

export default function SetupWizard({ onDone }) {
  const [phase, setPhase] = useState('consent')
  const [status, setStatus] = useState(null)
  const [ig, setIg] = useState(null)
  const [gemmaOk, setGemmaOk] = useState(false)
  const [agplOk, setAgplOk] = useState(false)
  const [adultOk, setAdultOk] = useState(false)
  const [showTerms, setShowTerms] = useState(false)
  const [accepting, setAccepting] = useState(false)
  const [preset, setPreset] = useState(null)
  const [exiting, setExiting] = useState(false)
  const [sliding, setSliding] = useState(false)
  const startedRef = useRef(false)
  const agplRef = useRef(false)
  const llmSeenRef = useRef(new Set())
  const igSeenRef = useRef(new Set())

  function pickDefault(s, prev) {
    if (prev) return prev
    const list = s?.presets || []
    return (list.find((p) => p.current) || list[0])?.key || null
  }

  useEffect(() => {
    let alive = true
    async function poll() {
      try {
        const s = await api.setupStatus()
        if (!alive) return
        setStatus(s)
        setPreset((prev) => pickDefault(s, prev))
        let igStatus = null
        try { igStatus = await api.imagegenStatus(); setIg(igStatus) } catch {}
        if (!s.needs_setup && s.agreement_ok !== false) {
          setExiting(true)
          setTimeout(() => onDone?.(), EXIT_MS)
          return
        }
        if (startedRef.current) {
          for (const m of s.models || []) if (!m.present) llmSeenRef.current.add(m.key)
          for (const c of igStatus?.components || []) if (!c.present) igSeenRef.current.add(c.key)
        }
        if ((s.downloading || igStatus?.installing) && !startedRef.current) {
          startedRef.current = true
          setPhase('install')
        }
      } catch {}
      if (alive) setTimeout(poll, 1500)
    }
    poll()
    return () => { alive = false }
  }, [onDone])

  function startAll() {
    if (startedRef.current) return
    startedRef.current = true
    agplRef.current = agplOk
    setPhase('install')
    setSliding(true)
    api.setupAgreement().catch(() => {})
    api.setupStart(preset || undefined).catch(() => {})
    if (agplOk) api.imagegenInstall(true).catch(() => {})
    else api.imagegenInstallNonAgpl().catch(() => {})
  }

  const termsOnly = !!status && !status.needs_setup && status.agreement_ok === false
  async function acceptTerms() {
    if (accepting) return
    setAccepting(true)
    const r = await api.setupAgreement().catch(() => null)
    if (r?.ok) {
      setExiting(true)
      setTimeout(() => onDone?.(), EXIT_MS)
    } else {
      setAccepting(false)
    }
  }

  const presets = status?.presets || []
  const chosen = presets.find((p) => p.key === preset) || null
  const progByKey = {}
  for (const p of status?.progress || []) progByKey[p.key] = p
  const llmFiles = (status?.models || []).filter(
    (m) => !m.present || llmSeenRef.current.has(m.key))
  const anyLlmError = (status?.progress || []).some((p) => p.status === 'error')
  const anyVerifying = (status?.progress || []).some((p) => p.status === 'verifying')
  const anyExtracting = (status?.progress || []).some((p) => p.status === 'extracting')

  let llmTotal = 0
  let llmDone = 0
  for (const m of llmFiles) {
    const p = progByKey[m.key]
    llmTotal += m.size
    llmDone += m.present || p?.status === 'done' ? m.size : Math.min(p?.downloaded || 0, m.size)
  }
  const llmPct = llmTotal ? Math.round((llmDone / llmTotal) * 100) : 0
  const meterStatus = anyLlmError ? 'Ошибка загрузки'
    : anyVerifying ? 'Проверка файлов'
    : anyExtracting ? 'Распаковка'
    : llmPct >= 100 ? 'Почти готово'
    : status?.downloading ? 'Загрузка модели'
    : 'Подготовка'

  const igProgByKey = {}
  for (const p of ig?.progress || []) igProgByKey[p.key] = p
  const igFiles = (ig?.components || []).filter(
    (c) => !c.user_provided && (!c.present || igSeenRef.current.has(c.key))
      && (agplRef.current || !c.agpl))
  const agplSkipped = !agplRef.current
    && (ig?.components || []).some((c) => c.agpl && !c.present)

  function igRight(c, p) {
    if (c.present || p?.status === 'done') return 'готово'
    if (!p || p.status === 'pending') return 'в очереди'
    if (p.status === 'error') return 'ошибка'
    if (p.status === 'extracting') return 'распаковка…'
    if (p.status === 'pip') return 'зависимости…'
    if (p.total) return `${Math.round((p.downloaded / p.total) * 100)}%`
    return 'загрузка…'
  }

  return (
    <div className="setup-wizard">
      <div className="setup-wizard-card">
        <div className="setup-wizard-card">

        </div>
        <svg className="setup-wizard-card-lines" width="658" height="906"
             viewBox="0 0 658 906" xmlns="http://www.w3.org/2000/svg">
          <path d="M564.505 886L55 885.91V884H556.5L581.021 860H590.93L564.505 886Z" />
          <path d="M587.627 886H577.718L604.143 860H614.052L587.627 886Z" />
          <path d="M611.575 886H601.666L628.091 860H638L611.575 886Z" />
          <path d="M94.4946 21L604 21.09V23H102.5L77.9789 47H68.0696L94.4946 21Z" />
          <path d="M71.3727 21H81.2821L54.8571 47H44.9477L71.3727 21Z" />
          <path d="M47.425 21H57.3344L30.9094 47H21L47.425 21Z" />
        </svg>

        {import.meta.env.DEV && (
          <button
            className="setup-wizard-mock-close"
            onClick={() => api.setupMock(false).then(() => window.location.reload()).catch(() => {})}
          >закрыть (мок)</button>
        )}

        <div className={`setup-wizard-content${exiting ? ' setup-wizard-content--exit' : ''}`}>
          <div className="setup-wizard-head">
            <img className="setup-wizard-logo" src={maidLinkLogo} alt="MaidLink"
                 width={383} height={95} draggable={false} />
            <p className="setup-wizard-subtitle">
              {status
                ? (status.gpu?.has_gpu
                    ? `${status.gpu.name} · ${status.gpu.vram_gb} ГБ · квант ${status.recommended_quant}`
                    : 'GPU не найдена — без неё модель будет работать медленно')
                : 'Проверяю систему…'}
            </p>
          </div>

          <div className="setup-wizard-stage">
            {(phase === 'consent' || sliding) && (
              <div className={`setup-wizard-pane${sliding ? ' setup-wizard-pane--out' : ''}`}
                   inert={sliding}>
                <div className="setup-wizard-body">
                  {termsOnly && (
                    <>
                      <SectionTitle>Соглашение</SectionTitle>
                      <p className="setup-wizard-text">
                        Перед продолжением подтвердите возраст и примите
                        пользовательское соглашение.
                      </p>
                    </>
                  )}
                  {!termsOnly && presets.length > 0 && (
                    <>
                      <SectionTitle>Модель</SectionTitle>
                      <div className="setup-wizard-models">
                        {presets.map((p) => (
                          <label
                            key={p.key}
                            className={`setup-wizard-model${preset === p.key ? ' is-selected' : ''}`}
                          >
                            <input type="radio" name="setup-preset" value={p.key}
                                   checked={preset === p.key}
                                   onChange={() => setPreset(p.key)} />
                            <span>
                              <div className="setup-wizard-model-label">
                                {p.label}
                                <span className="setup-wizard-model-size">загрузка ~{fmtGB(p.size)} ГБ</span>
                              </div>
                              <div className="setup-wizard-model-hint">{p.hint}</div>
                            </span>
                          </label>
                        ))}
                      </div>
                    </>
                  )}

                  {!termsOnly && <SectionTitle>Соглашения</SectionTitle>}
                  {!termsOnly && <p className="setup-wizard-text">
                    Будут загружены и установлены: модель{' '}
                    <b>{chosen ? chosen.label.replace(/\s*\([^)]*\)\s*$/, '') : 'Gemma 12B'}</b>
                    {chosen ? (chosen.vision ? ' с vision-проектором' : ' (без анализа картинок)') : ' с vision-проектором'}
                    {' '}(~{chosen ? fmtGB(chosen.size) : '7'} ГБ), эмбеддер памяти (Apache-2.0),
                    библиотеки NVIDIA CUDA для видеокарты (~0.4 ГБ) и модуль
                    рисования — <b>ComfyUI</b> (GPL-3.0), Impact Pack (GPL-3.0),
                    SAM (Apache-2.0), эмбеддинги (FAIPL-1.0-SD).
                  </p>}

                  <label className="setup-wizard-consent">
                    <input type="checkbox" checked={adultOk}
                           onChange={(e) => setAdultOk(e.target.checked)} />
                    <span>
                      Мне исполнилось 18 лет, и я принимаю{' '}
                      <button type="button" className="setup-wizard-link setup-wizard-link--button"
                              onClick={(e) => { e.preventDefault(); setShowTerms((v) => !v) }}>
                        пользовательское соглашение</button>.
                      Обязательно — приложение только для взрослых.
                    </span>
                  </label>
                  {showTerms && <div className="setup-wizard-terms">{termsText}</div>}

                  {!termsOnly && <>
                  <label className="setup-wizard-consent">
                    <input type="checkbox" checked={gemmaOk}
                           onChange={(e) => setGemmaOk(e.target.checked)} />
                    <span>
                      Принимаю условия лицензии модели Gemma 4
                      (<a href="https://www.apache.org/licenses/LICENSE-2.0" target="_blank" rel="noreferrer"
                          className="setup-wizard-link">Apache License 2.0, Google</a>).
                      Обязательно — модель является ядром приложения.
                    </span>
                  </label>

                  <label className="setup-wizard-consent">
                    <input type="checkbox" checked={agplOk}
                           onChange={(e) => setAgplOk(e.target.checked)} />
                    <span>
                      Согласен(на) установить AGPL-компоненты рисования: Impact
                      Subpack и YOLO-детекторы лица/рук (AGPL-3.0). Необязательно —
                      без них эти компоненты будут пропущены, но рисование не
                      заработает, пока вы не установите их позже
                      (Настройки → Рисование).
                    </span>
                  </label>

                  <QuoteBox>
                    Исключение: <b>чекпойнт рисования</b> (.safetensors) не
                    загружается автоматически — у него строгая некоммерческая
                    лицензия. Свой файл вы добавите сами: Настройки → Рисование
                    (перетащить в окно).
                  </QuoteBox>
                  </>}

                  {termsOnly
                    ? <button className="setup-wizard-button" onClick={acceptTerms}
                              disabled={!adultOk || accepting}>Продолжить</button>
                    : <button className="setup-wizard-button" onClick={startAll}
                              disabled={!gemmaOk || !adultOk}>Начать установку</button>}
                  <div className={`setup-wizard-gate${adultOk && (termsOnly || gemmaOk) ? ' setup-wizard-gate--hidden' : ''}`}>
                    {termsOnly ? 'Для продолжения подтвердите возраст и примите соглашение.'
                      : 'Для продолжения подтвердите возраст и примите условия лицензии модели.'}
                  </div>
                </div>
              </div>
            )}

            {phase === 'install' && (
              <div className={`setup-wizard-pane${sliding ? ' setup-wizard-pane--in' : ''}`}
                   onAnimationEnd={(e) => { if (e.target === e.currentTarget) setSliding(false) }}>
                <div className="setup-wizard-body">
                  <div className="setup-wizard-meter">
                    <img className="setup-wizard-meter-bars" src={loadingBars} alt=""
                         width={452} height={95} draggable={false} />
                    <div className="setup-wizard-meter-status">
                      <span key={meterStatus}>{meterStatus}</span>
                    </div>
                    <div className="setup-wizard-meter-track">
                      <div className="setup-wizard-meter-fill" style={{ width: `${llmPct}%` }} />
                    </div>
                    <div className="setup-wizard-meter-pct">{llmPct}%</div>
                  </div>

                  <SectionTitle>Компоненты</SectionTitle>
                  <div className="setup-wizard-progress-list">
                    {llmFiles.map((m) => {
                      const p = progByKey[m.key]
                      const done = m.present || p?.status === 'done'
                      const pct = p && p.total ? Math.round((p.downloaded / p.total) * 100) : 0
                      return (
                        <ProgressRow
                          key={m.key}
                          label={m.title || m.filename}
                          right={p?.status === 'error' ? 'ошибка'
                            : p?.status === 'verifying' ? 'проверка…'
                            : p?.status === 'extracting' ? 'распаковка…'
                            : done ? 'готово'
                            : `${pct}% · ${fmtGB(p?.downloaded || 0)}/${fmtGB(m.size)} ГБ`}
                          pct={done ? 100 : pct}
                          error={p?.status === 'error' ? p.error : ''}
                        />
                      )
                    })}

                    {igFiles.map((c) => {
                      const p = igProgByKey[c.key]
                      const pct = c.present || p?.status === 'done' ? 100
                        : p && p.total ? Math.round((p.downloaded / p.total) * 100) : 0
                      return (
                        <ProgressRow
                          key={c.key}
                          label={`${c.title}${c.agpl ? '  ⚠ AGPL' : ''}`}
                          right={igRight(c, p)}
                          pct={pct}
                          error={p?.status === 'error' ? p.error : ''}
                        />
                      )
                    })}
                  </div>

                  {anyLlmError && (
                    <button
                      className="setup-wizard-retry"
                      onClick={() => api.setupStart().catch(() => {})}
                    >Повторить</button>
                  )}

                  <QuoteBox>
                    Модуль рисования ставится в фоне — общение станет доступно, как
                    только загрузится модель. Чекпойнт (.safetensors) добавите позже:
                    Настройки → Рисование.
                    {agplSkipped && (
                      <> AGPL-компоненты пропущены (без согласия) — рисование
                      заработает после их установки там же.</>
                    )}
                  </QuoteBox>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
