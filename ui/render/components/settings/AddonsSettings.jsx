import React, { useState } from 'react'
import { api } from '@/lib/api'
import { useAddons, setAddonEnabled, refreshAddons } from '@/lib/addons'
import Toggle from './Toggle'

export default function AddonsSettings() {
  const addons = useAddons()
  const [dropOver, setDropOver] = useState(false)
  const [path, setPath] = useState('')
  const [note, setNote] = useState('')
  const [noteOk, setNoteOk] = useState(false)

  async function install(p) {
    if (!p) return
    setNote(''); setNoteOk(false)
    let r
    try { r = await api.installAddon(p) } catch { setNote('не удалось связаться с бэкендом'); return }
    if (!r.ok) { setNote(r.error || 'не удалось установить аддон'); return }
    setPath('')
    setNoteOk(true)
    setNote(`Установлен: ${r.addon?.name || r.addon?.id}. Включите его галкой выше.`)
    refreshAddons()
  }

  function onDrop(e) {
    e.preventDefault()
    setDropOver(false)
    const f = e.dataTransfer?.files?.[0]
    if (!f) return
    const n = f.name.toLowerCase()
    if (!n.endsWith('.zip') && !n.endsWith('.maidaddon')) {
      setNoteOk(false); setNote('Нужен .zip-пакет аддона'); return
    }
    const p = window.maidlink?.getPathForFile?.(f)
    if (p) install(p)
    else { setNoteOk(false); setNote('Перетаскивание доступно в приложении; в браузере укажите путь ниже.') }
  }

  return (
    <div className="settings-addons">
      {addons.map((a) => (
        <div key={a.id} className="settings-addons-item">
          <div className="settings-addons-item-head">
            <span className="settings-addons-label">{a.name || a.id}</span>
            <Toggle value={!!a.enabled} onChange={(v) => setAddonEnabled(a.id, v)} />
          </div>
          {a.description && <div className="settings-addons-hint settings-addons-desc">{a.description}</div>}
        </div>
      ))}

      {!addons.length && (
        <div className="settings-addons-hint settings-addons-empty">Аддонов пока нет — установите пакет ниже.</div>
      )}

      <div className="settings-addons-install">
        <div
          onDragOver={(e) => { e.preventDefault(); setDropOver(true) }}
          onDragLeave={() => setDropOver(false)}
          onDrop={onDrop}
          className={`settings-addons-drop${dropOver ? ' is-over' : ''}`}
        >Перетащите сюда <b>.zip</b>-пакет аддона</div>
        <div className="settings-addons-path">
          <input value={path} onChange={(e) => setPath(e.target.value)}
            placeholder="…или путь к пакету" className="settings-addons-input" />
          <button onClick={() => install(path.trim())} className="settings-addons-button">Указать</button>
        </div>
        {note && <div className={`settings-addons-note${noteOk ? ' is-ok' : ''}`}>{note}</div>}
        <div className="settings-addons-hint settings-addons-footnote">
          Контент аддона применится после перезапуска. Переключение — сразу.
        </div>
      </div>
    </div>
  )
}
