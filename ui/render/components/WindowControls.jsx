import React, { useEffect } from 'react'
import { useUIStructure, windowControlsSvg } from '@/lib/uiStructure'

function handleClose()    { window.maidlink?.close() }
function handleMinimize() { window.maidlink?.minimize() }
function handleMaximize() { window.maidlink?.maximize() }
function handleDots()     {}

export default function WindowControls({ onToggleExpand, neutral = false }) {
  const svgStructure = useUIStructure()
  const toggleMaximize = () => { handleMaximize(); onToggleExpand?.() }

  useEffect(() => window.maidlink?.onMaximizeKey?.(toggleMaximize), [onToggleExpand])

  return (
    <div className={`window-controls-container no-select${neutral ? ' window-controls-container--neutral' : ''}`}>
      <div
        className="window-controls-bg"
        dangerouslySetInnerHTML={{ __html: windowControlsSvg(svgStructure) }}
      />

      <div className="wc-buttons">
        <button className="wc-btn" onClick={handleClose} title="Скрыть в трей">
          <svg width="17" height="17" viewBox="0 0 17 17" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path className="svg-window-controls-button-close" d="M16.459 2.12109L10.4961 8.08398L16.8486 14.4365L14.7275 16.5586L8.37402 10.2051L2.12109 16.459L0 14.3379L6.25293 8.08398L0.427734 2.25781L2.54883 0.136719L8.375 5.96289L14.3379 0L16.459 2.12109Z"/>
          </svg>
        </button>
        <button className="wc-btn" onClick={handleMinimize} title="Свернуть">
          <svg width="16" height="3" viewBox="0 0 16 3" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect className="svg-window-controls-button-minimize" width="16" height="3"/>
          </svg>
        </button>
        <button className="wc-btn" onClick={toggleMaximize} title="Развернуть">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect className='svg-window-controls-button-maximize' x="1.5" y="1.5" width="13" height="13" strokeWidth="3"/>
          </svg>
        </button>
        <button className="wc-btn" onClick={handleDots} title="Ещё">
          
        </button>
      </div>
    </div>
  )
}
