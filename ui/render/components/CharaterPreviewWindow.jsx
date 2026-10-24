import React, { useEffect, useRef, useState } from 'react'
import avatarMira from '../../assets/avatars/avatar_mira.png'
import { useSetting } from '@/lib/settings'
import { useUIStructure } from '@/lib/uiStructure'
import { api } from '@/lib/api'
import { FALLBACK_GESTURES, dispatchGesture } from '@/lib/gestures'

export default function CharaterPreviewWindow({ character, activeChar, identity, portraitUrl, expandMode }) {
  const svgStructure = useUIStructure()
  const [moodPortraits] = useSetting('drawing.mood_portraits_enabled')

  const [gestures, setGestures] = useState(FALLBACK_GESTURES)
  useEffect(() => {
    let alive = true
    api.gestures()
      .then((r) => { if (alive && Array.isArray(r?.gestures) && r.gestures.length) setGestures(r.gestures) })
      .catch(() => {})
    return () => { alive = false }
  }, [activeChar?.id])
  const headGesture = gestures.find((g) => g.zone === 'head')
  const lastPatRef = useRef(0)
  function onPat() {
    const now = Date.now()
    if (!headGesture || now - lastPatRef.current < 700) return
    lastPatRef.current = now
    dispatchGesture(headGesture)
  }

  const mood = identity?.reaction_state
    || identity?.mood_live
    || identity?.mood_state
    || character?.mood

  const frameSvg = svgStructure?.CharacterPreviewWindow?.['CharacterPreviewWindow.SVG'] || ''

  return (
    <div className={`no-select character-preview-container${expandMode === 'avatar' ? '' : ' character-preview-container--hidden'}`}>
        <div className='character-preview-background'/>
        <div className='character-preview-avatar'>
            <img src={portraitUrl || avatarMira} onError={(e) => { e.currentTarget.src = avatarMira }} alt="avatar" />
            {headGesture && (
              <div className='character-preview-pat-zone' title={headGesture.title}
                   onMouseDown={(e) => e.preventDefault()}
                   onClick={onPat} />
            )}
        </div>
        <div className='character-preview-svg' dangerouslySetInnerHTML={{ __html: frameSvg }} />
        <div className='charater-preview-id-text'>ID: {activeChar?.instance_id || activeChar?.baseline_id || activeChar?.id}</div>
       
        <div className='charater-preview-thoughts-text'>{identity?.thoughts?.[0]?.text}</div>
        <div className='charater-preview-mood-text'>{mood}</div>
    </div>




  )
}
