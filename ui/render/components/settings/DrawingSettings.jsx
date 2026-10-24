import React from 'react'
import { useCapability } from '@/lib/capabilities'
import ImageGenSetup from './ImageGenSetup'

export default function DrawingSettings() {
  const drawingAvailable = useCapability('drawing')
  if (!drawingAvailable) return <ImageGenSetup />
  return (
    <div className="settings-drawing">
      <div className="settings-drawing-status">
        Модуль рисования подключён. Стиль рисования (выбор и импорт по коду) — в окне гардероба.
      </div>
    </div>
  )
}
