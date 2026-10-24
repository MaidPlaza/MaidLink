import React, { useCallback, useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { api } from '@/lib/api'
import { API_BASE, resolveUrl } from '@/lib/url'

const isNsfw = (it) => String(it?.rating || '').toLowerCase() === 'nsfw'

const shotTime = (it) => (it && (it.created_at || it.added_at)) || 0

function fmtAdded(sec) {
  const n = Number(sec)
  if (!n) return ''
  return new Date(n * 1000).toLocaleString('ru-RU', {
    day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

export default function CharacterGallery() {
  const [data, setData] = useState({ items: [], count: 0, max: 100 })
  const [open, setOpen] = useState(null)
  const [confirm, setConfirm] = useState(false)
  const [revealed, setRevealed] = useState(() => new Set())

  function onCellClick(it) {
    if (isNsfw(it) && !revealed.has(it.id)) {
      setRevealed((prev) => { const next = new Set(prev); next.add(it.id); return next })
      return
    }
    openItem(it)
  }

  const load = useCallback(() => {
    api.gallery().then((r) => { if (r && !r.error) setData(r) }).catch(() => {})
  }, [])
  useEffect(() => { load() }, [load])
  useEffect(() => {
    const unsub = window.maidlink?.onGalleryChanged?.(() => load())
    return () => { if (typeof unsub === 'function') unsub() }
  }, [load])

  function viewerTheme() {
    try {
      const cs = getComputedStyle(document.documentElement)
      const v = (n) => cs.getPropertyValue(n).trim()
      return {
        bar: v('--chat-character-information-gallery-viewer-bar-background') || '',
        fg: v('--chat-character-information-gallery-viewer-font-color') || '',
        stage: v('--chat-character-information-gallery-viewer-stage-background') || '',
      }
    } catch {
      return {}
    }
  }

  function openItem(it) {
    const bridge = window.maidlink
    if (bridge && typeof bridge.openImageViewer === 'function') {
      bridge.openImageViewer({
        id: it.id, url: resolveUrl(it.url), intent: it.intent || '',
        added_at: it.added_at || 0,
        width: it.width, height: it.height, api: API_BASE,
        theme: viewerTheme(),
      })
      return
    }
    setOpen(it)
    setConfirm(false)
  }

  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => { if (e.key === 'Escape') setOpen(null) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  async function remove(item) {
    let r
    try { r = await api.galleryRemove(item.id) } catch { r = null }
    if (r && r.ok) {
      setOpen(null)
      setConfirm(false)
      load()
    }
  }

  return (
    <div className="character-gallery">
      <div className="character-gallery-count">{data.count} / {data.max}</div>
      {data.items.length === 0 ? (
        <div className="character-gallery-empty">
          Пока пусто — сердечко на снимке в чате сохранит его сюда.
        </div>
      ) : (
        <div className="character-gallery-grid">
          {data.items.map((it) => {
            const blurred = isNsfw(it) && !revealed.has(it.id)
            return (
              <button
                key={it.id}
                type="button"
                className={`character-gallery-cell${blurred ? ' is-blurred' : ''}`}
                title={blurred ? 'Снимок 18+ — клик, чтобы показать' : fmtAdded(shotTime(it))}
                aria-label={blurred ? 'Снимок 18+, скрыт' : undefined}
                onClick={() => onCellClick(it)}
              >
                <img src={resolveUrl(it.thumb_url)} alt="" loading="lazy" />
                {blurred && <span className="character-gallery-cell-badge">18+</span>}
              </button>
            )
          })}
        </div>
      )}
      {open && createPortal(
        <div className="character-gallery-lightbox" onClick={() => setOpen(null)}>
          <div className="character-gallery-lightbox-body" onClick={(e) => e.stopPropagation()}>
            <img src={resolveUrl(open.url)} alt="" />
            <div className="character-gallery-lightbox-bar">
              <span className="character-gallery-lightbox-intent">{fmtAdded(shotTime(open))}</span>
              {!confirm ? (
                <button type="button" onClick={() => setConfirm(true)}>Удалить из галереи</button>
              ) : (
                <>
                  <button type="button" className="is-danger" onClick={() => remove(open)}>Точно удалить</button>
                  <button type="button" onClick={() => setConfirm(false)}>Оставить</button>
                </>
              )}
              <button type="button" onClick={() => setOpen(null)}>Закрыть</button>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </div>
  )
}
