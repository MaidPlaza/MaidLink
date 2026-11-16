import React, { useEffect, useState } from 'react'
import { getSettingValue, setSettingValue } from '@/lib/settings'

export default function UsageGuide({ ready, name }) {
  const [open, setOpen] = useState(false)
  const [shown, setShown] = useState(false)
  const [dontShow, setDontShow] = useState(false)

  useEffect(() => {
    if (!ready || shown) return
    setShown(true)
    if (getSettingValue('session.usage_guide') !== false) setOpen(true)
  }, [ready, shown])

  if (!open) return null
  const who = name || 'персонаж'

  function close() {
    if (dontShow) setSettingValue('session.usage_guide', false)
    setOpen(false)
  }

  return (
    <div className="usage-guide-backdrop">
      <div className="usage-guide-card" role="dialog" aria-label="Памятка">
        <div className="usage-guide-label">Памятка</div>
        <div className="usage-guide-title">Чтобы всё работало так, как задумано</div>
        <p className="usage-guide-lead">
          В свободное время {who} обдумывает прошедшие разговоры. Только так
          появляются воспоминания, записи в дневнике и перемены в отношении к
          вам. Без этого {who} ничего не запомнит.
        </p>
        <div className="usage-guide-label">Что для этого нужно</div>
        <ol className="usage-guide-steps">
          <li className="usage-guide-step">
            <span className="usage-guide-step-title">Завершайте разговор.</span>{' '}
            Попрощайтесь, нажмите Ctrl+Shift+Enter или закройте окно
            крестиком. Если просто отойти, разговор завершится сам после паузы
            (её длина — в настройках).
          </li>
          <li className="usage-guide-step">
            <span className="usage-guide-step-title">Не выключайте приложение сразу.</span>{' '}
            Крестик не закрывает MaidLink, а сворачивает его в трей.
            Обдумывание идёт, пока приложение свёрнуто или открыто без дела, —
            несколько минут, на слабом компьютере дольше.
          </li>
          <li className="usage-guide-step">
            <span className="usage-guide-step-title">«Выход» — когда всё обдумано.</span>{' '}
            «Выход» в меню значка в трее закрывает приложение совсем:
            незавершённый разговор при этом пропадёт, а необдуманный подождёт
            следующего запуска. Что происходит сейчас, подскажет значок в
            трее — наведите на него курсор.
          </li>
        </ol>
        <div className="usage-guide-note">Итоги обдумывания — в карточке персонажа: дневник, мысли, отношения.</div>
        <div className="usage-guide-footer">
          <label className="usage-guide-check">
            <input type="checkbox" checked={dontShow} onChange={(e) => setDontShow(e.target.checked)} />
            Больше не показывать
          </label>
          <button type="button" className="usage-guide-button" onClick={close}>Понятно</button>
        </div>
        <div className="usage-guide-note">Вернуть памятку можно в настройках, раздел «Сессия».</div>
      </div>
    </div>
  )
}
