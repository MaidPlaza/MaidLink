import React, { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { api } from '@/lib/api'

const fmtN = (n) => (typeof n === 'number' && Number.isFinite(n) ? n.toLocaleString('ru-RU') : '—')

const SOURCE_RU = { default: 'обычный образ', gacha: 'выпало из билета', innate: 'своё от рождения', legacy: 'было до билетов' }

const PANEL_W = 200

function chipTitle(it) {
  const parts = [it.tag]
  if (it.worn) parts.push(it.worn_as ? `надето как «${it.worn_as}»` : 'надето сейчас')
  if (it.rarity_label) parts.push(it.rarity_label)
  if (SOURCE_RU[it.source]) parts.push(SOURCE_RU[it.source])
  return parts.join(' · ')
}

function findItem(section, tag) {
  for (const c of (section && section.categories) || []) {
    for (const it of c.items || []) if (it.tag === tag) return it
  }
  return null
}

function ColorsPanel({ item, pos, pinned, spheres, panelRef, onSphereUsed }) {
  const [sel, setSel] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  useEffect(() => { setSel(null); setErr('') }, [item.tag])
  const colors = item.colors || []
  const open = colors.filter((c) => c.open)
  const locked = colors.filter((c) => !c.open)
  const patterns = item.patterns || []
  const openP = patterns.filter((p) => p.open)
  const lockedP = patterns.filter((p) => !p.open)
  const anyLocked = locked.length + lockedP.length > 0
  const canSphere = pinned && spheres > 0 && anyLocked
  const selItem = sel && (sel.kind === 'color' ? locked : lockedP).find((c) => c.key === sel.key)
  const isSel = (kind, key) => !!sel && sel.kind === kind && sel.key === key
  const toggleSel = (kind, key) => setSel(isSel(kind, key) ? null : { kind, key })

  const applySphere = () => {
    if (!selItem || busy) return
    setBusy(true)
    setErr('')
    api.gachaSphere(item.tag, sel.kind === 'color' ? selItem.key : '', sel.kind === 'pattern' ? selItem.key : '')
      .then((r) => {
        if (r && r.ok) { setSel(null); onSphereUsed(r.styling) }
        else setErr((r && r.error) || 'не вышло')
      })
      .catch((e) => setErr(String(e)))
      .finally(() => setBusy(false))
  }

  return createPortal(
    <div
      ref={panelRef}
      className={`character-styling-colors no-select${pinned ? ' is-pinned' : ''}`}
      role={pinned ? 'dialog' : 'tooltip'}
      style={{ top: pos.top, left: pos.left }}
    >
      <div className="character-styling-colors-head">
        Цвета · {open.length} из {colors.length}
      </div>
      {open.length > 0 ? (
        <div className="character-styling-colors-list">
          {open.map((c) => (
            <span key={c.key} className={`character-styling-colors-row${c.worn ? ' is-worn' : ''}`}>
              <i className={`style-swatch is-${c.key}`} aria-hidden="true" />
              {c.label}{c.worn ? ' · надет' : ''}
            </span>
          ))}
        </div>
      ) : (
        <div className="character-styling-colors-empty">цвет пока не открыт</div>
      )}
      {locked.length > 0 && (
        <div className={`character-styling-colors-locked${canSphere ? ' is-sphere' : ''}`}>
          {locked.map((c) => (canSphere ? (
            <button
              key={c.key}
              type="button"
              className={`style-swatch is-${c.key} character-styling-colors-pick${isSel('color', c.key) ? ' is-selected' : ''}`}
              title={c.label}
              aria-label={c.label}
              onClick={() => toggleSel('color', c.key)}
            />
          ) : (
            <i key={c.key} className={`style-swatch is-${c.key}`} title={pinned ? c.label : undefined} aria-hidden="true" />
          )))}
        </div>
      )}
      {patterns.length > 0 && (
        <>
          <div className="character-styling-colors-head">
            Узоры · {openP.length} из {patterns.length}
          </div>
          {openP.length > 0 && (
            <div className="character-styling-colors-list">
              {openP.map((p) => (
                <span key={p.key} className={`character-styling-colors-row${p.worn ? ' is-worn' : ''}`}>
                  {p.label}{p.worn ? ' · надет' : ''}
                </span>
              ))}
            </div>
          )}
          {lockedP.length > 0 && (
            <div className={`character-styling-colors-locked${canSphere ? ' is-sphere' : ''}`}>
              {lockedP.map((p) => (canSphere ? (
                <button
                  key={p.key}
                  type="button"
                  className={`character-styling-pattern-chip character-styling-colors-pick${isSel('pattern', p.key) ? ' is-selected' : ''}`}
                  onClick={() => toggleSel('pattern', p.key)}
                >{p.label}</button>
              ) : (
                <span key={p.key} className="character-styling-pattern-chip">{p.label}</span>
              )))}
            </div>
          )}
        </>
      )}
      {pinned && anyLocked && (canSphere ? (
        <div className="character-styling-colors-sphere">
          {selItem ? (
            <button type="button" className="character-styling-colors-sphere-btn" disabled={busy} onClick={applySphere}>
              {busy ? 'Открываем…' : `Открыть: ${selItem.label}`}
            </button>
          ) : (
            <span className="character-styling-colors-sphere-hint">
              Выбери {patterns.length ? 'цвет или узор' : 'цвет'} — откроется сферой изменения (есть {fmtN(spheres)})
            </span>
          )}
          {err && <span className="character-styling-colors-sphere-hint">{err}</span>}
        </div>
      ) : (
        <div className="character-styling-colors-sphere">
          <span className="character-styling-colors-sphere-hint">
            Закрытые {patterns.length ? 'цвета и узоры' : 'цвета'} выпадают из билетов удачи или открываются сферой изменения
          </span>
        </div>
      ))}
    </div>,
    document.body,
  )
}

export default function CharacterStyling({ section, onSectionChange }) {
  const [hover, setHover] = useState(null)
  const [pinned, setPinned] = useState(null)
  const panelRef = useRef(null)
  useEffect(() => {
    if (!hover && !pinned) return
    const close = (e) => {
      if (e && e.target instanceof Node && panelRef.current && panelRef.current.contains(e.target)) return
      setHover(null)
      setPinned(null)
    }
    window.addEventListener('scroll', close, true)
    window.addEventListener('resize', close)
    return () => {
      window.removeEventListener('scroll', close, true)
      window.removeEventListener('resize', close)
    }
  }, [hover, pinned])
  useEffect(() => {
    if (!pinned) return
    const onDown = (e) => {
      if (panelRef.current && panelRef.current.contains(e.target)) return
      if (e.target instanceof Element && e.target.closest('.character-styling-chip')) return
      setPinned(null)
    }
    const onKey = (e) => { if (e.key === 'Escape') setPinned(null) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [pinned])
  if (!section) return <div className="character-entries-empty">…</div>
  const cats = (section.categories || []).filter((c) => (c.items && c.items.length) || c.locked > 0)
  const tickets = Number(section.tickets) || 0
  const spheres = Number(section.spheres) || 0

  const posOf = (el) => {
    const r = el.getBoundingClientRect()
    const right = r.right + 6 + PANEL_W <= window.innerWidth
    return { top: Math.round(r.top), left: Math.round(right ? r.right + 6 : r.left - 6 - PANEL_W) }
  }
  const showColors = (it) => (e) => setHover({ tag: it.tag, pos: posOf(e.currentTarget) })
  const hideColors = () => setHover(null)
  const togglePin = (it) => (e) => {
    if (pinned && pinned.tag === it.tag) { setPinned(null); return }
    setPinned({ tag: it.tag, pos: posOf(e.currentTarget) })
  }
  const shown = pinned || hover
  const shownItem = shown ? findItem(section, shown.tag) : null

  const ticketsLine = [tickets > 0 ? `билетов: ${fmtN(tickets)}` : 'билетов нет']
  if (spheres > 0) ticketsLine.push(`сфер изменения: ${fmtN(spheres)}`)

  return (
    <div className="character-styling">
      <div className="character-styling-head">
        <span>Открыто <b>{fmtN(section.unlocked)}</b> из {fmtN(section.total)} · надето <b>{fmtN(section.worn_count)}</b></span>
        <span className="character-styling-tickets">{ticketsLine.join(' · ')}</span>
      </div>
      {cats.length === 0 ? (
        <div className="character-entries-empty">Пока ничего не открыто — билеты удачи ждут в чате.</div>
      ) : cats.map((c) => (
        <div className="character-styling-cat" key={c.key}>
          <div className="character-stats-group">
            <span>{c.label}{c.items.length ? ` · ${c.items.length}` : ''}</span>
            <i aria-hidden="true" />
          </div>
          <div className="character-styling-chips">
            {c.items.map((it) => {
              const colorable = (it.colors || []).length > 0
              return (
                <span
                  key={it.tag}
                  className={`character-styling-chip is-${it.rarity || 'common'}${it.worn ? ' is-worn' : ''}${colorable ? ' is-colorable' : ''}`}
                  title={colorable ? undefined : chipTitle(it)}
                  onMouseEnter={colorable ? showColors(it) : undefined}
                  onMouseLeave={colorable ? hideColors : undefined}
                  onClick={colorable ? togglePin(it) : undefined}
                >
                  {it.worn ? <i className="character-styling-dot" aria-hidden="true" /> : null}
                  {it.label || it.tag}
                </span>
              )
            })}
            {c.locked > 0 && (
              <span className="character-styling-chip is-locked" title="Ещё не выпало из билетов удачи">
                не открыто: {fmtN(c.locked)}
              </span>
            )}
          </div>
        </div>
      ))}
      <div className="character-stats-note">
        ● — надето сейчас; рамка — редкость: синяя обычная, фиолетовая редкая, золотая легендарная;
        наведи на украшение, макияж или бельё — покажет открытые цвета, клик — закрепит
        {spheres > 0 ? ' (там же открывается цвет сферой изменения)' : ''}
      </div>
      {shown && shownItem && (
        <ColorsPanel
          item={shownItem}
          pos={shown.pos}
          pinned={!!pinned && pinned.tag === shown.tag}
          spheres={spheres}
          panelRef={panelRef}
          onSphereUsed={(styling) => { if (styling && onSectionChange) onSectionChange(styling) }}
        />
      )}
    </div>
  )
}
