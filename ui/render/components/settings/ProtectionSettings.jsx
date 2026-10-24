import React, { useEffect, useState } from 'react'
import { api } from '@/lib/api'

function Row({ label, children, last }) {
  return (
    <div className={`settings-protection-row${last ? ' is-last' : ''}`}>
      <span className="settings-protection-row-label">{label}</span>
      {children}
    </div>
  )
}

export default function ProtectionSettings({ open = false }) {
  const [charId, setCharId] = useState(null)
  const [charName, setCharName] = useState('')
  const [protectedOn, setProtectedOn] = useState(false)
  const [mode, setMode] = useState(null)
  const [pw, setPw] = useState('')
  const [pw2, setPw2] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [code, setCode] = useState('')

  const resolveActive = async () => {
    const list = await api.characters()
    const act = list.characters.find((c) => c.active) || null
    setCharId(act?.id ?? null)
    setCharName(act?.name || '')
    return act
  }

  const refresh = async () => {
    try {
      const [ch] = await Promise.all([api.character(), resolveActive()])
      setProtectedOn(!!ch?.is_protected)
    } catch {}
  }

  useEffect(() => { refresh() }, [])
  useEffect(() => { if (open) { reset(); refresh() } }, [open])

  const reset = () => { setMode(null); setPw(''); setPw2(''); setErr('') }

  async function withActive(fn) {
    setBusy(true); setErr('')
    let act = null
    try { act = await resolveActive() } catch {}
    if (!act) {
      setBusy(false)
      setErr('Не вижу активного персонажа — выберите его и повторите')
      return null
    }
    const r = await fn(act.id).catch(() => null)
    setBusy(false)
    return r
  }

  async function enable() {
    if (pw.length < 4) { setErr('Пароль слишком короткий'); return }
    if (pw !== pw2) { setErr('Пароли не совпадают'); return }
    const r = await withActive((id) => api.protectCharacter(id, pw))
    if (!r) return
    if (!r.ok) { setErr(r.error || 'Не удалось включить'); return }
    setCode(r.recovery_code || '')
    reset(); setProtectedOn(true)
  }

  async function disable() {
    const r = await withActive((id) => api.unprotectCharacter(id, pw))
    if (!r) return
    if (!r.ok) { setErr(r.error || 'Не удалось снять'); return }
    reset(); setProtectedOn(false)
  }

  async function change() {
    if (pw2.length < 4) { setErr('Новый пароль слишком короткий'); return }
    const r = await withActive((id) => api.changeCharacterPassword(id, pw, pw2))
    if (!r) return
    if (!r.ok) { setErr(r.error || 'Не удалось сменить'); return }
    reset()
  }

  if (!charId) {
    return <Row label="Персонаж не выбран" last><span /></Row>
  }

  return (
    <>
      <Row label={`${charName ? charName + ' · ' : ''}${
        protectedOn ? 'память зашифрована' : 'память не защищена'}`}>
        {mode === null && (
          <div className="settings-protection-actions">
            {protectedOn ? (
              <>
                <button className="settings-protection-button" onClick={() => setMode('change')}>
                  Сменить пароль
                </button>
                <button className="settings-protection-button is-secondary" onClick={() => setMode('off')}>
                  Снять
                </button>
              </>
            ) : (
              <button className="settings-protection-button" onClick={() => setMode('on')}>
                Поставить пароль
              </button>
            )}
          </div>
        )}
        {mode !== null && (
          <button className="settings-protection-button is-cancel" onClick={reset}>
            Отмена
          </button>
        )}
      </Row>

      {mode === 'on' && (
        <>
          <Row label="Новый пароль">
            <input className="settings-protection-input" type="password" autoFocus value={pw}
                   onChange={(e) => setPw(e.target.value)} disabled={busy} />
          </Row>
          <Row label="Ещё раз">
            <input className="settings-protection-input" type="password" value={pw2}
                   onChange={(e) => setPw2(e.target.value)} disabled={busy} />
          </Row>
          <Row label="" last>
            <button className="settings-protection-button" onClick={enable} disabled={busy}>
              {busy ? 'Шифрую…' : 'Включить защиту'}
            </button>
          </Row>
        </>
      )}

      {mode === 'off' && (
        <>
          <Row label="Пароль или код">
            <input className="settings-protection-input" type="password" autoFocus value={pw}
                   onChange={(e) => setPw(e.target.value)} disabled={busy} />
          </Row>
          <Row label="" last>
            <button className="settings-protection-button" onClick={disable} disabled={busy || !pw}>
              {busy ? 'Снимаю…' : 'Снять защиту'}
            </button>
          </Row>
        </>
      )}

      {mode === 'change' && (
        <>
          <Row label="Текущий пароль">
            <input className="settings-protection-input" type="password" autoFocus value={pw}
                   onChange={(e) => setPw(e.target.value)} disabled={busy} />
          </Row>
          <Row label="Новый пароль">
            <input className="settings-protection-input" type="password" value={pw2}
                   onChange={(e) => setPw2(e.target.value)} disabled={busy} />
          </Row>
          <Row label="" last>
            <button className="settings-protection-button" onClick={change} disabled={busy || !pw}>
              {busy ? 'Меняю…' : 'Сменить'}
            </button>
          </Row>
        </>
      )}

      {err && <div className="settings-protection-error">{err}</div>}

      {code && (
        <div className="settings-protection-code">
          <div className="settings-protection-code-text">
            Код восстановления — единственный запасной ключ. Запишите его:
            повторно он не покажется, а без пароля и кода память открыть
            невозможно (останется только сброс персонажа).
          </div>
          <div className="settings-protection-code-value">{code}</div>
          <button className="settings-protection-button settings-protection-code-ack" onClick={() => setCode('')}>
            Я записал(а)
          </button>
        </div>
      )}
    </>
  )
}
