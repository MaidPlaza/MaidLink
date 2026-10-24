import React from 'react'
import { useSetting } from '@/lib/settings'
import Toggle from './Toggle'

export default function NsfwContent() {
  const [rating, setRating] = useSetting('drawing.max_rating')
  const on = rating === 'nsfw'
  return (
    <div className="settings-nsfw">
      <div className="settings-nsfw-head">
        <span className="settings-nsfw-label">Откровенный контент (18+)</span>
        <Toggle value={on} onChange={(v) => setRating(v ? 'nsfw' : 'sfw')} />
      </div>
      <div className="settings-nsfw-hint">
        Разрешает откровенные темы и кадры. Степень — по тиру близости и согласию.
      </div>
    </div>
  )
}
